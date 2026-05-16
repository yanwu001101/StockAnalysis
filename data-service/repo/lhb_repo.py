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


def get_recent_lhb(code: str, days: int = 60) -> pd.DataFrame:
    return fetch_df(
        f"SELECT * FROM {TABLE} WHERE code=:c "
        f"AND trade_date >= (CURDATE() - INTERVAL :d DAY) "
        f"ORDER BY trade_date DESC",
        {"c": code, "d": days},
    )


def get_institution_picks(days: int = 30) -> pd.DataFrame:
    """Codes whose LHB entries in the last N days include 机构席位."""
    return fetch_df(
        "SELECT code, COUNT(*) AS n_inst, SUM(net_amount) AS net_sum "
        "FROM stock_lhb WHERE seat_type='机构' "
        "AND trade_date >= (CURDATE() - INTERVAL :d DAY) "
        "GROUP BY code ORDER BY net_sum DESC",
        {"d": days},
    )
