# -*- coding: utf-8 -*-
"""Accruals Anomaly (Sloan 1996).

"Do Stock Prices Fully Reflect Information in Accruals and Cash Flows?"
documents that earnings driven by cash (low accruals) persist, while earnings
inflated by accruals reverse. We score:
  Accruals = (NI - OCF) / TotalAssets
High accruals (>10% of assets) → low quality earnings → penalise.
Low / negative accruals → cash-driven → reward.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class AccrualsQualityParams(Params):
    high_accrual_threshold: float = 0.10
    low_accrual_threshold: float = 0.02


class AccrualsQuality(AbstractStrategy):
    id = "accruals_quality"
    name = "应计利润质量"
    default_weight = 0.06
    Params = AccrualsQualityParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.fundamental_df
        if df is None or df.empty:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})

        df = df.sort_values("report_date", ascending=False).reset_index(drop=True)
        cur = df.iloc[0]

        def f(v):
            try:
                return float(v) if pd.notna(v) else None
            except Exception:
                return None

        # The pipeline stores per-share OCF (元/股) in `op_cashflow` and per-share
        # earnings in `eps`. Sloan's accruals ratio = (NI - OCF) / Assets, but
        # without total_assets we use the per-share equivalent:
        #   accruals_per_share = EPS - per_share_OCF
        #   accruals_ratio     = accruals_per_share / BVPS
        eps = f(cur.get("eps"))
        ocf_ps = f(cur.get("op_cashflow"))
        bvps = f(cur.get("bvps"))

        if eps is None or ocf_ps is None or not bvps or bvps <= 0:
            return ScoreResult(score=0, signal="neutral",
                               details={"no_data": True, "missing": [
                                   k for k, v in {"eps": eps, "op_cashflow": ocf_ps,
                                                  "bvps": bvps}.items() if v in (None, 0)]})

        accruals = (eps - ocf_ps) / bvps
        p = self.params
        score = 50.0
        details = {"accruals_ratio": round(accruals, 4),
                   "eps": eps, "ocf_ps": ocf_ps, "bvps": bvps}

        if accruals <= 0:
            score = 80 + min(15, abs(accruals) * 100)
            details["cash_driven"] = True
        elif accruals <= p.low_accrual_threshold:
            score = 70
        elif accruals <= p.high_accrual_threshold:
            score = 45
        else:
            score = max(20, 45 - (accruals - p.high_accrual_threshold) * 200)
            details["high_accrual_warning"] = True

        # OCF / EPS cash conversion
        if eps and eps > 0:
            cash_conv = ocf_ps / eps
            details["cash_conversion"] = round(cash_conv, 2)
            if cash_conv >= 1.0:
                score = min(100.0, score + 10)
            elif cash_conv < 0.3:
                score = max(0.0, score - 10)

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=60),
            details=details, factors={"accruals": accruals},
            triggered=score >= 70,
        )
