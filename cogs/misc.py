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
cogs/misc.py

A small collection of general-purpose utility commands for your Discord crypto bot.
These commands are not tied to price, indicators, or alerts — just useful extras.

Commands:
  - !ping         → Bot latency
  - !about        → Bot info
  - !helpme       → Custom help overview
  - !convert      → Convert an amount of COIN to fiat (using simple price API)
  - !invite       → Shows bot invite link if you've set CLIENT_ID in .env
"""
from __future__ import annotations

import inspect
import os
import time
import discord
from discord.ext import commands

from utils.coingecko import get_simple_price


CLIENT_ID = os.getenv("CLIENT_ID")  # Optional: for generating invite links


class MiscCog(commands.Cog):
    """General utility & helper commands."""
    async def shutdown(self):
        """Misc cog cleanup (close sessions if present)."""
        try:
            if getattr(self, "_session", None):
                await self._session.close()
        except Exception:
            logger.exception("Error during MiscCog.shutdown()")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------- PING ----------------
    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context):
        """Show bot latency."""
        start = time.monotonic()
        msg = await ctx.send("Pinging...")
        end = time.monotonic()
        ws_latency = round(self.bot.latency * 1000, 2)
        api_latency = round((end - start) * 1000, 2)
        await msg.edit(content=f"🏓 Pong! WS: {ws_latency}ms | API: {api_latency}ms")

    # ---------------- ABOUT ----------------
    @commands.command(name="about")
    async def about(self, ctx: commands.Context):
        """Show bot information."""
        embed = discord.Embed(
            title="Crypto Bot",
            description="A lightweight crypto bot using CoinGecko, charts, alerts, and indicators.",
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Developer", value=f"{ctx.bot.user.name}")
        embed.add_field(name="Library", value="discord.py 2.x")
        embed.set_footer(text="Thanks for using the bot!")
        await ctx.send(embed=embed)

    # ---------------- HELPME (custom help) ----------------
    @commands.command(name="helpme")
    async def helpme(self, ctx: commands.Context):
        """Show a simple custom help page."""
        embed = discord.Embed(title="Crypto Bot Commands", color=discord.Color.green())

        embed.add_field(name="Price", value="`!price <coin> <vs>` — Show live price", inline=False)
        embed.add_field(name="Chart", value="`!chart <coin> <vs> <days>` — Show price chart", inline=False)
        embed.add_field(name="Indicators", value="`!indicator <coin> <vs> <days> <type>` — SMA/EMA/RSI/MACD", inline=False)
        embed.add_field(name="Alerts", value="`!alert set/list/remove/clear` — Price alerts", inline=False)
        embed.add_field(name="Misc", value="`!ping`, `!about`, `!convert`", inline=False)

        await ctx.send(embed=embed)

    # ---------------- CONVERT ----------------
    @commands.command(name="convert")
    async def convert(self, ctx: commands.Context, amount: float, coin: str = "bitcoin", vs: str = "usd"):
        """Convert an amount of a cryptocurrency to fiat.

        Example: `!convert 2 bitcoin usd`
        """
        await ctx.trigger_typing()

        data = await get_simple_price(coin, vs)
        if not data or vs not in data:
            await ctx.send("Invalid coin or unavailable data.")
            return

        price = data[vs]
        total = amount * price

        embed = discord.Embed(color=discord.Color.gold())
        embed.title = "Conversion Result"
        embed.add_field(name="Coin", value=coin.capitalize())
        embed.add_field(name="Rate", value=f"1 {coin} = {price} {vs.upper()}")
        embed.add_field(name="Amount", value=str(amount))
        embed.add_field(name="Total", value=f"{total} {vs.upper()}")
        await ctx.send(embed=embed)

    # ---------------- INVITE ----------------
    @commands.command(name="invite")
    async def invite(self, ctx: commands.Context):
        """Show bot invite link (requires CLIENT_ID in .env)."""
        if not CLIENT_ID:
            await ctx.send("No CLIENT_ID set in environment — cannot generate invite link.")
            return

        perms = 8  # admin; change if needed
        url = f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}&permissions={perms}&scope=bot%20applications.commands"
        await ctx.send(f"Invite me to your server:{url}")

async def setup(bot: commands.Bot):
    cog = MiscCog(bot)  # REPLACE PriceCog with the cog class in this file
    maybe = bot.add_cog(cog)
    if inspect.isawaitable(maybe):
        await maybe
