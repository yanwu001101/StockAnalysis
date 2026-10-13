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
import pandas as pd

import cache
import eastmoney
import kline_repo
import db
import spot_meta
from pipelines import spot as spot_pipe
from pipelines import lhb as lhb_pipe
from pipelines._helpers import gather_codes
from pipelines.kline import _to_legacy_chinese as _to_legacy
from pipelines import moneyflow as mf_pipe
from pipelines import northbound as nb_pipe

log = logging.getLogger(__name__)

WARMUP_ON_START = os.getenv("WARMUP_ON_START", "false").lower() in ("1", "true", "yes")
WARMUP_DELAY_SEC = int(os.getenv("WARMUP_DELAY_SEC", "60"))
# 0 = 全市场活跃股（成交额>0）。历史值 300 会让榜外股票永远拿不到每日增量,
# 因子/回测宇宙被悄悄截断——覆盖度必须显式跟住现货快照。
WARMUP_TOP_N = int(os.getenv("WARMUP_TOP_N", "0"))
WARMUP_BATCH_SIZE = int(os.getenv("WARMUP_BATCH_SIZE", "50"))

_sched: BackgroundScheduler | None = None
_lock = threading.Lock()


import notifier


def _chunks(seq, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def _spot_ok(df) -> bool:
    """宇宙按市值排序:没有市值列的残帧会把 top800 排错,宁可不留。"""
    return (df is not None and not df.empty and "总市值_亿" in df.columns
            and len(df) >= 4000)


def _fetch_spot_chain() -> pd.DataFrame:
    """全市场快照多源链。每个源各自护栏——单源抛错(东财被墙即抛
    Server disconnected)绝不能掀掉整条链。腾讯批量行情带总市值且无
    指纹墙,排首位;东财两源留作参考口径(行业/量比更全)的兜底。"""
    df = pd.DataFrame()
    try:
        import tx_realtime
        df = tx_realtime.fetch_all_spot()
        if df is not None and not df.empty:
            spot_meta.record("tencent:qt.gtimg.cn", len(df))
    except Exception as e:
        log.warning("[scheduler] tx_realtime spot failed: %s", e)
        df = pd.DataFrame()
    if not _spot_ok(df):
        try:
            import em_realtime
            d2 = em_realtime.fetch_all_spot()
            if d2 is not None and not d2.empty and "代码" in d2.columns:
                d2["代码"] = d2["代码"].astype(str).str.zfill(6)
                spot_meta.record("eastmoney:" + str(d2.attrs.get("source_host") or "push2delay"), len(d2))
                if _spot_ok(d2):
                    df = d2
        except Exception as e:
            log.debug("[scheduler] em_realtime spot failed: %s", e)
    if not _spot_ok(df):
        try:
            d3 = eastmoney.fetch_all_spot()
            if d3 is not None and not d3.empty:
                spot_meta.record("eastmoney:aiohttp", len(d3))
                if _spot_ok(d3):
                    df = d3
        except Exception as e:
            log.debug("[scheduler] eastmoney aiohttp spot failed: %s", e)
    return df


def refresh_spot_cache():
    # 抓新后直接覆盖写(不预删缓存:全量抓取需 ~20-30s,预删会让并发 API 请求
    # 也触发冷抓取,行情接口被拖到 30s+)。东财 clist 被墙后主源是腾讯批量行情,
    # 每分钟全量打 qt.gtimg.cn 会被限流,调度侧已同步放宽到 5 分钟一档。
    try:
        df = _fetch_spot_chain()
        if df is not None and not df.empty:
            cache.set("spot", df, 300)
            log.info("[scheduler] spot cache refreshed: %d rows", len(df))
        else:
            log.warning("[scheduler] spot chain returned no usable frame, cache untouched")
        try:
            import asyncio
            v2 = asyncio.run(spot_pipe.run())
            if v2 is not None and not v2.empty:
                log.info("[scheduler] spot_v2 cache refreshed: %d rows", len(v2))
        except Exception as e:
            log.warning("[scheduler] refresh spot_v2 failed: %s", e)
    except Exception as e:
        log.warning("[scheduler] refresh_spot_cache failed: %s", e)


def _kline_fallback(codes: list[str], count: int) -> int:
    """legacy aiohttp 主路漏掉的股票，用 httpx 客户端的第二条腿补。

    每只按 新浪→东财 顺序取（两个源都是 period='daily' 的日线；新浪与库内
    口径实测逐 bar 一致，东财 fqt=1 放最后以免开接缝）。
    """
    import asyncio

    from sources.eastmoney import default as em_src
    from sources.sina import default as sina_src

    async def _run():
        res = await gather_codes(
            list(codes),
            lambda c: _first_nonempty([sina_src(), em_src()], c, count),
            concurrency=6,
        )
        total = 0
        for code, df in res.items():
            if df is not None and not df.empty:
                written = kline_repo.upsert_daily(code, _to_legacy(df))
                required = kline_repo.BASIS_REFRESH_REQUIRED.get((kline_repo.DAILY_TABLE, code))
                if not written and required:
                    full = await _first_nonempty([sina_src(), em_src()], code, max(1000, required))
                    if full is not None and not full.empty:
                        written = kline_repo.upsert_daily(code, _to_legacy(full))
                total += written
        return total

    return asyncio.run(_run())


async def _first_nonempty(sources, code: str, count: int):
    import pandas as pd

    for src in sources:
        try:
            df = await src.fetch_kline(code, period="daily", count=count)
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        except Exception as e:
            log.debug("[scheduler] kline fallback src=%s %s err=%s", src.name, code, e)
    return None


def warmup_klines(top_n: int = WARMUP_TOP_N, count: int = 250):
    # Pull spot, then concurrently upsert daily/weekly K-lines for the universe
    # (top_n<=0 = 全部活跃股) into MySQL. Safe on second-run (incremental upsert).
    if db.get_engine() is None:
        log.info("[scheduler] MySQL unavailable; skipping warmup")
        return
    try:
        # 全市场快照:warm 缓存优先,否则走多源链(腾讯主源,单源抛错不掀整链)。
        # 历史上 aiohttp 源一抛 Server disconnected 整个日K增量就被跳过,因子日K停在几天前。
        spot = cache.get("spot")
        if (spot is None or getattr(spot, "empty", True)
                or "总市值_亿" not in getattr(spot, "columns", [])):
            spot = _fetch_spot_chain()
        if spot is None or getattr(spot, "empty", True):
            log.warning("[scheduler] warmup: empty spot, skipping")
            return
        sort_col = "总市值_亿" if "总市值_亿" in spot.columns else None
        if sort_col:
            spot = spot.sort_values(sort_col, ascending=False, na_position="last")
        codes = spot["代码"].astype(str).str.zfill(6)
        # 停牌/无成交股票当日无新棒,且会稀释宇宙——与决策宇宙同口径过滤
        if "成交额" in spot.columns:
            amt = pd.to_numeric(spot["成交额"], errors="coerce").fillna(0)
            codes = codes[amt.values > 0]
        codes = codes.tolist()
        if top_n and top_n > 0:
            codes = codes[:top_n]
        log.info("[scheduler] warmup start: %d codes (count=%d)", len(codes), count)

        total_daily = 0
        total_weekly = 0
        t0 = time.time()
        for batch in _chunks(codes, WARMUP_BATCH_SIZE):
            # Daily — legacy aiohttp 主路（单股 push2his 未被墙）
            daily_map = eastmoney.batch_klines(batch, klt=101, count=count)
            for code, df in daily_map.items():
                if df is not None and not df.empty:
                    total_daily += kline_repo.upsert_with_basis_refresh(code, df)
            # Weekly (every code, less frequent)
            weekly_map = eastmoney.batch_klines(batch, klt=102, count=max(count // 5, 60))
            for code, df in weekly_map.items():
                if df is not None and not df.empty:
                    total_weekly += kline_repo.upsert_with_basis_refresh(code, df, klt=102)
            # 兜底：主路漏掉的股票走第二条腿。legacy 内部已按 腾讯→新浪→同花顺
            # 依次尝试,整批失败通常是 aiohttp 通道被限——换 httpx 客户端的源再打一次。
            # 顺序按复权基准实测排：sources.sina 与库内逐 bar 完全一致(600 根 0 差),
            # 东财 httpx(fqt=1) 放最后,避免在腾讯口径序列上开新接缝。
            # DataFrame has no truth value: `not frame` aborts the entire warmup
            # after its first batch, even when the fetch succeeded.
            missing = [c for c in batch
                       if daily_map.get(c) is None or daily_map[c].empty]
            if missing:
                try:
                    n = _kline_fallback(missing, count)
                    total_daily += n
                    if n:
                        log.info("[scheduler] kline fallback served %d rows for %d codes", n, len(missing))
                except Exception as e:
                    log.warning("[scheduler] kline fallback failed: %s", e)
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
    if df is None or df.empty or "总市值_亿" not in df.columns:
        try:
            import tx_realtime
            df = tx_realtime.fetch_all_spot()
        except Exception:
            df = None
    if df is None or df.empty or "总市值_亿" not in df.columns:
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


def _get_amount_codes(top_n: int = 600) -> list[str]:
    """按成交额取活跃股作资金流宇宙——主力净额集中在活跃股上,市值口径
    会把低换手权重股排进来、把高换手中盘股排出去。"""
    df = cache.get("spot")
    if df is None or df.empty or "成交额" not in getattr(df, "columns", []):
        try:
            import tx_realtime
            df = tx_realtime.fetch_all_spot()
        except Exception:
            df = None
    if df is None or df.empty or "成交额" not in df.columns or "代码" not in df.columns:
        return _get_universe_codes(300)
    d = pd.DataFrame({
        "code": df["代码"].astype(str).str.zfill(6),
        "amt": pd.to_numeric(df["成交额"], errors="coerce"),
    }).dropna()
    return d.sort_values("amt", ascending=False)["code"].head(top_n).tolist()


def refresh_moneyflow_northbound(days: int = 5):
    """Pull money flow + northbound holdings for top-N universe.

    days defaults to 5 (incremental). First-run warmup passes 60 to seed history."""
    import asyncio
    if db.get_engine() is None:
        log.info("[scheduler] MySQL unavailable; skipping moneyflow/northbound")
        return
    mf_codes = _get_amount_codes(600)
    if not mf_codes:
        log.warning("[scheduler] empty universe; skipping moneyflow/northbound")
        return
    try:
        asyncio.run(mf_pipe.run_batch(mf_codes, days=days))
        log.info("[scheduler] moneyflow refresh done (days=%d, codes=%d)", days, len(mf_codes))
    except Exception as e:
        log.warning("[scheduler] moneyflow refresh failed: %s", e)
        notifier.job_failed("资金流刷新", str(e))
    nb_codes = _get_universe_codes(300)
    try:
        asyncio.run(nb_pipe.run_batch(nb_codes, days=days))
        log.info("[scheduler] northbound refresh done (days=%d)", days)
    except Exception as e:
        log.warning("[scheduler] northbound refresh failed: %s", e)
        notifier.job_failed("北向资金刷新", str(e))


def _industry_index_safe():
    """申万二级行业指数日线：行业动量策略的 as-of 数据源（表内已有则只增量）。"""
    try:
        import asyncio
        from pipelines import industry_index as ind_pipe
        res = asyncio.run(ind_pipe.run())
        log.info("[scheduler] industry index refresh: %s", res)
    except Exception as e:
        log.warning("[scheduler] industry index refresh failed: %s", e)
        notifier.job_failed("行业指数刷新", str(e))


def _index_kline_safe():
    """基准指数日线（沪深300/中证500）。这些 bar 同时是回测器的交易日历,
    停更会让最近窗口的会话表被静默截断,超额收益也变成跟旧曲线比。"""
    try:
        import asyncio
        from pipelines import index_kline as idx_pipe
        n = asyncio.run(idx_pipe.run())
        log.info("[scheduler] index kline refresh: %d rows", n)
    except Exception as e:
        log.warning("[scheduler] index kline refresh failed: %s", e)
        notifier.job_failed("基准指数日线刷新", str(e))


def _stock_list_safe():
    """交易所官方清单刷新:补新股/改名/补齐缺失行业。周日 20:00 跑,周一开盘生效。"""
    try:
        from jobs import stock_list
        stats = stock_list.run()
        log.info("[scheduler] stock_list refresh: %s", stats)
    except Exception as e:
        log.warning("[scheduler] stock_list refresh failed: %s", e)
        notifier.job_failed("股票基础清单刷新", str(e))


def _industry_fill_safe():
    """每日 30 只的小配额补行业:新股入库后不必等整周,又不会突发打爆单股行情。"""
    try:
        from jobs import stock_list
        n = stock_list.fill_only(fill_limit=30)
        if n:
            log.info("[scheduler] industry fill done: %d codes", n)
    except Exception as e:
        log.warning("[scheduler] industry fill failed: %s", e)


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

        # 基准指数日线 16:20——先于 16:30 的全市场增量,回测日历与基准曲线当天可用
        sched.add_job(
            _index_kline_safe,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=20, timezone="Asia/Shanghai"),
            id="index_kline_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # Spot refresh during trading hours (5 min: full-market batch quotes
        # now take ~20-30s via tencent; 1-min cadence would hammer the host)
        sched.add_job(
            refresh_spot_cache,
            CronTrigger(hour="9-15", minute="*/5", timezone="Asia/Shanghai"),
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

        # 行业指数（申万二级）16:22——行业动量策略的排名面板依赖它
        sched.add_job(
            _industry_index_safe,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=22, timezone="Asia/Shanghai"),
            id="industry_index_refresh",
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

        # 股票基础清单（新股/改名/行业补齐）——周日 20:00，周一开盘前生效
        sched.add_job(
            _stock_list_safe,
            CronTrigger(day_of_week="sun", hour=20, minute=0, timezone="Asia/Shanghai"),
            id="stock_list_refresh",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

        # 缺失行业的每日小配额补齐（30 只 / 1s 间隔，开盘前跑）
        sched.add_job(
            _industry_fill_safe,
            CronTrigger(day_of_week="mon-fri", hour=8, minute=40, timezone="Asia/Shanghai"),
            id="industry_fill",
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
