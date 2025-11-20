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

# cogs/chart.py
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import List, Tuple

import inspect
import aiohttp
from discord import File
from discord.ext import commands

from utils.converters import normalize_coin

logger = logging.getLogger("crypto-bot.chart")

COINGECKO_MARKET_CHART = "https://api.coingecko.com/api/v3/coins/{id}/market_chart"


async def fetch_market_chart(session: aiohttp.ClientSession, coin: str, vs: str, days: str) -> List[Tuple[float, float]]:
    params = {"vs_currency": vs, "days": days}
    url = COINGECKO_MARKET_CHART.format(id=coin)
    async with session.get(url, params=params, timeout=20) as resp:
        text = await resp.text()
        if resp.status != 200:
            logger.warning("CoinGecko market_chart returned %s: %s", resp.status, text[:400])
            return []
        payload = await resp.json()
        return payload.get("prices", [])


# Try to import mplfinance helper if present
# Try to import mplfinance helper if present (defensive)
try:
    from utils.charting import plot_candles_mpf
    _HAS_MPF = callable(plot_candles_mpf)
    if not _HAS_MPF:
        logger.warning("utils.charting.plot_candles_mpf imported but is not callable.")
except Exception as e:
    plot_candles_mpf = None  # type: ignore
    _HAS_MPF = False
    logger.debug("mplfinance helper not available: %s", e)

# Fallback matplotlib helper
try:
    from utils.charting import plot_price_png
    _HAS_MPL = callable(plot_price_png)
    if not _HAS_MPL:
        logger.warning("utils.charting.plot_price_png imported but is not callable.")
except Exception as e:
    plot_price_png = None  # type: ignore
    _HAS_MPL = False
    logger.debug("matplotlib helper not available: %s", e)


class ChartCog(commands.Cog):
    """Cog that produces charts. Can use 'mplf' engine (mplfinance) or 'mpl' (matplotlib fallback)."""

    VALID_DAYS = {"1", "7", "14", "30", "90", "180", "365", "max"}
    VALID_ENGINES = {"mplf", "mpl"}
    async def shutdown(self):
        """Close aiohttp session and cancel any created tasks."""
        # cancel any _bg_task if present
        try:
            if getattr(self, "_bg_task", None):
                self._bg_task.cancel()
                try:
                    await self._bg_task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    logger.exception("Error waiting for ChartCog._bg_task")
        except Exception:
            logger.exception("Error cancelling ChartCog._bg_task")

        # close the aiohttp session
        try:
            if getattr(self, "_session", None):
                await self._session.close()
        except Exception:
            logger.exception("Failed to close aiohttp session in ChartCog")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session = aiohttp.ClientSession()

    def cog_unload(self) -> None:
        try:
            self.bot.loop.create_task(self._session.close())
        except Exception:
            pass

    @commands.command(name="chart")
    async def chart(self, ctx: commands.Context, coin: str = "bitcoin", vs: str = "usd", days: str = "7", engine: str = "mplf"):
        """
        Send a PNG chart for a coin.

        Usage: !chart <coin> [vs] [days] [engine]
        - coin: symbol or coingecko id (e.g. btc or bitcoin)
        - vs: fiat (usd)
        - days: 1,7,14,30,90,180,365 or max
        - engine: 'mplf' (mplfinance) | 'mpl' (matplotlib fallback)

        Example:
          !chart btc usd 7 mplf
        """
        await ctx.trigger_typing()

        # normalize inputs
        coin_raw = coin
        coin = normalize_coin(coin)  # maps btc->bitcoin etc.
        coin_id = coin.lower().strip()
        vs = vs.lower().strip()
        days = str(days).lower().strip()
        engine = (engine or "mplf").lower().strip()

        # validate days
        if days not in self.VALID_DAYS:
            await ctx.send(f"Invalid days value `{days}`. Valid options: {', '.join(sorted(self.VALID_DAYS))}")
            return

        # validate engine
        if engine not in self.VALID_ENGINES:
            await ctx.send(f"Invalid engine `{engine}`. Valid engines: {', '.join(sorted(self.VALID_ENGINES))}")
            return

        # Fetch market chart data
        try:
            prices = await fetch_market_chart(self._session, coin_id, vs, days)
        except Exception as e:
            logger.exception("Failed fetching market chart for %s (%s): %s", coin_id, coin_raw, e)
            await ctx.send("Failed to fetch chart data. Try again later.")
            return

        if not prices:
            # helpful message if coin not found
            await ctx.send(f"No chart data found for `{coin_raw}` (resolved to `{coin_id}`).\n"
                           "Make sure you used a valid coin symbol or CoinGecko id (e.g. `btc` → `bitcoin`).")
            return

        # prepare data
        try:
            dates = [datetime.fromtimestamp(int(ts / 1000), tz=timezone.utc) for ts, _ in prices]
            price_vals = [p for _, p in prices]
        except Exception:
            logger.exception("Invalid price data returned for %s", coin_id)
            await ctx.send("Invalid chart data returned from provider.")
            return

        # Choose engine: prefer mplfinance (mplf) when available
        png_bytes = None
        if engine == "mplf" and _HAS_MPF:
            try:
                # run synchronous plotting in executor
                png_bytes = await ctx.bot.loop.run_in_executor(
                    None,
                    plot_candles_mpf,
                    dates,
                    price_vals,
                    coin_id,
                    vs,
                    days,
                    "1H",  # timeframe (unused in simple candles helper)
                    [20],
                    [20],
                    True,
                    True,
                )
            except Exception:
                logger.exception("mplfinance charting failed for %s, will try fallback.", coin_id)
                png_bytes = None

        # fallback to older matplotlib-based helper
        if png_bytes is None and _HAS_MPL:
            try:
                png_bytes = await ctx.bot.loop.run_in_executor(None, plot_price_png, dates, price_vals, coin_id, vs, days, [20, 50])
            except Exception:
                logger.exception("matplotlib charting failed for %s.", coin_id)
                png_bytes = None

        if not png_bytes:
            await ctx.send("Failed to render chart (missing dependencies or an error occurred). Install `pandas` and `mplfinance` for best results.")
            return

        file = File(io.BytesIO(png_bytes), filename=f"{coin_id}-{vs}-{days}.png")
        await ctx.send(file=file)

# Robust setup for different discord.py versions:
async def setup(bot: commands.Bot):
    cog = ChartCog(bot)
    maybe = bot.add_cog(cog)
    if inspect.isawaitable(maybe):
        await maybe
