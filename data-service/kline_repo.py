# -*- coding: utf-8 -*-
# K-line persistence layer. Reads from MySQL, fetches missing days from eastmoney,
# upserts result back. Falls through to eastmoney-only when MySQL is down.
from __future__ import annotations
import datetime as dt
import logging
from typing import Optional

import pandas as pd
from sqlalchemy import text

import db
import eastmoney

log = logging.getLogger(__name__)

DAILY_TABLE = "stock_kline_daily"
WEEKLY_TABLE = "stock_kline_weekly"


def _table(klt: int) -> str:
    return WEEKLY_TABLE if klt == 102 else DAILY_TABLE


def get_max_date(code: str, klt: int = 101) -> Optional[dt.date]:
    eng = db.get_engine()
    if eng is None:
        return None
    try:
        with eng.connect() as conn:
            row = conn.execute(
                text(f"SELECT MAX(trade_date) FROM {_table(klt)} WHERE code=:c"),
                {"c": code},
            ).fetchone()
            return row[0] if row and row[0] else None
    except Exception as e:
        log.debug("get_max_date(%s) failed: %s", code, e)
        return None


def select_daily(code: str, days: int) -> pd.DataFrame:
    """Return last `days` rows ordered by trade_date asc, with Chinese cols."""
    eng = db.get_engine()
    if eng is None:
        return pd.DataFrame()
    try:
        sql = text(
            f"SELECT trade_date, open, close, high, low, volume "
            f"FROM {DAILY_TABLE} WHERE code=:c "
            f"ORDER BY trade_date DESC LIMIT :n"
        )
        with eng.connect() as conn:
            df = pd.read_sql(sql, conn, params={"c": code, "n": days})
        if df.empty:
            return df
        df = df.sort_values("trade_date").reset_index(drop=True)
        df = df.rename(columns={
            "trade_date": "日期", "open": "开盘", "close": "收盘",
            "high": "最高", "low": "最低", "volume": "成交量",
        })
        df["日期"] = df["日期"].astype(str)
        for c in ("开盘", "收盘", "最高", "最低"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["成交量"] = pd.to_numeric(df["成交量"], errors="coerce")
        return df
    except Exception as e:
        log.debug("select_daily(%s) failed: %s", code, e)
        return pd.DataFrame()


def select_weekly(code: str, weeks: int) -> pd.DataFrame:
    eng = db.get_engine()
    if eng is None:
        return pd.DataFrame()
    try:
        sql = text(
            f"SELECT trade_date, open, close, high, low, volume "
            f"FROM {WEEKLY_TABLE} WHERE code=:c "
            f"ORDER BY trade_date DESC LIMIT :n"
        )
        with eng.connect() as conn:
            df = pd.read_sql(sql, conn, params={"c": code, "n": weeks})
        if df.empty:
            return df
        df = df.sort_values("trade_date").reset_index(drop=True)
        df = df.rename(columns={
            "trade_date": "日期", "open": "开盘", "close": "收盘",
            "high": "最高", "low": "最低", "volume": "成交量",
        })
        df["日期"] = df["日期"].astype(str)
        for c in ("开盘", "收盘", "最高", "最低"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["成交量"] = pd.to_numeric(df["成交量"], errors="coerce")
        return df
    except Exception as e:
        log.debug("select_weekly(%s) failed: %s", code, e)
        return pd.DataFrame()


def upsert_daily(code: str, df: pd.DataFrame) -> int:
    return _upsert(code, df, DAILY_TABLE)


def upsert_weekly(code: str, df: pd.DataFrame) -> int:
    return _upsert(code, df, WEEKLY_TABLE)


def _upsert(code: str, df: pd.DataFrame, table: str) -> int:
    eng = db.get_engine()
    if eng is None or df is None or df.empty:
        return 0
    rows = []
    for _, r in df.iterrows():
        d = r.get("日期")
        if not d:
            continue
        rows.append({
            "code": code,
            "trade_date": str(d)[:10],
            "open": float(r["开盘"]) if pd.notna(r.get("开盘")) else None,
            "close": float(r["收盘"]) if pd.notna(r.get("收盘")) else None,
            "high": float(r["最高"]) if pd.notna(r.get("最高")) else None,
            "low": float(r["最低"]) if pd.notna(r.get("最低")) else None,
            "volume": int(r["成交量"]) if pd.notna(r.get("成交量")) else None,
        })
    if not rows:
        return 0
    sql = text(
        f"INSERT INTO {table} (code, trade_date, open, close, high, low, volume) "
        f"VALUES (:code, :trade_date, :open, :close, :high, :low, :volume) "
        f"ON DUPLICATE KEY UPDATE "
        f"open=VALUES(open), close=VALUES(close), high=VALUES(high), "
        f"low=VALUES(low), volume=VALUES(volume)"
    )
    try:
        with eng.begin() as conn:
            conn.execute(sql, rows)
        return len(rows)
    except Exception as e:
        log.debug("upsert %s failed: %s", code, e)
        return 0


def get_daily(code: str, days: int = 250) -> pd.DataFrame:
    """MySQL-first read; pulls missing tail from eastmoney and upserts.

    Returns DataFrame with Chinese column names (sorted asc by date).
    Falls back to eastmoney-only when MySQL is unreachable.
    """
    eng = db.get_engine()
    if eng is None:
        return eastmoney.fetch_kline(code, klt=101, count=days)

    today = dt.date.today()
    last = get_max_date(code, klt=101)

    need_refresh = (last is None) or (last < today)
    if need_refresh:
        # Pull from eastmoney enough to cover gap + slack
        gap_days = (today - last).days + 5 if last else max(days, 60)
        # eastmoney count = trading days, not calendar; use a generous count
        fresh = eastmoney.fetch_kline(code, klt=101, count=max(gap_days, days))
        if fresh is not None and not fresh.empty:
            if last is not None:
                fresh = fresh[fresh["日期"] > str(last)]
            if not fresh.empty:
                upsert_daily(code, fresh)

    df = select_daily(code, days)
    if df.empty:
        # MySQL had nothing and refresh didn't land. Final fallback: live fetch.
        return eastmoney.fetch_kline(code, klt=101, count=days)
    return df


def get_weekly(code: str, weeks: int = 200) -> pd.DataFrame:
    eng = db.get_engine()
    if eng is None:
        return eastmoney.fetch_kline(code, klt=102, count=weeks)

    today = dt.date.today()
    last = get_max_date(code, klt=102)

    need_refresh = (last is None) or ((today - last).days >= 7)
    if need_refresh:
        count = max(weeks, 200)
        fresh = eastmoney.fetch_kline(code, klt=102, count=count)
        if fresh is not None and not fresh.empty:
            upsert_weekly(code, fresh)

    df = select_weekly(code, weeks)
    if df.empty:
        return eastmoney.fetch_kline(code, klt=102, count=weeks)
    return df


def batch_get_weekly(codes, weeks: int = 200) -> dict:
    """Weekly bars for many codes, keyed by the code string passed in.
    Mirrors eastmoney.batch_klines semantics: codes with no/empty data are
    omitted so callers can treat a missing key as "no trend data". Used by the
    screener's weekly-trend enrichment (app.py)."""
    out: dict = {}
    for c in codes:
        try:
            df = get_weekly(c, weeks)
        except Exception:
            continue
        if df is not None and not df.empty:
            out[c] = df
    return out
