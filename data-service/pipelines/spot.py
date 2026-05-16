# -*- coding: utf-8 -*-
"""Spot snapshot pipeline.

Pulls the whole-market real-time table once, used to feed the screener and to
identify the universe (top-N by market cap) for slower follow-up pipelines.
"""
from __future__ import annotations

import pandas as pd

import cache
from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty


# Use a v2 key so legacy `app.py` paths that read cache key "spot" (Chinese
# column DataFrame produced by the legacy `eastmoney.fetch_all_spot`) aren't
# poisoned by our English-column shape.
CACHE_KEY = "spot_v2"
CACHE_TTL = 300


async def run() -> pd.DataFrame:
    df = await fetch_first_nonempty("spot")
    if df is None or df.empty:
        logger.warning("[pipeline:spot] all sources empty")
        return pd.DataFrame()
    try:
        cache.set(CACHE_KEY, df, CACHE_TTL)
    except Exception as e:
        logger.debug("[pipeline:spot] cache set failed: %s", e)
    PIPELINE_ROWS.labels(pipeline="spot").inc(len(df))
    logger.info("[pipeline:spot] %d rows", len(df))
    return df


def get_cached() -> pd.DataFrame:
    cached = cache.get(CACHE_KEY)
    return cached if isinstance(cached, pd.DataFrame) else pd.DataFrame()
