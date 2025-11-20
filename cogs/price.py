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

# cogs/price.py
from __future__ import annotations

import json
import logging
import inspect
import time
from typing import Optional, Dict, Tuple

import discord
from discord.ext import commands

from utils.coingecko import get_simple_price, get_coin_info
from utils.converters import normalize_coin
from utils.formatting import make_price_embed
from utils.errors import RateLimitError

logger = logging.getLogger("crypto-bot.price")

# Simple in-memory debounce cache to prevent double responses (user,channel,command) -> timestamp
_price_debounce: Dict[Tuple[int, int, str], float] = {}
_DEBOUNCE_WINDOW = 0.9  # seconds


def _should_process(ctx: commands.Context, window_seconds: float = _DEBOUNCE_WINDOW) -> bool:
    """Return True if this command should be processed (not a rapid duplicate)."""
    try:
        key = (ctx.author.id, ctx.channel.id, ctx.command.name)
    except Exception:
        return True
    now = time.time()
    last = _price_debounce.get(key)
    if last and (now - last) < window_seconds:
        return False
    _price_debounce[key] = now
    # occasional cleanup to avoid unbounded growth
    if len(_price_debounce) > 2000:
        cutoff = now - 300
        for k, v in list(_price_debounce.items()):
            if v < cutoff:
                _price_debounce.pop(k, None)
    return True


class PriceCog(commands.Cog):
    """Simple price lookup commands using CoinGecko."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def shutdown(self):
        try:
            if getattr(self, "_session", None):
                await self._session.close()
        except Exception:
            logger.exception("Error during PriceCog.shutdown()")

    # Per-user cooldown: 5 uses per 10 seconds
    @commands.command(name="price", aliases=["p"])
    @commands.cooldown(rate=5, per=10, type=commands.BucketType.user)
    async def price(self, ctx: commands.Context, coin: str = "bitcoin", vs: str = "usd", raw: Optional[str] = None):
        """
        Usage: !price <coin> [vs]
        Examples:
          !price btc usd
          !price ethereum eur
        Add `raw` as a third argument to print the raw JSON (for debugging).
        """
        await ctx.trigger_typing()

        # quick debounce to avoid double-sends if handler invoked twice
        if not _should_process(ctx):
            logger.debug("Debounced duplicate price command from %s in %s", ctx.author.id, ctx.channel.id)
            return

        # normalize user input -> coin_id
        try:
            coin_id = normalize_coin(coin)
            coin_id = (coin_id or "bitcoin").lower().strip()
        except Exception:
            logger.exception("Error normalizing coin input: %s", coin)
            await ctx.send("Invalid coin input. Try a symbol like `btc` or a CoinGecko id like `bitcoin`.")
            return

        vs = (vs or "usd").lower().strip()

        # fetch price data and coin info
        try:
            data = await get_simple_price(coin_id, vs)
        except RateLimitError as e:
            wait = f"{e.retry_after:.0f}s" if getattr(e, "retry_after", None) else "a few seconds"
            await ctx.send(f"⚠️ **Rate limit reached!** Please wait **{wait}** before trying again.")
            return
        except Exception:
            logger.exception("Error fetching price for %s/%s", coin_id, vs)
            await ctx.send("❌ Unexpected error while fetching price. Try again later.")
            return

        if not data:
            await ctx.send("No data available or invalid coin/currency.")
            return

        # optional raw JSON output for debugging
        if raw:
            snippet = json.dumps(data, indent=2)[:1900]
            await ctx.send(f"```json\n{snippet}\n```")
            return

        # Fetch coin info once (defensive)
        info = {}
        try:
            info = await get_coin_info(coin_id) or {}
        except Exception:
            logger.debug("get_coin_info failed for %s (non-fatal)", coin_id)

        # build embed defensively
        try:
            embed = make_price_embed(coin_id, vs, data, info=info)
        except TypeError:
            # older make_price_embed signature may not accept info
            try:
                embed = make_price_embed(coin_id, vs, data)
            except Exception:
                logger.exception("make_price_embed failed for %s", coin_id)
                await ctx.send("Failed to format price data.")
                return
        except Exception:
            logger.exception("make_price_embed unexpected failure for %s", coin_id)
            await ctx.send("Failed to format price data.")
            return

        embed.set_footer(text=f"Queried: {coin_id} / {vs.upper()}")
        await ctx.send(embed=embed)

    # Friendly cooldown error handler
    @price.error
    async def price_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"You're doing that too fast — try again in {error.retry_after:.1f}s.")
        else:
            # re-raise so global error handler can log unexpected issues
            raise error


# robust setup compatible with discord.py versions that have sync/async add_cog
async def setup(bot: commands.Bot):
    cog = PriceCog(bot)
    maybe = bot.add_cog(cog)
    if inspect.isawaitable(maybe):
        await maybe
