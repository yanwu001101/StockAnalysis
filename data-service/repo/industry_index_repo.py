# -*- coding: utf-8 -*-
"""行业指数日线（申万二级）落库与读取。

供「行业动量轮动」类策略取 as-of 的行业相对强度——策略要的是行业指数的历史
序列，用当日全市场涨跌快照近似排名会把横截面动量退化成日内情绪指标。
"""
from __future__ import annotations

import datetime as dt

import pandas as pd
from sqlalchemy import text

from repo.base import engine, upsert

TABLE = "industry_index_daily"

DDL = """
CREATE TABLE IF NOT EXISTS `industry_index_daily` (
    `code` VARCHAR(12) NOT NULL COMMENT '申万二级行业指数代码，如 801016',
    `industry` VARCHAR(50) NOT NULL COMMENT '行业名（与 stock_info.industry 同口径）',
    `trade_date` DATE NOT NULL,
    `close` DECIMAL(16,4),
    `volume` DECIMAL(24,6),
    `amount` DECIMAL(24,6),
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`code`, `trade_date`),
    INDEX `idx_iid_date` (`trade_date`),
    INDEX `idx_iid_industry` (`industry`, `trade_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

COLS = ["code", "industry", "trade_date", "close", "volume", "amount"]


def ensure_table() -> None:
    eng = engine()
    if eng is None:
        return
    with eng.begin() as conn:
        conn.execute(text(DDL))


def max_date() -> dt.date | None:
    """表内最新报告期；表还不存在时返回 None（新库首次运行前不应报错）。"""
    eng = engine()
    if eng is None:
        return None
    try:
        with eng.connect() as conn:
            row = conn.execute(text(f"SELECT MAX(trade_date) FROM {TABLE}")).fetchone()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def upsert_rows(df: pd.DataFrame) -> int:
    if df is None or df.empty:
        return 0
    ensure_table()
    return upsert(TABLE, df, COLS, update_columns=["industry", "close", "volume", "amount"])


def close_panel(start: dt.date, end: dt.date) -> pd.DataFrame:
    """宽表：index=trade_date, columns=industry, values=close（行业相对强度的计算入口）。"""
    eng = engine()
    if eng is None:
        return pd.DataFrame()
    with eng.connect() as conn:
        df = pd.read_sql(
            text(f"SELECT trade_date, industry, close FROM {TABLE} "
                 f"WHERE trade_date BETWEEN :s AND :e"),
            conn, params={"s": start, "e": end},
        )
    if df.empty:
        return pd.DataFrame()
    wide = df.pivot_table(index="trade_date", columns="industry", values="close", aggfunc="last")
    return wide.sort_index()
