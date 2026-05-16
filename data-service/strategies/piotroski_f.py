# -*- coding: utf-8 -*-
"""Piotroski F-Score (Piotroski 2000).

9 binary signals across profitability, leverage/liquidity, and operating
efficiency. Each scores 1 if pass, 0 if fail. Total 0-9 mapped to 0-100.
Historically the long-high / short-low F-Score portfolio earned ~7.5% annual
abnormal return on high-book-to-market stocks.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class PiotroskiFParams(Params):
    bullish_threshold: int = 7      # F-score >= 7 -> bullish
    bearish_threshold: int = 3


class PiotroskiF(AbstractStrategy):
    id = "piotroski_f"
    name = "Piotroski F-Score"
    default_weight = 0.12
    Params = PiotroskiFParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.fundamental_df
        if df is None or len(df) < 2:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})
        df = df.sort_values("report_date", ascending=False).reset_index(drop=True)
        cur, prev = df.iloc[0], df.iloc[1]

        def f(v):
            try:
                return float(v) if pd.notna(v) else 0.0
            except Exception:
                return 0.0

        signals = {}
        # --- Profitability (4) ---
        signals["positive_ni"] = 1 if f(cur.get("net_profit")) > 0 else 0
        signals["positive_ocf"] = 1 if f(cur.get("op_cashflow")) > 0 else 0
        # ROE growth
        signals["roe_growth"] = 1 if f(cur.get("roe")) > f(prev.get("roe")) else 0
        # Accrual: OCF > NI (cash earnings backed by cash)
        signals["accrual"] = 1 if f(cur.get("op_cashflow")) > f(cur.get("net_profit")) else 0

        # --- Leverage / liquidity (3) ---
        signals["leverage_down"] = 1 if f(cur.get("debt_ratio")) < f(prev.get("debt_ratio")) else 0
        signals["liquidity_up"] = 1 if f(cur.get("current_ratio")) > f(prev.get("current_ratio")) else 0
        # No equity issuance proxy: net_assets per share rising
        signals["no_dilution"] = 1 if f(cur.get("bvps")) >= f(prev.get("bvps")) else 0

        # --- Operating efficiency (2) ---
        signals["gross_margin_up"] = 1 if f(cur.get("gross_margin")) > f(prev.get("gross_margin")) else 0
        # Asset turnover: revenue / total_assets
        cur_at = f(cur.get("revenue")) / (f(cur.get("total_assets")) or 1)
        prev_at = f(prev.get("revenue")) / (f(prev.get("total_assets")) or 1)
        signals["asset_turnover_up"] = 1 if cur_at > prev_at else 0

        f_score = sum(signals.values())
        score = (f_score / 9) * 100
        signal = "bullish" if f_score >= self.params.bullish_threshold else \
                 "bearish" if f_score <= self.params.bearish_threshold else "neutral"
        return ScoreResult(
            score=score, signal=signal,
            details={"f_score": f_score, **signals},
            factors={"roe": f(cur.get("roe")), "debt_ratio": f(cur.get("debt_ratio"))},
            triggered=f_score >= self.params.bullish_threshold,
        )
