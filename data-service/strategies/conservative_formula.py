# -*- coding: utf-8 -*-
"""Conservative Formula inspired by van Vliet & Blitz.

The practical idea is simple: prefer stocks with low realized volatility,
positive momentum, and decent shareholder yield / quality proxies. In this
A-share implementation we use fields already available in the project:
low 60d volatility, positive 3m trend, stable ROE, cash conversion, and
not-too-high leverage.
"""
from __future__ import annotations

import math

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class ConservativeFormulaParams(Params):
    vol_days: int = 60
    momentum_days: int = 63
    max_debt_ratio: float = 65.0
    min_roe: float = 8.0


class ConservativeFormula(AbstractStrategy):
    id = "conservative_formula"
    name = "保守公式"
    default_weight = 0.08
    Params = ConservativeFormulaParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < max(p.vol_days, p.momentum_days) + 5:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float).reset_index(drop=True)
        rets = close.pct_change().dropna().tail(p.vol_days)
        vol = float(rets.std() * math.sqrt(252)) if not rets.empty else 1.0
        last = float(close.iloc[-1])
        prev = float(close.iloc[-1 - p.momentum_days])
        momentum = last / prev - 1.0 if prev > 0 else 0.0

        roe = 0.0
        debt = 100.0
        cash_conversion = 0.0
        if ctx.fundamental_df is not None and not ctx.fundamental_df.empty:
            fdf = ctx.fundamental_df.sort_values("report_date", ascending=False)
            cur = fdf.iloc[0]
            roe = _float(cur.get("roe"))
            debt = _float(cur.get("debt_ratio"), 100.0)
            eps = _float(cur.get("eps"))
            ocf = _float(cur.get("op_cashflow"))
            if eps > 0:
                cash_conversion = ocf / eps

        score = 0.0
        details = {
            "vol_60d_ann": round(vol, 4),
            "momentum_3m": round(momentum, 4),
            "roe": round(roe, 2),
            "debt_ratio": round(debt, 2),
            "cash_conversion": round(cash_conversion, 2),
        }

        if vol <= 0.22:
            score += 30
            details["low_vol"] = True
        elif vol <= 0.35:
            score += 20
        elif vol >= 0.60:
            score -= 10

        if momentum >= 0.12:
            score += 25
            details["trend_ok"] = True
        elif momentum >= 0.03:
            score += 15
        elif momentum <= -0.12:
            score -= 15

        if roe >= 18:
            score += 20
        elif roe >= p.min_roe:
            score += 12
        elif roe < 0:
            score -= 15

        if debt <= 35:
            score += 12
        elif debt <= p.max_debt_ratio:
            score += 6
        else:
            score -= 10

        if cash_conversion >= 1.0:
            score += 13
            details["cash_backed"] = True
        elif cash_conversion > 0.5:
            score += 6
        elif cash_conversion < 0 and roe > 0:
            score -= 8

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score,
            signal=self._bullish(score, threshold=60),
            details=details,
            factors={"vol": vol, "momentum": momentum, "roe": roe},
            triggered=score >= 65,
        )


def _float(v, fallback: float = 0.0) -> float:
    try:
        return float(v) if pd.notna(v) else fallback
    except Exception:
        return fallback
