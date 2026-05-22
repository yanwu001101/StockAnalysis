# -*- coding: utf-8 -*-
"""Turtle Breakout — Donchian channel breakout with ATR confirmation.

Richard Dennis's Turtle Traders system (1983). A bullish signal fires when
close crosses above the prior 20-day high while ATR-normalised volatility
is healthy enough to support a real trend (not a noise spike).
"""
from __future__ import annotations

import pandas as pd

from indicators import calc_atr
from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class TurtleBreakoutParams(Params):
    channel_days: int = 20
    atr_period: int = 14
    atr_mult_min: float = 0.8


class TurtleBreakout(AbstractStrategy):
    id = "turtle_breakout"
    name = "海龟通道突破"
    default_weight = 0.06
    Params = TurtleBreakoutParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        n = self.params.channel_days
        if df is None or len(df) < n + self.params.atr_period + 2:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float)
        high = df["最高"].astype(float)
        low = df["最低"].astype(float)
        volume = df["成交量"].astype(float)

        prior_hh = high.shift(1).rolling(n).max()
        prior_ll = low.shift(1).rolling(n).min()
        atr = calc_atr(high, low, close, period=self.params.atr_period)

        last_close = float(close.iloc[-1])
        last_atr = float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else 0.0
        hh = float(prior_hh.iloc[-1]) if pd.notna(prior_hh.iloc[-1]) else 0.0
        ll = float(prior_ll.iloc[-1]) if pd.notna(prior_ll.iloc[-1]) else 0.0

        score = 0.0
        details: dict = {}

        if hh > 0 and last_close > hh:
            score += 55
            details["breakout_up"] = True
            details["channel_high"] = round(hh, 3)
        elif ll > 0 and last_close < ll:
            score = 20
            details["breakout_down"] = True

        # ATR check: avoid super low-vol breakouts that fade quickly.
        atr_pct = last_atr / last_close if last_close > 0 else 0.0
        if atr_pct >= 0.01 * self.params.atr_mult_min:
            score += 15
            details["atr_ok"] = True

        # Volume confirmation
        if len(volume) >= 20:
            avg_v = float(volume.tail(20).mean())
            if avg_v > 0 and float(volume.iloc[-1]) > 1.5 * avg_v:
                score += 15
                details["volume_confirm"] = True

        # Sustained trend (MA20 > MA60)
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]
        if pd.notna(ma20) and pd.notna(ma60) and ma20 > ma60:
            score += 15
            details["trend_up"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details=details,
            factors={"close": last_close, "atr_pct": round(atr_pct, 4)},
            triggered=score >= 60,
        )
