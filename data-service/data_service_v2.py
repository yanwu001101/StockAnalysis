# -*- coding: utf-8 -*-
"""
Enhanced data service with multi-source fallback and quality validation.

Drop-in replacement for the current fetch_spot() / fetch_kline() functions.
Uses the new aggregator + enhanced cache for maximum stability.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import math
from typing import Optional

import pandas as pd

from cache_enhanced import enhanced as enhanced_cache
from core.trace import logger
from core import health
from sources.aggregator import default_aggregator
from sources import browser


# ---------------------------------------------------------------------------
# Enhanced fetch functions with multi-source fallback
# ---------------------------------------------------------------------------

async def fetch_spot_async() -> pd.DataFrame:
    """Fetch spot data with multi-source fallback + stale cache graceful degradation."""
    agg = default_aggregator()

    # If browser source is enabled, add it as last resort
    if browser.default().enabled():
        agg.sources.append(browser.default())

    def validator(df: pd.DataFrame) -> bool:
        return (
            df is not None
            and not df.empty
            and "code" in df.columns
            and len(df) >= 3000
        )

    def fetcher():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(agg.fetch_spot())
        finally:
            loop.close()

    return enhanced_cache().get_or_fetch_with_fallback(
        key="spot_v2",
        ttl=300,
        fetcher=fetcher,
        validator=validator,
    )


def fetch_spot() -> pd.DataFrame:
    """Sync wrapper for fetch_spot_async."""
    try:
        return asyncio.run(fetch_spot_async())
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(fetch_spot_async())).result()


async def fetch_kline_async(
    code: str, period: str = "daily", count: int = 250
) -> pd.DataFrame:
    """Fetch K-line with multi-source fallback."""
    agg = default_aggregator()

    def validator(df: pd.DataFrame) -> bool:
        return (
            df is not None
            and not df.empty
            and len(df) >= min(30, count // 5)
        )

    def fetcher():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(agg.fetch_kline(code, period, count))
        finally:
            loop.close()

    return enhanced_cache().get_or_fetch_with_fallback(
        key=f"kline_v2:{code}:{period}:{count}",
        ttl=120,
        fetcher=fetcher,
        validator=validator,
    )


def fetch_kline(code: str, period: str = "daily", count: int = 250) -> pd.DataFrame:
    """Sync wrapper for fetch_kline_async."""
    try:
        return asyncio.run(fetch_kline_async(code, period, count))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(
                lambda: asyncio.run(fetch_kline_async(code, period, count))
            ).result()


async def fetch_minute_kline_async(
    code: str, period: str = "5min", count: int = 240
) -> pd.DataFrame:
    """Fetch minute K-line with multi-source fallback."""
    agg = default_aggregator()

    def validator(df: pd.DataFrame) -> bool:
        return df is not None and not df.empty and len(df) >= min(20, count // 10)

    def fetcher():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(agg.fetch_minute_kline(code, period, count))
        finally:
            loop.close()

    return enhanced_cache().get_or_fetch_with_fallback(
        key=f"min_kline_v2:{code}:{period}:{count}",
        ttl=60,
        fetcher=fetcher,
        validator=validator,
    )


def fetch_minute_kline(
    code: str, period: str = "5min", count: int = 240
) -> pd.DataFrame:
    """Sync wrapper for fetch_minute_kline_async."""
    try:
        return asyncio.run(fetch_minute_kline_async(code, period, count))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(
                lambda: asyncio.run(fetch_minute_kline_async(code, period, count))
            ).result()


# ---------------------------------------------------------------------------
# Health check endpoint
# ---------------------------------------------------------------------------

async def get_sources_health() -> dict:
    """Return health status of all sources."""
    checker = health.default()
    all_health = await checker.get_all_health()
    return {
        name: {
            "available": h.available,
            "success_rate": round(h.success_rate * 100, 2),
            "health_score": round(h.health_score, 2),
            "avg_latency_ms": round(h.avg_latency_ms, 2),
            "circuit_open": h.circuit_open,
        }
        for name, h in all_health.items()
    }


def get_sources_health_sync() -> dict:
    """Sync wrapper for get_sources_health."""
    try:
        return asyncio.run(get_sources_health())
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(get_sources_health())).result()
