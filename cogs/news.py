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
cogs/news.py

News cog updated to use utils.news (CryptoPanic wrapper) and utils.formatting for consistent embeds.

Commands:
  - !news [coin] [limit]   -> fetch recent news (default limit=5)
  - !newsraw [coin] [limit] -> owner-only: show raw JSON for debugging

This cog expects `utils/news.py` to provide `fetch_news` and `fetch_news_for_coin`.
"""
from __future__ import annotations

import inspect
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import discord
from discord.ext import commands

from utils.formatting import make_error_embed
from utils.news import fetch_news, fetch_news_for_coin

logger = logging.getLogger("crypto-bot.news")

DEFAULT_LIMIT = 5
MAX_LIMIT = 20


def _make_embed_from_post(post: Dict[str, Any]) -> discord.Embed:
    """Convert a CryptoPanic post dict to a Discord embed.

    Expected post fields vary but commonly include:
      - title
      - published_at / created_at
      - domain
      - url
      - votes (optional)
      - description / body
    """
    title = post.get("title") or post.get("domain") or "Crypto News"
    url = post.get("url") or post.get("share_url")
    domain = post.get("domain") or post.get("source", {}).get("domain")
    published = post.get("published_at") or post.get("created_at")
    # Try multiple description fields
    description = post.get("excerpt") or post.get("description") or (post.get("body") or "")

    embed = discord.Embed(title=(title[:256]), description=(description[:2048] + ("…" if len(description) > 2048 else "")), color=discord.Color.blurple())
    if domain:
        embed.add_field(name="Source", value=str(domain), inline=True)
    if url:
        embed.add_field(name="Link", value=f"[Read]({url})", inline=True)

    if published:
        try:
            # CryptoPanic returns ISO timestamps; normalize
            dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            embed.set_footer(text=f"Published (UTC): {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            embed.timestamp = dt
        except Exception:
            pass

    return embed


class NewsCog(commands.Cog):
    """Cog that exposes a !news command to fetch recent crypto news using utils.news."""
    async def shutdown(self):
        """News Cog tidy-up (no heavy resources by default)."""
        # If you later add sessions or background tasks, tidy them here.
        try:
            if getattr(self, "_session", None):
                await self._session.close()
        except Exception:
            logger.exception("Failed to close session in NewsCog")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="news")
    async def news(self, ctx: commands.Context, coin: Optional[str] = None, limit: int = DEFAULT_LIMIT):
        """Fetch recent crypto news.

        Usage:
          !news                -> latest updates (default limit)
          !news bitcoin        -> updates mentioning 'bitcoin'
          !news bitcoin 10     -> up to 10 items (max 20)
        """
        await ctx.trigger_typing()

        try:
            limit = int(limit)
        except Exception:
            limit = DEFAULT_LIMIT
        limit = max(1, min(limit, MAX_LIMIT))

        posts: Optional[List[Dict[str, Any]]]
        try:
            if coin:
                posts = await fetch_news_for_coin(coin, limit=limit)
            else:
                posts = await fetch_news(limit=limit)
        except Exception as e:
            logger.exception("Error fetching news: %s", e)
            await ctx.send(embed=make_error_embed("Failed to fetch news. Try again later."))
            return

        if not posts:
            await ctx.send(embed=make_error_embed("No news found."))
            return

        embeds: List[discord.Embed] = []
        for p in posts[:limit]:
            try:
                embed = _make_embed_from_post(p)
                embeds.append(embed)
            except Exception:
                logger.exception("Failed to build embed for post")

        # Discord supports multiple embeds in one message (up to 10). Chunk if needed.
        chunk_size = 10
        for i in range(0, len(embeds), chunk_size):
            try:
                await ctx.send(embeds=embeds[i : i + chunk_size])
            except Exception:
                # fallback: send individually
                for e in embeds[i : i + chunk_size]:
                    try:
                        await ctx.send(embed=e)
                    except Exception:
                        logger.exception("Failed to send news embed")

    @commands.command(name="newsraw")
    @commands.is_owner()
    async def news_raw(self, ctx: commands.Context, coin: Optional[str] = None, limit: int = DEFAULT_LIMIT):
        """Owner-only: show raw JSON from utils.news for debugging."""
        await ctx.trigger_typing()
        try:
            limit = int(limit)
        except Exception:
            limit = DEFAULT_LIMIT
        limit = max(1, min(limit, MAX_LIMIT))

        try:
            if coin:
                posts = await fetch_news_for_coin(coin, limit=limit)
            else:
                posts = await fetch_news(limit=limit)
        except Exception as e:
            logger.exception("Error fetching raw news: %s", e)
            await ctx.send(embed=make_error_embed("Failed to fetch raw news."))
            return

        if not posts:
            await ctx.send("No data.")
            return

        import json

        payload = json.dumps(posts[:limit], indent=2)
        # Truncate if too long
        if len(payload) > 1900:
            payload = payload[:1900] + "...truncated..."
        await ctx.send(f"```json{payload}```")

async def setup(bot: commands.Bot):
    cog = NewsCog(bot)  # REPLACE PriceCog with the cog class in this file
    maybe = bot.add_cog(cog)
    if inspect.isawaitable(maybe):
        await maybe
