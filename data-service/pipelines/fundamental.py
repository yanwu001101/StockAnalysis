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


# stock_fundamental 里比率/每股类列是 decimal(10,4)（整数位只有 6 位），
# 而东财整表里出现过 5e10 这类同比增速——不裁掉会整批 upsert 报 1264 回滚。
# 超界一律置 None（该值不可信/放不进列），不裁剪成边界值冒充真实数字。
_PCT_BOUND = 999_999.0
_PCT_COLS = ("roe", "gross_margin", "debt_ratio", "revenue_yoy",
             "net_profit_yoy", "eps", "bvps")


def _num(v, bound: float | None = None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    if bound is not None and abs(f) > bound:
        return None
    return f


def _universe_codes() -> set[str]:
    """A 股宇宙（stock_info）。业绩报表整表还含新三板 8xx/4xx 代码，且与
    北交所同号重复（同一公司两条代码、数值一致），不过滤就会污染财务表。"""
    try:
        from repo.base import fetch_df
        df = fetch_df("SELECT code FROM stock_info", {})
        if df is None or df.empty:
            return set()
        return {parser.normalize_code(c) for c in df["code"]}
    except Exception:
        return set()


def _safe(fn, **kw) -> pd.DataFrame:
    try:
        return fn(**kw)
    except Exception:
        return pd.DataFrame()


async def fetch(code: str, periods: int = 8) -> pd.DataFrame:
    """Per-code path — used by ad-hoc on-stock evaluations."""
    return await fetch_first_nonempty("fundamental", code, periods=periods)


def _pick_col(df: pd.DataFrame, *keys: str) -> str | None:
    """按列名取列：先精确相等，再按关键字模糊匹配——akshare 的资产负债类接口
    列名改过多次，且 '资产-总资产' 与 '资产-总资产同比' 互为前缀，只用 in 会挑错。"""
    names = [str(c) for c in df.columns]
    for k in keys:
        if k in names:
            return k
    for k in keys:
        for name in names:
            if k in name:
                return name
    return None


async def run_batch(codes: Iterable[str] | None, periods: int = 4,
                    quarters: Iterable[dt.date] | None = None) -> int:
    """Batch path — pre-fetches whole-market tables, then assembles per code.

    Much faster than per-code fan-out because akshare's `stock_yjbb_em` and
    `stock_zcfz_em` each return ~5k rows in one call.

    `quarters` 给定时按这些报告期取数（历史深度回补用，否则只能从今天往回数）；
    `codes=None` 表示不过滤（整张表都入库，回补时正是想要的）。
    """
    import akshare as ak  # local import to keep cold-path light

    if codes is None:
        # 整表入库时也要卡在 A 股宇宙内（剔掉新三板同号重复）
        code_set = _universe_codes() or None
    else:
        norm = [parser.normalize_code(c) for c in codes]
        if not norm:
            return 0
        code_set = set(norm)
    today = dt.date.today()
    candidates = list(quarters) if quarters else _quarter_ends(today, periods + 1)
    if not candidates:
        return 0
    logger.info("[pipeline:fundamental] pre-fetching %d quarters", len(candidates))

    yjbb_by_qe: dict[dt.date, pd.DataFrame] = {}
    zcfz_by_qe: dict[dt.date, pd.DataFrame] = {}

    async def _pull(qe: dt.date):
        date_str = qe.strftime("%Y%m%d")
        df_y = await asyncio.to_thread(_safe, ak.stock_yjbb_em, date=date_str)
        df_z = await asyncio.to_thread(_safe, ak.stock_zcfz_em, date=date_str)
        if df_y is not None and not df_y.empty and "股票代码" in df_y.columns:
            df_y = df_y.copy()
            df_y["股票代码"] = df_y["股票代码"].astype(str).str.zfill(6)
            yjbb_by_qe[qe] = df_y
        if df_z is not None and not df_z.empty and "股票代码" in df_z.columns:
            df_z = df_z.copy()
            df_z["股票代码"] = df_z["股票代码"].astype(str).str.zfill(6)
            zcfz_by_qe[qe] = df_z

    await asyncio.gather(*(_pull(qe) for qe in candidates))
    logger.info("[pipeline:fundamental] pre-fetch done: yjbb=%d, zcfz=%d quarters",
                len(yjbb_by_qe), len(zcfz_by_qe))

    rows: list[dict] = []
    for qe in candidates:
        df_y = yjbb_by_qe.get(qe)
        if df_y is None:
            continue
        if code_set is not None:
            df_y = df_y[df_y["股票代码"].isin(code_set)]
        if df_y.empty:
            continue
        df_z = zcfz_by_qe.get(qe)
        debt_map: dict[str, object] = {}
        bal_maps: list[tuple[str, dict[str, object]]] = []
        if df_z is not None and not df_z.empty:
            z_codes = df_z["股票代码"]
            col = _pick_col(df_z, "资产负债率")
            if col:
                debt_map = dict(zip(z_codes, df_z[col]))
            # 总资产/总负债/股东权益:应计利润质量与资产增长异象要靠这几列,
            # 业绩报表里没有,但资产负债表整张表都带着——不拿就白丢。
            for field, keys in (("total_assets", ("资产-总资产", "总资产")),
                                ("total_liab", ("负债-总负债", "总负债")),
                                ("total_equity", ("股东权益合计", "股东权益", "所有者权益"))):
                col = _pick_col(df_z, *keys)
                if col:
                    bal_maps.append((field, dict(zip(z_codes, df_z[col]))))
        for _, r in df_y.iterrows():
            c = r["股票代码"]
            row = {
                "code": c,
                "report_date": qe,
                "period_type": "Q",
                "revenue": _num(r.get("营业总收入-营业总收入")),
                "net_profit": _num(r.get("净利润-净利润")),
                "eps": _num(r.get("每股收益"), _PCT_BOUND),
                "revenue_yoy": _num(r.get("营业总收入-同比增长"), _PCT_BOUND),
                "net_profit_yoy": _num(r.get("净利润-同比增长"), _PCT_BOUND),
                "roe": _num(r.get("净资产收益率"), _PCT_BOUND),
                "gross_margin": _num(r.get("销售毛利率"), _PCT_BOUND),
                "op_cashflow": _num(r.get("每股经营现金流量")),
                "bvps": _num(r.get("每股净资产"), _PCT_BOUND),
                "debt_ratio": _num(debt_map.get(c), _PCT_BOUND),
                # ann_date 刻意留空：yjbb 的『最新公告日期』实测是「最近一次公告」
                # （FY2024 报告的中位数落到 2026-04-24，99% 的行晚于报告期末+200 天），
                # 不是原始披露日。回填它会让回测的 as-of 门控把这几年整段看成不可知，
                # 比留空更糟——留空时引擎按法定披露截止日兜底（见 backtest/engine.py）。
                "ann_date": None,
            }
            for field, m in bal_maps:
                v = _num(m.get(c))
                if v is not None and row.get(field) is None:
                    row[field] = v
            if row["revenue"] is None and row["net_profit"] is None:
                continue
            rows.append(row)

    if not rows:
        logger.warning("[pipeline:fundamental] no rows assembled")
        return 0
    df = pd.DataFrame(rows)
    n = fundamental_repo.upsert_fundamental(df)
    PIPELINE_ROWS.labels(pipeline="fundamental").inc(n)
    logger.info("[pipeline:fundamental] %d rows upserted across %d codes", n, df["code"].nunique())
    return n
