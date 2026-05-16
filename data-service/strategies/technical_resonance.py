# -*- coding: utf-8 -*-
"""Technical Resonance — MACD + price/volume + short-term northbound confirmation.

Short-term timing layer. Combines the strongest signal from the original
`macd_ma` (which we keep) with a recent 5-day northbound net-buy confirmation
to filter out technical setups without flow support.
"""
from __future__ import annotations

import pandas as pd

from indicators import calc_macd
from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class TechnicalResonanceParams(Params):
    golden_cross_lookback: int = 5
    volume_surge_factor: float = 1.5


class TechnicalResonance(AbstractStrategy):
    id = "technical_resonance"
    name = "技术共振 (MACD+量价+北向)"
    default_weight = 0.10
    Params = TechnicalResonanceParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        if df is None or len(df) < 30:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float)
        volume = df["成交量"].astype(float)
        dif, dea, hist = calc_macd(close)

        score = 0.0
        details: dict = {}

        # MACD golden cross within window
        for i in range(-self.params.golden_cross_lookback, 0):
            if i - 1 < -len(dif):
                continue
            if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
                score += 30
                details["macd_golden_cross"] = True
                break

        # Histogram turning positive
        if len(hist) >= 2 and hist.iloc[-1] > 0 and hist.iloc[-2] <= 0:
            score += 15
            details["hist_positive"] = True

        # Price stack
        ma5 = close.rolling(5).mean().iloc[-1]
        ma20 = close.rolling(20).mean().iloc[-1]
        ma60 = close.rolling(60).mean().iloc[-1]
        if pd.notna(ma20) and close.iloc[-1] > ma20: score += 10
        if pd.notna(ma60) and pd.notna(ma20) and ma20 > ma60: score += 10
        if pd.notna(ma5) and pd.notna(ma20) and ma5 > ma20: score += 5

        # Volume surge
        if len(volume) >= 20:
            avg = volume.tail(20).mean()
            if volume.iloc[-1] >= self.params.volume_surge_factor * avg:
                score += 15
                details["volume_surge"] = True

        # Northbound 5-day confirmation
        nb = ctx.northbound_df
        if nb is not None and not nb.empty and "hold_shares" in nb.columns:
            try:
                nb_sorted = nb.sort_values("trade_date", ascending=False).reset_index(drop=True)
                if len(nb_sorted) >= 6:
                    cur = float(nb_sorted["hold_shares"].iloc[0] or 0)
                    old = float(nb_sorted["hold_shares"].iloc[5] or 0)
                    if cur > old:
                        score += 15
                        details["nb_accumulating"] = True
            except Exception:
                pass

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=55),
            details=details,
            factors={"close": float(close.iloc[-1])},
            triggered=score >= 55,
        )
