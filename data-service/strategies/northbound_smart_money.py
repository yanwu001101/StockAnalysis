# -*- coding: utf-8 -*-
"""Northbound Smart Money tracker.

Foreign institutional flows via Stock Connect (沪深股通) are widely treated as
"smart money" in A-share research. Score rewards stocks that show:
  * Net share accumulation over the last 5 / 10 / 20 days
  * Hold ratio rising (vs. 30 days ago)
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class NorthboundSmartMoneyParams(Params):
    short_window: int = 5
    mid_window: int = 10
    long_window: int = 20


class NorthboundSmartMoney(AbstractStrategy):
    id = "northbound_smart_money"
    name = "北向资金追踪"
    default_weight = 0.08
    Params = NorthboundSmartMoneyParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.northbound_df
        if df is None or df.empty:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})
        df = df.copy()
        if "trade_date" in df:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        df = df.sort_values("trade_date", ascending=False).reset_index(drop=True)

        def col_change(col: str, window: int) -> float:
            if col not in df.columns or len(df) < window + 1:
                return 0.0
            try:
                cur = float(df[col].iloc[0]) if pd.notna(df[col].iloc[0]) else 0.0
                old = float(df[col].iloc[window]) if pd.notna(df[col].iloc[window]) else 0.0
                return cur - old
            except Exception:
                return 0.0

        d_shares_5 = col_change("hold_shares", self.params.short_window)
        d_shares_10 = col_change("hold_shares", self.params.mid_window)
        d_shares_20 = col_change("hold_shares", self.params.long_window)
        d_ratio_20 = col_change("hold_ratio", self.params.long_window)

        score = 0.0
        details = {
            "d_shares_5": d_shares_5,
            "d_shares_10": d_shares_10,
            "d_shares_20": d_shares_20,
            "d_ratio_20": d_ratio_20,
        }
        if d_shares_5 > 0: score += 25
        if d_shares_10 > 0: score += 20
        if d_shares_20 > 0: score += 25
        if d_ratio_20 > 0: score += 20

        # Magnitude bonus: ratio rising > 0.5 pp in 20 days
        if d_ratio_20 >= 0.5: score += 10
        elif d_ratio_20 <= -0.5: score -= 15

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=50),
            details=details, factors={"d_ratio_20": d_ratio_20},
            triggered=score >= 50,
        )
