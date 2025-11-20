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
cogs/volume.py

Commands to inspect trading volume and related metrics using CoinGecko's
`/coins/markets` endpoint.

Commands:
  - !volume <coin> [vs]         -> show 24h volume, market cap, and volume/marketcap ratio
  - !topvolume [vs] [limit]     -> list top `limit` coins by 24h volume (default limit=10)

This cog keeps a short in-memory cache to avoid frequent requests and uses
aiohttp for HTTP. It follows the same style as other cogs in the project.
"""
from __future__ import annotations

import inspect
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
import discord
from discord.ext import commands

logger = logging.getLogger("crypto-bot.volume")

COINGECKO_MARKETS = "https://api.coingecko.com/api/v3/coins/markets"
CACHE_TTL = timedelta(seconds=30)
DEFAULT_LIMIT = 10
MAX_LIMIT = 50


class CoinGeckoMarkets:
    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Dict[str, Any]] = {}  # key -> {'ts': datetime, 'data': ...}
        self._lock = asyncio.Lock()

    async def _session_or_create(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def fetch_markets(self, vs: str = "usd", ids: Optional[List[str]] = None, per_page: int = 100, page: int = 1) -> List[Dict[str, Any]]:
        """Fetch markets from CoinGecko. If `ids` is provided it will be sent as a comma-separated list.
        The result is a list of market objects as returned by CoinGecko.
        """
        vs = vs.lower().strip()
        params: Dict[str, Any] = {"vs_currency": vs, "order": "market_cap_desc", "per_page": per_page, "page": page, "price_change_percentage": "24h"}
        if ids:
            params["ids"] = ",".join(ids)

        key = f"markets:vs={vs}:ids={','.join(ids) if ids else 'all'}:per={per_page}:page={page}"

        async with self._lock:
            now = datetime.now(tz=timezone.utc)
            cached = self._cache.get(key)
            if cached and (now - cached["ts"]) < CACHE_TTL:
                return cached["data"]

        session = await self._session_or_create()
        try:
            async with session.get(COINGECKO_MARKETS, params=params, timeout=15) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning("CoinGecko markets returned %s: %s", resp.status, text[:200])
                    return []
                payload = await resp.json()
        except Exception:
            logger.exception("Error fetching markets from CoinGecko")
            return []

        async with self._lock:
            self._cache[key] = {"ts": datetime.now(tz=timezone.utc), "data": payload}
        return payload


def _format_number(n: Optional[float]) -> str:
    if n is None:
        return "n/a"
    try:
        if abs(n) >= 1:
            return f"{n:,.2f}"
        else:
            return f"{n:.8f}"
    except Exception:
        return str(n)


class VolumeCog(commands.Cog):
    """Volume inspection commands."""
    async def shutdown(self):
        """Volume cog cleanup (if any)."""
        try:
            if getattr(self, "_session", None):
                await self._session.close()
        except Exception:
            logger.exception("Error during VolumeCog.shutdown()")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.client = CoinGeckoMarkets()

    def cog_unload(self) -> None:
        try:
            self.bot.loop.create_task(self.client.close())
        except Exception:
            pass

    @commands.command(name="volume")
    async def volume(self, ctx: commands.Context, coin: str, vs: str = "usd"):
        """Show 24h volume and market cap for a coin.

        Usage: !volume bitcoin usd
        """
        await ctx.trigger_typing()
        coin = coin.lower().strip()
        vs = vs.lower().strip()

        data = await self.client.fetch_markets(vs=vs, ids=[coin], per_page=1)
        if not data:
            await ctx.send("No data available for that coin or failed to fetch.")
            return

        m = data[0]
        name = m.get("name") or coin
        symbol = m.get("symbol", "").upper()
        price = m.get("current_price")
        vol = m.get("total_volume")
        mcap = m.get("market_cap")
        change = m.get("price_change_percentage_24h")

        embed = discord.Embed(title=f"{name} ({symbol}) — Volume info", color=discord.Color.blurple())
        embed.add_field(name="Price", value=_format_number(price) + f" {vs.upper()}", inline=True)
        embed.add_field(name="24h Volume", value=_format_number(vol) + f" {vs.upper()}", inline=True)
        embed.add_field(name="Market Cap", value=_format_number(mcap) + f" {vs.upper()}", inline=True)
        if change is not None:
            sign = "+" if change >= 0 else ""
            embed.add_field(name="24h Change", value=f"{sign}{change:.2f}%", inline=True)

        # volume / marketcap ratio (a simple liquidity heuristic)
        try:
            ratio = (vol / mcap) if (vol is not None and mcap) else None
        except Exception:
            ratio = None
        if ratio is not None:
            embed.add_field(name="24h Volume / Market Cap", value=f"{ratio:.4f}", inline=True)

        embed.set_footer(text=f"Data from CoinGecko • Queried: {coin}/{vs}")
        await ctx.send(embed=embed)

    @commands.command(name="topvolume")
    async def topvolume(self, ctx: commands.Context, vs: str = "usd", limit: int = DEFAULT_LIMIT):
        """List top coins by 24h trading volume.

        Usage: !topvolume usd 10
        """
        await ctx.trigger_typing()
        vs = vs.lower().strip()
        try:
            limit = int(limit)
        except Exception:
            limit = DEFAULT_LIMIT
        limit = max(1, min(limit, MAX_LIMIT))

        # fetch first `per_page=limit` markets (CoinGecko supports up to 250 per page)
        data = await self.client.fetch_markets(vs=vs, per_page=limit, page=1)
        if not data:
            await ctx.send("Failed to fetch market data.")
            return

        lines: List[str] = []
        for i, m in enumerate(sorted(data, key=lambda x: x.get("total_volume") or 0, reverse=True)[:limit], start=1):
            name = m.get("name") or m.get("id")
            sym = (m.get("symbol") or "").upper()
            vol = m.get("total_volume")
            price = m.get("current_price")
            lines.append(f"{i}. **{name} ({sym})** — Vol(24h): {_format_number(vol)} {vs.upper()} — Price: {_format_number(price)} {vs.upper()}")

        # chunk into message(s)
        chunk_size = 10
        for i in range(0, len(lines), chunk_size):
            await ctx.send("\n".join(lines[i : i + chunk_size]))


async def setup(bot: commands.Bot):
    cog = VolumeCog(bot)  # REPLACE PriceCog with the cog class in this file
    maybe = bot.add_cog(cog)
    if inspect.isawaitable(maybe):
        await maybe
