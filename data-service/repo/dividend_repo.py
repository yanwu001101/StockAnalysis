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
    return upsert(TABLE, df, COLS, update_columns=COLS[2:])


def get_dividend(code: str, years: int = 10) -> pd.DataFrame:
    return fetch_df(
        f"SELECT * FROM {TABLE} WHERE code=:c "
        f"AND ann_date >= (CURDATE() - INTERVAL :y YEAR) "
        f"ORDER BY ann_date DESC",
        {"c": code, "y": years},
    )


def get_yield_universe() -> pd.DataFrame:
    """Per-code: trailing 12-month total cash per share, count of years paying."""
    return fetch_df(
        "SELECT code, "
        "  SUM(CASE WHEN ann_date >= (CURDATE() - INTERVAL 1 YEAR) THEN cash_per_10/10 ELSE 0 END) AS cash_ttm, "
        "  COUNT(DISTINCT YEAR(ann_date)) AS pay_years "
        "FROM stock_dividend WHERE cash_per_10 > 0 GROUP BY code"
    )
