# -*- coding: utf-8 -*-
"""MAX Reversal — lottery-preference anomaly (Bali, Cakici, Whitelaw 2011).

"Maximum Daily Return as a Predictor of the Cross Section of Expected Returns"
documents that stocks with the highest single-day returns over the past month
*underperform* going forward, because retail investors overpay for lottery-like
upside. We score the inverse — stocks with low recent MAX get a high score.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class MaxReversalParams(Params):
    window_days: int = 22
    top_k: int = 5
    high_max_pct: float = 0.09


class MaxReversal(AbstractStrategy):
    id = "max_reversal"
    name = "彩票异象反向 (MAX)"
    default_weight = 0.05
    Params = MaxReversalParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.window_days + 5:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float)
        rets = close.pct_change().tail(p.window_days).dropna()
        if rets.empty:
            return ScoreResult(score=0, signal="neutral")

        top_k = sorted(rets.tolist(), reverse=True)[: p.top_k]
        avg_max = float(sum(top_k) / len(top_k)) if top_k else 0.0

        score = max(0.0, min(100.0, (p.high_max_pct - avg_max) / p.high_max_pct * 100))
        triggered = avg_max < p.high_max_pct * 0.5
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details={"avg_top_k_return": round(avg_max, 4),
                     "warning": "high lottery preference" if avg_max > p.high_max_pct else None},
            factors={"max_return": float(max(rets)) if len(rets) else 0.0},
            triggered=triggered,
        )
