# -*- coding: utf-8 -*-
"""Fundamentals repo — quarterly / annual income+balance+cashflow merged view."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_fundamental"
COLS = [
    "code", "report_date", "period_type",
    "revenue", "net_profit", "op_cashflow", "ebit",
    "total_assets", "total_liab", "total_equity",
    "current_assets", "current_liab", "fixed_assets",
    "roe", "gross_margin", "debt_ratio",
    "ann_date", "current_ratio",
    "revenue_yoy", "net_profit_yoy", "eps", "bvps",
]


def upsert_fundamental(df: pd.DataFrame, columns: list[str] | None = None) -> int:
    """落库。

    `columns` 默认取 df 里真实存在的那些列——不把 COLS 全量写进去，是为了避免
    「一条只补了营收/净利的新链路」把另一条链路写过的 total_assets/current_assets
    等列覆写成 NULL（akshare 业绩报表本来就没有这些字段）。
    """
    if df is None or df.empty:
        return 0
    if "period_type" not in df.columns:
        df = df.copy()
        df["period_type"] = "Q"
    cols = columns or [c for c in COLS if c in df.columns]
    if "code" not in cols or "report_date" not in cols:
        return 0
    return upsert(TABLE, df, cols, update_columns=[c for c in cols[2:]])


