# -*- coding: utf-8 -*-
"""PEAD — Post-Earnings Announcement Drift (Ball & Brown 1968).

Premise: after a positive earnings surprise (net_profit_yoy beats prior trend),
prices drift up over the following ~60 trading days. The score combines two
ingredients:
  * Recent earnings announcement (within `event_days`)
  * Magnitude of YoY net-profit growth vs. trailing 4-quarter average
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class PeadParams(Params):
    event_window_days: int = 60
    strong_growth_threshold: float = 30.0    # net_profit_yoy >= 30% -> strong


class Pead(AbstractStrategy):
    id = "pead"
    name = "PEAD 盈余惊喜后漂移"
    default_weight = 0.10
    Params = PeadParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.fundamental_df
        if df is None or df.empty:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})
        df = df.sort_values("report_date", ascending=False).reset_index(drop=True)

        def f(v):
            try:
                return float(v) if pd.notna(v) else 0.0
            except Exception:
                return 0.0

        cur = df.iloc[0]
        cur_yoy = f(cur.get("net_profit_yoy"))
        revenue_yoy = f(cur.get("revenue_yoy"))
        # If both YoY series are missing/zero and there is no recent earnings
        # event, PEAD cannot meaningfully score — flag as no_data so the
        # composite layer drops it instead of treating 0 as bearish.
        if cur_yoy == 0 and revenue_yoy == 0 and not ctx.has_earnings_announcement:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})

        score = 0.0
        details: dict = {}

        # Trailing 4-quarter average (excluding current)
        past = [f(r.get("net_profit_yoy")) for _, r in df.iloc[1:5].iterrows()]
        avg_past = (sum(past) / len(past)) if past else 0.0
        surprise = cur_yoy - avg_past
        details["yoy"] = cur_yoy
        details["yoy_baseline"] = avg_past
        details["surprise"] = surprise

        # Magnitude scoring
        if cur_yoy >= self.params.strong_growth_threshold: score += 30
        elif cur_yoy >= 15: score += 20
        elif cur_yoy >= 0: score += 8

        if surprise >= 20: score += 25
        elif surprise >= 10: score += 15
        elif surprise >= 0: score += 5
        elif surprise < -20: score -= 10

        # Event amplifier: recent announcement detected
        if ctx.has_earnings_announcement:
            score += 25
            details["event_recent"] = True

        # Revenue confirmation (avoid one-off gains)
        if f(cur.get("revenue_yoy")) >= 10:
            score += 15
            details["revenue_confirms"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=55),
            details=details, factors={"yoy": cur_yoy, "surprise": surprise},
            triggered=score >= 55 and ctx.has_earnings_announcement,
        )
