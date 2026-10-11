# -*- coding: utf-8 -*-
"""Strategy score repo — pre-computed alpha scores for the dashboard
"each strategy Top-N" panel. The scoring job writes per-(code, strategy)
rows; the API just SELECTs.

Indexed on (strategy_id, score) so top-N is a millisecond query.
"""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_strategy_score"
COLS = ["code", "strategy_id", "score", "signal_type", "triggered"]


def upsert_scores(df: pd.DataFrame) -> int:
    """Replace today's score rows. `df` must have COLS columns."""
    if df is None or df.empty:
        return 0
    return upsert(TABLE, df, COLS, update_columns=["score", "signal_type", "triggered"])


def top_n_all(n: int = 10) -> pd.DataFrame:
    """All strategies' top-N in one trip, using a window function.

    Returns long-format frame: (strategy_id, code, score, rank). Caller
    pivots client-side. We use ROW_NUMBER() so ties get distinct ranks.
    """
    sql = (
        "SELECT strategy_id, code, score, signal_type, triggered, rn FROM ("
        "  SELECT code, strategy_id, score, signal_type, triggered, "
        "    ROW_NUMBER() OVER (PARTITION BY strategy_id ORDER BY score DESC) AS rn "
        f"  FROM {TABLE} WHERE score > 0"
        ") t WHERE rn <= :n"
    )
    return fetch_df(sql, {"n": int(n)})


def latest_computed_at():
    df = fetch_df(f"SELECT MAX(computed_at) AS ts FROM {TABLE}")
    if df.empty:
        return None
    return df.iloc[0]["ts"]


def row_count() -> int:
    df = fetch_df(f"SELECT COUNT(*) AS n FROM {TABLE}")
    return int(df.iloc[0]["n"]) if not df.empty else 0
