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

import pandas as pd
from sqlalchemy import text

from config import settings
from core.job_outcome import JobOutcome, failed_outcome, skipped_outcome
from core.trace import logger
from core.universe import select_codes
from pipelines import index_kline as index_kline_pipe
from pipelines import kline as kline_pipe
from pipelines import lhb as lhb_pipe
from pipelines import moneyflow as mf_pipe
from pipelines import northbound as nb_pipe
from pipelines import spot as spot_pipe


async def _universe(top_n: int) -> list[str]:
    df = await spot_pipe.run()
    return select_codes(df, top_n)


def _ex_div_codes_today() -> list[str]:
    """今日除权的股票：前复权口径当天整体重算，必须全量重刷历史，
    否则 250 根增量窗口之外的老 K 线还停留在旧复权基准上，序列出现断缝。"""
    from repo.base import engine
    eng = engine()
    if eng is None:
        raise RuntimeError("数据库不可用，无法检查今日除权股票")
    # fetch_df intentionally swallows DB errors; this task must distinguish a
    # failed eligibility check from a confirmed empty ex-dividend calendar.
    with eng.connect() as conn:
        df = pd.read_sql(text("SELECT DISTINCT code FROM stock_dividend WHERE ex_date = :d"),
                         conn, params={"d": dt.date.today()})
    if df is None or df.empty:
        return []
    return df["code"].astype(str).str.zfill(6).tolist()


async def run_async() -> dict:
    # 周末防呆：双休无新数据，跳过重任务（法定节假日表后续接入日历再挡）
    if dt.date.today().weekday() >= 5:
        logger.info("[job:postmarket] weekend — skip")
        return skipped_outcome("postmarket", "weekend")
    top_n = settings.sched.warmup_top_n
    try:
        codes = await _universe(top_n)
    except Exception as error:
        return failed_outcome("postmarket", "universe", error)
    if not codes:
        logger.warning("[job:postmarket] empty universe; aborting")
        return failed_outcome("postmarket", "universe", "行情股票池为空，未启动数据采集")

    outcome = JobOutcome("postmarket", universe_size=len(codes))
    await outcome.run_step("daily_kline", lambda: kline_pipe.run_daily_batch(codes, count=800))

    # 除权漂移治理：当天除权的股票强制全量重刷（覆盖 250 根增量窗口外的老 bar）
    try:
        ex_div = _ex_div_codes_today()
        if ex_div:
            await outcome.run_step("ex_dividend_kline", lambda: kline_pipe.run_daily_batch(ex_div, count=6000))
        else:
            outcome.skipped("ex_dividend_kline", "no_ex_dividends")
    except Exception as error:
        outcome.failed("ex_dividend_calendar", error)
    await outcome.run_step("weekly_kline", lambda: kline_pipe.run_weekly_batch(codes, count=200))
    await outcome.run_step("moneyflow", lambda: mf_pipe.run_batch(codes, days=60))
    await outcome.run_step("northbound", lambda: nb_pipe.run_batch(codes, days=60))
    await outcome.run_step("lhb", lambda: lhb_pipe.run(start=dt.date.today() - dt.timedelta(days=60),
                                                       end=dt.date.today()))
    await outcome.run_step("index_kline", index_kline_pipe.run)
    result = outcome.finish()
    logger.info("[job:postmarket] %s: %d reported upsert rows", result["status"], result["rows"])
    return result


def run() -> dict:
    try:
        result = asyncio.run(run_async())
    except Exception as e:
        logger.exception("[job:postmarket] failed: %s", e)
        result = failed_outcome("postmarket", "runner", e)
    if result["status"] == "failed":
        try:
            import notifier
            notifier.job_failed("盘后数据任务", result.get("error", "任务失败"))
        except Exception:
            pass
    return result
