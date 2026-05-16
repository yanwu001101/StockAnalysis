# -*- coding: utf-8 -*-
"""Low Volatility Anomaly (Frazzini & Pedersen, "Betting Against Beta").

Low-volatility stocks have historically earned higher risk-adjusted returns
than the high-vol cohort. We score by the inverse of 60-day return std dev.
Combined with a positive-trend filter to avoid "low-vol because dying".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class LowVolatilityParams(Params):
    lookback_days: int = 60
    annualize: bool = True


class LowVolatility(AbstractStrategy):
    id = "low_volatility"
    name = "低波动异象"
    default_weight = 0.08
    Params = LowVolatilityParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        n = self.params.lookback_days
        if df is None or len(df) < n + 5:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float)
        rets = close.pct_change().tail(n).dropna()
        if rets.empty:
            return ScoreResult(score=0, signal="neutral")
        std = float(rets.std())
        if self.params.annualize:
            std = std * np.sqrt(252)

        ma60 = close.rolling(60).mean().iloc[-1]
        trend_ok = bool(close.iloc[-1] > ma60) if pd.notna(ma60) else False

        score = max(0.0, min(100.0, (0.40 - std) / 0.30 * 100))
        if not trend_ok:
            score *= 0.6
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=55),
            details={"vol_ann": round(std, 4), "trend_ok": trend_ok},
            factors={"sigma_60d_ann": std},
            triggered=score >= 55 and trend_ok,
        )
