# -*- coding: utf-8 -*-
"""K-line pipeline (daily / weekly / minute), incremental upsert."""
from __future__ import annotations
from typing import Iterable

import pandas as pd

import kline_repo  # legacy daily/weekly repo
from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty, gather_codes
from repo import kline_min_repo


def _to_legacy_chinese(df: pd.DataFrame) -> pd.DataFrame:
    """Adapt new-source English columns to legacy Chinese-column upsert."""
    if df is None or df.empty:
        return df
    rename = {
        "trade_date": "日期", "open": "开盘", "close": "收盘",
        "high": "最高", "low": "最低", "volume": "成交量",
    }
    out = df.rename(columns=rename)
    if "日期" in out:
        out["日期"] = out["日期"].astype(str)
    return out


async def fetch_daily(code: str, count: int = 250) -> pd.DataFrame:
    return await fetch_first_nonempty("kline", code, period="daily", count=count)


async def fetch_weekly(code: str, count: int = 200) -> pd.DataFrame:
    return await fetch_first_nonempty("kline", code, period="weekly", count=count)


async def fetch_minute(code: str, period: str = "5min", count: int = 240) -> pd.DataFrame:
    return await fetch_first_nonempty("minute_kline", code, period=period, count=count)


async def run_daily_batch(codes: Iterable[str], count: int = 250) -> int:
    res = await gather_codes(list(codes), lambda c: fetch_daily(c, count), concurrency=8)
    total = 0
    for code, df in res.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            total += kline_repo.upsert_daily(code, _to_legacy_chinese(df))
    PIPELINE_ROWS.labels(pipeline="kline_daily").inc(total)
    logger.info("[pipeline:kline_daily] %d rows", total)
    return total


async def run_weekly_batch(codes: Iterable[str], count: int = 200) -> int:
    res = await gather_codes(list(codes), lambda c: fetch_weekly(c, count), concurrency=8)
    total = 0
    for code, df in res.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            total += kline_repo.upsert_weekly(code, _to_legacy_chinese(df))
    PIPELINE_ROWS.labels(pipeline="kline_weekly").inc(total)
    logger.info("[pipeline:kline_weekly] %d rows", total)
    return total


async def run_minute_batch(codes: Iterable[str], period: str = "5min", count: int = 240) -> int:
    res = await gather_codes(list(codes), lambda c: fetch_minute(c, period, count), concurrency=6)
    total = 0
    for code, df in res.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            total += kline_min_repo.upsert_minute(df)
    PIPELINE_ROWS.labels(pipeline=f"kline_{period}").inc(total)
    logger.info("[pipeline:kline_%s] %d rows", period, total)
    return total
