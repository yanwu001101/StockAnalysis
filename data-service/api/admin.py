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


# ---------------------------------------------------------------------------
# Health detail
# ---------------------------------------------------------------------------

# Tables we surface row-counts for. Keep alphabetical so the UI is stable.
_TABLES = [
    "stock_announcement", "stock_concept", "stock_dividend", "stock_fundamental",
    "stock_info", "stock_kline_daily", "stock_kline_minute", "stock_kline_weekly",
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
        return {"connected": True, "tables": rows}
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
    """Keep the in-memory run history bounded."""
    if len(_RUNS) <= _RUNS_MAX:
        return
    drop_n = len(_RUNS) - _RUNS_MAX
    by_start = sorted(_RUNS.items(), key=lambda kv: kv[1].get("started_at") or "")
    for k, _ in by_start[:drop_n]:
        _RUNS.pop(k, None)


@bp.route("/warmup", methods=["POST"])
def warmup_start():
    body = request.get_json(silent=True) or {}
    job = (request.args.get("job") or body.get("job") or "postmarket").strip()
    if job not in _VALID_JOBS:
        return jsonify({"error": f"unknown job: {job}", "valid": list(_VALID_JOBS)}), 400

    run_id = uuid.uuid4().hex[:12]
    started_at = dt.datetime.now().isoformat(timespec="seconds")
    with _RUNS_LOCK:
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
        start = dt.datetime.now()
        try:
            mod = __import__(f"jobs.{job}", fromlist=["run"])
            mod.run()
            with _RUNS_LOCK:
                _RUNS[run_id]["status"] = "success"
        except Exception as e:
            with _RUNS_LOCK:
                _RUNS[run_id]["status"] = "failed"
                _RUNS[run_id]["error"] = str(e)[:500]
        finally:
            end = dt.datetime.now()
            with _RUNS_LOCK:
                _RUNS[run_id]["finished_at"] = end.isoformat(timespec="seconds")
                _RUNS[run_id]["duration_s"] = round((end - start).total_seconds(), 1)

    threading.Thread(target=_runner, daemon=True, name=f"warmup-{job}-{run_id}").start()
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
        return jsonify({"jobs": [], "running": False})
    jobs = []
    for j in sched.get_jobs():
        jobs.append({
            "id": j.id,
            "next_run_time": str(j.next_run_time) if j.next_run_time else None,
            "trigger": str(j.trigger),
        })
    return jsonify({"jobs": jobs, "running": True, "valid_runs": list(_VALID_JOBS)})
