# -*- coding: utf-8 -*-
"""Trend pullback and trailing-stop strategy.

This strategy translates a common discretionary workflow into a rule score:
keep or add only when the major trend is intact and the pullback is controlled;
reduce when price breaks the moving-average / ATR trailing risk line.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class TrendPullbackStopParams(Params):
    fast_ma: int = 20
    slow_ma: int = 60
    atr_days: int = 14
    trail_mult: float = 2.6
    pullback_min: float = -0.10
    pullback_max: float = -0.03


class TrendPullbackStop(AbstractStrategy):
    id = "trend_pullback_stop"
    name = "趋势回撤止盈"
    default_weight = 0.07
    Params = TrendPullbackStopParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        need = max(p.slow_ma, p.atr_days) + 30
        if df is None or len(df) < need:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = pd.to_numeric(df["收盘"], errors="coerce").reset_index(drop=True)
        high = pd.to_numeric(df["最高"], errors="coerce").reset_index(drop=True)
        low = pd.to_numeric(df["最低"], errors="coerce").reset_index(drop=True)

        last = float(close.iloc[-1])
        ma_fast = close.rolling(p.fast_ma).mean()
        ma_slow = close.rolling(p.slow_ma).mean()
        ma20 = float(ma_fast.iloc[-1])
        ma60 = float(ma_slow.iloc[-1])
        ma60_prev = float(ma_slow.iloc[-20])
        trend_ok = last > ma60 and ma60 > ma60_prev

        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(p.atr_days).mean().iloc[-1])
        high20 = float(high.tail(20).max())
        drawdown = last / high20 - 1.0 if high20 > 0 else 0.0
        trail_stop = high20 - p.trail_mult * atr

        score = 50.0
        details = {
            "ma20": round(ma20, 2),
            "ma60": round(ma60, 2),
            "ma60_rising": ma60 > ma60_prev,
            "atr": round(atr, 3),
            "drawdown_20d": round(drawdown, 4),
            "trail_stop": round(trail_stop, 2),
            "trend_ok": trend_ok,
        }

        if trend_ok:
            score += 20
            if p.pullback_min <= drawdown <= p.pullback_max and last >= ma20 * 0.985:
                score += 18
                details["healthy_pullback"] = True
            elif drawdown > -0.02:
                score += 6
        else:
            score -= 16

        if last < trail_stop:
            score -= 28
            details["trailing_stop_break"] = True
        elif last < ma60:
            score -= 18
            details["ma60_break"] = True
        elif last < ma20:
            score -= 6
            details["below_ma20"] = True

        if drawdown <= -0.18:
            score -= 12
            details["deep_drawdown"] = True
        if drawdown >= -0.01 and trend_ok:
            details["near_recent_high"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score,
            signal=self._bullish(score, threshold=58),
            details=details,
            factors={"drawdown_20d": drawdown, "trail_stop": trail_stop},
            triggered=details.get("healthy_pullback", False) or details.get("trailing_stop_break", False),
        )
