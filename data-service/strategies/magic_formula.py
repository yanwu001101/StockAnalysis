# -*- coding: utf-8 -*-
"""Magic Formula (Joel Greenblatt, "The Little Book That Beats the Market").

Rank stocks by:
  * Return on Capital  = EBIT / (Net Working Capital + Net Fixed Assets)
  * Earnings Yield     = EBIT / Enterprise Value

Combine the two ranks. Lower combined rank is better. We translate the rank
into a 0-100 score so it fits the framework — the actual production usage
should be cross-sectional ranking, which the runner can do over the result.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class MagicFormulaParams(Params):
    # Minimum EBIT (in CNY) to filter out tiny / unprofitable firms
    min_ebit: float = 1e8


class MagicFormula(AbstractStrategy):
    id = "magic_formula"
    name = "Magic Formula"
    default_weight = 0.10
    Params = MagicFormulaParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.fundamental_df
        if df is None or df.empty:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})
        cur = df.sort_values("report_date", ascending=False).iloc[0]

        def f(v):
            try:
                return float(v) if pd.notna(v) else 0.0
            except Exception:
                return 0.0

        net_profit = f(cur.get("net_profit"))
        # A-share fundamentals don't always expose EBIT; approximate it as
        # net_profit / (1 - typical tax rate 0.25) for ranking continuity
        ebit = f(cur.get("ebit")) or (net_profit / 0.75 if net_profit > 0 else 0.0)
        if ebit < self.params.min_ebit:
            return ScoreResult(score=0, signal="neutral",
                               details={"ebit_too_small": True, "ebit": ebit})

        net_working_capital = f(cur.get("current_assets")) - f(cur.get("current_liab"))
        net_fixed_assets = f(cur.get("fixed_assets"))
        invested_capital = max(net_working_capital + net_fixed_assets, 1.0)
        roc = ebit / invested_capital

        # Enterprise Value ≈ market_cap (亿) * 1e8 + total_liab - cash_approx (skipped)
        ev_yi = ctx.market_cap_yi
        ev = max(ev_yi * 1e8 + f(cur.get("total_liab")), 1.0)
        earnings_yield = ebit / ev

        # Map both onto [0, 50] so total = [0, 100]
        roc_score = min(50, max(0, roc * 100))          # ROC of 50%+ -> max
        ey_score = min(50, max(0, earnings_yield * 250))  # EY of 20%+ -> max

        score = roc_score + ey_score
        return ScoreResult(
            score=score, signal=self._bullish(score),
            details={"roc": round(roc, 4), "earnings_yield": round(earnings_yield, 4)},
            factors={"ebit": ebit, "invested_capital": invested_capital, "ev": ev},
            triggered=score >= 60,
        )
