# -*- coding: utf-8 -*-
"""52-Week High Effect (George & Hwang 2004).

"The 52-Week High and Momentum Investing" — stocks trading close to their
52-week high outperform on a 6-12 month horizon. The anchor effect makes
investors slow to react to good news once price punches through the prior
high. We score by closeness to the high (within 5% → strong) plus a trend
filter so a stock chopping near a long-broken high doesn't qualify.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class FiftyTwoWeekHighParams(Params):
    lookback_days: int = 250
    high_proximity_pct: float = 0.95
    very_close_pct: float = 0.98


class FiftyTwoWeekHigh(AbstractStrategy):
    id = "fifty_two_week_high"
    name = "52周新高效应"
    default_weight = 0.07
    Params = FiftyTwoWeekHighParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.lookback_days * 0.6:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float)
        high = df["最高"].astype(float)
        volume = df["成交量"].astype(float)

        window = high.tail(p.lookback_days)
        last = float(close.iloc[-1])
        hh_52w = float(window.max())
        if hh_52w <= 0:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})

        proximity = last / hh_52w
        score = 0.0
        details: dict = {"proximity": round(proximity, 3), "hh_52w": round(hh_52w, 2)}

        # Score curve: very close (>=98%) → strong, close (>=95%) → medium,
        # within 90% → mild, otherwise zero / penalize when far below.
        if proximity >= p.very_close_pct:
            score += 55
            details["very_close"] = True
        elif proximity >= p.high_proximity_pct:
            score += 40
        elif proximity >= 0.90:
            score += 20
        elif proximity <= 0.50:
            score -= 10

        # Trend confirmation: above MA60 + MA60 rising
        ma60 = close.rolling(60).mean()
        if len(ma60.dropna()) >= 20:
            ma60_last = float(ma60.iloc[-1])
            ma60_prev = float(ma60.iloc[-20])
            if last > ma60_last:
                score += 15
                details["above_ma60"] = True
            if ma60_last > ma60_prev:
                score += 10
                details["ma60_rising"] = True

        # Volume on push-up: last 5 days avg vs prior 20
        if len(volume) >= 25:
            v5 = float(volume.tail(5).mean())
            v20 = float(volume.tail(25).head(20).mean())
            if v20 > 0 and v5 > 1.2 * v20:
                score += 15
                details["volume_push"] = True

        # Punishment when fresh 52w low (catches catastrophic drops)
        ll_52w = float(df["最低"].astype(float).tail(p.lookback_days).min())
        if ll_52w > 0 and last <= ll_52w * 1.02:
            score = max(score - 25, 5)
            details["near_52w_low"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=55),
            details=details,
            factors={"proximity_52w_high": proximity},
            triggered=score >= 55 and proximity >= p.high_proximity_pct,
        )
