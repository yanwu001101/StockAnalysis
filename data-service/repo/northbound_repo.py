# -*- coding: utf-8 -*-
"""Northbound (沪深股通) holdings repo."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_northbound"
COLS = ["code", "trade_date", "hold_shares", "hold_market_cap", "hold_ratio", "net_buy"]


def upsert_northbound(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return upsert(TABLE, df, COLS, update_columns=COLS[2:])


def get_northbound(code: str, days: int = 60) -> pd.DataFrame:
    return fetch_df(
        f"SELECT * FROM {TABLE} WHERE code=:c "
        f"ORDER BY trade_date DESC LIMIT :n",
        {"c": code, "n": days},
    )


def get_recent_inflows(days: int = 5) -> pd.DataFrame:
    """For each code: net change in hold_shares over the trailing `days`."""
    return fetch_df(
        "SELECT code, SUM(net_buy) AS net_buy_sum "
        "FROM stock_northbound "
        "WHERE trade_date >= (CURDATE() - INTERVAL :n DAY) "
        "GROUP BY code ORDER BY net_buy_sum DESC",
        {"n": days},
    )
