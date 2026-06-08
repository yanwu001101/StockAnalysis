# -*- coding: utf-8 -*-
"""A-share short-term reversal with growth anchor.

China A-share studies often find short-horizon momentum/reversal is unstable,
while refined reversal signals work better when the loser is not fundamentally
broken. This strategy rewards controlled pullbacks with still-positive quality
or growth context, and penalizes overheated short-term spikes.
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class AShareShortReversalParams(Params):
    window_days: int = 10
    oversold_return: float = -0.08
    overheat_return: float = 0.15
    min_growth: float = 0.0
    min_roe: float = 8.0


class AShareShortReversal(AbstractStrategy):
    id = "ashare_short_reversal"
    name = "A股短期反转"
    default_weight = 0.07
    Params = AShareShortReversalParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.daily_df
        p = self.params
        if df is None or len(df) < p.window_days + 25:
            return ScoreResult(score=0, signal="neutral", details={"insufficient_data": True})

        close = df["收盘"].astype(float).reset_index(drop=True)
        volume = df["成交量"].astype(float).reset_index(drop=True)
        last = float(close.iloc[-1])
        base = float(close.iloc[-1 - p.window_days])
        if base <= 0:
            return ScoreResult(score=0, signal="neutral", details={"no_data": True})

        ret = last / base - 1.0
        ma20 = float(close.rolling(20).mean().iloc[-1])
        v5 = float(volume.tail(5).mean())
        v20 = float(volume.tail(25).head(20).mean()) if len(volume) >= 25 else v5

        growth = 0.0
        roe = 0.0
        if ctx.fundamental_df is not None and not ctx.fundamental_df.empty:
            cur = ctx.fundamental_df.sort_values("report_date", ascending=False).iloc[0]
            growth = _float(cur.get("net_profit_yoy"))
            roe = _float(cur.get("roe"))

        quality_anchor = growth >= p.min_growth or roe >= p.min_roe
        details = {
            "ret_10d": round(ret, 4),
            "above_ma20": last >= ma20 if ma20 > 0 else False,
            "volume_ratio": round(v5 / v20, 2) if v20 > 0 else None,
            "net_profit_yoy": round(growth, 2),
            "roe": round(roe, 2),
            "quality_anchor": quality_anchor,
        }

        score = 50.0
        if ret <= p.oversold_return and quality_anchor:
            score += 28
            details["controlled_pullback"] = True
        elif ret <= p.oversold_return:
            score += 10
            details["weak_rebound_only"] = True
        elif ret >= p.overheat_return:
            score -= 30
            details["overheated_warning"] = True
        elif ret >= 0.08:
            score -= 12

        if last >= ma20:
            score += 10
        elif ret < 0:
            score -= 8

        if v20 > 0 and v5 < 0.75 * v20 and ret < 0:
            score += 8
            details["sell_pressure_dryup"] = True
        if v20 > 0 and v5 > 1.8 * v20 and ret > 0.08:
            score -= 10
            details["chase_volume_warning"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score,
            signal=self._bullish(score, threshold=60),
            details=details,
            factors={"ret_10d": ret, "growth": growth, "roe": roe},
            triggered=score >= 65,
        )


def _float(v) -> float:
    try:
        return float(v) if pd.notna(v) else 0.0
    except Exception:
        return 0.0
