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
BASIS_REFRESH_REQUIRED: dict[tuple[str, str], int] = {}


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


def upsert_with_basis_refresh(code: str, df: pd.DataFrame, klt: int = 101) -> int:
    """Legacy synchronous writers: retry a rejected rebase with full history once.

    Never relax the guard or scale the stored prefix. If the provider truncates
    history, preserve the old series and its explicit BASIS_REFRESH_REQUIRED flag.
    Async pipelines have their own source-aware retry and use upsert_daily directly.
    """
    if klt not in (101, 102):
        raise ValueError("Only daily and weekly bars support basis refresh")
    write = upsert_weekly if klt == 102 else upsert_daily
    written = write(code, df)
    required = BASIS_REFRESH_REQUIRED.get((_table(klt), code))
    if written or not required:
        return written
    try:
        full = eastmoney.fetch_kline(code, klt=klt, count=max(1000, required))
        if full is not None and not full.empty:
            written = write(code, full)
    except Exception as exc:
        log.warning("[kline:basis] %s full refresh failed: %s", code, exc)
    if not written:
        log.warning("[kline:basis] %s history incomplete; prior basis preserved", code)
    return written


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
    # A short adjusted-price update must not leave an older prefix on another basis.
    # Applies to every writer (legacy scheduler and v2 pipelines alike).
    from core.adjustment_guard import needs_full_refresh
    try:
        with eng.connect() as conn:
            existing = pd.read_sql(text(f"SELECT trade_date, close FROM {table} WHERE code=:c"),
                                   conn, params={"c": code})
        if needs_full_refresh(existing, pd.DataFrame(rows)):
            BASIS_REFRESH_REQUIRED[(table, code)] = len(existing) + 300
            log.warning("[kline:basis] %s partial rewrite rejected; full history required (%d bars)", code, len(existing))
            return 0
    except Exception as e:
        log.warning("[kline:basis] %s validation failed; no data written: %s", code, e)
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
        BASIS_REFRESH_REQUIRED.pop((table, code), None)
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
            # Keep the overlap: the adjustment guard needs an unchanged price
            # anchor. Dropping <= last makes every incremental update unverifiable.
            upsert_with_basis_refresh(code, fresh)

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
            upsert_with_basis_refresh(code, fresh, klt=102)

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
