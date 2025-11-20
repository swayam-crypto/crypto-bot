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
utils/converters.py

Simple coin symbol / alias normalizer for CoinGecko & Binance usage.

- normalize_coin(coin) -> coin_id (CoinGecko style)
- symbol_to_binance_pair(sym, vs="USDT") -> e.g. BTC -> BTCUSDT
- add_alias(alias, coin_id) -> runtime extension
"""

from __future__ import annotations
from typing import Dict, Optional

# Core mapping: common ticker/symbol -> coingecko id
# Add entries as you (or users) request them.
COIN_SYMBOLS: Dict[str, str] = {
    "btc": "bitcoin",
    "bitcoin": "bitcoin",
    "eth": "ethereum",
    "ethereum": "ethereum",
    "ethe": "ethereum",
    "usdt": "tether",
    "usd-tether": "tether",
    "bnb": "binancecoin",
    "bnb-chain": "binancecoin",
    "ada": "cardano",
    "xrp": "ripple",
    "ripp": "ripple",
    "doge": "dogecoin",
    "dogecoin": "dogecoin",
    "dot": "polkadot",
    "polka": "polkadot",
    "matic": "matic-network",
    "mn":"matic-network",
    "sol": "solana",
    "ltc": "litecoin",
    "lite-coin":"litecoin",
    "litec":"litecoin",
    "shib": "shiba-inu",
    "shibainu":"shiba-inu",
    "trx": "tron",
    "uni": "uniswap",
    "link": "chainlink",
    # add more as needed...
}

# Optional manual overrides for coin names that have ambiguous symbols.
# e.g. {'pay': 'tenpay'}  (example)
CUSTOM_OVERRIDES: Dict[str, str] = {}

def add_alias(alias: str, coin_id: str) -> None:
    """Register an alias at runtime (useful for admin commands)."""
    COIN_SYMBOLS[alias.lower().strip()] = coin_id.lower().strip()

def normalize_coin(coin: str) -> str:
    """
    Convert user input (symbol, ticker, or coingecko id) into a coin id suitable
    for CoinGecko calls.

    Examples:
        "btc" -> "bitcoin"
        "Bitcoin" -> "bitcoin"
        "ethereum" -> "ethereum" (unchanged)
    """
    if not coin:
        return coin
    key = coin.lower().strip()
    # custom overrides first
    if key in CUSTOM_OVERRIDES:
        return CUSTOM_OVERRIDES[key]
    return COIN_SYMBOLS.get(key, key)  # default to the input (assume it's already an id)

# ----------------- Binance helpers -----------------
# Convert a simple symbol into a typical Binance pair symbol.
# You can expand logic to detect stablecoins or user preferences (USDT vs USDC vs BUSD).
def symbol_to_binance_pair(sym: str, vs: str = "USDT") -> Optional[str]:
    """
    Convert e.g. "btc" -> "BTCUSDT".
    Returns None if input empty.
    """
    if not sym:
        return None
    s = sym.upper().strip()
    v = vs.upper().strip()
    # basic safety: if user already passed a pair like BTCUSDT, return as-is
    if len(s) >= 6 and (s.endswith("USDT") or s.endswith("BTC") or s.endswith("USDC") or s.endswith("BUSD")):
        return s
    return f"{s}{v}"

__all__ = ["normalize_coin", "add_alias", "symbol_to_binance_pair", "COIN_SYMBOLS"]
