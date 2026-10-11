# -*- coding: utf-8 -*-
"""公告 repo."""
from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy import text

from repo.base import engine, fetch_df


def upsert_announcement(df: pd.DataFrame) -> int:
    eng = engine()
    if eng is None or df is None or df.empty:
        return 0
    rows = []
    for r in df.to_dict("records"):
        rows.append({
            "code": r.get("code"),
            "ann_date": r.get("ann_date"),
            "title": (r.get("title") or "")[:500],
            "type": (r.get("type") or "")[:50],
            "url": (r.get("url") or "")[:500],
        })
    sql = text(
        "INSERT IGNORE INTO stock_announcement "
        "(code, ann_date, title, type, url) "
        "VALUES (:code, :ann_date, :title, :type, :url)"
    )
    try:
        with eng.begin() as conn:
            conn.execute(sql, rows)
        return len(rows)
    except Exception:
        return 0


