# -*- coding: utf-8 -*-
"""股东户数 pipeline."""
from __future__ import annotations
from typing import Iterable

import pandas as pd

from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty, gather_codes
from repo import shareholder_repo


async def fetch(code: str) -> pd.DataFrame:
    return await fetch_first_nonempty("shareholder", code)


async def run_batch(codes: Iterable[str]) -> int:
    res = await gather_codes(list(codes), fetch, concurrency=4)
    total = 0
    for _, df in res.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            total += shareholder_repo.upsert_shareholder(df)
    PIPELINE_ROWS.labels(pipeline="shareholder").inc(total)
    logger.info("[pipeline:shareholder] %d rows", total)
    return total
