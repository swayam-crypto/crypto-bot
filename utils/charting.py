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

# utils/charting.py
from __future__ import annotations
import io
import logging
from datetime import datetime
from typing import Sequence, List

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logger = logging.getLogger("crypto-bot.charting")

# mplfinance optional import
try:
    import mplfinance as mpf
    _HAS_MPLFINANCE = True
except Exception:
    _HAS_MPLFINANCE = False


def plot_price_png(dates: Sequence[datetime], prices: Sequence[float], coin: str, vs: str, days: str, ma_periods: List[int] = None) -> bytes:
    if ma_periods is None:
        ma_periods = []
    try:
        df = pd.DataFrame({"price": list(prices)}, index=pd.DatetimeIndex(list(dates)))
    except Exception:
        df = pd.DataFrame({"price": list(prices)})

    fig, ax = plt.subplots(figsize=(10, 4), dpi=100)
    ax.plot(df.index, df["price"], linewidth=1.25)
    ax.set_title(f"{coin.upper()} — last {days} days  ({vs.upper()})")
    ax.set_ylabel(vs.upper())
    ax.grid(alpha=0.15)

    for p in ma_periods:
        try:
            df[f"ma{p}"] = df["price"].rolling(window=p, min_periods=1).mean()
            ax.plot(df.index, df[f"ma{p}"], linewidth=0.9, label=f"MA{p}")
        except Exception:
            logger.debug("Failed to compute MA%d", p)

    if ma_periods:
        ax.legend(loc="upper left", fontsize="small")

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _build_ohlc_from_prices(dates: Sequence[datetime], prices: Sequence[float]) -> pd.DataFrame:
    # Best-effort pseudo-OHLC: create small windows to derive open/high/low/close.
    try:
        s = pd.Series(list(prices), index=pd.DatetimeIndex(list(dates)))
        ohlc = s.resample("1D").ohlc().dropna()
        # If resample produces no rows (short series), fallback to rolling
        if ohlc.empty:
            raise RuntimeError("resample empty")
        ohlc = ohlc.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close"})
        return ohlc
    except Exception:
        arr = []
        for i in range(len(prices)):
            window = prices[max(0, i - 3) : i + 1]
            o = window[0]
            c = window[-1]
            h = max(window)
            l = min(window)
            arr.append((dates[i], o, h, l, c))
        pdf = pd.DataFrame(arr, columns=["dt", "Open", "High", "Low", "Close"])
        pdf = pdf.set_index(pd.DatetimeIndex(pdf["dt"]))
        return pdf[["Open", "High", "Low", "Close"]]


def plot_candles_mpf(dates: Sequence[datetime], prices: Sequence[float], coin: str, vs: str, days: str,
                     timeframe: str = "1H", sma_list: List[int] = None, ema_list: List[int] = None,
                     show_rsi: bool = False, show_macd: bool = False) -> bytes:
    """
    Build candlestick-like PNG using mplfinance. Raises if mplfinance not installed.
    Returns PNG bytes.
    """
    if sma_list is None:
        sma_list = []
    if not _HAS_MPLFINANCE:
        raise RuntimeError("mplfinance not available")

    ohlc = _build_ohlc_from_prices(dates, prices)

    mc = mpf.make_marketcolors(up="g", down="r", inherit=True)
    style = mpf.make_mpf_style(marketcolors=mc, gridstyle=":", y_on_right=False)

    mav = sma_list if sma_list else None

    try:
        fig, axlist = mpf.plot(ohlc, type="candle", style=style, mav=mav, volume=False, returnfig=True,
                               title=f"{coin.upper()} — last {days} ({vs.upper()})")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.02)
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    except Exception:
        logger.exception("mplfinance plotting failed")
        raise
