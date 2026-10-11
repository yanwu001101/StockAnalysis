# -*- coding: utf-8 -*-
"""概念板块成分 repo."""
from __future__ import annotations

import pandas as pd

from repo.base import fetch_df, upsert


TABLE = "stock_concept"
COLS = ["concept_code", "concept_name", "code", "weight"]


def upsert_concept(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    return upsert(TABLE, df, COLS, update_columns=["concept_name", "weight"])


