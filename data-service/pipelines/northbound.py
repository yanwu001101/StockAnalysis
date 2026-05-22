# -*- coding: utf-8 -*-
"""Northbound (沪深股通) holdings pipeline."""
from __future__ import annotations
from typing import Iterable

import pandas as pd

from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty, gather_codes
from repo import northbound_repo


async def fetch(code: str, days: int = 60) -> pd.DataFrame:
    return await fetch_first_nonempty("northbound_holdings", code, days=days)


async def run_batch(codes: Iterable[str], days: int = 60) -> int:
    res = await gather_codes(list(codes), lambda c: fetch(c, days), concurrency=12)
    total = 0
    for code, df in res.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            total += northbound_repo.upsert_northbound(df)
    PIPELINE_ROWS.labels(pipeline="northbound").inc(total)
    logger.info("[pipeline:northbound] %d rows", total)
    return total
