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


def get_concepts_for(code: str) -> pd.DataFrame:
    return fetch_df(
        f"SELECT concept_code, concept_name, weight FROM {TABLE} "
        f"WHERE code=:c",
        {"c": code},
    )


def get_members_of(concept_code: str) -> pd.DataFrame:
    return fetch_df(
        f"SELECT code, weight FROM {TABLE} WHERE concept_code=:cc",
        {"cc": concept_code},
    )
