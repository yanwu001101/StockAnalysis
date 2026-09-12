# -*- coding: utf-8 -*-
"""Index daily kline repo (benchmark series + trading calendar source)."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert

TABLE = "index_kline_daily"
COLS = ["code", "trade_date", "open", "close", "high", "low", "volume", "amount"]


def upsert_index_kline(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return upsert(TABLE, df, COLS, update_columns=COLS[2:])


def get_index_close(code: str, start=None, end=None) -> pd.Series:
    """Close series indexed by trade_date, ascending."""
    conds = ["code = :c"]
    params: dict = {"c": code}
    if start is not None:
        conds.append("trade_date >= :s")
        params["s"] = start
    if end is not None:
        conds.append("trade_date <= :e")
        params["e"] = end
    df = fetch_df(
        f"SELECT trade_date, close FROM {TABLE} WHERE {' AND '.join(conds)} "
        "ORDER BY trade_date",
        params,
    )
    if df.empty:
        return pd.Series(dtype=float)
    s = pd.Series(
        pd.to_numeric(df["close"], errors="coerce").values,
        index=pd.to_datetime(df["trade_date"]),
    ).dropna()
    return s.sort_index()
