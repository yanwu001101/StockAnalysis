# -*- coding: utf-8 -*-
"""Research job runner：回测/因子检验等交互式长计算的后台执行。

与 api/admin.py 的 warmup 同一模式：线程池 + 进程内注册表（gunicorn 单 worker
保证单例）。此前回测/因子检验是同步 HTTP 请求，靠 RestTemplate 5 分钟超时硬撑，
慢一次就整个页面转圈 5 分钟；现在提交即返回 job_id，前端轮询取结果。

完成后的任务结果保留 1 小时 / 最多 40 份；最多 8 个运行或等待中的任务。
运行中的任务不会被结果清理驱逐；服务重启即失——交互式计算重跑即可，
不做持久化（持久化的长任务见 factormine.jobs 的挖掘队列）。
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from core.research_auth import validate_owner

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="research")
_KEEP = 40
_TTL_S = 3600.0
_MAX_ACTIVE = 8
_TERMINAL = frozenset({"DONE", "FAILED"})


class QueueFullError(RuntimeError):
    """Admission rejected before allocating a job or enqueuing computation."""


def submit(kind: str, fn, *, owner_id: int) -> str:
    """提交任务：fn() -> result dict（异常视为 FAILED）。立即返回 job_id。"""
    owner_id = validate_owner(owner_id)
    job_id = f"RJ_{time.strftime('%Y%m%d')}_{uuid.uuid4().hex}"
    with _LOCK:
        _gc()
        if sum(j["status"] not in _TERMINAL for j in _JOBS.values()) >= _MAX_ACTIVE:
            raise QueueFullError("研究任务队列已满，请稍后重试")
        _JOBS[job_id] = {"id": job_id, "owner_id": owner_id, "kind": kind, "status": "QUEUED",
                         "created_at": time.time(), "started_at": None,
                         "finished_at": None, "result": None, "error": None}
        job = _JOBS[job_id]

    def _run():
        with _LOCK:
            if job["id"] not in _JOBS:
                return
            job["status"] = "RUNNING"
            job["started_at"] = time.time()
        try:
            out = fn()
            with _LOCK:
                if job["id"] in _JOBS:
                    job["result"] = out
                    job["status"] = "DONE"
                    job["finished_at"] = time.time()
                    _gc()
        except Exception as e:
            with _LOCK:
                if job["id"] in _JOBS:
                    job["error"] = str(e)[:500]
                    job["status"] = "FAILED"
                    job["finished_at"] = time.time()
                    _gc()

    try:
        _POOL.submit(_run)
    except Exception:
        # A shut-down executor must not leave a permanently QUEUED phantom job.
        with _LOCK:
            _JOBS.pop(job_id, None)
        raise
    return job_id


def get_job(job_id: str, *, owner_id: int) -> dict | None:
    owner_id = validate_owner(owner_id)
    with _LOCK:
        _gc()
        job = _JOBS.get(job_id)
        # Missing and foreign jobs deliberately share the same result. Legacy
        # ownerless records are never assigned to the first caller or shared.
        if not job or job.get("owner_id") != owner_id:
            return None
        out = dict(job)
        out.pop("owner_id", None)
        end = out["finished_at"] if out["finished_at"] is not None else time.time()
        start = out["started_at"] if out["started_at"] is not None else out["created_at"]
        out["elapsed_s"] = max(0, int(end - start))
        return out


def _gc() -> None:
    """Caller holds _LOCK. TTL and retention apply only to completed results."""
    now = time.time()
    completed = [k for k, j in _JOBS.items() if j["status"] in _TERMINAL]
    for k in [k for k in completed if now - _JOBS[k]["finished_at"] >= _TTL_S]:
        _JOBS.pop(k, None)
    completed = sorted((k for k in completed if k in _JOBS),
                       key=lambda k: _JOBS[k]["finished_at"])
    for k in completed[:max(0, len(completed) - _KEEP)]:
        _JOBS.pop(k, None)
