# -*- coding: utf-8 -*-
"""分红送转 pipeline."""
from __future__ import annotations
from typing import Iterable

import pandas as pd

from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty, gather_codes
from repo import dividend_repo


async def fetch(code: str) -> pd.DataFrame:
    return await fetch_first_nonempty("dividend", code)


async def run_batch(codes: Iterable[str]) -> int:
    res = await gather_codes(list(codes), fetch, concurrency=4)
    total = 0
    for _, df in res.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            total += dividend_repo.upsert_dividend(df)
    PIPELINE_ROWS.labels(pipeline="dividend").inc(total)
    logger.info("[pipeline:dividend] %d rows", total)
    return total
