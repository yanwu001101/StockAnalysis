# -*- coding: utf-8 -*-
"""分红送转 repo."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_dividend"
COLS = ["code", "ann_date", "ex_date", "cash_per_10", "share_per_10", "transfer_per_10"]


def upsert_dividend(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    cols = [c for c in COLS if c in df.columns]
    if not {"code", "ann_date"}.issubset(cols):
        return 0
    df = df.dropna(subset=["code", "ann_date"])
    return upsert(TABLE, df, cols, update_columns=[c for c in cols if c not in ("code", "ann_date")],
                  preserve_non_null=True)


