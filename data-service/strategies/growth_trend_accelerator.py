# -*- coding: utf-8 -*-
"""Growth + trend accelerator.

This is the portfolio's return-seeking sleeve: prefer companies with
accelerating earnings/revenue while price confirms with an intact trend. It is
less defensive than quality/low-volatility and should help the app stop selling
every winner too early.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class GrowthTrendAcceleratorParams(Params):
    min_profit_yoy: float = 20.0
    min_revenue_yoy: float = 10.0
    momentum_days: int = 63
    max_3m_return: float = 0.80


class GrowthTrendAccelerator(AbstractStrategy):
    id = "growth_trend_accelerator"
    name = "成长趋势加速"
    default_weight = 0.09
    Params = GrowthTrendAcceleratorParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.momentum_days + 20:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = pd.to_numeric(df["收盘"], errors="coerce").reset_index(drop=True)
        volume = pd.to_numeric(df["成交量"], errors="coerce").reset_index(drop=True)
        last = float(close.iloc[-1])
        base = float(close.iloc[-1 - p.momentum_days])
        mom_3m = last / base - 1.0 if base > 0 else 0.0
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma60 = float(close.rolling(60).mean().iloc[-1])
        v10 = float(volume.tail(10).mean())
        v60 = float(volume.tail(60).mean())

        profit_yoy = 0.0
        revenue_yoy = 0.0
        roe = 0.0
        if ctx.fundamental_df is not None and not ctx.fundamental_df.empty:
            fdf = ctx.fundamental_df.sort_values("report_date", ascending=False)
            cur = fdf.iloc[0]
            profit_yoy = _num(cur.get("net_profit_yoy"))
            revenue_yoy = _num(cur.get("revenue_yoy"))
            roe = _num(cur.get("roe"))

        score = 35.0
        details = {
            "net_profit_yoy": round(profit_yoy, 2),
            "revenue_yoy": round(revenue_yoy, 2),
            "roe": round(roe, 2),
            "momentum_3m": round(mom_3m, 4),
            "above_ma20_ma60": last > ma20 > ma60,
            "volume_ratio_10_60": round(v10 / v60, 2) if v60 > 0 else None,
        }

        if profit_yoy >= 50:
            score += 24
            details["profit_accelerating"] = True
        elif profit_yoy >= p.min_profit_yoy:
            score += 16
        elif profit_yoy < 0:
            score -= 18

        if revenue_yoy >= 25:
            score += 16
            details["revenue_accelerating"] = True
        elif revenue_yoy >= p.min_revenue_yoy:
            score += 10

        if roe >= 15:
            score += 10
        elif roe >= 8:
            score += 5

        if 0.08 <= mom_3m <= p.max_3m_return:
            score += 20
            details["trend_confirmed"] = True
        elif mom_3m > p.max_3m_return:
            score -= 10
            details["too_extended"] = True
        elif mom_3m < -0.08:
            score -= 12

        if last > ma20 > ma60:
            score += 10
        if v60 > 0 and v10 > 1.25 * v60 and mom_3m > 0:
            score += 8
            details["volume_expansion"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score,
            signal=self._bullish(score, threshold=60),
            details=details,
            factors={"profit_yoy": profit_yoy, "revenue_yoy": revenue_yoy, "momentum_3m": mom_3m},
            triggered=score >= 68,
        )


def _num(v) -> float:
    try:
        return float(v) if pd.notna(v) else 0.0
    except Exception:
        return 0.0
