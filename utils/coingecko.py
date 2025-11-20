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
utils/coingecko.py

Robust CoinGecko helpers with caching, concurrency limiting, and 429 handling.

Public functions:
 - get_simple_price(coin_id, vs="usd", ttl=DEFAULT_CACHE_TTL)
 - get_coin_info(coin_id, ttl=DEFAULT_CACHE_TTL*2)
 - close_session()
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple

import aiohttp

logger = logging.getLogger("crypto-bot.coingecko")

BASE_URL = "https://api.coingecko.com/api/v3"
DEFAULT_CACHE_TTL = 30  # seconds
_CONCURRENCY_LIMIT = 6  # concurrent outbound requests

_session: Optional[aiohttp.ClientSession] = None
_semaphore = asyncio.Semaphore(_CONCURRENCY_LIMIT)

# in-memory cache: key -> (timestamp_seconds, payload)
_cache: Dict[str, Tuple[float, Any]] = {}


def _cache_get(key: str, ttl: int = DEFAULT_CACHE_TTL) -> Optional[Any]:
    """Return cached payload or None if expired/missing."""
    entry = _cache.get(key)
    if not entry:
        return None
    ts, payload = entry
    if (time.time() - ts) > ttl:
        # expired
        try:
            del _cache[key]
        except Exception:
            pass
        return None
    return payload


def _cache_set(key: str, payload: Any) -> None:
    """Store payload in cache with current timestamp."""
    _cache[key] = (time.time(), payload)


async def _get_session() -> aiohttp.ClientSession:
    """Create or return a global aiohttp session."""
    global _session
    if _session and not _session.closed:
        return _session
    _session = aiohttp.ClientSession()
    return _session


async def _fetch_json(
    url: str, params: Optional[Dict] = None, timeout: int = 15, retries: int = 2
) -> Optional[Dict]:
    """
    Fetch JSON with retries and 429 handling.

    Raises:
      - RateLimitError (from utils.errors) when a 429 is returned (with retry_after attribute if provided)

    Returns parsed JSON (dict) or None on non-200 failures.
    """
    session = await _get_session()
    backoff = 0.5
    for attempt in range(retries + 1):
        async with _semaphore:
            try:
                async with session.get(url, params=params, timeout=timeout) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        try:
                            return await resp.json()
                        except Exception:
                            logger.exception("Invalid JSON from %s", url)
                            return None
                    elif resp.status == 429:
                        # rate limited — prefer raising explicit RateLimitError with retry info
                        ra = resp.headers.get("Retry-After")
                        retry_after: Optional[float] = None
                        try:
                            if ra:
                                retry_after = float(ra)
                        except Exception:
                            retry_after = None
                        # dynamic import to avoid circulars when utils.errors also imports coingecko
                        from utils.errors import RateLimitError

                        raise RateLimitError(retry_after)
                    else:
                        logger.warning("Request to %s returned status %s: %s", url, resp.status, text[:400])
                        return None
            except asyncio.TimeoutError:
                logger.warning("Timeout fetching %s (attempt %s)", url, attempt)
            except Exception:
                logger.exception("Error fetching %s (attempt %s)", url, attempt)
        # wait before next retry
        await asyncio.sleep(backoff)
        backoff *= 2
    return None


async def get_simple_price(coin_id: str, vs: str = "usd", ttl: int = DEFAULT_CACHE_TTL) -> Optional[Dict[str, Any]]:
    """
    Get CoinGecko /simple/price result for a coin and vs-currency.

    Returns a dict for the coin (e.g. {'usd': 1234.5, 'usd_market_cap': ..., ...}) or None on failure.
    Uses a small in-memory cache keyed by coin+vs for `ttl` seconds.
    """
    coin_id = (coin_id or "").lower().strip()
    vs = (vs or "usd").lower().strip()
    key = f"simple:{coin_id}:{vs}"
    cached = _cache_get(key, ttl)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": vs,
        "include_market_cap": "true",
        "include_24hr_change": "true",
        "include_24hr_high": "true",
        "include_24hr_low": "true",
    }
    payload = await _fetch_json(url, params=params)
    if payload is None:
        return None

    result = payload.get(coin_id) if isinstance(payload, dict) else payload
    _cache_set(key, result)
    return result


async def get_coin_info(coin_id: str, ttl: int = DEFAULT_CACHE_TTL * 2) -> Optional[Dict[str, Any]]:
    """
    Fetch coin metadata (/coins/{id}) and return a small dict:
      {'id', 'symbol', 'name', 'image'}
    Caches results for `ttl` seconds.
    """
    coin_id = (coin_id or "").lower().strip()
    key = f"info:{coin_id}"
    cached = _cache_get(key, ttl)
    if cached is not None:
        return cached

    url = f"{BASE_URL}/coins/{coin_id}"
    params = {
        "localization": "false",
        "tickers": "false",
        "market_data": "false",
        "community_data": "false",
        "developer_data": "false",
        "sparkline": "false",
    }
    payload = await _fetch_json(url, params=params, timeout=20, retries=1)
    if not payload:
        return None

    image = None
    img_obj = payload.get("image") or {}
    if isinstance(img_obj, dict):
        image = img_obj.get("large") or img_obj.get("thumb")

    out: Dict[str, Optional[str]] = {
        "id": payload.get("id"),
        "symbol": payload.get("symbol"),
        "name": payload.get("name"),
        "image": image,
    }
    _cache_set(key, out)
    return out


async def close_session() -> None:
    """Close the global aiohttp session (call this on bot shutdown)."""
    global _session
    try:
        if _session and not _session.closed:
            await _session.close()
    except Exception:
        logger.exception("Error closing aiohttp session")
    _session = None
