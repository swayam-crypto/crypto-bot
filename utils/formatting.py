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
utils/formatting.py

Helper functions for building Discord embeds in a consistent style.

Used by:
  - cogs/price.py
  - cogs/alerts.py
  - cogs/portfolio.py
  - utils/binance.py
  - utils/coingecko.py

Exports:
  - make_price_embed(coin, vs, data)
  - make_success_embed(title, text)
  - make_error_embed(text)
  - format_num(n)
  - format_percent(n)
"""

from __future__ import annotations
import discord
from utils.converters import normalize_coin


# -------------------------- Formatting helpers -------------------------- #

def format_num(n: float) -> str:
    """
    Smart number formatting:
    - > 1        → 2 decimals
    - 0.01–1     → 4 decimals
    - < 0.01     → 8 decimals (for coins like SHIB/DOGE)
    - No trailing zeros
    """
    if n is None:
        return "N/A"

    n = float(n)

    if n >= 1:
        fmt = "{:,.2f}"
    elif n >= 0.01:
        fmt = "{:,.4f}"
    else:
        fmt = "{:,.8f}"

    # remove useless trailing zeros and dots
    out = fmt.format(n).rstrip("0").rstrip(".")
    return out


def format_percent(n: float, precision: int = 2) -> str:
    """
    Format percentage:
      5.234 → '5.23%'
    """
    if n is None:
        return "N/A"
    try:
        return f"{n:.{precision}f}%"
    except Exception:
        return str(n)


# -------------------------- Embed Builders ------------------------------ #

def make_price_embed(coin: str, vs: str, data: dict, logo_url: str = None, info=None) -> discord.Embed:
    coin = coin.lower().strip()
    coin_id=normalize_coin(coin)
    vs = vs.lower().strip()
    price = data.get(vs)

    embed = discord.Embed(
        title=f"{info.get('name', coin_id).title()} Price",
        description=f"Current price in **{vs.upper()}**",
        color=discord.Color.gold()
    )

    price = data.get(vs)
    embed.add_field(name="Price", value=f"{price:,.4f} {vs.upper()}", inline=False)

    # add thumbnail (the coin avatar)
    if info and info.get("image"):
        embed.set_thumbnail(url=info["image"])

    return embed


def make_success_embed(title: str, text: str) -> discord.Embed:
    """Green success message."""
    embed = discord.Embed(
        title=title,
        description=text,
        color=discord.Color.green()
    )
    return embed


def make_error_embed(text: str) -> discord.Embed:
    """Red error message."""
    embed = discord.Embed(
        description=f"❌ {text}",
        color=discord.Color.red()
    )
    return embed


def make_confirmation_embed(action: str, user: discord.User | discord.Member) -> discord.Embed:
    """
    Optional: Consistent confirmation messages.

    Example:
        embed = make_confirmation_embed("Alert created", ctx.author)
    """
    embed = discord.Embed(
        title="✅ Success",
        description=f"{action}\nRequested by: **{user}**",
        color=discord.Color.green(),
    )
    return embed
