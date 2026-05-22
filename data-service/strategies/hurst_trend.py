# -*- coding: utf-8 -*-
"""Hurst Exponent — trend vs mean-reversion classifier (Mandelbrot, 1971).

H > 0.55 → persistent trend (momentum follow). H < 0.45 → anti-persistent
(mean reverting). H ≈ 0.5 → random walk. Combined with the current trend
direction to award score: high H + uptrend = strong bullish; low H +
near low = mean-reversion buy.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


def _hurst_rs(series: pd.Series, min_lag: int = 8, max_lag: int = 64) -> float:
    """Rescaled-range Hurst estimate. Returns 0.5 on failure."""
    lags = range(min_lag, min(max_lag, len(series) // 2))
    arr = series.dropna().values
    if len(arr) < max_lag * 2:
        return 0.5
    tau = []
    for lag in lags:
        diffs = arr[lag:] - arr[:-lag]
        sd = float(np.std(diffs))
        if sd <= 0:
            continue
        tau.append((lag, sd))
    if len(tau) < 4:
        return 0.5
    xs = np.log([t[0] for t in tau])
    ys = np.log([t[1] for t in tau])
    slope = float(np.polyfit(xs, ys, 1)[0])
    return slope


class HurstTrendParams(Params):
    lookback_days: int = 180
    trend_threshold: float = 0.55
    revert_threshold: float = 0.45


class HurstTrend(AbstractStrategy):
    id = "hurst_trend"
    name = "Hurst 趋势性"
    default_weight = 0.04
    Params = HurstTrendParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.lookback_days:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float).tail(p.lookback_days).reset_index(drop=True)
        log_close = np.log(close.replace(0, np.nan).dropna())
        h = _hurst_rs(log_close)

        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]
        last = float(close.iloc[-1])
        trend_up = bool(pd.notna(ma20) and pd.notna(ma60) and ma20 > ma60 and last > ma20)

        ll_60 = float(close.tail(60).min())
        near_low = last < ll_60 * 1.05

        score = 50.0
        details: dict = {"hurst": round(h, 3)}
        if h >= p.trend_threshold:
            details["regime"] = "trend"
            score = 60 + (h - p.trend_threshold) * 200
            if trend_up:
                score += 15
                details["trend_up"] = True
            else:
                score -= 20
        elif h <= p.revert_threshold:
            details["regime"] = "mean-revert"
            score = 60 + (p.revert_threshold - h) * 200
            if near_low:
                score += 10
                details["near_low"] = True
            else:
                score -= 10
        else:
            details["regime"] = "random"
            score = 45

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details=details,
            factors={"hurst": float(h)},
            triggered=score >= 60,
        )
