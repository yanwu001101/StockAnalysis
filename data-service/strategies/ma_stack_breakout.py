# -*- coding: utf-8 -*-
"""Moving-Average Stack & Breakout — main wave entry pattern.

Common A-share institutional setup: multiple MAs (5/10/20/30/60) compress
into a tight band ("黏合"), then price breaks out above all of them with
volume expansion. This is widely treated as the start of a new "主升浪".
We measure:
  * Compression: spread of (max-min) MAs relative to price, recent <= threshold
  * Breakout: current close above each MA, last close > prior close
  * Bullish stack: short MA > long MA progressively
  * Volume confirmation
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class MAStackParams(Params):
    ma_periods: tuple = (5, 10, 20, 30, 60)
    compression_threshold: float = 0.04
    very_compressed: float = 0.025


class MAStack(AbstractStrategy):
    id = "ma_stack_breakout"
    name = "均线粘合突破"
    default_weight = 0.06
    Params = MAStackParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        max_period = max(p.ma_periods)
        if df is None or len(df) < max_period + 10:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float)
        volume = df["成交量"].astype(float)
        mas = {n: close.rolling(n).mean() for n in p.ma_periods}

        last_mas = {n: float(s.iloc[-1]) for n, s in mas.items() if pd.notna(s.iloc[-1])}
        if len(last_mas) < len(p.ma_periods):
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        last = float(close.iloc[-1])
        ma_vals = list(last_mas.values())
        spread = (max(ma_vals) - min(ma_vals)) / last if last > 0 else 1.0

        score = 0.0
        details: dict = {"ma_spread": round(spread, 4),
                         "ma_last": {str(k): round(v, 2) for k, v in last_mas.items()}}

        # Compression
        if spread <= p.very_compressed:
            score += 30
            details["very_compressed"] = True
        elif spread <= p.compression_threshold:
            score += 20
            details["compressed"] = True

        # Bullish stack (5>10>20>30>60)
        sorted_periods = sorted(p.ma_periods)
        stacked = all(last_mas[a] >= last_mas[b]
                      for a, b in zip(sorted_periods, sorted_periods[1:]))
        if stacked:
            score += 25
            details["bullish_stack"] = True

        # Breakout: close above ALL MAs
        if all(last > v for v in ma_vals):
            score += 25
            details["above_all_mas"] = True

        # Yesterday->today momentum
        if len(close) >= 2:
            prev = float(close.iloc[-2])
            if last > prev:
                score += 10
                details["bar_up"] = round((last / prev - 1), 4)

        # Volume engagement
        if len(volume) >= 21:
            v5 = float(volume.tail(5).mean())
            v20 = float(volume.tail(25).head(20).mean())
            if v20 > 0 and v5 > 1.3 * v20:
                score += 15
                details["volume_expand"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details=details,
            factors={"ma_spread": spread, "stacked": stacked},
            triggered=score >= 70 and stacked,
        )
