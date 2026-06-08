# -*- coding: utf-8 -*-
"""Daily momentum / reversal T+0 assistant.

A-share intraday/next-day trading often rewards very short bursts, then mean
reverts quickly. This strategy is intentionally short-horizon: it rewards a
fresh 1-2 day momentum burst when it is not yet crowded, and warns when a
multi-day spike becomes chase-risk.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class DailyMomentumReversalTParams(Params):
    momentum_1d: float = 0.018
    hot_3d: float = 0.075
    hot_5d: float = 0.12
    dip_1d: float = -0.025
    volume_confirm: float = 1.15


class DailyMomentumReversalT(AbstractStrategy):
    id = "daily_momentum_reversal_t"
    name = "日频动量反转T"
    default_weight = 0.08
    Params = DailyMomentumReversalTParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < 30:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = pd.to_numeric(df["收盘"], errors="coerce").reset_index(drop=True)
        volume = pd.to_numeric(df["成交量"], errors="coerce").reset_index(drop=True)
        if close.isna().any() or close.iloc[-6] <= 0:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})

        r1 = float(close.iloc[-1] / close.iloc[-2] - 1.0) if close.iloc[-2] > 0 else 0.0
        r2 = float(close.iloc[-1] / close.iloc[-3] - 1.0) if close.iloc[-3] > 0 else 0.0
        r3 = float(close.iloc[-1] / close.iloc[-4] - 1.0) if close.iloc[-4] > 0 else 0.0
        r5 = float(close.iloc[-1] / close.iloc[-6] - 1.0)
        ma20 = float(close.rolling(20).mean().iloc[-1])
        v5 = float(volume.tail(5).mean())
        v20 = float(volume.tail(25).head(20).mean()) if len(volume) >= 25 else v5
        vol_ratio = v5 / v20 if v20 > 0 else 1.0

        score = 50.0
        details = {
            "r1": round(r1, 4),
            "r2": round(r2, 4),
            "r3": round(r3, 4),
            "r5": round(r5, 4),
            "volume_ratio": round(vol_ratio, 2),
            "above_ma20": close.iloc[-1] >= ma20,
        }

        if r1 >= p.momentum_1d and r3 < p.hot_3d and r5 < p.hot_5d:
            score += 24
            details["fresh_daily_momentum"] = True
        if r2 >= p.momentum_1d * 1.5 and r5 < p.hot_5d:
            score += 10
        if r1 <= p.dip_1d and close.iloc[-1] >= ma20 * 0.985:
            score += 18
            details["trend_dip_for_t"] = True
        if vol_ratio >= p.volume_confirm and (r1 > 0 or r2 > 0):
            score += 10
            details["volume_confirmed"] = True
        if r3 >= p.hot_3d or r5 >= p.hot_5d:
            score -= 30
            details["overheat_reversal_risk"] = True
        if close.iloc[-1] < ma20 and r1 < 0:
            score -= 10

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score,
            signal=self._bullish(score, threshold=60),
            details=details,
            factors={"r1": r1, "r3": r3, "r5": r5},
            triggered=score >= 65 or score <= 30,
        )
