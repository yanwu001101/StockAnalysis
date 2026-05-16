# -*- coding: utf-8 -*-
"""龙虎榜 pipeline."""
from __future__ import annotations
import datetime as dt

import pandas as pd

from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty
from repo import lhb_repo


async def run(start: dt.date | None = None, end: dt.date | None = None) -> int:
    end = end or dt.date.today()
    start = start or (end - dt.timedelta(days=7))
    df = await fetch_first_nonempty("lhb", start, end)
    if df is None or df.empty:
        logger.info("[pipeline:lhb] empty")
        return 0
    n = lhb_repo.upsert_lhb(df)
    PIPELINE_ROWS.labels(pipeline="lhb").inc(n)
    logger.info("[pipeline:lhb] %d rows", n)
    return n
