# -*- coding: utf-8 -*-
"""Minute-level K-line repo."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_kline_minute"
COLS = ["code", "dt", "period", "open", "close", "high", "low", "volume", "amount"]


def upsert_minute(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return upsert(TABLE, df, COLS, update_columns=COLS[3:])


def get_minute(code: str, period: str = "5min", limit: int = 240) -> pd.DataFrame:
    return fetch_df(
        f"SELECT * FROM {TABLE} WHERE code=:c AND period=:p "
        f"ORDER BY dt DESC LIMIT :n",
        {"c": code, "p": period, "n": limit},
    )
