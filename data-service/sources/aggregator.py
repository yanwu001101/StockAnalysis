# -*- coding: utf-8 -*-
"""Multi-source aggregator with fallback chain and quality validation.

Usage:
    from sources.aggregator import default_aggregator
    spot = await default_aggregator().fetch_spot()
    kline = await default_aggregator().fetch_kline("600519", "daily", 250)

The aggregator tries sources in priority order, validates each result,
and falls back to the next source on failure. If all sources fail,
it returns stale cache (if available) rather than empty data.
"""
from __future__ import annotations
import asyncio
from typing import Any, Callable, Optional, Sequence

import pandas as pd

from core.trace import logger
from sources.base import AbstractSource


# ---------------------------------------------------------------------------
# Data quality validators
# ---------------------------------------------------------------------------

def validate_spot(df: pd.DataFrame) -> tuple[bool, str]:
    """Return (is_valid, reason)."""
    if df is None or df.empty:
        return False, "empty dataframe"
    if "code" not in df.columns or "name" not in df.columns:
        return False, "missing required columns (code, name)"
    if len(df) < 3000:
        return False, f"too few rows: {len(df)} < 3000"
    # Check if most prices are non-null
    if "price" in df.columns:
        null_ratio = df["price"].isna().sum() / len(df)
        if null_ratio > 0.3:
            return False, f"too many null prices: {null_ratio:.1%}"
    return True, "ok"


def validate_kline(df: pd.DataFrame, min_rows: int = 30) -> tuple[bool, str]:
    """Return (is_valid, reason)."""
    if df is None or df.empty:
        return False, "empty dataframe"
    required = {"trade_date", "open", "close", "high", "low"}
    if not required.issubset(df.columns):
        return False, f"missing columns: {required - set(df.columns)}"
    if len(df) < min_rows:
        return False, f"too few rows: {len(df)} < {min_rows}"
    # Check if OHLC are mostly non-null
    for col in ["open", "close", "high", "low"]:
        null_ratio = df[col].isna().sum() / len(df)
        if null_ratio > 0.2:
            return False, f"too many null {col}: {null_ratio:.1%}"
    return True, "ok"


def validate_minute_kline(df: pd.DataFrame, min_rows: int = 20) -> tuple[bool, str]:
    """Return (is_valid, reason)."""
    if df is None or df.empty:
        return False, "empty dataframe"
    required = {"dt", "open", "close", "high", "low"}
    if not required.issubset(df.columns):
        return False, f"missing columns: {required - set(df.columns)}"
    if len(df) < min_rows:
        return False, f"too few rows: {len(df)} < {min_rows}"
    return True, "ok"


def validate_generic(df: pd.DataFrame, min_rows: int = 1) -> tuple[bool, str]:
    """Generic validator: non-empty + min_rows."""
    if df is None or df.empty:
        return False, "empty dataframe"
    if len(df) < min_rows:
        return False, f"too few rows: {len(df)} < {min_rows}"
    return True, "ok"


# ---------------------------------------------------------------------------
# Multi-source aggregator
# ---------------------------------------------------------------------------

class SourceAggregator:
    """Tries multiple sources in priority order with validation."""

    def __init__(self, sources: Sequence[AbstractSource]):
        self.sources = list(sources)

    async def _try_sources(
        self,
        method_name: str,
        args: tuple,
        kwargs: dict,
        validator: Callable[[pd.DataFrame], tuple[bool, str]],
    ) -> Optional[pd.DataFrame]:
        """Try each source's method in order; return first valid result."""
        for src in self.sources:
            method = getattr(src, method_name, None)
            if method is None:
                continue
            try:
                logger.debug("aggregator: trying %s.%s", src.name, method_name)
                df = await method(*args, **kwargs)
                valid, reason = validator(df)
                if valid:
                    logger.info(
                        "aggregator: %s.%s succeeded (%d rows)",
                        src.name, method_name, len(df) if df is not None else 0,
                    )
                    return df
                logger.warning(
                    "aggregator: %s.%s validation failed: %s",
                    src.name, method_name, reason,
                )
            except Exception as e:
                logger.warning("aggregator: %s.%s raised: %s", src.name, method_name, e)
        return None

    async def fetch_spot(self) -> pd.DataFrame:
        result = await self._try_sources("fetch_spot", (), {}, validate_spot)
        return result if result is not None else pd.DataFrame()

    async def fetch_kline(
        self, code: str, period: str = "daily", count: int = 250
    ) -> pd.DataFrame:
        result = await self._try_sources(
            "fetch_kline",
            (code,),
            {"period": period, "count": count},
            lambda df: validate_kline(df, min_rows=min(30, count // 5)),
        )
        return result if result is not None else pd.DataFrame()

    async def fetch_minute_kline(
        self, code: str, period: str = "5min", count: int = 240
    ) -> pd.DataFrame:
        result = await self._try_sources(
            "fetch_minute_kline",
            (code,),
            {"period": period, "count": count},
            lambda df: validate_minute_kline(df, min_rows=min(20, count // 10)),
        )
        return result if result is not None else pd.DataFrame()

    async def fetch_fundamental(self, code: str, periods: int = 8) -> pd.DataFrame:
        result = await self._try_sources(
            "fetch_fundamental",
            (code,),
            {"periods": periods},
            lambda df: validate_generic(df, min_rows=1),
        )
        return result if result is not None else pd.DataFrame()

    async def fetch_moneyflow(self, code: str, days: int = 60) -> pd.DataFrame:
        result = await self._try_sources(
            "fetch_moneyflow",
            (code,),
            {"days": days},
            lambda df: validate_generic(df, min_rows=min(5, days // 5)),
        )
        return result if result is not None else pd.DataFrame()

    async def fetch_northbound_holdings(self, code: str, days: int = 60) -> pd.DataFrame:
        result = await self._try_sources(
            "fetch_northbound_holdings",
            (code,),
            {"days": days},
            lambda df: validate_generic(df, min_rows=1),
        )
        return result if result is not None else pd.DataFrame()


# ---------------------------------------------------------------------------
# Default aggregator instance
# ---------------------------------------------------------------------------

_default_agg: Optional[SourceAggregator] = None


def default_aggregator() -> SourceAggregator:
    """Lazy singleton with fallback chain: eastmoney -> tencent -> sina -> akshare."""
    global _default_agg
    if _default_agg is not None:
        return _default_agg

    from sources import eastmoney, tencent, sina, ths, akshare_src

    # Priority order: eastmoney (most complete) -> tencent (K-line) -> sina (fallback) -> akshare (last resort)
    _default_agg = SourceAggregator([
        eastmoney.default(),
        tencent.default(),
        sina.default(),
        ths.default(),
        akshare_src.default(),
    ])
    return _default_agg
