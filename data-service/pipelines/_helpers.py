# -*- coding: utf-8 -*-
"""Pipeline orchestration helpers."""
from __future__ import annotations
import asyncio
import datetime as dt
from typing import Any, Awaitable, Callable, Iterable

import pandas as pd

from core.trace import logger
from sources import chain


async def fetch_first_nonempty(
    capability: str, *args, **kwargs
) -> pd.DataFrame:
    """Walk the fallback chain for `capability`, return first non-empty result."""
    last_err: Exception | None = None
    for src in chain(capability):
        try:
            fn = getattr(src, f"fetch_{capability}")
            df = await fn(*args, **kwargs)
            if isinstance(df, pd.DataFrame) and not df.empty:
                logger.debug("pipeline %s served by %s rows=%d", capability, src.name, len(df))
                return df
        except Exception as e:
            last_err = e
            logger.debug("pipeline %s src=%s err=%s", capability, src.name, e)
    if last_err:
        logger.debug("pipeline %s all sources failed: %s", capability, last_err)
    return pd.DataFrame()


async def gather_codes(
    codes: Iterable[str],
    coro_factory: Callable[[str], Awaitable[Any]],
    *,
    concurrency: int = 8,
) -> dict[str, Any]:
    """Apply `coro_factory(code)` to each code with bounded concurrency."""
    sem = asyncio.Semaphore(concurrency)
    out: dict[str, Any] = {}

    async def _one(code: str):
        async with sem:
            try:
                out[code] = await coro_factory(code)
            except Exception as e:
                logger.debug("gather_codes %s failed: %s", code, e)
                out[code] = None

    await asyncio.gather(*(_one(c) for c in codes), return_exceptions=True)
    return out


def trading_day_back(days: int) -> dt.date:
    """Approximate (ignores holidays — fine for windowing)."""
    d = dt.date.today()
    while days > 0:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            days -= 1
    return d
