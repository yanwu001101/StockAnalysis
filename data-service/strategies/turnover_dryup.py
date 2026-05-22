# -*- coding: utf-8 -*-
"""Turnover Dry-up — A-share specific bottoming pattern.

Persistent low turnover combined with price refusing to set a new low is a
well-known A-share retail capitulation signal. When the float stops being
distributed and the candlestick range tightens, accumulation often follows.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class TurnoverDryUpParams(Params):
    lookback_days: int = 30
    low_quantile: float = 0.30
    near_low_pct: float = 0.05


class TurnoverDryUp(AbstractStrategy):
    id = "turnover_dryup"
    name = "缩量企稳 (底部)"
    default_weight = 0.04
    Params = TurnoverDryUpParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.lookback_days * 3:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float)
        volume = df["成交量"].astype(float)

        # Volume regime: recent average vs the longer-term distribution.
        recent_v = volume.tail(p.lookback_days)
        base_v = volume.tail(p.lookback_days * 3)
        if recent_v.empty or base_v.empty:
            return ScoreResult(score=0, signal="neutral")
        recent_mean = float(recent_v.mean())
        threshold = float(base_v.quantile(p.low_quantile))
        dried_up = recent_mean <= threshold

        # Volatility contraction (ATR-equivalent via close range)
        ranges = (df["最高"].astype(float) - df["最低"].astype(float)).tail(p.lookback_days)
        prior_ranges = (df["最高"].astype(float) - df["最低"].astype(float)).tail(p.lookback_days * 3).head(p.lookback_days * 2)
        narrow = float(ranges.mean()) <= float(prior_ranges.mean()) * 0.85 if not prior_ranges.empty else False

        # Price near (within 5%) the lookback low but NOT making a fresh low.
        low_band = float(close.tail(p.lookback_days * 2).min())
        last = float(close.iloc[-1])
        near_low = last <= low_band * (1 + p.near_low_pct)
        fresh_low = last <= low_band

        score = 0.0
        details: dict = {}
        if dried_up:
            score += 35
            details["volume_dryup"] = True
        if narrow:
            score += 20
            details["range_contraction"] = True
        if near_low and not fresh_low:
            score += 30
            details["holding_above_low"] = True
        elif fresh_low:
            details["fresh_low_warning"] = True
            score = max(score - 15, 5)

        # Confirmation: most recent bar shows tiny up bar with low volume
        if len(close) >= 2:
            chg = (last / float(close.iloc[-2]) - 1) if float(close.iloc[-2]) > 0 else 0
            if 0 < chg < 0.015:
                score += 15
                details["mild_up_bar"] = round(chg, 4)

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details=details,
            factors={"recent_vol_ratio": recent_mean / threshold if threshold else 0.0},
            triggered=score >= 60,
        )
