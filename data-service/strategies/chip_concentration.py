# -*- coding: utf-8 -*-
"""Chip Concentration — proxy for shareholder cost-basis clustering.

When the bulk of trading volume in the recent window happened in a narrow
price band, the float is tightly held at known cost. When price then sits
just above that band on rising volume, it strongly suggests the institutions
that built the position are now in profit and have committed capital to defend.
This is a classic A-share retail/private-fund signal.

We estimate the cost band via a volume-weighted lookback of typical prices
(VWAP-ish), measure the dispersion (band width / mean), and award score
when the band is narrow AND current price is above it AND on healthy volume.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class ChipConcentrationParams(Params):
    lookback_days: int = 60
    tight_band_pct: float = 0.10
    very_tight_pct: float = 0.06


class ChipConcentration(AbstractStrategy):
    id = "chip_concentration"
    name = "筹码集中度"
    default_weight = 0.05
    Params = ChipConcentrationParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.lookback_days:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        recent = df.tail(p.lookback_days)
        close = recent["收盘"].astype(float)
        high = recent["最高"].astype(float)
        low = recent["最低"].astype(float)
        volume = recent["成交量"].astype(float)

        typical = (high + low + close) / 3.0
        total_v = float(volume.sum())
        if total_v <= 0:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})

        vwap = float((typical * volume).sum() / total_v)
        # Estimate cost dispersion via volume-weighted MAD around VWAP
        mad = float(((typical - vwap).abs() * volume).sum() / total_v)
        band_width = (mad / vwap) if vwap > 0 else 1.0

        last = float(close.iloc[-1])
        price_pos = last / vwap if vwap > 0 else 1.0

        score = 0.0
        details = {
            "vwap": round(vwap, 2),
            "band_width": round(band_width, 4),
            "price_pos": round(price_pos, 3),
        }

        # Tighter band = higher concentration
        if band_width <= p.very_tight_pct:
            score += 50
            details["very_concentrated"] = True
        elif band_width <= p.tight_band_pct:
            score += 35
            details["concentrated"] = True
        elif band_width <= 0.15:
            score += 15

        # Position above the cost band = institutions in profit
        if 1.0 <= price_pos <= 1.10:
            score += 30
            details["above_cost"] = True
        elif 1.10 < price_pos <= 1.25:
            score += 15
            details["well_above_cost"] = True
        elif price_pos < 0.95:
            score = max(score - 15, 5)
            details["below_cost_warning"] = True

        # Volume confirmation: recent 5d volume above the lookback avg
        avg_v = float(volume.mean())
        last5_v = float(volume.tail(5).mean())
        if avg_v > 0 and last5_v > avg_v * 1.1:
            score += 15
            details["volume_engaging"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details=details,
            factors={"chip_band_width": band_width, "price_pos": price_pos},
            triggered=score >= 60 and band_width <= p.tight_band_pct and price_pos >= 1.0,
        )
