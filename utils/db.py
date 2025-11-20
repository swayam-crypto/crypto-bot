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

Portfolio cog updated to use utils.db (SQLite) instead of a JSON file for persistence.
The cog will ensure the DB schema exists by calling `await db.init_db()` in setup.
"""
from __future__ import annotations

import io
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import discord
from discord.ext import commands

from utils.coingecko import get_simple_price
from utils.db import db

logger = logging.getLogger("crypto-bot.portfolio")


@dataclass
class Holding:
    id: int
    user_id: int
    coin: str
    amount: float
    label: Optional[str]
    created_at: str


class PortfolioStoreDB:
    def __init__(self):
        pass

    async def add_or_update(self, user_id: int, coin: str, amount: float, label: Optional[str]) -> Holding:
        await db.init_db()
        # Try to find existing holding for same user+coin+label
        rows = await db.fetchall("SELECT * FROM portfolios WHERE user_id=? AND coin=? AND (label IS ? OR label=?)", (user_id, coin.lower().strip(), label, label))
        if rows:
            # update first match
            row = rows[0]
            hid = int(row["id"])
            await db.execute("UPDATE portfolios SET amount=? WHERE id=?", (float(amount), hid))
            updated = await db.fetchone("SELECT * FROM portfolios WHERE id=?", (hid,))
            return Holding(id=int(updated["id"]), user_id=int(updated["user_id"]), coin=str(updated["coin"]), amount=float(updated["amount"]), label=updated["label"], created_at=str(updated["created_at"]))

        created_at = datetime.now(tz=timezone.utc).isoformat()
        await db.execute(
            "INSERT INTO portfolios (user_id, coin, amount, label, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, coin.lower().strip(), float(amount), label, created_at),
        )
        row = await db.fetchone("SELECT last_insert_rowid() as id", None)
        hid = int(row["id"]) if row else 0
        return Holding(id=hid, user_id=user_id, coin=coin.lower().strip(), amount=float(amount), label=label, created_at=created_at)

    async def remove(self, hid: int, user_id: int) -> bool:
        await db.init_db()
        row = await db.fetchone("SELECT id, user_id FROM portfolios WHERE id=?", (hid,))
        if not row:
            return False
        if int(row["user_id"]) != int(user_id):
            return False
        await db.execute("DELETE FROM portfolios WHERE id=?", (hid,))
        return True

    async def list_for_user(self, user_id: int) -> List[Holding]:
        await db.init_db()
        rows = await db.fetchall("SELECT * FROM portfolios WHERE user_id=?", (user_id,))
        out: List[Holding] = []
        for r in rows:
            out.append(Holding(id=int(r["id"]), user_id=int(r["user_id"]), coin=str(r["coin"]), amount=float(r["amount"]), label=r["label"], created_at=str(r["created_at"])))
        return out

    async def export_for_user(self, user_id: int) -> str:
        holdings = await self.list_for_user(user_id)
        import json

        return json.dumps([asdict(h) for h in holdings], indent=2)


class PortfolioCog(commands.Cog):
    """Commands to manage a simple crypto portfolio using SQLite."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = PortfolioStoreDB()

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
        await ctx.send("```" + "".join(lines) + "```")

    @portfolio_group.command(name="value")
    async def portfolio_value(self, ctx: commands.Context, vs: str = "usd", precision: int = 2):
        """Calculate total portfolio value for the user in given fiat (default USD)."""
        await ctx.trigger_typing()
        vs = vs.lower().strip()
        items = await self.store.list_for_user(ctx.author.id)
        if not items:
            await ctx.send("No holdings to value.")
            return

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

            amount = sum(h.amount for h in items if h.coin == coin)
            value = (price * amount) if price is not None else None
            if value is not None:
                total += value
                details.append(f"{coin}: {amount} × {price:.{precision}f} = {value:.{precision}f} {vs.upper()}")
            else:
                details.append(f"{coin}: price unavailable")

        embed = discord.Embed(title=f"Portfolio value ({vs.upper()})", color=discord.Color.green())
        embed.add_field(name="Total", value=f"{total:.{precision}f} {vs.upper()}", inline=False)
        embed.add_field(name="Breakdown", value="".join(details)[:1024], inline=False)
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
    await db.init_db()
    await bot.add_cog(PortfolioCog(bot))
