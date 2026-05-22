# -*- coding: utf-8 -*-
"""Multi-Horizon Momentum — institutional-grade momentum factor.

Combines five widely-cited momentum specifications used by AQR / BlackRock /
Robeco quant equity books:

  * 1-week return       — short-term reversal sniff (Jegadeesh 1990)
  * 1-month return      — short momentum (Carhart 4-factor)
  * 3-month return      — quarterly momentum
  * 12-1 month return   — Jegadeesh-Titman 1993 cornerstone factor
  * Risk-adjusted (Sharpe-like) — return / realized vol over 60d

Crucially scores the *consistency* of signs across horizons. A stock
that's positive on every horizon (or negative on every) gets a confidence
bonus; mixed signals get penalised. This filters out chop and prefers
trending names.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class MultiHorizonMomentumParams(Params):
    short_days: int = 5
    medium_days: int = 21
    long_days: int = 63
    skip_days: int = 21       # for the 12-1 month carve-out
    big_lookback: int = 252
    consistency_min: int = 3   # need ≥3/4 horizons aligned for bonus


class MultiHorizonMomentum(AbstractStrategy):
    id = "multi_horizon_momentum"
    name = "多维度动量"
    default_weight = 0.10
    Params = MultiHorizonMomentumParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        need = p.big_lookback + 5
        if df is None or len(df) < p.medium_days * 3:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float).reset_index(drop=True)

        def ret(n: int) -> float | None:
            if len(close) <= n:
                return None
            a, b = float(close.iloc[-1]), float(close.iloc[-1 - n])
            return (a / b - 1.0) if b > 0 else None

        r_1w = ret(p.short_days)
        r_1m = ret(p.medium_days)
        r_3m = ret(p.long_days)
        r_12_1 = None
        if len(close) > p.big_lookback:
            a, b = float(close.iloc[-1 - p.skip_days]), float(close.iloc[-1 - p.big_lookback])
            if b > 0:
                r_12_1 = (a / b - 1.0)

        # Sharpe-like: 60-day mean daily return / std, annualised
        ret_series = close.pct_change().dropna().tail(p.long_days)
        if not ret_series.empty:
            mu = float(ret_series.mean()) * 252
            sd = float(ret_series.std()) * math.sqrt(252)
            sharpe = (mu / sd) if sd > 0 else 0.0
        else:
            sharpe = 0.0

        signals = [r_1w, r_1m, r_3m, r_12_1]
        valid = [s for s in signals if s is not None]
        if len(valid) < 2:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        details: dict = {
            "r_1w": round(r_1w, 4) if r_1w is not None else None,
            "r_1m": round(r_1m, 4) if r_1m is not None else None,
            "r_3m": round(r_3m, 4) if r_3m is not None else None,
            "r_12_1": round(r_12_1, 4) if r_12_1 is not None else None,
            "sharpe_annual": round(sharpe, 2),
        }

        # Direction-strength map: each horizon contributes a partial score.
        # Short-term reversal: tiny positive return is bullish, big positive
        # short-term spike is actually bearish (lottery preference / late chase).
        score = 50.0

        def bucket(r: float, mild: float, strong: float, extreme: float, weight: float) -> float:
            if r is None:
                return 0.0
            if r >= extreme:
                return -0.4 * weight       # too hot → reverse
            if r >= strong:
                return weight
            if r >= mild:
                return weight * 0.6
            if r <= -strong:
                return -weight
            if r <= -mild:
                return -weight * 0.6
            return 0.0

        # 1w: smaller bands (5-15% spike is exceptional)
        score += bucket(r_1w, 0.01, 0.05, 0.15, 6) * 4
        # 1m
        score += bucket(r_1m, 0.03, 0.10, 0.30, 6) * 4
        # 3m
        score += bucket(r_3m, 0.05, 0.15, 0.50, 6) * 4
        # 12-1
        score += bucket(r_12_1, 0.10, 0.30, 1.00, 6) * 4

        # Consistency bonus / penalty: same-sign across at least 3/4 horizons
        signs = [1 if s > 0 else (-1 if s < 0 else 0) for s in valid]
        pos = sum(1 for s in signs if s > 0)
        neg = sum(1 for s in signs if s < 0)
        aligned = max(pos, neg)
        if aligned >= p.consistency_min:
            bias = 1 if pos > neg else -1
            score += bias * 10
            details["aligned"] = f"{aligned}/{len(valid)} 同向"
            details["bias"] = "bullish" if bias > 0 else "bearish"

        # Sharpe boost
        if sharpe >= 1.5:
            score += 10
            details["high_sharpe"] = True
        elif sharpe >= 0.8:
            score += 5
        elif sharpe <= -0.8:
            score -= 8

        # Idiosyncratic strength: drawdown from 60-day high
        if len(close) >= p.long_days:
            window = close.tail(p.long_days)
            dd = float(close.iloc[-1] / window.max() - 1.0) if window.max() > 0 else 0.0
            details["drawdown_60d"] = round(dd, 4)
            if dd >= -0.05:
                score += 5      # near 60d high
            elif dd <= -0.20:
                score -= 5      # well off

        score = max(0.0, min(100.0, score))
        signal = self._bullish(score, threshold=58)
        triggered = score >= 65 and aligned >= p.consistency_min
        return ScoreResult(
            score=score, signal=signal, details=details,
            factors={"r_12_1": r_12_1 or 0, "sharpe": sharpe},
            triggered=triggered,
        )
