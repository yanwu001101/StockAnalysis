# -*- coding: utf-8 -*-
"""因子挖掘任务系统：MySQL 持久化队列 + 单 worker 线程 + 逐候选 checkpoint。

状态机：QUEUED → RUNNING → COMPLETED / FAILED / CANCELLED / PAUSED。
断点续跑：候选与结果全部逐条落库（fm_factor 即 checkpoint），PAUSED/FAILED
任务 resume 后只处理库里剩余的 PENDING 候选，绝不从 0 重跑。
服务重启时由 api/factormine.py 导入侧调用 mark_interrupted_jobs()，把遗留
RUNNING 标记为 PAUSED（可继续）。
"""
from __future__ import annotations

import datetime as dt
import json
import threading
import uuid

from core.trace import logger

from factormine import repo
from factormine.pipeline import (CancelRequested, Control, MiningConfig, MiningPipeline,
                                 PauseRequested)

_queue_evt = threading.Event()
_lock = threading.Lock()
_controls: dict[str, Control] = {}
_worker_started = False


def ensure_worker() -> None:
    global _worker_started
    with _lock:
        if _worker_started:
            return
        t = threading.Thread(target=_worker_loop, name="factormine-worker", daemon=True)
        t.start()
        _worker_started = True


def submit(config_raw: dict) -> tuple[str | None, str | None]:
    """创建挖掘任务。返回 (job_id, error)。"""
    try:
        cfg = MiningConfig(config_raw)
    except Exception as e:
        return None, f"配置无效: {e}"
    if cfg.end_date <= cfg.start_date:
        return None, "结束日期必须晚于开始日期"
    if (cfg.end_date - cfg.start_date).days > 366 * 8:
        return None, "研究区间过长（上限 8 年）——请缩小时间范围"
    if not cfg.horizons:
        return None, "至少选择一个预测周期"
    if not (10 <= cfg.budget <= 10000):
        return None, "候选因子预算须在 10 ~ 10000 之间"
    if cfg.start_date < dt.date(2015, 1, 1):
        return None, "开始日期过早（K 线数据自 2015 年起可用）"
    job_id = f"FMJ_{dt.date.today().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
    repo.create_job(job_id, cfg.public())
    ensure_worker()
    _queue_evt.set()
    return job_id, None


def pause(job_id: str) -> tuple[bool, str | None]:
    ctl = _controls.get(job_id)
    if ctl:
        ctl.pause = True
        return True, None
    j = repo.get_job(job_id)
    if j and j["status"] == "QUEUED":
        repo.update_job(job_id, status="PAUSED", note="已暂停（排队中）")
        return True, None
    return False, "任务不在运行/排队状态"


def resume(job_id: str) -> tuple[bool, str | None]:
    j = repo.get_job(job_id)
    if not j:
        return False, "任务不存在"
    if j["status"] not in ("PAUSED", "FAILED"):
        return False, f"当前状态 {j['status']} 不可继续"
    repo.update_job(job_id, status="QUEUED", error=None, note="从断点继续")
    ensure_worker()
    _queue_evt.set()
    return True, None


def cancel(job_id: str) -> tuple[bool, str | None]:
    ctl = _controls.get(job_id)
    if ctl:
        ctl.cancel = True
    j = repo.get_job(job_id)
    if j and j["status"] in ("QUEUED", "PAUSED"):
        repo.update_job(job_id, status="CANCELLED", finished_at=dt.datetime.now(), note="已取消")
        return True, None
    if not ctl:
        return False, "任务不在运行/排队状态"
    return True, None


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------

def _worker_loop() -> None:
    logger.info("[factormine] worker started")
    while True:
        _queue_evt.wait(timeout=30)
        _queue_evt.clear()
        while True:
            job = _next_queued()
            if not job:
                break
            _run_job(job)


def _next_queued() -> dict | None:
    for j in repo.list_jobs(limit=50):
        if j["status"] == "QUEUED":
            return j
    return None


def _run_job(job: dict) -> None:
    job_id = job["id"]
    ctl = Control()
    with _lock:
        _controls[job_id] = ctl
    try:
        full = repo.get_job(job_id) or {}
        cfg = MiningConfig(json.loads(full.get("config_json") or "{}"))
        repo.update_job(job_id, status="RUNNING", started_at=dt.datetime.now(),
                        note=None, error=None)
        pipe = MiningPipeline(job_id, cfg, ctl)
        pipe.prepare()
        repo.update_progress(job_id, pipe.progress, "GENERATE")
        pipe.ensure_candidates()
        pipe.quick_stage()
        reps = pipe.dedup_stage()
        repo.update_progress(job_id, pipe.progress, "VALIDATE")
        pipe.validate_stage(reps)
        repo.update_job(job_id, status="COMPLETED", phase="DONE",
                        finished_at=dt.datetime.now())
        logger.info("[factormine] job %s completed: %s", job_id, repo.funnel(job_id))
    except CancelRequested:
        repo.update_job(job_id, status="CANCELLED", phase="CANCELLED",
                        finished_at=dt.datetime.now(), note="已取消")
    except PauseRequested:
        repo.update_job(job_id, status="PAUSED", phase="PAUSED",
                        note="已暂停，可从断点继续")
    except Exception as e:
        logger.exception("[factormine] job %s failed", job_id)
        repo.update_job(job_id, status="FAILED", error=str(e)[:2000],
                        finished_at=dt.datetime.now())
    finally:
        with _lock:
            _controls.pop(job_id, None)
