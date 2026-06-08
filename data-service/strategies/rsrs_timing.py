# -*- coding: utf-8 -*-
"""RSRS timing signal.

RSRS (Resistance Support Relative Strength) regresses high prices on low
prices over a short window, then standardizes the slope over a longer lookback.
It is useful as a timing filter: strong positive standardized slope means
resistance is being lifted; strong negative slope means support is weakening.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class RsrsTimingParams(Params):
    window_days: int = 18
    zscore_days: int = 110
    bullish_z: float = 0.7
    bearish_z: float = -0.7


class RsrsTiming(AbstractStrategy):
    id = "rsrs_timing"
    name = "RSRS支撑阻力强度"
    default_weight = 0.06
    Params = RsrsTimingParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        need = p.window_days + p.zscore_days + 5
        if df is None or len(df) < need:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        high = pd.to_numeric(df["最高"], errors="coerce").reset_index(drop=True)
        low = pd.to_numeric(df["最低"], errors="coerce").reset_index(drop=True)
        close = pd.to_numeric(df["收盘"], errors="coerce").reset_index(drop=True)

        slopes: list[float] = []
        r2s: list[float] = []
        for i in range(p.window_days, len(df) + 1):
            x = low.iloc[i - p.window_days:i].to_numpy(dtype=float)
            y = high.iloc[i - p.window_days:i].to_numpy(dtype=float)
            if np.isnan(x).any() or np.isnan(y).any() or np.std(x) == 0:
                slopes.append(np.nan)
                r2s.append(0.0)
                continue
            beta, alpha = np.polyfit(x, y, 1)
            fitted = alpha + beta * x
            ss_res = float(np.sum((y - fitted) ** 2))
            ss_tot = float(np.sum((y - y.mean()) ** 2))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            slopes.append(float(beta))
            r2s.append(max(0.0, min(1.0, r2)))

        slope_series = pd.Series(slopes).dropna()
        if len(slope_series) < p.zscore_days:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        recent = slope_series.tail(p.zscore_days)
        mean = float(recent.mean())
        std = float(recent.std())
        last_slope = float(slope_series.iloc[-1])
        z = (last_slope - mean) / std if std > 0 else 0.0
        r2 = float(r2s[-1]) if r2s else 0.0
        adjusted = z * r2

        ma20 = float(close.rolling(20).mean().iloc[-1])
        last = float(close.iloc[-1])
        score = 50.0 + adjusted * 22.0
        if adjusted >= p.bullish_z:
            score += 12
        elif adjusted <= p.bearish_z:
            score -= 12
        if last >= ma20:
            score += 6
        else:
            score -= 6

        score = max(0.0, min(100.0, score))
        details = {
            "slope": round(last_slope, 4),
            "zscore": round(z, 3),
            "r2": round(r2, 3),
            "adjusted_rsrs": round(adjusted, 3),
            "above_ma20": last >= ma20,
            "breakout_quality": adjusted >= p.bullish_z,
            "support_weakening": adjusted <= p.bearish_z,
        }
        return ScoreResult(
            score=score,
            signal=self._bullish(score, threshold=58),
            details=details,
            factors={"adjusted_rsrs": adjusted, "slope": last_slope},
            triggered=adjusted >= p.bullish_z or adjusted <= p.bearish_z,
        )
