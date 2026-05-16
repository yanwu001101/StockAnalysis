# -*- coding: utf-8 -*-
"""Fundamentals pipeline (quarterly statements + key ratios).

Akshare-backed batch optimization: we pre-fetch the whole-market 业绩报表 /
资产负债 tables for each candidate quarter ONCE, then look up each code in
memory. This is ~200x faster than the per-code fetch path because the akshare
endpoints return the entire market in one call.
"""
from __future__ import annotations
import asyncio
import calendar
import datetime as dt
from typing import Iterable

import pandas as pd

from core import parser
from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty, gather_codes
from repo import fundamental_repo


def _quarter_ends(today: dt.date, n: int) -> list[dt.date]:
    out: list[dt.date] = []
    y, m = today.year, today.month
    for _ in range(n + 2):
        qe_month = ((m - 1) // 3) * 3
        if qe_month == 0:
            qe_year, qe_month = y - 1, 12
        else:
            qe_year = y
        last_day = calendar.monthrange(qe_year, qe_month)[1]
        qe = dt.date(qe_year, qe_month, last_day)
        if qe < today and qe not in out:
            out.append(qe)
        m -= 3
        if m <= 0:
            m += 12
            y -= 1
        if len(out) >= n:
            break
    return out


def _safe(fn, **kw) -> pd.DataFrame:
    try:
        return fn(**kw)
    except Exception:
        return pd.DataFrame()


async def fetch(code: str, periods: int = 8) -> pd.DataFrame:
    """Per-code path — used by ad-hoc on-stock evaluations."""
    return await fetch_first_nonempty("fundamental", code, periods=periods)


async def run_batch(codes: Iterable[str], periods: int = 4) -> int:
    """Batch path — pre-fetches whole-market tables, then assembles per code.

    Much faster than per-code fan-out because akshare's `stock_yjbb_em` and
    `stock_zcfz_em` each return ~5k rows in one call.
    """
    import akshare as ak  # local import to keep cold-path light

    codes = [parser.normalize_code(c) for c in codes]
    if not codes:
        return 0
    today = dt.date.today()
    candidates = _quarter_ends(today, periods + 1)
    logger.info("[pipeline:fundamental] pre-fetching %d quarters", len(candidates))

    yjbb_by_qe: dict[dt.date, pd.DataFrame] = {}
    zcfz_by_qe: dict[dt.date, pd.DataFrame] = {}

    async def _pull(qe: dt.date):
        date_str = qe.strftime("%Y%m%d")
        df_y = await asyncio.to_thread(_safe, ak.stock_yjbb_em, date=date_str)
        df_z = await asyncio.to_thread(_safe, ak.stock_zcfz_em, date=date_str)
        if df_y is not None and not df_y.empty:
            df_y["股票代码"] = df_y["股票代码"].astype(str).str.zfill(6)
            yjbb_by_qe[qe] = df_y
        if df_z is not None and not df_z.empty and "股票代码" in df_z.columns:
            df_z["股票代码"] = df_z["股票代码"].astype(str).str.zfill(6)
            zcfz_by_qe[qe] = df_z

    await asyncio.gather(*(_pull(qe) for qe in candidates))
    logger.info("[pipeline:fundamental] pre-fetch done: yjbb=%d, zcfz=%d quarters",
                len(yjbb_by_qe), len(zcfz_by_qe))

    rows: list[dict] = []
    code_set = set(codes)
    for qe in candidates:
        df_y = yjbb_by_qe.get(qe)
        if df_y is None:
            continue
        df_y = df_y[df_y["股票代码"].isin(code_set)]
        if df_y.empty:
            continue
        df_z = zcfz_by_qe.get(qe)
        debt_map: dict[str, float | None] = {}
        if df_z is not None and not df_z.empty:
            debt_map = dict(zip(df_z["股票代码"], df_z.get("资产负债率", [])))
        for _, r in df_y.iterrows():
            c = r["股票代码"]
            rows.append({
                "code": c,
                "report_date": qe,
                "period_type": "Q",
                "revenue": r.get("营业总收入-营业总收入"),
                "net_profit": r.get("净利润-净利润"),
                "eps": r.get("每股收益"),
                "revenue_yoy": r.get("营业总收入-同比增长"),
                "net_profit_yoy": r.get("净利润-同比增长"),
                "roe": r.get("净资产收益率"),
                "gross_margin": r.get("销售毛利率"),
                "op_cashflow": r.get("每股经营性现金流"),
                "bvps": r.get("每股净资产"),
                "debt_ratio": debt_map.get(c),
            })

    if not rows:
        logger.warning("[pipeline:fundamental] no rows assembled")
        return 0
    df = pd.DataFrame(rows)
    n = fundamental_repo.upsert_fundamental(df)
    PIPELINE_ROWS.labels(pipeline="fundamental").inc(n)
    logger.info("[pipeline:fundamental] %d rows upserted across %d codes", n, df["code"].nunique())
    return n
