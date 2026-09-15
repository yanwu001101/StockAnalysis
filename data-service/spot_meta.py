# -*- coding: utf-8 -*-
"""行情快照跟踪:记录最近一次全市场快照的抓取时间与来源。

spot 本身缓存在 redis(`ds:spot`),但没有"什么时候取的、从哪取的"元信息;
排名快照与决策页需要把行情时间与数据源明确展示给用户,所以单独记录。
"""
from __future__ import annotations
import datetime as dt

import cache

KEY = "spot_meta"
TTL = 6 * 3600


def record(source: str, rows: int = 0, fetched_at: dt.datetime | None = None) -> dict:
    meta = {
        "fetched_at": (fetched_at or dt.datetime.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "source": source or "unknown",
        "rows": int(rows or 0),
    }
    try:
        cache.set(KEY, meta, TTL)
    except Exception:
        pass
    return meta


def get() -> dict | None:
    try:
        m = cache.get(KEY)
    except Exception:
        return None
    return m if isinstance(m, dict) else None
