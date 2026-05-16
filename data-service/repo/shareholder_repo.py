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
    return upsert(TABLE, df, COLS, update_columns=COLS[2:])


def get_shareholder(code: str, periods: int = 12) -> pd.DataFrame:
    return fetch_df(
        f"SELECT * FROM {TABLE} WHERE code=:c "
        f"ORDER BY report_date DESC LIMIT :n",
        {"c": code, "n": periods},
    )
