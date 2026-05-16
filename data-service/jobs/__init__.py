# -*- coding: utf-8 -*-
"""APScheduler registration.

Replaces the old monolithic scheduler.py. Each job is a thin wrapper around a
pipeline; the scheduler just registers cron triggers and lets APScheduler's
max_instances=1 + coalesce settings handle overlap.
"""
from __future__ import annotations
import threading
import datetime as dt

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from config import settings
from core.trace import logger
from jobs import intraday, postmarket, premarket, weekend


_sched: BackgroundScheduler | None = None
_lock = threading.Lock()


def start() -> BackgroundScheduler:
    global _sched
    with _lock:
        if _sched is not None:
            return _sched
        sched = BackgroundScheduler(timezone=settings.tz)
        tz = settings.tz

        sched.add_job(
            premarket.run,
            CronTrigger(day_of_week="mon-fri", hour=8, minute=30, timezone=tz),
            id="premarket",
            replace_existing=True,
            max_instances=1, coalesce=True,
        )
        sched.add_job(
            intraday.run,
            CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/5", timezone=tz),
            id="intraday",
            replace_existing=True,
            max_instances=1, coalesce=True,
        )
        sched.add_job(
            postmarket.run,
            CronTrigger(day_of_week="mon-fri", hour=16, minute=30, timezone=tz),
            id="postmarket",
            replace_existing=True,
            max_instances=1, coalesce=True,
        )
        sched.add_job(
            weekend.run,
            CronTrigger(day_of_week="sat", hour=10, minute=0, timezone=tz),
            id="weekend",
            replace_existing=True,
            max_instances=1, coalesce=True,
        )

        if settings.sched.warmup_on_start:
            run_at = dt.datetime.now() + dt.timedelta(seconds=settings.sched.warmup_delay_sec)
            sched.add_job(
                postmarket.run,
                DateTrigger(run_date=run_at),
                id="startup_warmup",
                replace_existing=True,
            )
            logger.info("[jobs] startup warmup scheduled at %s", run_at)

        sched.start()
        _sched = sched
        logger.info("[jobs] scheduler started: premarket / intraday / postmarket / weekend")
        return sched
