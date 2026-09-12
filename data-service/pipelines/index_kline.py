# -*- coding: utf-8 -*-
"""Benchmark index daily kline pipeline (沪深300 / 中证500).

Index daily bars double as the trading calendar: their trade_date column is
the authoritative SSE/SZSE session list, so the backtester no longer has to
approximate weekdays.
"""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from core.trace import PIPELINE_ROWS, logger
from repo import index_kline_repo
from sources.eastmoney import default as _em_default

# 东财指数 secid：沪市指数前缀 1.，深市 0.
BENCHMARKS: dict[str, str] = {
    "000300": "1.000300",  # 沪深300
    "000905": "1.000905",  # 中证500
}


async def run(codes: Iterable[str] | None = None, count: int = 900) -> int:
    """Sync index daily bars (default ~3.5 years, enough for backtest windows)."""
    src = _em_default()
    wanted = dict(BENCHMARKS)
    if codes:
        keep = set(codes)
        wanted = {k: v for k, v in BENCHMARKS.items() if k in keep}
    total = 0
    for code, secid in wanted.items():
        try:
            df = await src.fetch_index_kline(secid, count=count)
        except Exception as e:
            logger.warning("[pipeline:index_kline] %s fetch failed: %s", code, e)
            continue
        if df is None or df.empty:
            continue
        df = df.copy()
        df["code"] = code
        cols = ["code", "trade_date", "open", "close", "high", "low", "volume", "amount"]
        df = df[[c for c in cols if c in df.columns]]
        total += index_kline_repo.upsert_index_kline(df)
    PIPELINE_ROWS.labels(pipeline="index_kline").inc(total)
    logger.info("[pipeline:index_kline] %d rows", total)
    return total
