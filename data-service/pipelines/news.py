# -*- coding: utf-8 -*-
"""Announcements pipeline (公告 + 业绩日历)."""
from __future__ import annotations
from typing import Iterable

import pandas as pd

from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty
from repo import announcement_repo


async def run(codes: Iterable[str], days: int = 7) -> int:
    codes = list(codes)
    if not codes:
        return 0
    # Batch in chunks to avoid one huge request
    BATCH = 50
    total = 0
    for i in range(0, len(codes), BATCH):
        chunk = codes[i:i + BATCH]
        df = await fetch_first_nonempty("announcements", chunk, days=days)
        if isinstance(df, pd.DataFrame) and not df.empty:
            total += announcement_repo.upsert_announcement(df)
    PIPELINE_ROWS.labels(pipeline="news").inc(total)
    logger.info("[pipeline:news] %d rows", total)
    return total
