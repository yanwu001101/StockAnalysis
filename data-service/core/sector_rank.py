# -*- coding: utf-8 -*-
"""行业相对强度排名（as-of，20 交易日窗口）。

「行业动量轮动」策略文档写的是 20 日相对强度前 20%，但原先唯一的注入点
(api/strategies_v2)用的是**当日**全市场涨跌幅均值排名：既与文档口径不符，又让
研究链路（factorlab / 回测）完全拿不到 sector_rank —— 该策略每个报告期都是
no_data，体检直接判 coverage。

这里把口径统一到一处：只用 ≤as_of 的行业指数收盘算 20 日动量，再在截面上排名。
rank_pct 约定与旧实现一致——0.0 = 最强，≤0.20 即前 20%（策略据此加分）。
"""
from __future__ import annotations

import datetime as dt
import threading

import pandas as pd

from core.trace import logger
from repo import industry_index_repo

LOOKBACK = 20          # 与策略文档一致
START = dt.date(2019, 1, 1)
_TTL_S = 1800.0

_lock = threading.Lock()
_cache: dict = {"ranks": None, "n": None, "ts": 0.0, "index": None}


def _build() -> tuple[pd.Series, pd.Series, pd.DatetimeIndex] | None:
    wide = industry_index_repo.close_panel(START, dt.date.today())
    if wide is None or wide.empty or len(wide) <= LOOKBACK:
        return None
    mom = wide / wide.shift(LOOKBACK) - 1.0
    order = mom.rank(axis=1, ascending=False)
    n = order.notna().sum(axis=1).astype("float64")
    # DataFrame / Series 默认按「列」对齐——这里必须 axis=0 按日期对齐，
    # 否则索引为日期的 n 会和行业列求并集，结果整片 NaN（实测踩过）。
    ranks = order.sub(1.0, axis=0).div(n, axis=0)
    ranks.index = pd.to_datetime(ranks.index.astype(str))
    n.index = pd.to_datetime(n.index.astype(str))
    return ranks, n, ranks.index


def _ensure() -> tuple[pd.Series, pd.Series] | None:
    now = dt.datetime.now().timestamp()
    with _lock:
        if _cache["ranks"] is not None and now - _cache["ts"] < _TTL_S:
            return _cache["ranks"], _cache["n"]
    try:
        built = _build()
    except Exception as e:
        logger.warning("[sector_rank] build failed: %s", e)
        return None
    if built is None:
        return None
    ranks, n, index = built
    with _lock:
        _cache.update({"ranks": ranks, "n": n, "index": index, "ts": now})
    return ranks, n


def _locate(index: pd.DatetimeIndex, as_of: dt.date) -> int:
    """取 ≤as_of 的最后一个交易日；早于数据起点返回 -1。"""
    pos = index.searchsorted(pd.Timestamp(as_of), side="right") - 1
    return int(pos)


def rank_at(industry: str, as_of: dt.date | None = None) -> tuple[float, int] | None:
    """(rank_pct, 行业总数)；无数据或行业缺失返回 None（调用方按 no_data 处理）。"""
    if not industry:
        return None
    got = _ensure()
    if got is None:
        return None
    ranks, n = got
    as_of = as_of or dt.date.today()
    i = _locate(ranks.index, as_of)
    if i < 0:
        return None
    ts = ranks.index[i]
    if industry not in ranks.columns:
        return None
    v = ranks.iloc[i].get(industry)
    if v is None or pd.isna(v):
        return None
    try:
        return float(v), int(n.iloc[i] or 0)
    except (TypeError, ValueError):
        return None


def as_of_date() -> str | None:
    """当前排名面板的最后日期（前端可据此显示「行业强度截至 X」）。"""
    got = _ensure()
    if got is None:
        return None
    return str(got[0].index[-1].date())
