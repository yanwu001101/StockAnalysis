# -*- coding: utf-8 -*-
"""股东户数 repo."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_shareholder"
COLS = ["code", "report_date", "holder_count", "top10_ratio", "institution_ratio"]


def upsert_shareholder(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    cols = [c for c in COLS if c in df.columns]
    if not {"code", "report_date"}.issubset(cols):
        return 0
    df = df.dropna(subset=["code", "report_date"])
    return upsert(TABLE, df, cols, update_columns=[c for c in cols if c not in ("code", "report_date")],
                  preserve_non_null=True)


