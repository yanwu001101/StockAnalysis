# -*- coding: utf-8 -*-
"""Fund-flow / price divergence.

For A-share trading, price-only signals are often noisy. This strategy compares
recent price direction with main-fund flow: accumulation on pullback is a
watch/buy signal, while rising price with sustained outflow is a distribution
warning.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class FundPriceDivergenceParams(Params):
    window_days: int = 5
    strong_inflow: float = 50_000_000
    strong_outflow: float = -50_000_000


class FundPriceDivergence(AbstractStrategy):
    id = "fund_price_divergence"
    name = "资金价量背离"
    default_weight = 0.07
    Params = FundPriceDivergenceParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        price_df = ctx.daily_df
        flow_df = ctx.moneyflow_df
        p = self.params
        if price_df is None or flow_df is None or len(price_df) < p.window_days + 2 or flow_df.empty:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = price_df["收盘"].astype(float).reset_index(drop=True)
        last = float(close.iloc[-1])
        base = float(close.iloc[-1 - p.window_days])
        price_ret = last / base - 1.0 if base > 0 else 0.0

        mf = flow_df.sort_values("trade_date", ascending=False).head(p.window_days)
        main_sum = float(pd.to_numeric(mf.get("main_net"), errors="coerce").fillna(0).sum())
        super_sum = float(pd.to_numeric(mf.get("super_large_net"), errors="coerce").fillna(0).sum())
        large_sum = float(pd.to_numeric(mf.get("large_net"), errors="coerce").fillna(0).sum())

        details = {
            "price_ret_5d": round(price_ret, 4),
            "main_net_5d": round(main_sum, 2),
            "super_large_net_5d": round(super_sum, 2),
            "large_net_5d": round(large_sum, 2),
        }

        score = 50.0
        if price_ret < -0.03 and main_sum > p.strong_inflow:
            score += 30
            details["accumulation_on_pullback"] = True
        elif price_ret < 0 and main_sum > 0:
            score += 18
            details["mild_accumulation"] = True
        elif price_ret > 0.05 and main_sum < p.strong_outflow:
            score -= 32
            details["distribution_warning"] = True
        elif price_ret > 0 and main_sum < 0:
            score -= 15

        if super_sum + large_sum > p.strong_inflow:
            score += 12
            details["big_order_support"] = True
        elif super_sum + large_sum < p.strong_outflow:
            score -= 12
            details["big_order_exit"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score,
            signal=self._bullish(score, threshold=60),
            details=details,
            factors={"price_ret": price_ret, "main_net": main_sum},
            triggered=score >= 65 or score <= 30,
        )
