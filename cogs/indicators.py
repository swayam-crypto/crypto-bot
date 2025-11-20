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

# cogs/indicators.py
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import List, Tuple
from utils.converters import normalize_coin

import inspect
import aiohttp
import matplotlib.pyplot as plt
from discord import File
from discord.ext import commands

logger = logging.getLogger("crypto-bot.indicators")

COINGECKO_MARKET_CHART = "https://api.coingecko.com/api/v3/coins/{id}/market_chart"


async def fetch_market_chart(session: aiohttp.ClientSession, coin: str, vs: str, days: str) -> List[Tuple[float, float]]:
    params = {"vs_currency": vs, "days": days}
    url = COINGECKO_MARKET_CHART.format(id=coin)
    async with session.get(url, params=params, timeout=20) as resp:
        if resp.status != 200:
            text = await resp.text()
            logger.warning("CoinGecko market_chart returned %s: %s", resp.status, text[:200])
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


# Keep the pure-python indicator implementations for numeric outputs
def sma(values: List[float], period: int) -> List[float]:
    out = [None] * len(values)
    if period <= 0:
        return out
    window_sum = 0.0
    for i, v in enumerate(values):
        window_sum += v
        if i >= period:
            window_sum -= values[i - period]
        if i >= period - 1:
            out[i] = window_sum / period
    return out


def ema(values: List[float], period: int) -> List[float]:
    out = [None] * len(values)
    if period <= 0:
        return out
    k = 2 / (period + 1)
    prev = None
    for i, v in enumerate(values):
        if prev is None:
            prev = v
            out[i] = v
        else:
            prev = v * k + prev * (1 - k)
            out[i] = prev
    return out


def rsi(values: List[float], period: int = 14) -> List[float]:
    out = [None] * len(values)
    if period <= 0 or len(values) < period + 1:
        return out

    gains = [0.0]
    losses = [0.0]
    for i in range(1, len(values)):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
    out[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(values)):
        gain = gains[i]
        loss = losses[i]
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        rs = avg_gain / avg_loss if avg_loss != 0 else float("inf")
        out[i] = 100 - (100 / (1 + rs))

    return out


def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line = [None if (f is None or s is None) else f - s for f, s in zip(fast_ema, slow_ema)]
    compact = [v for v in macd_line if v is not None]
    signal_compact = ema(compact, signal)
    signal_line: List[float] = [None] * len(macd_line)
    if signal_compact:
        first_idx = next(i for i, v in enumerate(macd_line) if v is not None)
        for i, val in enumerate(signal_compact):
            signal_line[first_idx + i] = val
    histogram = [None if (m is None or s is None) else m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, histogram


class IndicatorsCog(commands.Cog):
    """Cog to render technical indicators as charts."""
    async def shutdown(self):
        """Indicators cog cleanup (no resources by default)."""
        # cancel any background tasks if present
        try:
            if getattr(self, "_bg_task", None):
                self._bg_task.cancel()
                try:
                    await self._bg_task
                except asyncio.CancelledError:
                    pass
        except Exception:
            logger.exception("Error shutting down IndicatorsCog")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session = aiohttp.ClientSession()

    def cog_unload(self) -> None:
        try:
            self.bot.loop.create_task(self._session.close())
        except Exception:
            pass

    @commands.command(name="indicator")
    async def indicator(self, ctx: commands.Context, coin: str = "bitcoin", vs: str = "usd", days: str = "30", indicator: str = "all", engine: str = "mplf"):
        """
        Generate a chart showing technical indicators.

        Usage: !indicator <coin> [vs] [days] [indicator] [engine]
        indicator: sma | ema | rsi | macd | all
        engine: 'mplf' (mplfinance) | 'mpl' (fallback)
        """
        await ctx.trigger_typing()

        # normalize coin symbol -> coingecko id (e.g. btc -> bitcoin)
        coin = normalize_coin(coin)
        coin_id = coin.lower().strip()

        vs = vs.lower().strip()
        days = str(days).lower().strip()
        indicator = indicator.lower().strip()
        engine = (engine or "mplf").lower().strip()

        # optional: validate days (same set as chart cog)
        VALID_DAYS = {"1", "7", "14", "30", "90", "180", "365", "max"}
        if days not in VALID_DAYS:
            await ctx.send(f"Invalid days value `{days}`. Valid: {', '.join(sorted(VALID_DAYS))}")
            return


        if indicator not in ("sma", "ema", "rsi", "macd", "all"):
            await ctx.send("Indicator must be one of: sma, ema, rsi, macd, all")
            return

        try:
            prices_raw = await fetch_market_chart(self._session, coin_id, vs, days)
        except Exception as e:
            logger.exception("Failed fetching market chart: %s", e)
            await ctx.send("Failed to fetch chart data. Try again later.")
            return

        if not prices_raw:
            await ctx.send("No chart data available for that coin / timeframe.")
            return

        dates = [datetime.fromtimestamp(int(ts / 1000), tz=timezone.utc) for ts, _ in prices_raw]
        prices = [p for _, p in prices_raw]

        png_bytes = None
        if engine == "mplf" and _HAS_MPF:
            try:
                # mplfinance helper can plot indicators; request the requested indicator(s)
                show_rsi = indicator in ("rsi", "all")
                show_macd = indicator in ("macd", "all")
                sma_periods = [20] if indicator in ("sma", "all") else []
                ema_periods = [20] if indicator in ("ema", "all") else []
                png_bytes = await ctx.bot.loop.run_in_executor(
                    None,
                    plot_candles_mpf,
                    dates,
                    prices,
                    coin,
                    vs,
                    days,
                    "1H",
                    sma_periods,
                    ema_periods,
                    show_rsi,
                    show_macd,
                )
            except Exception:
                logger.exception("mplfinance indicator plotting failed.")
                png_bytes = None

        # Fallback: if mplfinance not available, try to build a minimal chart using matplotlib inline
        if png_bytes is None:
            # build a very simple combined chart for 'all' or per-indicator using matplotlib (keeps original behavior)
            try:
                # simple plotting: price + requested indicators
                fig, axes = None, None
                if indicator == "rsi":
                    fig, (ax_price, ax_rsi) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
                    ax_price.plot(dates, prices)
                    ax_rsi.plot(dates, rsi(prices))
                    ax_rsi.axhline(70, linestyle="--", alpha=0.5)
                    ax_rsi.axhline(30, linestyle="--", alpha=0.5)
                elif indicator == "macd":
                    fig, (ax_price, ax_macd) = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={"height_ratios": [3, 1]}, sharex=True)
                    ax_price.plot(dates, prices)
                    macd_line, signal_line, histogram = macd(prices)
                    ax_macd.plot(dates, macd_line, label="MACD")
                    ax_macd.plot(dates, signal_line, label="Signal")
                    ax_macd.bar(dates, [h or 0 for h in histogram], width=0.01)
                    ax_macd.legend(loc="best")
                elif indicator in ("sma", "ema"):
                    fig, ax = plt.subplots(figsize=(10, 4))
                    ax.plot(dates, prices, label="Price")
                    if indicator == "sma":
                        ax.plot(dates, sma(prices, 20), label="SMA(20)")
                    else:
                        ax.plot(dates, ema(prices, 20), label="EMA(20)")
                    ax.legend(loc="best")
                else:  # all
                    fig, (ax_price, ax_rsi, ax_macd) = plt.subplots(3, 1, figsize=(10, 9), gridspec_kw={"height_ratios": [3, 1, 1]}, sharex=True)
                    ax_price.plot(dates, prices, label="Price")
                    ax_price.plot(dates, sma(prices, 20), label="SMA(20)")
                    ax_price.plot(dates, ema(prices, 20), label="EMA(20)")
                    ax_price.legend(loc="best")
                    ax_rsi.plot(dates, rsi(prices))
                    ax_rsi.axhline(70, linestyle="--", alpha=0.5)
                    ax_rsi.axhline(30, linestyle="--", alpha=0.5)
                    macd_line, signal_line, histogram = macd(prices)
                    ax_macd.plot(dates, macd_line, label="MACD")
                    ax_macd.plot(dates, signal_line, label="Signal")
                    ax_macd.bar(dates, [h or 0 for h in histogram], width=0.01)
                    ax_macd.legend(loc="best")

                buf = io.BytesIO()
                fig.savefig(buf, format="png", bbox_inches="tight")
                plt.close(fig)
                buf.seek(0)
                png_bytes = buf.read()
            except Exception:
                logger.exception("Fallback indicator plotting failed.")
                png_bytes = None

        if not png_bytes:
            await ctx.send("Failed to render indicators chart (missing dependencies or error). Install `pandas` and `mplfinance` for nicer charts.")
            return

        file = File(io.BytesIO(png_bytes), filename=f"{coin}-{vs}-{days}-{indicator}.png")
        await ctx.send(file=file)

async def setup(bot: commands.Bot):
    cog = IndicatorsCog(bot)
    maybe = bot.add_cog(cog)
    if inspect.isawaitable(maybe):
        await maybe