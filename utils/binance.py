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
utils/binance.py

Lightweight Binance API helper (NO API key required).
Fetches:
  - current price
  - 24h ticker (price, volume, high/low, % change)

Only public endpoints are used:
  • https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT
  • https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT

This keeps your bot safe, requires no authentication, and integrates well
with your existing project structure.

Functions:
  - get_symbol_price(symbol)
  - get_24h_ticker(symbol)
  - format_ticker_embed(symbol, data)

Usage example:
  from utils.binance import get_symbol_price
  price = await get_symbol_price("BTCUSDT")
"""
from __future__ import annotations
from utils.converters import symbol_to_binance_pair

import aiohttp
import logging
from typing import Optional, Dict, Any
import discord

logger = logging.getLogger("crypto-bot.binance")

BINANCE_BASE = "https://api.binance.com/api/v3"
PRICE_ENDPOINT = BINANCE_BASE + "/ticker/price"
TICKER_24H_ENDPOINT = BINANCE_BASE + "/ticker/24hr"


# ------------------- SESSION HANDLING -------------------
_session: Optional[aiohttp.ClientSession] = None

async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession()
    return _session

async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()


# ------------------- PRICE: SIMPLE -------------------
async def get_symbol_price(symbol: str) -> Optional[float]:
    """
    Returns the latest price for a trading pair like "BTCUSDT".
    Returns float or None.
    """
    symbol = symbol.upper().strip()
    session = await _get_session()
    try:
        async with session.get(PRICE_ENDPOINT, params={"symbol": symbol}, timeout=10) as resp:
            if resp.status != 200:
                logger.warning("Binance price returned %s", resp.status)
                return None
            payload = await resp.json()
            price = float(payload.get("price"))
            return price
    except Exception:
        logger.exception("Error fetching Binance price for %s", symbol)
        return None


# ------------------- 24H TICKER -------------------
async def get_24h_ticker(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Returns dict containing:
        priceChange, priceChangePercent, weightedAvgPrice,
        lastPrice, highPrice, lowPrice,
        volume, quoteVolume, etc.
    """
    symbol = symbol.upper().strip()
    session = await _get_session()
    try:
        async with session.get(TICKER_24H_ENDPOINT, params={"symbol": symbol}, timeout=10) as resp:
            if resp.status != 200:
                logger.warning("Binance 24hr returned %s", resp.status)
                return None
            payload = await resp.json()
            return payload
    except Exception:
        logger.exception("Error fetching Binance 24h ticker for %s", symbol)
        return None


# ------------------- EMBED BUILDER -------------------
def format_ticker_embed(symbol: str, data: Dict[str, Any]) -> discord.Embed:
    """
    Convert Binance 24h ticker data into a Discord embed.
    """
    symbol = symbol.upper()
    last = float(data.get("lastPrice", 0))
    high = float(data.get("highPrice", 0))
    low = float(data.get("lowPrice", 0))
    vol = float(data.get("volume", 0))
    change = float(data.get("priceChangePercent", 0))

    embed = discord.Embed(title=f"Binance — {symbol} 24h Stats", color=discord.Color.gold())
    embed.add_field(name="Last Price", value=f"{last:,}", inline=True)
    embed.add_field(name="High (24h)", value=f"{high:,}", inline=True)
    embed.add_field(name="Low (24h)", value=f"{low:,}", inline=True)
    embed.add_field(name="Volume (24h)", value=f"{vol:,}", inline=True)

    sign = "+" if change >= 0 else ""
    embed.add_field(name="Change (24h)", value=f"{sign}{change:.2f}%", inline=True)

    embed.set_footer(text="Data from Binance API")
    return embed
