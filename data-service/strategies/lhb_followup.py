# -*- coding: utf-8 -*-
"""LHB (Dragon Tiger Board) institutional follow-up.

When 机构席位 (institutional seats) appear on the LHB with net BUY, the stock
often shows a 3-10 day positive drift. We score:
  * Institution seats present in the last `window`
  * Net buy magnitude
  * No 机构 selling on the other side
"""
from __future__ import annotations

import pandas as pd

from models import ScoreResult
from strategies.base import AbstractStrategy, Params, StrategyContext


class LhbFollowupParams(Params):
    window_days: int = 7
    strong_net: float = 50_000_000   # 5000 万 net = strong


class LhbFollowup(AbstractStrategy):
    id = "lhb_followup"
    name = "龙虎榜机构跟随"
    default_weight = 0.08
    Params = LhbFollowupParams

    def score(self, ctx: StrategyContext) -> ScoreResult:
        df = ctx.lhb_df
        if df is None or df.empty:
            return ScoreResult(score=0, signal="neutral", details={"no_lhb": True})
        df = df.copy()
        if "trade_date" in df:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce")
        df = df.sort_values("trade_date", ascending=False)
        df = df.head(self.params.window_days * 4)  # multiple seats per day

        def f(v):
            try:
                return float(v) if pd.notna(v) else 0.0
            except Exception:
                return 0.0

        # Prefer institutional-seat rows when seat_type is populated; otherwise
        # treat every LHB row as a tradable signal — the EM datacenter LHB
        # endpoint we backfill from doesn't return seat tags reliably, so the
        # whole-LHB fallback is what makes this strategy actually score in
        # production.
        has_seat_type = ("seat_type" in df.columns and
                         df["seat_type"].astype(str).str.strip().ne("").any())
        if has_seat_type:
            inst_rows = df[df["seat_type"].astype(str).str.contains("机构", na=False)]
            if inst_rows.empty:
                inst_rows = df
                tagged = False
            else:
                tagged = True
        else:
            inst_rows = df
            tagged = False

        net_sum = inst_rows["net_amount"].apply(f).sum() if "net_amount" in inst_rows else 0.0
        buy_sum = inst_rows["buy_amount"].apply(f).sum() if "buy_amount" in inst_rows else 0.0
        sell_sum = inst_rows["sell_amount"].apply(f).sum() if "sell_amount" in inst_rows else 0.0
        unique_days = inst_rows["trade_date"].dt.date.nunique() if "trade_date" in inst_rows else len(inst_rows)

        score = 0.0
        details = {
            "tagged_inst": tagged,
            "appearances": int(unique_days),
            "rows": int(len(inst_rows)),
            "net_sum": round(net_sum, 0),
            "buy_sum": round(buy_sum, 0),
            "sell_sum": round(sell_sum, 0),
        }

        # Frequency on LHB (per unique day)
        score += min(40, unique_days * 12)
        # Net flow magnitude
        if net_sum >= self.params.strong_net: score += 35
        elif net_sum >= self.params.strong_net / 2: score += 22
        elif net_sum > 0: score += 10
        elif net_sum < -self.params.strong_net / 2: score -= 25

        # Buy dominance ratio
        if buy_sum + sell_sum > 0:
            buy_ratio = buy_sum / (buy_sum + sell_sum)
            if buy_ratio >= 0.8: score += 25
            elif buy_ratio >= 0.6: score += 15
            details["buy_ratio"] = round(buy_ratio, 2)

        # Bonus if we actually identified tagged institutional seats
        if tagged:
            score += 10
            details["inst_seat_bonus"] = True

        score = max(0.0, min(100.0, score))
        return ScoreResult(
            score=score, signal=self._bullish(score, threshold=50),
            details=details, factors={"net_sum": net_sum},
            triggered=score >= 50,
        )
