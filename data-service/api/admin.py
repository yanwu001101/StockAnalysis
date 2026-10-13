# -*- coding: utf-8 -*-
"""Admin / ops endpoints for the Settings page.

  GET  /api/admin/health-detail   — db / redis / spot snapshot / circuits status
  POST /api/admin/cache/clear     — wipe `ds:*` keys from Redis (or custom pattern)
  POST /api/admin/warmup          — trigger jobs/{postmarket,weekend,...}.run() in a thread
  GET  /api/admin/warmup/status   — poll job status (single by ?id=, or recent list)
"""
from __future__ import annotations
import datetime as dt
import threading
import time
import uuid

from flask import Blueprint, jsonify, request
from sqlalchemy import text

import cache
import db
import scheduler as scheduler_mod


bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# In-memory run tracker. Process-local, lost on restart — acceptable for an
# admin-triggered action that the user is actively watching.
_RUNS: dict[str, dict] = {}
_RUNS_LOCK = threading.Lock()
_RUNS_MAX = 50
_MAX_ACTIVE_RUNS = 2


# ---------------------------------------------------------------------------
# Health detail
# ---------------------------------------------------------------------------

# Tables we surface row-counts for. Keep alphabetical so the UI is stable.
_TABLES = [
    "stock_announcement", "stock_concept", "stock_dividend", "stock_fundamental",
    "stock_info", "stock_kline_daily", "stock_kline_weekly",
    "index_kline_daily", "industry_index_daily",
    "stock_lhb", "stock_moneyflow", "stock_northbound", "stock_shareholder",
    "user", "watchlist", "watchlist_group",
]


def _mysql_status() -> dict:
    eng = db.get_engine()
    if eng is None:
        return {"connected": False}
    rows: dict = {}
    try:
        with eng.connect() as conn:
            for t in _TABLES:
                try:
                    r = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).fetchone()
                    rows[t] = int(r[0]) if r else 0
                except Exception:
                    rows[t] = None  # table missing or other error
            from core.data_health import collect_freshness
            diagnostics = collect_freshness(conn, cache.get("spot"))
        return {"connected": True, "tables": rows, **diagnostics}
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _redis_status() -> dict:
    cli = cache._client()
    if not cli:
        return {"connected": False}
    try:
        info = cli.info("memory")
        keys = list(cli.scan_iter("ds:*", count=500))
        return {
            "connected": True,
            "ds_key_count": len(keys),
            "memory_used_bytes": int(info.get("used_memory", 0)),
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}


def _spot_status() -> dict:
    cli = cache._client()
    if not cli:
        return {"present": False}
    try:
        raw = cli.get("ds:spot")
        ttl = int(cli.ttl("ds:spot") or -2)
        if raw is None:
            return {"present": False, "ttl_seconds": ttl}
        spot = cache._decode(raw)
        rows = 0
        if spot is not None and hasattr(spot, "shape"):
            rows = int(spot.shape[0])
        return {
            "present": True,
            "ttl_seconds": ttl,
            "rows": rows,
            "size_bytes": len(raw),
        }
    except Exception as e:
        return {"present": False, "error": str(e)}


def _circuit_status() -> dict:
    try:
        from core import circuit
        return circuit.snapshot() if hasattr(circuit, "snapshot") else {}
    except Exception:
        return {}


@bp.route("/health-detail")
def health_detail():
    return jsonify({
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "mysql": _mysql_status(),
        "redis": _redis_status(),
        "spot": _spot_status(),
        "circuits": _circuit_status(),
    })


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

@bp.route("/cache/clear", methods=["POST"])
def cache_clear():
    body = request.get_json(silent=True) or {}
    pattern = (request.args.get("pattern") or body.get("pattern") or "ds:*").strip()
    if "*" not in pattern:
        # Safety: refuse to single-key delete via this path; use Redis directly.
        return jsonify({"deleted": 0, "error": "pattern must contain wildcard"}), 400
    if pattern in ("*", "**"):
        # Refuse to wipe the entire Redis instance — backend caches live here too.
        return jsonify({"deleted": 0, "error": "refusing to match all keys"}), 400
    cli = cache._client()
    if not cli:
        return jsonify({"deleted": 0, "error": "redis unavailable"}), 503
    try:
        deleted = 0
        for k in cli.scan_iter(pattern, count=500):
            cli.delete(k)
            deleted += 1
        return jsonify({"deleted": deleted, "pattern": pattern})
    except Exception as e:
        return jsonify({"deleted": 0, "error": str(e)}), 500


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------

_VALID_JOBS = ("postmarket", "weekend", "premarket", "intraday", "strategy_score")


def _trim_runs() -> None:
    """Bound terminal history only. Caller holds _RUNS_LOCK."""
    terminal = [(k, v) for k, v in _RUNS.items() if v.get("status") != "running"]
    by_start = sorted(terminal, key=lambda kv: kv[1].get("started_at") or "")
    for k, _ in by_start[:max(0, len(terminal) - _RUNS_MAX)]:
        _RUNS.pop(k, None)


@bp.route("/warmup", methods=["POST"])
def warmup_start():
    body = request.get_json(silent=True)
    if request.get_data() and not isinstance(body, dict):
        return jsonify({"error": "请求体必须是 JSON 对象"}), 400
    job = request.args.get("job") if "job" in request.args else (body or {}).get("job", "postmarket")
    if not isinstance(job, str):
        return jsonify({"error": "job 必须为字符串"}), 400
    job = job.strip()
    if job not in _VALID_JOBS:
        return jsonify({"error": f"unknown job: {job}", "valid": list(_VALID_JOBS)}), 400

    run_id = uuid.uuid4().hex[:12]
    started_at = dt.datetime.now().isoformat(timespec="seconds")
    with _RUNS_LOCK:
        active = [r for r in _RUNS.values() if r.get("status") == "running"]
        if any(r["job"] == job for r in active):
            return jsonify({"error": "同名任务仍在运行，请等待当前任务结束", "code": "WARMUP_ALREADY_RUNNING"}), 409
        if len(active) >= _MAX_ACTIVE_RUNS:
            return jsonify({"error": "数据任务并发已满，请稍后重试", "code": "WARMUP_CAPACITY"}), 429
        _RUNS[run_id] = {
            "id": run_id,
            "job": job,
            "status": "running",
            "started_at": started_at,
            "finished_at": None,
            "duration_s": None,
            "error": None,
        }
        _trim_runs()

    def _runner():
        start = time.monotonic()
        update = {}
        try:
            mod = __import__(f"jobs.{job}", fromlist=["run"])
            outcome = mod.run()
            valid = (isinstance(outcome, dict) and outcome.get("outcome_version") == 1
                     and outcome.get("status") in ("success", "partial", "failed", "skipped"))
            if valid:
                update = {"status": outcome["status"], "outcome": outcome,
                          "outcome_version": 1, "universe_size": outcome.get("universe_size"),
                          "row_semantics": outcome.get("row_semantics"),
                          "error": outcome.get("error"), "rows": outcome.get("rows"),
                          "reason": outcome.get("reason"), "steps": outcome.get("steps", [])}
            else:
                # Legacy None/int is not evidence of writes; e.g. an old
                # strategy-score job returns the total table size, not delta.
                update = {"status": "unknown", "rows": None,
                          "reason": "legacy_unverified",
                          "note": "任务已返回，但未提供可验证的本轮执行结果。"}
        except Exception as e:
            update = {"status": "failed", "error": str(e)[:500], "rows": None}
        finally:
            end = dt.datetime.now()
            with _RUNS_LOCK:
                _RUNS[run_id].update(update)
                _RUNS[run_id]["finished_at"] = end.isoformat(timespec="seconds")
                _RUNS[run_id]["duration_s"] = round(time.monotonic() - start, 1)
                _trim_runs()

    try:
        threading.Thread(target=_runner, daemon=True, name=f"warmup-{job}-{run_id}").start()
    except Exception:
        with _RUNS_LOCK:
            _RUNS.pop(run_id, None)
        return jsonify({"error": "数据任务启动失败，请稍后重试", "code": "WARMUP_UNAVAILABLE"}), 503
    return jsonify({"id": run_id, "job": job, "status": "running", "started_at": started_at})


@bp.route("/warmup/status")
def warmup_status():
    run_id = request.args.get("id")
    with _RUNS_LOCK:
        if run_id:
            entry = _RUNS.get(run_id)
            if not entry:
                return jsonify({"error": "not found"}), 404
            return jsonify(dict(entry))
        items = sorted(_RUNS.values(),
                       key=lambda x: x.get("started_at") or "",
                       reverse=True)[:20]
        return jsonify({"items": [dict(x) for x in items]})


# ---------------------------------------------------------------------------
# Scheduler — list registered APScheduler jobs (admin task center view)
# ---------------------------------------------------------------------------

@bp.route("/scheduler/jobs")
def scheduler_jobs():
    sched = getattr(scheduler_mod, "_sched", None)
    if sched is None:
        return jsonify({"jobs": [], "running": False, "valid_runs": list(_VALID_JOBS)})
    jobs = []
    for j in sched.get_jobs():
        jobs.append({
            "id": j.id,
            "next_run_time": str(j.next_run_time) if j.next_run_time else None,
            "trigger": str(j.trigger),
        })
    return jsonify({"jobs": jobs, "running": True, "valid_runs": list(_VALID_JOBS)})
