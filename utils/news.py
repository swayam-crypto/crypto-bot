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
utils/news.py

Async wrapper around CryptoPanic news API.

Functions:
    fetch_news()
    fetch_news_for_coin(coin)
"""

from __future__ import annotations
import aiohttp
import logging
import os
from typing import List, Dict, Optional

logger = logging.getLogger("crypto-bot.news")

BASE_URL = "https://cryptopanic.com/api/v1/posts/"
API_KEY = os.getenv("CRYPTOPANIC_KEY")  # Optional


async def _get(url: str, params: dict) -> Optional[dict]:
    """Internal helper for making GET requests with aiohttp."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status != 200:
                    logger.warning(f"CryptoPanic request failed: {resp.status}")
                    return None
                return await resp.json()
    except Exception as e:
        logger.exception("Failed to fetch CryptoPanic news: %s", e)
        return None


async def fetch_news(limit: int = 5) -> Optional[List[Dict]]:
    """
    Fetch general crypto news.
    Returns a list of posts:
      { 'title': ..., 'url': ..., 'source': ... }
    """
    params = {
        "auth_token": API_KEY,
        "filter": "news",
        "kind": "news",
        "public": "true",
        "limit": limit,
    }

    data = await _get(BASE_URL, params)
    if not data or "results" not in data:
        return None

    return data["results"]


async def fetch_news_for_coin(coin: str, limit: int = 5) -> Optional[List[Dict]]:
    """
    Fetch news filtered by coin keyword.
    Example:
        fetch_news_for_coin("bitcoin")
        fetch_news_for_coin("btc")
    """
    params = {
        "auth_token": API_KEY,
        "filter": "news",
        "public": "true",
        "q": coin.lower(),
        "limit": limit,
    }

    data = await _get(BASE_URL, params)
    if not data or "results" not in data:
        return None

    return data["results"]
