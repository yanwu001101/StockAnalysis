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
from core.job_outcome import JobOutcome, failed_outcome
from core.trace import logger
from core.universe import select_codes
from pipelines import concept as concept_pipe
from pipelines import dividend as div_pipe
from pipelines import fundamental as fund_pipe
from pipelines import shareholder as sh_pipe
from pipelines import spot as spot_pipe


async def run_async() -> dict:
    try:
        df = await spot_pipe.run()
        codes = select_codes(df, settings.sched.warmup_top_n)
    except Exception as error:
        return failed_outcome("weekend", "universe", error)
    if not codes:
        logger.warning("[job:weekend] empty universe; aborting")
        return failed_outcome("weekend", "universe", "行情股票池为空，未启动数据采集")
    outcome = JobOutcome("weekend", universe_size=len(codes))
    await outcome.run_step("fundamentals", lambda: fund_pipe.run_batch(codes, periods=8))
    await outcome.run_step("shareholder", lambda: sh_pipe.run_batch(codes))
    await outcome.run_step("dividend", lambda: div_pipe.run_batch(codes))
    await outcome.run_step("concept", concept_pipe.run)
    result = outcome.finish()
    logger.info("[job:weekend] %s: %d reported upsert rows", result["status"], result["rows"])
    return result


def run() -> dict:
    try:
        return asyncio.run(run_async())
    except Exception as e:
        logger.exception("[job:weekend] failed: %s", e)
        return failed_outcome("weekend", "runner", e)
