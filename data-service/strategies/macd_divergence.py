# -*- coding: utf-8 -*-
"""MACD Divergence — classic reversal signal.

Bullish (bottom) divergence: price prints a lower low while MACD histogram
makes a higher low. Bearish (top) divergence: price prints a higher high
while MACD makes a lower high. We scan over a 30-bar window for the two
most recent pivots.
"""
from __future__ import annotations

import pandas as pd

from indicators import calc_macd
from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class MacdDivergenceParams(Params):
    lookback_days: int = 60
    pivot_window: int = 5


class MacdDivergence(AbstractStrategy):
    id = "macd_divergence"
    name = "MACD 背离"
    default_weight = 0.05
    Params = MacdDivergenceParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.lookback_days + 10:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float).tail(p.lookback_days).reset_index(drop=True)
        dif, dea, hist = calc_macd(close)

        w = p.pivot_window
        pivots_low: list[int] = []
        pivots_high: list[int] = []
        for i in range(w, len(close) - w):
            window = close.iloc[i - w:i + w + 1]
            if close.iloc[i] == window.min():
                pivots_low.append(i)
            if close.iloc[i] == window.max():
                pivots_high.append(i)

        score = 0.0
        details: dict = {}
        signal = "neutral"

        # Bullish divergence: last two lows
        if len(pivots_low) >= 2:
            i2, i1 = pivots_low[-1], pivots_low[-2]
            if close.iloc[i2] < close.iloc[i1] and hist.iloc[i2] > hist.iloc[i1]:
                score += 60
                signal = "bullish"
                details["bullish_divergence"] = {"low1": float(close.iloc[i1]),
                                                  "low2": float(close.iloc[i2])}

        # Bearish divergence: last two highs
        if len(pivots_high) >= 2:
            i2, i1 = pivots_high[-1], pivots_high[-2]
            if close.iloc[i2] > close.iloc[i1] and hist.iloc[i2] < hist.iloc[i1]:
                # bearish drags score down even if bullish also matched (rare)
                score = max(score - 30, 10)
                signal = "bearish" if score < 30 else signal
                details["bearish_divergence"] = {"high1": float(close.iloc[i1]),
                                                  "high2": float(close.iloc[i2])}

        # Recency boost — pivot in the last 10 bars matters more
        if pivots_low and (len(close) - 1 - pivots_low[-1]) <= 10 and signal == "bullish":
            score += 20
            details["recent_pivot"] = True

        score = max(0.0, min(100.0, score))
        if signal == "neutral":
            signal = self._bullish(score, threshold=60)
        return ScoreResult(
            score=score, signal=signal, details=details,
            factors={"hist_last": float(hist.iloc[-1])},
            triggered=score >= 60,
        )
