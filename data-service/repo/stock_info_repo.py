# -*- coding: utf-8 -*-
"""stock_info helpers for source fallbacks.

This module deliberately keeps the existing schema unchanged. It persists the
parts of spot snapshots that are useful for later offline fallbacks, then can
rebuild a broad universe from stock_info plus the latest stored K-line row.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from core import parser
from core.trace import logger
from repo import base


def _num(v):
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _normalize_market_cap_yi(row: pd.Series) -> float | None:
    """Return market cap in yi, accepting either raw yuan or already-yi input."""
    value = None
    for col in ("market_cap_yi", "总市值_亿", "鎬诲競鍊糭浜?"):
        if col in row:
            value = _num(row.get(col))
            if value and value > 0:
                return value
    for col in ("market_cap", "总市值", "鎬诲競鍊?"):
        if col in row:
            value = _num(row.get(col))
            if value and value > 0:
                return value / 1e8 if value > 1_000_000 else value
    return None


def upsert_from_spot(df: pd.DataFrame) -> int:
    """Persist code/name/industry/latest price/market cap from a spot snapshot."""
    eng = base.engine()
    if eng is None or df is None or df.empty:
        return 0

    rows: list[dict] = []
    for _, r in df.iterrows():
        code = r.get("code", r.get("代码", r.get("浠ｇ爜")))
        if code is None:
            continue
        code = parser.normalize_code(str(code))
        if not code:
            continue
        name = r.get("name", r.get("名称", r.get("鍚嶇О"))) or code
        industry = r.get("industry", r.get("行业", r.get("琛屼笟"))) or ""
        price = _num(r.get("price", r.get("最新价", r.get("鏈€鏂颁环"))))
        market_cap = _normalize_market_cap_yi(r)
        rows.append({
            "code": code,
            "name": str(name),
            "industry": str(industry) if industry is not None else "",
            "market_cap": market_cap,
            "latest_price": price,
        })

    if not rows:
        return 0

    sql = text("""
        INSERT INTO stock_info (code, name, industry, market_cap, latest_price)
        VALUES (:code, :name, :industry, :market_cap, :latest_price)
        ON DUPLICATE KEY UPDATE
          name = IF(VALUES(name) <> '', VALUES(name), name),
          industry = IF(VALUES(industry) <> '', VALUES(industry), industry),
          market_cap = IF(VALUES(market_cap) IS NOT NULL AND VALUES(market_cap) > 0,
                          VALUES(market_cap), market_cap),
          latest_price = IF(VALUES(latest_price) IS NOT NULL AND VALUES(latest_price) > 0,
                            VALUES(latest_price), latest_price)
    """)
    try:
        with eng.begin() as conn:
            conn.execute(sql, rows)
        return len(rows)
    except Exception as e:
        logger.debug("stock_info upsert_from_spot failed: %s", e)
        return 0


def load_spot_snapshot(limit: int | None = None) -> pd.DataFrame:
    """Build an English-column spot snapshot from local persisted data."""
    sql = """
    WITH ranked_kline AS (
      SELECT d.code,
             d.close,
             d.pct_change,
             d.volume,
             d.amount,
             LAG(d.close) OVER (PARTITION BY d.code ORDER BY d.trade_date) AS prev_close,
             ROW_NUMBER() OVER (PARTITION BY d.code ORDER BY d.trade_date DESC) AS rn
      FROM stock_kline_daily d
      WHERE d.close IS NOT NULL
    )
    SELECT si.code,
           si.name,
           COALESCE(si.industry, '') AS industry,
           COALESCE(NULLIF(si.latest_price, 0), k.close, 0) AS price,
           COALESCE(
             k.pct_change,
             CASE
               WHEN k.prev_close IS NOT NULL AND k.prev_close <> 0
               THEN (k.close - k.prev_close) / k.prev_close * 100
               ELSE NULL
             END
           ) AS pct_change,
           si.market_cap AS market_cap_yi,
           si.market_cap AS market_cap,
           k.volume,
           k.amount
    FROM stock_info si
    LEFT JOIN ranked_kline k ON k.code = si.code AND k.rn = 1
    ORDER BY CASE WHEN si.market_cap IS NULL OR si.market_cap <= 0 THEN 1 ELSE 0 END,
             si.market_cap DESC,
             si.code ASC
    """
    if limit and limit > 0:
        sql += " LIMIT :limit"
        return base.fetch_df(sql, {"limit": int(limit)})
    return base.fetch_df(sql)


def load_codes(limit: int | None = None) -> list[str]:
    df = load_spot_snapshot(limit)
    if df is None or df.empty or "code" not in df:
        return []
    return df["code"].astype(str).str.zfill(6).tolist()
