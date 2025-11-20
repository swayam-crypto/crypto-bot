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
utils/indicators.py

Lightweight, dependency-free implementations of common technical indicators.

All functions accept a list[float] `prices` (usually close prices) and return
a list of the same length where early indices that lack enough data contain None.

Usage examples:
    from utils.indicators import sma, rsi, macd
    s = sma(prices, 20)
    r = rsi(prices, 14)
    macd_line, signal, hist = macd(prices)
"""

from __future__ import annotations
from typing import List, Optional, Tuple
import math

def _safe_float(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0

def sma(values: List[float], period: int) -> List[Optional[float]]:
    """Simple moving average."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n == 0:
        return out
    window = 0.0
    for i in range(n):
        window += _safe_float(values[i])
        if i >= period:
            window -= _safe_float(values[i - period])
        if i >= period - 1:
            out[i] = window / period
    return out

def ema(values: List[float], period: int) -> List[Optional[float]]:
    """Exponential moving average. Uses the first value as seed."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n == 0:
        return out
    k = 2.0 / (period + 1)
    prev: Optional[float] = None
    for i, v in enumerate(values):
        v = _safe_float(v)
        if prev is None:
            prev = v
            out[i] = prev
        else:
            prev = v * k + prev * (1 - k)
            out[i] = prev
    return out

def rsi(values: List[float], period: int = 14) -> List[Optional[float]]:
    """Relative Strength Index (Wilder's smoothed)."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n < period + 1:
        return out

    gains: List[float] = [0.0] * n
    losses: List[float] = [0.0] * n
    for i in range(1, n):
        diff = _safe_float(values[i]) - _safe_float(values[i - 1])
        gains[i] = max(diff, 0.0)
        losses[i] = max(-diff, 0.0)

    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    # first RSI value at index == period
    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - (100.0 / (1.0 + rs))

    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out

def macd(values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    MACD implementation:
      - macd_line = EMA(fast) - EMA(slow)
      - signal = EMA(macd_line, signal) computed on compact non-None macd values
      - histogram = macd_line - signal (None where unavailable)
    """
    n = len(values)
    if n == 0:
        return [], [], []
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line: List[Optional[float]] = [None] * n
    for i in range(n):
        f = fast_ema[i]
        s = slow_ema[i]
        if f is None or s is None:
            macd_line[i] = None
        else:
            macd_line[i] = f - s

    # compact list of macd values (skip None) to compute signal ema
    compact = [v for v in macd_line if v is not None]
    signal_compact = ema(compact, signal) if compact else []
    signal_line: List[Optional[float]] = [None] * n
    if signal_compact:
        # align first signal value to the index of first non-None macd entry
        first_idx = next(i for i, v in enumerate(macd_line) if v is not None)
        for j, val in enumerate(signal_compact):
            signal_line[first_idx + j] = val

    hist: List[Optional[float]] = [None] * n
    for i in range(n):
        m = macd_line[i]
        s = signal_line[i]
        if m is None or s is None:
            hist[i] = None
        else:
            hist[i] = m - s
    return macd_line, signal_line, hist

def bollinger_bands(values: List[float], period: int = 20, width: float = 2.0) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    """
    Bollinger Bands: returns (middle_sma, upper_band, lower_band)
    upper = sma + width * stddev, lower = sma - width * stddev
    """
    n = len(values)
    middle = sma(values, period)
    upper: List[Optional[float]] = [None] * n
    lower: List[Optional[float]] = [None] * n
    if period <= 0 or n == 0:
        return middle, upper, lower

    for i in range(period - 1, n):
        window = [ _safe_float(values[j]) for j in range(i - period + 1, i + 1) ]
        mean = sum(window) / period
        var = sum((x - mean) ** 2 for x in window) / period
        std = math.sqrt(var)
        upper[i] = mean + width * std
        lower[i] = mean - width * std
    return middle, upper, lower

def true_range(highs: List[float], lows: List[float], closes: List[float]) -> List[Optional[float]]:
    """Compute True Range series given per-bar high/low/close lists (same length)."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    for i in range(n):
        h = _safe_float(highs[i])
        l = _safe_float(lows[i])
        if i == 0:
            out[i] = h - l
        else:
            prev_close = _safe_float(closes[i - 1])
            out[i] = max(h - l, abs(h - prev_close), abs(l - prev_close))
    return out

def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Average True Range using Wilder smoothing."""
    tr = true_range(highs, lows, closes)
    n = len(tr)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n < period:
        return out
    # first ATR value = simple average of first `period` TRs (index period-1)
    first_atr = sum(_safe_float(x) for x in tr[1: period + 1]) / period if period + 1 <= n else None
    if first_atr is None:
        return out
    out[period] = first_atr
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + _safe_float(tr[i])) / period
    return out

def roc(values: List[float], period: int = 12) -> List[Optional[float]]:
    """Rate of Change (%) = (price / price_n - 1) * 100"""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n <= period:
        return out
    for i in range(period, n):
        prev = _safe_float(values[i - period])
        if prev == 0:
            out[i] = None
        else:
            out[i] = (_safe_float(values[i]) / prev - 1.0) * 100.0
    return out

def compute_all(values: List[float], highs: List[float] = None, lows: List[float] = None, closes: List[float] = None) -> dict:
    """
    Convenience function returning a dict of common indicators computed from `values` (close prices).
    If you want ATR or TR you can pass highs/lows/closes. Example keys:
      { 'sma20': [...], 'ema20': [...], 'rsi14': [...], 'macd': (macd_line, signal, hist) }
    """
    out = {}
    out['sma20'] = sma(values, 20)
    out['ema20'] = ema(values, 20)
    out['rsi14'] = rsi(values, 14)
    out['macd'] = macd(values)  # tuple
    if highs is not None and lows is not None and closes is not None:
        out['atr14'] = atr(highs, lows, closes, 14)
    return out
