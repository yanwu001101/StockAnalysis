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
from pipelines import index_kline as index_kline_pipe
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


def _ex_div_codes_today() -> list[str]:
    """今日除权的股票：前复权口径当天整体重算，必须全量重刷历史，
    否则 250 根增量窗口之外的老 K 线还停留在旧复权基准上，序列出现断缝。"""
    from repo.base import fetch_df
    df = fetch_df(
        "SELECT DISTINCT code FROM stock_dividend WHERE ex_date = :d",
        {"d": dt.date.today()},
    )
    if df is None or df.empty:
        return []
    return df["code"].astype(str).str.zfill(6).tolist()


async def run_async() -> None:
    # 周末防呆：双休无新数据，跳过重任务（法定节假日表后续接入日历再挡）
    if dt.date.today().weekday() >= 5:
        logger.info("[job:postmarket] weekend — skip")
        return
    top_n = settings.sched.warmup_top_n
    codes = await _universe(top_n)
    if not codes:
        logger.warning("[job:postmarket] empty universe; aborting")
        return

    try:
        await kline_pipe.run_daily_batch(codes, count=800)   # 3 年+ 深度：因子检验/回测窗口依赖
    except Exception as e:
        logger.warning("[job:postmarket] daily kline failed: %s", e)

    # 除权漂移治理：当天除权的股票强制全量重刷（覆盖 250 根增量窗口外的老 bar）
    ex_div = _ex_div_codes_today()
    if ex_div:
        logger.info("[job:postmarket] ex-div today: %s — full kline refresh", ex_div)
        try:
            await kline_pipe.run_daily_batch(ex_div, count=6000)
        except Exception as e:
            logger.warning("[job:postmarket] ex-div refresh failed: %s", e)
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
    try:
        # 指数日线：回测基准 + 交易日历来源（量小，失败只降级不影响主流程）
        await index_kline_pipe.run()
    except Exception as e:
        logger.warning("[job:postmarket] index kline failed: %s", e)
    logger.info("[job:postmarket] done")


def run() -> None:
    try:
        asyncio.run(run_async())
    except Exception as e:
        logger.exception("[job:postmarket] failed: %s", e)
        try:
            import notifier
            notifier.job_failed("盘后数据任务", str(e))
        except Exception:
            pass
