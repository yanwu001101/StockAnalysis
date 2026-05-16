# -*- coding: utf-8 -*-
"""12-1 Month Momentum (Jegadeesh & Titman 1993).

Use trailing 12-month return excluding the most recent month (to skip 1-month
reversal). Stocks in the top decile of this measure earn ~12% annual return
premium over the bottom decile in developed markets; the A-share variant is
weaker but still has signal.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class Momentum12_1Params(Params):
    # We aim for ~12 months excluding the last month, but the stored window is
    # capped at ~250 trading days so we pick numbers that fit (and degrade
    # gracefully on shorter histories rather than returning insufficient_data).
    lookback_days: int = 220
    skip_days: int = 20
    min_history: int = 60


class Momentum12_1(AbstractStrategy):
    id = "momentum_12_1"
    name = "12-1 月动量"
    default_weight = 0.10
    Params = Momentum12_1Params

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        if df is None or len(df) < self.params.min_history + self.params.skip_days:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})
        close = df["收盘"].astype(float)
        # Auto-shrink window if the dataset is shorter than the configured one.
        usable = len(close) - self.params.skip_days
        lookback = min(self.params.lookback_days, usable - 1)
        end_idx = len(close) - self.params.skip_days
        start_idx = end_idx - lookback
        if start_idx < 0:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})
        p_start = close.iloc[start_idx]
        p_end = close.iloc[end_idx - 1]
        if p_start <= 0:
            return ScoreResult(score=0, signal="neutral")
        ret = (p_end / p_start) - 1.0
        score = max(0.0, min(100.0, (ret + 0.5) / 1.5 * 100))
        # Confirmation: above 200-day MA
        ma200 = close.rolling(min(200, len(close))).mean().iloc[-1]
        confirms = bool(close.iloc[-1] > ma200) if pd.notna(ma200) else False
        if confirms:
            score = min(100.0, score + 5)
        details = {"ret_window": round(ret, 4), "window_days": lookback, "above_ma200": confirms}
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=65),
            details=details, factors={"ret_12_1": ret},
            triggered=score >= 65,
        )
