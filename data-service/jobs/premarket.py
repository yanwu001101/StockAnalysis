# -*- coding: utf-8 -*-
"""Pre-market job (8:30 trading days).

Tasks:
  * Pull yesterday's LHB (公布次日早盘前)
  * Pull recent announcements (业绩日历) for the watched universe
"""
from __future__ import annotations
import asyncio
import datetime as dt

from core.trace import logger
from pipelines import lhb as lhb_pipe
from pipelines import news as news_pipe
from pipelines import spot as spot_pipe


async def run_async() -> None:
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    try:
        await lhb_pipe.run(start=yesterday, end=today)
    except Exception as e:
        logger.warning("[job:premarket] lhb failed: %s", e)

    try:
        df = spot_pipe.get_cached()
        if df is None or df.empty:
            df = await spot_pipe.run()
        if df is not None and not df.empty:
            sort_col = "market_cap_yi" if "market_cap_yi" in df.columns else "market_cap"
            codes = (
                df.sort_values(sort_col, ascending=False, na_position="last")
                  .head(500)["code"].astype(str).tolist()
            )
            await news_pipe.run(codes, days=2)
    except Exception as e:
        logger.warning("[job:premarket] announcements failed: %s", e)


def run() -> None:
    try:
        asyncio.run(run_async())
    except Exception as e:
        logger.exception("[job:premarket] failed: %s", e)
