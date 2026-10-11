# -*- coding: utf-8 -*-
"""龙虎榜 repo."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_lhb"
COLS = ["code", "trade_date", "reason", "buy_amount",
        "sell_amount", "net_amount", "seat_type", "seat_name"]


def upsert_lhb(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    df = df.copy()
    if "seat_type" not in df.columns:
        df["seat_type"] = ""
    if "seat_name" not in df.columns:
        df["seat_name"] = ""
    if "reason" not in df.columns:
        df["reason"] = ""
    return upsert(TABLE, df, COLS, update_columns=["buy_amount", "sell_amount",
                                                    "net_amount", "seat_type"])


