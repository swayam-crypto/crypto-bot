# ------------------------------------------------------------------------------------
# MIT License
# Copyright (c) 2025 swayam-crypto
#
# This file is part of the crypto-bot project and is licensed under the MIT License.
# See the LICENSE file in the project root for details.
#
# DISCLAIMER:
# This bot does NOT provide financial advice.
# Cryptocurrency markets are volatile — use this bot at your own risk.
# ------------------------------------------------------------------------------------

"""
cogs/portfolio.py

A simple portfolio management cog. Features:
  - !portfolio add <coin> <amount> [label]   -> add/update holding
  - !portfolio remove <id>                   -> remove holding by id
  - !portfolio list                          -> list holdings
  - !portfolio value [vs] [precision]        -> show total portfolio value (vs default: USD)
  - !portfolio export                        -> export holdings as JSON

Persistence: stores holdings in `data/portfolio.json` (simple file-backed store).
Pricing: uses `utils.coingecko.get_simple_price` to fetch current prices.

This is intentionally lightweight and uses the same project layout you already have.
"""
from __future__ import annotations

import inspect
import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import discord
from discord.ext import commands

from utils.coingecko import get_simple_price

logger = logging.getLogger("crypto-bot.portfolio")

DATA_DIR = Path("data")
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"


@dataclass
class Holding:
    id: int
    user_id: int
    coin: str
    amount: float
    label: Optional[str]
    created_at: str


class PortfolioStore:
    def __init__(self, path: Path = PORTFOLIO_FILE):
        self.path = path
        self._lock = asyncio.Lock()
        self._data: Dict[int, Holding] = {}
        self._next_id = 1
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for sid, obj in raw.items():
                h = Holding(**obj)
                self._data[h.id] = h
                self._next_id = max(self._next_id, h.id + 1)
            logger.info("Loaded %d portfolio holdings", len(self._data))
        except Exception:
            logger.exception("Failed to load portfolio file")

    async def _save(self) -> None:
        async with self._lock:
            try:
                to_dump = {str(i): asdict(h) for i, h in self._data.items()}
                self.path.write_text(json.dumps(to_dump, indent=2), encoding="utf-8")
            except Exception:
                logger.exception("Failed to save portfolio file")

    async def add_or_update(self, user_id: int, coin: str, amount: float, label: Optional[str]) -> Holding:
        async with self._lock:
            # update existing holding for same user+coin+label if exists
            for h in self._data.values():
                if h.user_id == user_id and h.coin == coin and (h.label or "") == (label or ""):
                    h.amount = float(amount)
                    await self._save()
                    return h

            hid = self._next_id
            self._next_id += 1
            h = Holding(id=hid, user_id=user_id, coin=coin.lower().strip(), amount=float(amount), label=label, created_at=datetime.now(tz=timezone.utc).isoformat())
            self._data[hid] = h
            await self._save()
            return h

    async def remove(self, hid: int, user_id: int) -> bool:
        async with self._lock:
            h = self._data.get(hid)
            if not h:
                return False
            if h.user_id != user_id:
                return False
            del self._data[hid]
            await self._save()
            return True

    async def list_for_user(self, user_id: int) -> List[Holding]:
        async with self._lock:
            return [h for h in self._data.values() if h.user_id == user_id]

    async def export_for_user(self, user_id: int) -> str:
        holdings = await self.list_for_user(user_id)
        return json.dumps([asdict(h) for h in holdings], indent=2)


class PortfolioCog(commands.Cog):
    """Commands to manage a simple crypto portfolio."""
    async def shutdown(self):
        """Persist portfolio state and close DB connection if present."""
        try:
            # if you maintain a DB wrapper with async close() or commit()
            if getattr(self, "db", None):
                close_fn = getattr(self.db, "close", None)
                if inspect.iscoroutinefunction(close_fn):
                    await close_fn()
                elif callable(close_fn):
                    close_fn()
        except Exception:
            logger.exception("Error shutting down PortfolioCog")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = PortfolioStore()

    @commands.group(name="portfolio", invoke_without_command=True)
    async def portfolio_group(self, ctx: commands.Context):
        await ctx.send("Usage: !portfolio add/remove/list/value/export")

    @portfolio_group.command(name="add")
    async def portfolio_add(self, ctx: commands.Context, coin: str, amount: float, *, label: Optional[str] = None):
        """Add or update a holding for the invoking user.

        Example: `!portfolio add bitcoin 0.5 Long-term`
        """
        await ctx.trigger_typing()
        try:
            holding = await self.store.add_or_update(ctx.author.id, coin, amount, label)
            await ctx.send(f"Saved holding #{holding.id}: {holding.amount} {holding.coin} ({holding.label or 'no label'})")
        except Exception:
            logger.exception("Failed to add holding")
            await ctx.send("Failed to save holding.")

    @portfolio_group.command(name="remove")
    async def portfolio_remove(self, ctx: commands.Context, hid: int):
        """Remove a holding by id (user can only remove their own)."""
        ok = await self.store.remove(hid, ctx.author.id)
        if ok:
            await ctx.send(f"Removed holding {hid}.")
        else:
            await ctx.send(f"No holding {hid} found or you are not the owner.")

    @portfolio_group.command(name="list")
    async def portfolio_list(self, ctx: commands.Context):
        """List your holdings."""
        items = await self.store.list_for_user(ctx.author.id)
        if not items:
            await ctx.send("You have no holdings saved.")
            return
        lines = []
        for h in items:
            lines.append(f"[{h.id}] {h.coin} — {h.amount} — {h.label or 'no label'}")
        # send in a code block if long
        await ctx.send("```\n" + "\n".join(lines) + "\n```")

    @portfolio_group.command(name="value")
    async def portfolio_value(self, ctx: commands.Context, vs: str = "usd", precision: int = 2):
        """Calculate total portfolio value for the user in given fiat (default USD)."""
        await ctx.trigger_typing()
        vs = vs.lower().strip()
        items = await self.store.list_for_user(ctx.author.id)
        if not items:
            await ctx.send("No holdings to value.")
            return

        # group coins to reduce API calls
        coins = list({h.coin for h in items})
        total = 0.0
        details = []
        for coin in coins:
            data = await get_simple_price(coin, vs)
            if not data or vs not in data:
                logger.debug("No price for %s %s", coin, vs)
                price = None
            else:
                price = float(data[vs])

            # sum amounts for this coin
            amount = sum(h.amount for h in items if h.coin == coin)
            value = (price * amount) if price is not None else None
            if value is not None:
                total += value
                details.append(f"{coin}: {amount} × {price:.{precision}f} = {value:.{precision}f} {vs.upper()}")
            else:
                details.append(f"{coin}: price unavailable")

        embed = discord.Embed(title=f"Portfolio value ({vs.upper()})", color=discord.Color.green())
        embed.add_field(name="Total", value=f"{total:.{precision}f} {vs.upper()}", inline=False)
        embed.add_field(name="Breakdown", value="\n".join(details)[:1024], inline=False)
        embed.set_footer(text=f"Requested by {ctx.author}")
        await ctx.send(embed=embed)

    @portfolio_group.command(name="export")
    async def portfolio_export(self, ctx: commands.Context):
        """Export holdings as JSON file."""
        data = await self.store.export_for_user(ctx.author.id)
        b = data.encode("utf-8")
        file = discord.File(io.BytesIO(b), filename=f"portfolio_{ctx.author.id}.json")
        await ctx.send("Here is your portfolio export:", file=file)


async def setup(bot: commands.Bot):
    cog = PortfolioCog(bot)  # REPLACE PriceCog with the cog class in this file
    maybe = bot.add_cog(cog)
    if inspect.isawaitable(maybe):
        await maybe
