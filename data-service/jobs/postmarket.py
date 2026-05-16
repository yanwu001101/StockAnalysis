# -*- coding: utf-8 -*-
"""Post-market job (16:30 trading days).

Heaviest job of the day. Refreshes:
  * Daily / weekly K-line for the active universe (top-N by market cap)
  * Money flow for the same universe
  * Northbound holdings
  * Today's LHB (publish ~16:00)
"""
from __future__ import annotations
import asyncio
import datetime as dt

from config import settings
from core.trace import logger
from pipelines import kline as kline_pipe
from pipelines import lhb as lhb_pipe
from pipelines import moneyflow as mf_pipe
from pipelines import northbound as nb_pipe
from pipelines import spot as spot_pipe


async def _universe(top_n: int) -> list[str]:
    df = await spot_pipe.run()
    if df is None or df.empty:
        return []
    sort_col = "market_cap_yi" if "market_cap_yi" in df.columns else "market_cap"
    return (
        df.sort_values(sort_col, ascending=False, na_position="last")
          .head(top_n)["code"].astype(str).str.zfill(6).tolist()
    )


async def run_async() -> None:
    top_n = settings.sched.warmup_top_n
    codes = await _universe(top_n)
    if not codes:
        logger.warning("[job:postmarket] empty universe; aborting")
        return

    try:
        await kline_pipe.run_daily_batch(codes, count=250)
    except Exception as e:
        logger.warning("[job:postmarket] daily kline failed: %s", e)
    try:
        await kline_pipe.run_weekly_batch(codes, count=200)
    except Exception as e:
        logger.warning("[job:postmarket] weekly kline failed: %s", e)
    try:
        await mf_pipe.run_batch(codes, days=60)
    except Exception as e:
        logger.warning("[job:postmarket] moneyflow failed: %s", e)
    try:
        await nb_pipe.run_batch(codes, days=60)
    except Exception as e:
        logger.warning("[job:postmarket] northbound failed: %s", e)
    try:
        await lhb_pipe.run(start=dt.date.today() - dt.timedelta(days=60),
                           end=dt.date.today())
    except Exception as e:
        logger.warning("[job:postmarket] lhb failed: %s", e)
    logger.info("[job:postmarket] done")


def run() -> None:
    try:
        asyncio.run(run_async())
    except Exception as e:
        logger.exception("[job:postmarket] failed: %s", e)
