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


