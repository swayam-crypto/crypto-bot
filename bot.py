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

#!/usr/bin/env python3
import os
import asyncio
import logging
import importlib
import inspect
import signal
from pathlib import Path
from typing import List

import discord
from dotenv import load_dotenv
from discord.ext import commands

load_dotenv()
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("crypto-bot")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
if not DISCORD_TOKEN:
    logger.error("DISCORD_TOKEN missing in environment.")
    raise SystemExit(1)

intents = discord.Intents.default()
intents.message_content = True

# dynamic prefix example (replace with your own callable if you use per-guild prefixes)
DEFAULT_PREFIX = "!"
def get_prefix(bot, message):
    return commands.when_mentioned_or(DEFAULT_PREFIX)(bot, message)

bot = commands.Bot(command_prefix=get_prefix, intents=intents)

COG_DIR = "cogs"

def discover_cogs(cog_dir: str = COG_DIR) -> List[str]:
    p = Path(cog_dir)
    if not p.exists() or not p.is_dir():
        logger.warning("Cog directory '%s' not found.", cog_dir)
        return []
    mods = []
    for fname in sorted(os.listdir(cog_dir)):
        if fname.endswith(".py") and not fname.startswith("__"):
            mods.append(f"{cog_dir}.{fname[:-3]}")
    return mods


async def load_cogs():
    mods = discover_cogs()
    for module_name in mods:
        try:
            mod = importlib.import_module(module_name)
            importlib.reload(mod)
        except Exception:
            logger.exception("Failed to import cog %s", module_name)
            continue

        setup_func = getattr(mod, "setup", None)
        if setup_func:
            try:
                if inspect.iscoroutinefunction(setup_func):
                    await setup_func(bot)
                else:
                    setup_func(bot)
                logger.info("Loaded cog: %s", module_name)
            except Exception:
                logger.exception("Error running setup() in %s", module_name)
            continue

        # fallback to load_extension
        try:
            res = bot.load_extension(module_name)
            if inspect.isawaitable(res):
                await res
            logger.info("Loaded extension via load_extension: %s", module_name)
        except Exception:
            logger.exception("Failed to load extension %s via load_extension()", module_name)


@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)


async def _shutdown_cogs():
    """
    Call .shutdown() on cogs that implement it (awaitable), then call cog_unload if present.
    This lets each cog close sessions/databases cleanly.
    """
    for name, cog in list(bot.cogs.items()):
        try:
            # prefer explicit async shutdown()
            shutdown = getattr(cog, "shutdown", None)
            if shutdown and inspect.iscoroutinefunction(shutdown):
                logger.info("Running async shutdown for cog %s", name)
                try:
                    await shutdown()
                except Exception:
                    logger.exception("Error in shutdown() of cog %s", name)
            # fall back to cog_unload (may be sync)
            unload = getattr(cog, "cog_unload", None)
            if unload:
                try:
                    unload()
                except Exception:
                    logger.exception("cog_unload failed for %s", name)
        except Exception:
            logger.exception("Error while shutting down cog %s", name)


async def main():
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()

    def _signal_handler():
        logger.info("Received stop signal, shutting down...")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    stop_task = None
    try:
        async with bot:
            await load_cogs()
            bot_task = asyncio.create_task(bot.start(DISCORD_TOKEN))

            # create a Task for the stop event waiter instead of passing coroutine
            stop_task = asyncio.create_task(stop.wait())

            # wait until either bot_task completes or stop event is set
            done, pending = await asyncio.wait(
                {bot_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            # If stop event triggered (stop_task done) and bot still running, cancel it
            if stop_task in done and not bot_task.done():
                logger.info("Stop event detected, cancelling bot task...")
                bot_task.cancel()
                try:
                    await bot_task
                except asyncio.CancelledError:
                    logger.debug("Bot task cancelled during shutdown.")
            # If bot_task completed first with an exception, re-raise to outer handler
            elif bot_task in done:
                # propagate exception if bot_task failed
                exc = bot_task.exception()
                if exc:
                    raise exc

    except Exception:
        logger.exception("Fatal error in main()")
    finally:
        # ensure stop_task is cleaned up
        if stop_task is not None:
            if not stop_task.done():
                stop_task.cancel()
            try:
                await stop_task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("stop_task cleanup error", exc_info=True)

        try:
            await _shutdown_cogs()
        except Exception:
            logger.exception("Error during cog shutdown.")
        try:
            if not bot.is_closed():
                logger.info("Closing bot connection...")
                await bot.close()
        except Exception:
            logger.exception("Error while closing bot.")
        logger.info("Bot shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Exiting.")
    except Exception:
        logger.exception("Unhandled exception in top-level run.")
