# -*- coding: utf-8 -*-
"""Concept-board members pipeline.

When playwright is enabled, we read the THS concept list. Otherwise we fall
through to akshare's `stock_board_concept_*` helpers (handled by the source chain).
"""
from __future__ import annotations
import asyncio

import pandas as pd

from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty
from repo import concept_repo


async def run() -> int:
    df = await fetch_first_nonempty("concept_members")
    if df is None or df.empty:
        # Fallback path: akshare concept names + members
        try:
            import akshare as ak
            ths_df = await asyncio.to_thread(ak.stock_board_concept_name_em)
            if ths_df is None or ths_df.empty:
                return 0
            rows = []
            for _, row in ths_df.head(50).iterrows():
                name = row.get("板块名称") or row.get("name")
                if not name:
                    continue
                try:
                    members = await asyncio.to_thread(ak.stock_board_concept_cons_em, symbol=name)
                except Exception:
                    continue
                if members is None or members.empty:
                    continue
                for _, m in members.iterrows():
                    rows.append({
                        "concept_code": str(row.get("板块代码") or name)[:20],
                        "concept_name": str(name)[:100],
                        "code": str(m.get("代码", "")).zfill(6),
                        "weight": None,
                    })
            df = pd.DataFrame(rows)
        except Exception as e:
            logger.debug("[pipeline:concept] akshare fallback failed: %s", e)
            return 0
    if df.empty:
        return 0
    n = concept_repo.upsert_concept(df)
    PIPELINE_ROWS.labels(pipeline="concept").inc(n)
    logger.info("[pipeline:concept] %d rows", n)
    return n
