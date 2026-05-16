# -*- coding: utf-8 -*-
"""Money-flow repo (主力 / 超大 / 大 / 中 / 小单净额)."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_moneyflow"
COLS = ["code", "trade_date", "super_large_net", "large_net",
        "medium_net", "small_net", "main_net"]


def upsert_moneyflow(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return upsert(TABLE, df, COLS, update_columns=COLS[2:])


def get_moneyflow(code: str, days: int = 60) -> pd.DataFrame:
    return fetch_df(
        f"SELECT * FROM {TABLE} WHERE code=:c "
        f"ORDER BY trade_date DESC LIMIT :n",
        {"c": code, "n": days},
    )
