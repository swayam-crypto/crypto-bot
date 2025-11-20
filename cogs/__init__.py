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
Package init for cogs folder.
This file allows Python to treat `cogs/` as a proper module so that
`bot.load_extension('cogs.filename')` works correctly.

You generally don't need to put anything here, but you *may* export
cog names if you want.
"""

__all__ = [
    'alerts',
    'chart',
    'indicators',
    'misc',
    'news',
    'portfolio',
    'price',
    'volume',
]
