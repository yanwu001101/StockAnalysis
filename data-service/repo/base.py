# -*- coding: utf-8 -*-
"""Generic upsert helper backed by SQLAlchemy.

Repos that just need ON DUPLICATE KEY UPDATE on a few columns reuse `upsert()`.
Repos with finer-grained logic (e.g. kline_repo's incremental gap fill) can
import this module's engine accessor and write their own SQL.
"""
from __future__ import annotations
import datetime as dt
from decimal import Decimal
from typing import Any, Iterable

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

import db
from core.trace import logger


def engine() -> Engine | None:
    return db.get_engine()


def _to_sql_value(v: Any) -> Any:
    if v is None:
        return None
    # NaN / NaT for scalars (pd.isna chokes on lists/dicts → guard with try)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    if isinstance(v, (dt.date, dt.datetime, str, int, bool)):
        return v
    if isinstance(v, Decimal):
        return v
    if isinstance(v, float):
        return float(v)
    return v


def _clean_rows(rows: Iterable[dict], columns: list[str]) -> list[dict]:
    out = []
    for r in rows:
        clean = {c: _to_sql_value(r.get(c)) for c in columns}
        out.append(clean)
    return out


def upsert(
    table: str,
    rows: list[dict] | pd.DataFrame,
    columns: list[str],
    update_columns: list[str] | None = None,
    preserve_non_null: bool = False,
) -> int:
    """Insert rows into `table`; on duplicate key, update `update_columns`.

    `columns` must include every column we're sending (incl. PK columns).
    `update_columns` defaults to non-PK columns inferred as columns minus the
    first column (assumed PK) — but for safety always pass it explicitly.
    """
    eng = engine()
    if eng is None or rows is None:
        return 0
    if isinstance(rows, pd.DataFrame):
        if rows.empty:
            return 0
        rows = rows.to_dict("records")
    if not rows:
        return 0
    if not columns:
        raise ValueError("upsert requires at least one column")
    cleaned = _clean_rows(rows, columns)
    if update_columns is None:
        update_columns = columns[1:]
    placeholders = ", ".join(f":{c}" for c in columns)
    col_list = ", ".join(f"`{c}`" for c in columns)
    update_clause = ", ".join(
        f"`{c}`=COALESCE(VALUES(`{c}`),`{c}`)" if preserve_non_null else f"`{c}`=VALUES(`{c}`)"
        for c in update_columns)
    # PK-only payloads may legitimately have no fields to update. Keep duplicates
    # unchanged instead of generating an empty ON DUPLICATE KEY UPDATE clause.
    if not update_clause:
        update_clause = f"`{columns[0]}`=`{columns[0]}`"
    sql = text(
        f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )
    try:
        with eng.begin() as conn:
            conn.execute(sql, cleaned)
        return len(cleaned)
    except Exception as e:
        logger.debug("upsert %s failed: %s", table, e)
        return 0


def fetch_df(sql: str, params: dict | None = None) -> pd.DataFrame:
    eng = engine()
    if eng is None:
        return pd.DataFrame()
    try:
        with eng.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params or {})
    except Exception as e:
        logger.debug("fetch_df failed: %s", e)
        return pd.DataFrame()
