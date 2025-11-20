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
cogs/alerts.py

A Discord cog that lets users create simple price alerts for coins (via CoinGecko).

Commands:
  - !alert set <coin> <vs> <operator> <price>   (operator: > or <)
  - !alert list
  - !alert remove <id>
  - !alert clear

Alerts are stored in a local JSON file (`data/alerts.json`) for persistence.
A background task checks prices every 60 seconds and dispatches alerts when
conditions are met. Alerts are removed after firing.

This file expects your project layout from earlier: `utils.coingecko.get_simple_price`
and `utils.formatting.make_price_embed` are used for fetching and formatting.
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
from discord.ext import commands, tasks

from utils.coingecko import get_simple_price
from utils.formatting import make_price_embed

logger = logging.getLogger("crypto-bot.alerts")

DATA_DIR = Path("data")
ALERTS_FILE = DATA_DIR / "alerts.json"
CHECK_INTERVAL_SECONDS = 60


@dataclass
class AlertItem:
    id: int
    guild_id: Optional[int]  # None for DMs
    channel_id: int
    user_id: int
    coin: str
    vs: str
    operator: str  # '>' or '<'
    price: float
    created_at: str  # ISO timestamp

    def matches(self, current_price: float) -> bool:
        if self.operator == ">":
            return current_price > self.price
        else:
            return current_price < self.price


class AlertsStore:
    """Simple file-backed store for alert items."""

    def __init__(self, path: Path = ALERTS_FILE):
        self.path = path
        self._data: Dict[int, AlertItem] = {}
        self._next_id = 1
        self._lock = asyncio.Lock()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
    # ensure directory exists
     DATA_DIR.mkdir(parents=True, exist_ok=True)

    # if file doesn't exist yet, nothing to load
     if not self.path.exists():
         logger.info("Alerts file not found, starting with empty store: %s", self.path)
         return

     try:
        # do the file read synchronously but guarded; for small files it's ok.
        # if you prefer fully non-blocking, use aiofiles + async wrapper.
         raw_text = self.path.read_text(encoding="utf-8")
         raw = json.loads(raw_text)
         for sid, obj in raw.items():
             try:
                 item = AlertItem(**obj)
                 self._data[item.id] = item
                 self._next_id = max(self._next_id, item.id + 1)
             except Exception:
                 logger.exception("Malformed alert entry %s in alerts file; skipping", sid)
         logger.info("Loaded %d alerts", len(self._data))
     except FileNotFoundError:
        # defensive: file might vanish between exists() check and read
         logger.info("Alerts file disappeared while loading; starting empty.")
     except json.JSONDecodeError:
         logger.exception("Alerts file contains invalid JSON; starting empty.")
     except Exception:
         logger.exception("Failed to load alerts file; starting with empty store.")


    async def _save(self) -> None:
        async with self._lock:
            try:
                to_dump = {str(i): asdict(it) for i, it in self._data.items()}
                #self.path.write_text(json.dumps(to_dump, indent=2), encoding="utf-8")
                loop = asyncio.get_running_loop()
                payload = json.dumps(to_dump, indent=2)
                await loop.run_in_executor(None, self.path.write_text, payload, "utf-8")

            except Exception:
                logger.exception("Failed to write alerts file")

    async def add(self, guild_id: Optional[int], channel_id: int, user_id: int, coin: str, vs: str, operator: str, price: float) -> AlertItem:
        async with self._lock:
            aid = self._next_id
            self._next_id += 1
            item = AlertItem(
                id=aid,
                guild_id=guild_id,
                channel_id=channel_id,
                user_id=user_id,
                coin=coin.lower().strip(),
                vs=vs.lower().strip(),
                operator=operator,
                price=price,
                created_at=datetime.now(tz=timezone.utc).isoformat(),
            )
            self._data[aid] = item
            await self._save()
            return item

    async def remove(self, aid: int) -> bool:
        async with self._lock:
            if aid in self._data:
                del self._data[aid]
                await self._save()
                return True
            return False

    async def list(self) -> List[AlertItem]:
        # Return copy
        async with self._lock:
            return list(self._data.values())

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
            await self._save()

    async def pop_matching(self, coin: str, vs: str, predicate) -> List[AlertItem]:
        """Find and remove alerts for a coin/vs that match predicate(current_price).
        Returns removed items.
        """
        removed: List[AlertItem] = []
        async with self._lock:
            to_remove = []
            for aid, item in self._data.items():
                if item.coin == coin and item.vs == vs and predicate(item):
                    to_remove.append(aid)
            for aid in to_remove:
                removed.append(self._data.pop(aid))
            if to_remove:
                await self._save()
        return removed


class AlertsCog(commands.Cog):
    """Cog providing price alerts."""
    async def shutdown(self):
        """Gracefully stop checker_task and persist store."""
        # Cancel the tasks.loop Loop safely
        try:
            loop_task = getattr(self, "checker_task", None)
            if loop_task is not None:
                try:
                    # cancel the looped task
                    loop_task.cancel()
                except Exception:
                    logger.exception("Failed to cancel checker_task")

                # wait (poll) until it stops, with a timeout
                try:
                    for _ in range(50):  # ~5 seconds (50 * 0.1)
                        if not getattr(loop_task, "is_running", lambda: False)():
                            break
                        await asyncio.sleep(0.1)
                except Exception:
                    logger.exception("Error while waiting for checker_task to stop")
        except Exception:
            logger.exception("Failed cancelling checker_task in AlertsCog")

        # persist store if possible
        try:
            if getattr(self, "store", None) and hasattr(self.store, "_save"):
                maybe_save = self.store._save()
                if inspect.isawaitable(maybe_save):
                    await maybe_save
        except Exception:
            logger.exception("Failed to save alerts store during shutdown.")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.store = AlertsStore()
        self.checker_task.start()

    def cog_unload(self) -> None:
        if self.checker_task.is_running():
            self.checker_task.cancel()

    @commands.group(name="alert", invoke_without_command=True)
    async def alert_group(self, ctx: commands.Context):
        """Base command. Use subcommands: set, list, remove, clear."""
        await ctx.send("Usage: !alert set <coin> <vs> <operator> <price> | !alert list | !alert remove <id> | !alert clear")

    @alert_group.command(name="set")
    async def alert_set(self, ctx: commands.Context, coin: str, vs: str, operator: str, price: float):
        """Set a new price alert.

        Example: `!alert set bitcoin usd > 60000`
        """
        operator = operator.strip()
        if operator not in (">", "<"):
            await ctx.send("Operator must be '>' or '<'.")
            return

        guild_id = ctx.guild.id if ctx.guild else None
        channel_id = ctx.channel.id
        item = await self.store.add(guild_id, channel_id, ctx.author.id, coin, vs, operator, price)
        await ctx.send(f"Alert created (id={item.id}): {coin.lower()} {operator} {price} {vs.upper()}")
        
    @alert_set.error
    async def alert_set_error(self, ctx: commands.Context, error: commands.CommandError):
        """
        Friendly error messages for !alert set.
        Shows usage in chat instead of only logging to terminal.
        """
        # Missing one or more required args
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                "Usage: `!alert set <coin> <vs> <operator> <price>`\n"
                "Example: `!alert set bitcoin usd > 60000`\n"
                "Operator must be `>` or `<`."
            )
            return

        # Wrong type (e.g. price couldn't be converted to float)
        if isinstance(error, commands.BadArgument):
            await ctx.send("Invalid argument. Make sure the price is a number (e.g. `60000.0`).")
            return

        # Permissions or other errors
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to use this command.")
            return

        # Fallback for unexpected errors
        logger.exception("Unhandled error in alert_set: %s", error)
        await ctx.send("An unexpected error occurred while creating the alert. Try again later.")

    @alert_group.command(name="list")
    async def alert_list(self, ctx: commands.Context):
        """List alerts visible to the user (in the same guild or DM)."""
        items = await self.store.list()
        lines = []
        for it in items:
         # DM: only show DM alerts for this user
            if ctx.guild is None:
                if it.guild_id is not None:
                   continue
                if it.user_id != ctx.author.id:
                   continue
            else:
             # In a guild: show alerts that are either:
             #  - created for this guild (it.guild_id == ctx.guild.id), OR
             #  - created by this user personally (private alerts)
               if it.guild_id is not None and it.guild_id != ctx.guild.id and it.user_id != ctx.author.id:
            # alert for another guild and not created by this user
                  continue
             # Optionally: if you want to hide other users' guild alerts unless the user created them:
               if it.guild_id == ctx.guild.id and it.user_id != ctx.author.id:
                  continue
            lines.append(f"[{it.id}] {it.coin} {it.operator} {it.price} {it.vs.upper()} (channel: {it.channel_id})")

        """for it in items:
            # if in a guild, only show guild alerts or personal alerts; in DM show only personal
            if ctx.guild:
                if it.guild_id is not None and it.guild_id != ctx.guild.id:
                    continue
            else:
                # DM: show only DM alerts for this user
                if it.guild_id is not None:
                    continue
            if it.user_id != ctx.author.id and (it.guild_id is None or it.guild_id != ctx.guild.id if ctx.guild else True):
                # allow users to see alerts they created; otherwise restrict
                continue
            lines.append(f"[{it.id}] {it.coin} {it.operator} {it.price} {it.vs.upper()} (channel: {it.channel_id})")"""

        if not lines:
            await ctx.send("No alerts found for this context.")
            return

        # chunk message if too long
        chunk = "\n".join(lines)
        await ctx.send(f"Alerts:\n{chunk}")

    @alert_group.command(name="remove")
    async def alert_remove(self, ctx: commands.Context, aid: int):
        """Remove an alert by ID."""
        ok = await self.store.remove(aid)
        if ok:
            await ctx.send(f"Removed alert {aid}.")
        else:
            await ctx.send(f"No alert with id {aid}.")

    @alert_group.command(name="clear")
    @commands.has_permissions(manage_guild=True)
    async def alert_clear(self, ctx: commands.Context):
        """Clear all alerts (guild-only, requires Manage Server permission)."""
        await self.store.clear()
        await ctx.send("All alerts cleared.")

    @tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
    async def checker_task(self) -> None:
        """Background task that checks alerts periodically."""
        try:
            items = await self.store.list()
            # group by (coin, vs) to reduce API calls
            groups: Dict[str, List[AlertItem]] = {}
            for it in items:
                key = f"{it.coin}::{it.vs}"
                groups.setdefault(key, []).append(it)

            for key, alerts in groups.items():
                coin, vs = key.split("::")
                # fetch price
                data = await get_simple_price(coin, vs)
                if not data:
                    logger.debug("No data for %s %s", coin, vs)
                    continue
                price = data.get(vs)
                if price is None:
                    logger.debug("No price key %s in payload for %s", vs, coin)
                    continue

                # find matching alerts
                def predicate(ai: AlertItem):
                    return ai.matches(price)

                matched = await self.store.pop_matching(coin, vs, predicate)
                for ai in matched:
                    # attempt to send message to the channel; fall back to DM
                    channel = None
                    try:
                        channel = self.bot.get_channel(ai.channel_id) or await self.bot.fetch_channel(ai.channel_id)
                    except Exception:
                        channel = None

                    embed = make_price_embed(ai.coin, ai.vs, data)
                    note = f"🔔 Alert #{ai.id}: {ai.coin} {ai.operator} {ai.price} {ai.vs.upper()} — current: {price}"

                    sent = False
                    if channel:
                        try:
                            await channel.send(content=note, embed=embed)
                            sent = True
                        except Exception:
                            logger.exception("Failed to send alert to channel %s", ai.channel_id)

                    if not sent:
                        # fallback to DM the user
                        try:
                            user = await self.bot.fetch_user(ai.user_id)
                            await user.send(content=note, embed=embed)
                            sent = True
                        except Exception:
                            logger.exception("Failed to DM user %s for alert %s", ai.user_id, ai.id)

                    logger.info("Dispatched alert %s (sent=%s)", ai.id, sent)

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error in alerts checker task")

    @checker_task.before_loop
    async def _before_checker(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    cog = AlertsCog(bot)
    maybe = bot.add_cog(cog)
    if inspect.isawaitable(maybe):
        await maybe
