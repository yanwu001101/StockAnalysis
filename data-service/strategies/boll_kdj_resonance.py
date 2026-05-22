# -*- coding: utf-8 -*-
"""Bollinger Band + KDJ Resonance — mean-reversion + momentum confluence.

Broker-research-backed pattern: price touching/closing below the lower Bollinger
band while KDJ J turns up from below 20 is treated as a high-quality reversal
buy signal. The opposite (upper band + J above 80 down-cross) flags exits.
"""
from __future__ import annotations

import pandas as pd

from indicators import calc_bollinger, calc_kdj
from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class BollKdjResonanceParams(Params):
    boll_period: int = 20
    boll_std: float = 2.0
    j_oversold: int = 20
    j_overbought: int = 80


class BollKdjResonance(AbstractStrategy):
    id = "boll_kdj_resonance"
    name = "布林+KDJ 共振"
    default_weight = 0.06
    Params = BollKdjResonanceParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.boll_period + 10:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float)
        high = df["最高"].astype(float)
        low = df["最低"].astype(float)

        upper, mid, lower = calc_bollinger(close, period=p.boll_period, std_dev=p.boll_std)
        k, d, j = calc_kdj(high, low, close)

        last_close = float(close.iloc[-1])
        last_lower = float(lower.iloc[-1]) if pd.notna(lower.iloc[-1]) else 0.0
        last_upper = float(upper.iloc[-1]) if pd.notna(upper.iloc[-1]) else 0.0
        last_j = float(j.iloc[-1]) if pd.notna(j.iloc[-1]) else 50.0
        prev_j = float(j.iloc[-2]) if pd.notna(j.iloc[-2]) else 50.0

        score = 0.0
        details: dict = {}

        # Bullish resonance: near lower band + J turning up from oversold
        if last_lower > 0 and last_close <= last_lower * 1.02:
            score += 30
            details["near_lower_band"] = True
        if last_j < p.j_oversold and last_j > prev_j:
            score += 30
            details["j_oversold_up"] = round(last_j, 1)

        # Trend filter
        ma60 = close.rolling(60).mean().iloc[-1]
        if pd.notna(ma60) and last_close > float(ma60):
            score += 15
            details["above_ma60"] = True

        # Bearish anti-resonance trimming
        if last_upper > 0 and last_close >= last_upper * 0.98 and last_j > p.j_overbought:
            score = max(score - 30, 10)
            details["overbought_warning"] = True

        # Volume on the bounce
        volume = df["成交量"].astype(float)
        if len(volume) >= 10:
            recent_v = float(volume.iloc[-1])
            base_v = float(volume.tail(10).mean())
            if base_v > 0 and recent_v > 1.2 * base_v:
                score += 15
                details["volume_pickup"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details=details,
            factors={"close": last_close, "j": round(last_j, 2)},
            triggered=score >= 60,
        )
