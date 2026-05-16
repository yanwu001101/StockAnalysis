# -*- coding: utf-8 -*-
"""Quality Factor (MSCI Quality style + A-share adaptations).

Combines stable high ROE, clean accruals (OCF >= NI), low leverage, and
gross-margin durability. This is the modern replacement of the original
`multi_factor` strategy — uses the same data, smarter weighting.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class QualityParams(Params):
    min_roe: float = 12.0
    max_debt_ratio: float = 60.0


class QualityFactor(AbstractStrategy):
    id = "quality_factor"
    name = "Quality Factor"
    default_weight = 0.18
    Params = QualityParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.fundamental_df
        if df is None or df.empty:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})
        df = df.sort_values("report_date", ascending=False).reset_index(drop=True)

        def f(v):
            try:
                return float(v) if pd.notna(v) else 0.0
            except Exception:
                return 0.0

        score = 0.0
        details: dict = {}

        # ROE level + stability (last up-to-8 periods)
        roes = [f(r.get("roe")) for _, r in df.iterrows()][:8]
        roe_mean = sum(roes) / len(roes) if roes else 0.0
        if roe_mean >= 20: score += 25
        elif roe_mean >= 15: score += 20
        elif roe_mean >= 10: score += 12
        elif roe_mean >= 5: score += 6
        details["roe_mean"] = round(roe_mean, 2)

        if len(roes) >= 4 and all(r >= self.params.min_roe / 2 for r in roes[:4]):
            score += 10
            details["roe_stable"] = True

        # Earnings backed by cash (avg OCF/NI over last 4 periods >= 0.8)
        recent = df.head(4)
        if len(recent) >= 1:
            ratios = []
            for _, r in recent.iterrows():
                ocf, ni = f(r.get("op_cashflow")), f(r.get("net_profit"))
                if ni > 0:
                    ratios.append(ocf / ni)
            if ratios:
                avg = sum(ratios) / len(ratios)
                if avg >= 1.0: score += 15
                elif avg >= 0.7: score += 10
                elif avg >= 0.4: score += 5
                details["ocf_ni_ratio"] = round(avg, 2)

        # Leverage
        cur_debt = f(df.iloc[0].get("debt_ratio"))
        if cur_debt <= 30: score += 15
        elif cur_debt <= 45: score += 10
        elif cur_debt <= self.params.max_debt_ratio: score += 5
        details["debt_ratio"] = cur_debt

        # Gross margin
        gm = f(df.iloc[0].get("gross_margin"))
        if gm >= 50: score += 10
        elif gm >= 35: score += 7
        elif gm >= 20: score += 3
        details["gross_margin"] = gm

        # Revenue growth
        rg = f(df.iloc[0].get("revenue_yoy"))
        if rg >= 20: score += 10
        elif rg >= 8: score += 6
        elif rg < -10: score -= 5
        details["revenue_yoy"] = rg

        # Market-cap discount (small bias toward mid/large, away from <50 亿)
        cap = ctx.market_cap_yi
        if cap >= 500: score += 10
        elif cap >= 200: score += 6
        elif cap < 50: score -= 5
        details["market_cap_yi"] = cap

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score),
            details=details, factors={"roe_mean": roe_mean, "debt_ratio": cur_debt},
            triggered=score >= 60,
        )
