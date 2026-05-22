# -*- coding: utf-8 -*-
"""Asset Growth Anomaly (Cooper, Gulen, Schill 2008).

"Asset Growth and the Cross-Section of Stock Returns" — firms that aggressively
grow their balance sheet (acquisitions, capex sprees, equity issues) tend to
underperform over the following year by ~10-20% relative to low-AG peers.
We compute YoY total-asset growth and reward modest organic growth (5-20%)
while penalising explosive expansion (>40%) and contraction (<-10%).
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class AssetGrowthParams(Params):
    healthy_low: float = 0.05
    healthy_high: float = 0.20
    explosive_threshold: float = 0.40


class AssetGrowth(AbstractStrategy):
    id = "asset_growth"
    name = "资产增长异象"
    default_weight = 0.05
    Params = AssetGrowthParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.fundamental_df
        if df is None or len(df) < 5:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})
        df = df.sort_values("report_date", ascending=False).reset_index(drop=True)

        def f(v):
            try:
                return float(v) if pd.notna(v) else None
            except Exception:
                return None

        # Pipeline doesn't store total_assets — proxy with per-share book value
        # (BVPS) growth YoY. Net new equity issuance + retained earnings drive
        # both, and over 4 quarters they track total-asset growth closely
        # enough for ranking purposes.
        cur = f(df.iloc[0].get("bvps"))
        prior = f(df.iloc[4].get("bvps")) if len(df) > 4 else f(df.iloc[-1].get("bvps"))
        if not cur or not prior or prior <= 0:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})

        ag = (cur / prior) - 1.0
        p = self.params
        details: dict = {"bvps_yoy": round(ag, 4), "cur_bvps": cur, "prior_bvps": prior}

        if ag < -0.10:
            score = 25
            details["contraction_warning"] = True
        elif ag < 0:
            score = 50
        elif ag <= p.healthy_low:
            score = 65
        elif ag <= p.healthy_high:
            score = 80
            details["healthy_growth"] = True
        elif ag <= p.explosive_threshold:
            score = 55
        else:
            score = max(15, 55 - (ag - p.explosive_threshold) * 100)
            details["explosive_warning"] = True

        # Confirmation: ROA holding up (high growth + ROA crash is the worst case)
        roe = f(df.iloc[0].get("roe"))
        if roe is not None:
            details["roe"] = round(roe, 4)
            if ag > p.explosive_threshold and roe < 0.05:
                score = max(score - 15, 10)
                details["growth_without_returns"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details=details, factors={"asset_growth": ag},
            triggered=p.healthy_low <= ag <= p.healthy_high and score >= 60,
        )
