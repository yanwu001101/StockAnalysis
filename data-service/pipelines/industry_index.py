# -*- coding: utf-8 -*-
"""行业指数日线管线（申万二级 → industry_index_daily）。

为什么用申万：
  * 我们的 `stock_info.industry` 就是申万二级口径（实测 128 个行业名里 127 个与
    申万二级官方名完全一致，仅「银行Ⅱ」需按去后缀匹配）；用同一套名字，行业指数
    与个股行业才能直接 JOIN，不存在人工映射表漂移。
  * 申万官网与东财无关：东财板块列表(push2 clist)已被封锁，这条路本来就走不通。

纪律：
  * 只取 close（行业动量算的是相对强度，OHLC 里那几个字段在申万接口里口径存疑）；
  * 首次全量（默认 2019-01-01 起），之后按表内 MAX(trade_date) 增量；
  * 串行 + 停顿：131 个指数一次性并发会把上游打成限流（本项目已在东财上踩过）。
"""
from __future__ import annotations

import asyncio
import datetime as dt
import re

import pandas as pd
from sqlalchemy import text

from core.trace import PIPELINE_ROWS, logger
from repo import industry_index_repo

_ROMAN = "ⅠⅡⅢⅣⅤ"

DEFAULT_START = dt.date(2019, 1, 1)


def _norm(name: str) -> str:
    s = str(name or "").strip()
    return re.sub(f"[{ _ROMAN}]+$", "", s).strip()


def _sw_code(raw: str) -> str:
    """'801016.SI' → '801016'。"""
    return str(raw or "").strip().split(".")[0]


def list_indices() -> list[tuple[str, str]]:
    import akshare as ak
    df = ak.sw_index_second_info()
    if df is None or df.empty or "行业代码" not in df.columns:
        return []
    out = []
    for _, r in df.iterrows():
        code = _sw_code(r.get("行业代码"))
        name = str(r.get("行业名称") or "").strip()
        if code and name:
            out.append((code, name))
    return out


async def _history(code: str) -> pd.DataFrame:
    import akshare as ak
    def _pull():
        return ak.index_hist_sw(symbol=code, period="day")
    try:
        df = await asyncio.to_thread(_pull)
    except Exception as e:
        logger.warning("[pipeline:industry_index] %s failed: %s", code, e)
        return pd.DataFrame()
    if df is None or df.empty or "日期" not in df.columns:
        return pd.DataFrame()
    out = pd.DataFrame({
        "code": code,
        "trade_date": pd.to_datetime(df["日期"], errors="coerce").dt.date,
        "close": pd.to_numeric(df.get("收盘"), errors="coerce"),
        "volume": pd.to_numeric(df.get("成交量"), errors="coerce"),
        "amount": pd.to_numeric(df.get("成交额"), errors="coerce"),
    })
    return out.dropna(subset=["trade_date", "close"])


async def run(start: dt.date = DEFAULT_START, sleep_s: float = 0.35) -> dict:
    """拉取全部申万二级行业指数日线并落库。

    行业名对齐：优先与 stock_info.industry 的取值精确匹配，匹配不上时按去掉
    Ⅰ/Ⅱ/Ⅲ 后缀再匹配（申万表里「银行」对应我们的「银行Ⅱ」）。落库时 industry
    一律写**我们口径**的名字，保证与个股行业能直接 JOIN；实在对不上的保留申万名
    并在结果里计数，避免静默错位。
    """
    import db

    industry_index_repo.ensure_table()
    pairs = list_indices()
    if not pairs:
        logger.warning("[pipeline:industry_index] 申万行业列表为空")
        return {"ok": False, "reason": "empty index list"}

    ours: set[str] = set()
    eng = db.get_engine()
    if eng is not None:
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT DISTINCT industry FROM stock_info "
                "WHERE industry IS NOT NULL AND industry NOT IN ('', '-')"
            )).fetchall()
        ours = {str(r[0]).strip() for r in rows}
    by_norm = {_norm(o): o for o in ours}

    since = industry_index_repo.max_date()
    cutoff = (since - dt.timedelta(days=3)) if (since and since > start) else start
    logger.info("[pipeline:industry_index] %d indices, fetch from %s", len(pairs), cutoff)

    total_rows = 0
    matched = 0
    unmatched_names: list[str] = []
    for code, sw_name in pairs:
        df = await _history(code)
        if df.empty:
            continue
        df = df[df["trade_date"] >= cutoff]
        if df.empty:
            continue
        if sw_name in ours:
            industry, matched = sw_name, matched + 1
        elif _norm(sw_name) in by_norm:
            industry, matched = by_norm[_norm(sw_name)], matched + 1
        else:
            industry = sw_name
            unmatched_names.append(sw_name)
        df = df.assign(industry=industry)
        total_rows += industry_index_repo.upsert_rows(df[["code", "industry", "trade_date", "close", "volume", "amount"]])
        if sleep_s:
            await asyncio.sleep(sleep_s)

    PIPELINE_ROWS.labels(pipeline="industry_index").inc(total_rows)
    res = {"ok": True, "indices": len(pairs), "rows": total_rows,
           "name_matched": matched, "name_unmatched": unmatched_names[:10],
           "from_date": str(cutoff)}
    logger.info("[pipeline:industry_index] %s", res)
    return res
