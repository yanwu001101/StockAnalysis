# -*- coding: utf-8 -*-
"""Sector / Concept Rotation (Moskowitz-Grinblatt style).

Award higher score when the stock's industry / leading concept sits in the top
20% of recent (20-day) relative strength rankings. The runner is responsible
for computing sector_rank and injecting it into the context.
"""
from __future__ import annotations

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class SectorRotationParams(Params):
    top_pct: float = 0.20    # top quintile -> bullish
    bottom_pct: float = 0.80


class SectorRotation(AbstractStrategy):
    id = "sector_rotation"
    name = "行业动量轮动"
    default_weight = 0.08
    Params = SectorRotationParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        if ctx.sector_rank is None:
            return ScoreResult(score=20, signal="neutral", details={"no_rank": True})
        r = ctx.sector_rank
        score = 0.0
        details = {"sector_rank": r, "sector_rank_n": ctx.sector_rank_n}
        if r <= self.params.top_pct: score += 70
        elif r <= 0.4: score += 45
        elif r >= self.params.bottom_pct: score -= 10
        else: score += 25

        # Daily df: stock outperforming its sector recently
        daily = ctx.daily_df
        if daily is not None and len(daily) >= 21:
            close = daily["收盘"].astype(float)
            r20 = float((close.iloc[-1] / close.iloc[-21]) - 1.0)
            details["ret_20d"] = round(r20, 4)
            if r20 > 0.10: score += 20
            elif r20 > 0.05: score += 12

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=55),
            details=details, factors={"sector_rank": r},
            triggered=score >= 55 and r <= self.params.top_pct,
        )
