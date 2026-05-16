# -*- coding: utf-8 -*-
"""Weekend job (Saturday).

Slow-moving data that only needs a weekly refresh:
  * Fundamentals (季度报表)
  * Shareholder counts
  * Dividend history
  * Concept board membership
"""
from __future__ import annotations
import asyncio

from config import settings
from core.trace import logger
from pipelines import concept as concept_pipe
from pipelines import dividend as div_pipe
from pipelines import fundamental as fund_pipe
from pipelines import shareholder as sh_pipe
from pipelines import spot as spot_pipe


async def run_async() -> None:
    df = await spot_pipe.run()
    if df is None or df.empty:
        logger.warning("[job:weekend] empty spot; aborting")
        return
    sort_col = "market_cap_yi" if "market_cap_yi" in df.columns else "market_cap"
    codes = (
        df.sort_values(sort_col, ascending=False, na_position="last")
          .head(settings.sched.warmup_top_n)["code"].astype(str).str.zfill(6).tolist()
    )

    try:
        await fund_pipe.run_batch(codes, periods=8)
    except Exception as e:
        logger.warning("[job:weekend] fundamentals failed: %s", e)
    try:
        await sh_pipe.run_batch(codes)
    except Exception as e:
        logger.warning("[job:weekend] shareholder failed: %s", e)
    try:
        await div_pipe.run_batch(codes)
    except Exception as e:
        logger.warning("[job:weekend] dividend failed: %s", e)
    try:
        await concept_pipe.run()
    except Exception as e:
        logger.warning("[job:weekend] concept failed: %s", e)
    logger.info("[job:weekend] done")


def run() -> None:
    try:
        asyncio.run(run_async())
    except Exception as e:
        logger.exception("[job:weekend] failed: %s", e)
