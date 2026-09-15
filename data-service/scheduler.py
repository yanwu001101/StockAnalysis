# -*- coding: utf-8 -*-
# APScheduler background tasks for warmup and periodic refresh.
#
# Triggers:
#   1) startup +60s: one-shot warmup (pull whole-market spot + top N K-lines into MySQL).
#   2) 16:30 daily:  incremental refresh of all listed stocks' daily K-lines.
#   3) 09:00-15:00 every 5 minutes: refresh spot cache only (cheap).
#
# Designed to NOT block Flask startup. All heavy work runs in a dedicated thread.
from __future__ import annotations
import logging
import os
import threading
import time
from typing import Iterable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
import datetime as dt

import cache
import eastmoney
import kline_repo
import db
import spot_meta
from pipelines import spot as spot_pipe
from pipelines import lhb as lhb_pipe
from pipelines import moneyflow as mf_pipe
from pipelines import northbound as nb_pipe

log = logging.getLogger(__name__)

WARMUP_ON_START = os.getenv("WARMUP_ON_START", "false").lower() in ("1", "true", "yes")
WARMUP_DELAY_SEC = int(os.getenv("WARMUP_DELAY_SEC", "60"))
WARMUP_TOP_N = int(os.getenv("WARMUP_TOP_N", "300"))
WARMUP_BATCH_SIZE = int(os.getenv("WARMUP_BATCH_SIZE", "50"))

_sched: BackgroundScheduler | None = None
_lock = threading.Lock()


import notifier


def _chunks(seq, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def refresh_spot_cache():
    # Force-refresh the in-memory/Redis spot cache by deleting then re-fetching.
    try:
        cache.delete("spot")
        cache.delete("spot_v2")
        df = None
        try:
            import em_realtime
            df = em_realtime.fetch_all_spot()
            if df is not None and not df.empty and "代码" in df.columns:
                df["代码"] = df["代码"].astype(str).str.zfill(6)
                spot_meta.record("eastmoney:" + str(df.attrs.get("source_host") or "push2delay"), len(df))
        except Exception as e:
            log.debug("[scheduler] em_realtime spot failed: %s", e)
            df = None
        if df is None or df.empty:
            df = eastmoney.fetch_all_spot()
            if df is not None and not df.empty:
                spot_meta.record("eastmoney:aiohttp", len(df))
        if df is not None and not df.empty:
            cache.set("spot", df, 60)
            log.info("[scheduler] spot cache refreshed: %d rows", len(df))
        try:
            import asyncio
            v2 = asyncio.run(spot_pipe.run())
            if v2 is not None and not v2.empty:
                log.info("[scheduler] spot_v2 cache refreshed: %d rows", len(v2))
        except Exception as e:
            log.warning("[scheduler] refresh spot_v2 failed: %s", e)
    except Exception as e:
        log.warning("[scheduler] refresh_spot_cache failed: %s", e)


def warmup_klines(top_n: int = WARMUP_TOP_N):
    # Pull spot, then concurrently upsert daily/weekly K-lines for the top N (by market cap)
    # into MySQL. Designed to be safe on second-run (incremental via kline_repo).
    if db.get_engine() is None:
        log.info("[scheduler] MySQL unavailable; skipping warmup")
        return
    try:
        # 全市场快照优先用 warm 缓存 / em_realtime(curl_cffi);aiohttp 批量源在本机常被拦截,
        # 之前一旦它失败整个日K增量就跳过,导致因子日K停在几天前。
        spot = cache.get("spot")
        if spot is None or getattr(spot, "empty", True):
            try:
                import em_realtime
                spot = em_realtime.fetch_all_spot()
                if spot is not None and not spot.empty and "代码" in spot.columns:
                    spot["代码"] = spot["代码"].astype(str).str.zfill(6)
            except Exception as e:
                log.warning("[scheduler] warmup: em_realtime spot failed: %s", e)
                spot = None
        if spot is None or getattr(spot, "empty", True):
            spot = eastmoney.fetch_all_spot()
        if spot is None or spot.empty:
            log.warning("[scheduler] warmup: empty spot, skipping")
            return
        sort_col = "总市值_亿" if "总市值_亿" in spot.columns else None
        if sort_col:
            spot = spot.sort_values(sort_col, ascending=False, na_position="last")
        codes = spot["代码"].astype(str).str.zfill(6).head(top_n).tolist()
        log.info("[scheduler] warmup start: %d codes", len(codes))

        total_daily = 0
        total_weekly = 0
        t0 = time.time()
        for batch in _chunks(codes, WARMUP_BATCH_SIZE):
            # Daily
            daily_map = eastmoney.batch_klines(batch, klt=101, count=250)
            for code, df in daily_map.items():
                if df is not None and not df.empty:
                    total_daily += kline_repo.upsert_daily(code, df)
            # Weekly (every code, less frequent)
            weekly_map = eastmoney.batch_klines(batch, klt=102, count=200)
            for code, df in weekly_map.items():
                if df is not None and not df.empty:
                    total_weekly += kline_repo.upsert_weekly(code, df)
            log.info("[scheduler] warmup batch %s done (daily=%d, weekly=%d so far, elapsed=%.1fs)",
                     batch[0], total_daily, total_weekly, time.time() - t0)
        log.info("[scheduler] warmup done: daily=%d, weekly=%d in %.1fs",
                 total_daily, total_weekly, time.time() - t0)
    except Exception as e:
        log.exception("[scheduler] warmup_klines failed: %s", e)


def _spawn_warmup_thread():
    # Run warmup in a background thread so APScheduler job slot returns immediately.
    t = threading.Thread(target=warmup_klines, name="warmup-klines", daemon=True)
    t.start()


def refresh_lhb():
    """Pull recent LHB data (past 60 days) into MySQL."""
    import asyncio
    try:
        asyncio.run(lhb_pipe.run(
            start=dt.date.today() - dt.timedelta(days=60),
            end=dt.date.today(),
        ))
        log.info("[scheduler] lhb refresh done")
    except Exception as e:
        log.warning("[scheduler] lhb refresh failed: %s", e)
        notifier.job_failed("龙虎榜刷新", str(e))


def _get_universe_codes(top_n: int = 300) -> list[str]:
    """Get top-N stock codes by market cap from spot cache."""
    df = cache.get("spot")
    if df is None or df.empty:
        try:
            df = eastmoney.fetch_all_spot()
        except Exception:
            return []
    if df is None or df.empty:
        return []
    sort_col = "总市值_亿" if "总市值_亿" in df.columns else "总市值"
    if sort_col not in df.columns:
        return []
    return (
        df.sort_values(sort_col, ascending=False, na_position="last")
          .head(top_n)["代码"].astype(str).str.zfill(6).tolist()
    )


def refresh_moneyflow_northbound(days: int = 5):
    """Pull money flow + northbound holdings for top-N universe.

    days defaults to 5 (incremental). First-run warmup passes 60 to seed history."""
    import asyncio
    if db.get_engine() is None:
        log.info("[scheduler] MySQL unavailable; skipping moneyflow/northbound")
        return
    codes = _get_universe_codes(300)
    if not codes:
        log.warning("[scheduler] empty universe; skipping moneyflow/northbound")
        return
    try:
        asyncio.run(mf_pipe.run_batch(codes, days=days))
        log.info("[scheduler] moneyflow refresh done (days=%d)", days)
    except Exception as e:
        log.warning("[scheduler] moneyflow refresh failed: %s", e)
        notifier.job_failed("资金流刷新", str(e))
    try:
        asyncio.run(nb_pipe.run_batch(codes, days=days))
        log.info("[scheduler] northbound refresh done (days=%d)", days)
    except Exception as e:
        log.warning("[scheduler] northbound refresh failed: %s", e)
        notifier.job_failed("北向资金刷新", str(e))


def refresh_strategy_scores():
    """Pre-compute every (code, strategy) score so the dashboard's
    'Top per strategy' panel becomes a millisecond SELECT."""
    try:
        from jobs import strategy_score
        strategy_score.run()
    except Exception as e:
        log.warning("[scheduler] strategy_score refresh failed: %s", e)
        notifier.job_failed("策略评分重算", str(e))


def _rank_snapshot_safe():
    """交易时段每 15 分钟一次排名快照(决策层的数据基础);周末不跑。"""
    try:
        from jobs import rank_snapshot
        rank_snapshot.run()
    except Exception as e:
        log.warning("[scheduler] rank snapshot failed: %s", e)
        notifier.job_failed("排名快照", str(e))


def _daily_push_safe():
    try:
        from jobs import daily_push
        daily_push.run()
    except Exception as e:
        log.warning("[scheduler] daily push failed: %s", e)
        notifier.job_failed("盘后摘要推送", str(e))


def _paper_trade_safe():
    try:
        from jobs import paper_trade
        paper_trade.run()
    except Exception as e:
        log.warning("[scheduler] paper trade failed: %s", e)
        notifier.job_failed("模拟盘调仓", str(e))


def start():
    global _sched
    with _lock:
        if _sched is not None:
            return _sched
        sched = BackgroundScheduler(timezone="Asia/Shanghai")

        # Daily K-line refresh at 16:30 (after market close + settlement)
        sched.add_job(
            _spawn_warmup_thread,
            CronTrigger(hour=16, minute=30, timezone="Asia/Shanghai"),
            id="daily_kline_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Spot refresh during trading hours
        sched.add_job(
            refresh_spot_cache,
            CronTrigger(hour="9-15", minute="*/1", timezone="Asia/Shanghai"),
            id="spot_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # LHB (龙虎榜) refresh daily at 17:00 (published ~16:00-16:30)
        sched.add_job(
            refresh_lhb,
            CronTrigger(hour=17, minute=0, timezone="Asia/Shanghai"),
            id="lhb_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Money flow + northbound holdings refresh at 17:10
        sched.add_job(
            refresh_moneyflow_northbound,
            CronTrigger(hour=17, minute=10, timezone="Asia/Shanghai"),
            id="mf_nb_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Strategy score rebuild at 17:30 — after K-line / LHB / moneyflow
        # have all landed, so each strategy sees today's complete data set.
        sched.add_job(
            refresh_strategy_scores,
            CronTrigger(hour=17, minute=30, timezone="Asia/Shanghai"),
            id="strategy_score_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Paper trading at 17:50 — mark-to-market + weekly rebalance
        sched.add_job(
            _paper_trade_safe,
            CronTrigger(hour=17, minute=50, timezone="Asia/Shanghai"),
            id="paper_trade",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Rank snapshots: 09:35/09:45, then every 15 min until 11:30 and 13:15-14:45, plus 15:05 close anchor
        for jid, hour, minute in (
            ("rank_snapshot_open", "9", "35,45"),
            ("rank_snapshot_am", "10", "0,15,30,45"),
            ("rank_snapshot_am2", "11", "0,15,30"),
            ("rank_snapshot_pm", "13", "15,30,45"),
            ("rank_snapshot_pm2", "14", "0,15,30,45"),
            ("rank_snapshot_close", "15", "5"),
        ):
            sched.add_job(
                _rank_snapshot_safe,
                CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute, timezone="Asia/Shanghai"),
                id=jid, replace_existing=True, max_instances=1, coalesce=True,
            )

        # Daily summary push at 17:45 — after scoring has landed
        sched.add_job(
            _daily_push_safe,
            CronTrigger(hour=17, minute=45, timezone="Asia/Shanghai"),
            id="daily_push",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Optional: warmup once after startup
        if WARMUP_ON_START:
            run_at = dt.datetime.now() + dt.timedelta(seconds=WARMUP_DELAY_SEC)
            sched.add_job(
                _spawn_warmup_thread,
                DateTrigger(run_date=run_at),
                id="startup_warmup",
                replace_existing=True,
            )
            # Also pull LHB data on startup (after a delay to let DB init)
            sched.add_job(
                refresh_lhb,
                DateTrigger(run_date=run_at + dt.timedelta(seconds=30)),
                id="startup_lhb",
                replace_existing=True,
            )
            # Money flow + northbound on startup (seed 60 days)
            sched.add_job(
                refresh_moneyflow_northbound,
                DateTrigger(run_date=run_at + dt.timedelta(seconds=60)),
                id="startup_mf_nb",
                kwargs={"days": 60},
                replace_existing=True,
            )
            # Strategy score rebuild ~3 min after startup — assumes spot,
            # K-lines, LHB, moneyflow have all landed by then.
            sched.add_job(
                refresh_strategy_scores,
                DateTrigger(run_date=run_at + dt.timedelta(seconds=180)),
                id="startup_strategy_score",
                replace_existing=True,
            )
            log.info("[scheduler] startup warmup scheduled at %s (top_n=%d)", run_at, WARMUP_TOP_N)

        sched.start()
        _sched = sched
        log.info("[scheduler] started (warmup_on_start=%s)", WARMUP_ON_START)
        return sched
