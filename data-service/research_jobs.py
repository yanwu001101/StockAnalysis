# -*- coding: utf-8 -*-
"""Research job runner：回测/因子检验等交互式长计算的后台执行。

与 api/admin.py 的 warmup 同一模式：线程池 + 进程内注册表（gunicorn 单 worker
保证单例）。此前回测/因子检验是同步 HTTP 请求，靠 RestTemplate 5 分钟超时硬撑，
慢一次就整个页面转圈 5 分钟；现在提交即返回 job_id，前端轮询取结果。

任务结果内存保留 1 小时 / 最多 40 份；服务重启即失——交互式计算重跑即可，
不做持久化（持久化的长任务见 factormine.jobs 的挖掘队列）。
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="research")
_KEEP = 40
_TTL_S = 3600.0


def submit(kind: str, fn) -> str:
    """提交任务：fn() -> result dict（异常视为 FAILED）。立即返回 job_id。"""
    job_id = f"RJ_{time.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "kind": kind, "status": "QUEUED",
                         "created_at": time.time(), "started_at": None,
                         "finished_at": None, "result": None, "error": None}
        _gc()
        job = _JOBS[job_id]

    def _run():
        with _LOCK:
            if job["id"] in _JOBS:
                job["status"] = "RUNNING"
                job["started_at"] = time.time()
        try:
            out = fn()
            with _LOCK:
                if job["id"] in _JOBS:
                    job["result"] = out
                    job["status"] = "DONE"
                    job["finished_at"] = time.time()
        except Exception as e:
            with _LOCK:
                if job["id"] in _JOBS:
                    job["error"] = str(e)[:500]
                    job["status"] = "FAILED"
                    job["finished_at"] = time.time()

    _POOL.submit(_run)
    return job_id


def get_job(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return None
        out = dict(job)
        out["elapsed_s"] = int(((out["finished_at"] or time.time()) - (out["started_at"] or out["created_at"])))
        return out


def _gc() -> None:
    now = time.time()
    for k in [k for k, j in _JOBS.items() if now - j["created_at"] > _TTL_S]:
        _JOBS.pop(k, None)
    while len(_JOBS) > _KEEP:
        _JOBS.pop(min(_JOBS, key=lambda k: _JOBS[k]["created_at"]))
