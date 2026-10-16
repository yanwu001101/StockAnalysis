"""Technical indicators — pure math over plain sequences.

No I/O, no pandas, no global state. Every function is a total function of its
inputs, which is what makes the backtest reproducible: identical bars in,
identical numbers out.

Conventions (matching the mainstream Chinese trading platforms):
  * EMA is the recursive form seeded with the first value (``adjust=False``),
  * RSI uses Wilder smoothing after a simple average seed,
  * every output array has the same length as the input and is padded with
    ``nan`` where the window is not yet filled.
"""
from __future__ import annotations

from typing import Sequence

import numpy as np

Array = np.ndarray


def _as_array(values: Sequence[float]) -> Array:
    return np.asarray(values, dtype=np.float64)


def sma(values: Sequence[float], window: int) -> Array:
    arr = _as_array(values)
    if window <= 0 or arr.size == 0:
        return np.full(arr.shape, np.nan)
    out = np.full(arr.shape, np.nan)
    for i in range(window - 1, arr.size):
        out[i] = arr[i - window + 1 : i + 1].mean()
    return out


def ema(values: Sequence[float], span: int) -> Array:
    """Recursive EMA seeded with the first observation."""
    arr = _as_array(values)
    if span <= 0 or arr.size == 0:
        return np.full(arr.shape, np.nan)
    alpha = 2.0 / (span + 1.0)
    out = np.empty(arr.shape, dtype=np.float64)
    out[0] = arr[0]
    for i in range(1, arr.size):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


def macd(
    close: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Array, Array, Array]:
    """Return (DIF, DEA, MACD histogram). Histogram = 2 * (DIF - DEA)."""
    arr = _as_array(close)
    if arr.size == 0:
        empty = np.empty(0)
        return empty, empty, empty
    dif = ema(arr, fast) - ema(arr, slow)
    dea = ema(dif, signal)
    return dif, dea, 2.0 * (dif - dea)


def rsi(close: Sequence[float], period: int = 14) -> Array:
    """Wilder RSI. Values before the seed window are ``nan``."""
    arr = _as_array(close)
    n = arr.size
    out = np.full(n, np.nan)
    if n <= period or period <= 0:
        return out
    delta = np.diff(arr)
    gains = np.where(delta > 0.0, delta, 0.0)
    losses = np.where(delta < 0.0, -delta, 0.0)

    avg_gain = float(gains[:period].mean())
    avg_loss = float(losses[:period].mean())
    for i in range(period, n):
        idx = i - 1
        avg_gain = (avg_gain * (period - 1) + gains[idx]) / period
        avg_loss = (avg_loss * (period - 1) + losses[idx]) / period
        if avg_loss <= 0.0:
            out[i] = 100.0 if avg_gain > 0.0 else 50.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def bollinger(
    close: Sequence[float], period: int = 20, num_std: float = 2.0
) -> tuple[Array, Array, Array]:
    """Return (upper, middle, lower). Population std (ddof=0)."""
    arr = _as_array(close)
    n = arr.size
    upper = np.full(n, np.nan)
    middle = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    if n < period or period <= 0:
        return upper, middle, lower
    for i in range(period - 1, n):
        window = arr[i - period + 1 : i + 1]
        mean = float(window.mean())
        std = float(window.std(ddof=0))
        middle[i] = mean
        upper[i] = mean + num_std * std
        lower[i] = mean - num_std * std
    return upper, middle, lower


def true_range(
    high: Sequence[float], low: Sequence[float], close: Sequence[float]
) -> Array:
    h = _as_array(high)
    low_arr = _as_array(low)
    c = _as_array(close)
    if c.size == 0:
        return np.empty(0)
    prev_close = np.roll(c, 1)
    prev_close[0] = c[0]
    return np.maximum.reduce([h - low_arr, np.abs(h - prev_close), np.abs(low_arr - prev_close)])


def atr(
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    period: int = 14,
) -> Array:
    """Wilder ATR."""
    tr = true_range(high, low, close)
    n = tr.size
    out = np.full(n, np.nan)
    if n < period or period <= 0:
        return out
    out[period - 1] = float(tr[:period].mean())
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out
