"""Admin runs use synthetic modules/threads, never scheduler execution."""
import sys
from types import SimpleNamespace

import pytest
from flask import Flask

from api import admin


@pytest.fixture
def client(monkeypatch):
    pending = []
    class Thread:
        def __init__(self, target, **kwargs):
            self.target = target
        def start(self):
            pending.append(self.target)
    monkeypatch.setattr(admin.threading, "Thread", Thread)
    monkeypatch.setattr(admin, "_RUNS", {})
    monkeypatch.setattr(admin, "_RUNS_MAX", 2)
    app = Flask(__name__)
    app.register_blueprint(admin.bp)
    return app.test_client(), pending


def fake_job(monkeypatch, result):
    monkeypatch.setitem(sys.modules, "jobs.postmarket", SimpleNamespace(run=lambda: result))


@pytest.mark.parametrize("status", ["success", "partial", "failed", "skipped"])
def test_returned_outcome_not_exception_alone_sets_status(client, monkeypatch, status):
    http, pending = client
    result = {"outcome_version": 1, "status": status, "rows": 0, "universe_size": 2,
              "steps": [{"name": "daily", "status": status, "rows": 0}], "error": "source failed"}
    fake_job(monkeypatch, result)
    run_id = http.post("/api/admin/warmup").json["id"]
    assert http.get(f"/api/admin/warmup/status?id={run_id}").json["status"] == "running"
    pending.pop()()
    out = http.get(f"/api/admin/warmup/status?id={run_id}").json
    assert out["status"] == status
    assert out["outcome"] == result
    assert out["steps"] == result["steps"]
    assert out["finished_at"] and out["duration_s"] >= 0


@pytest.mark.parametrize("result", [None, 100000, {"status": "success"}, {"outcome_version": 9, "status": "success"}])
def test_legacy_results_are_unverified_not_success_or_row_delta(client, monkeypatch, result):
    http, pending = client
    fake_job(monkeypatch, result)
    run_id = http.post("/api/admin/warmup").json["id"]
    pending.pop()()
    out = http.get(f"/api/admin/warmup/status?id={run_id}").json
    assert out["status"] == "unknown"
    assert out["rows"] is None


def test_admission_duplicate_capacity_and_running_retention(client, monkeypatch):
    http, pending = client
    first = http.post("/api/admin/warmup").json["id"]
    assert http.post("/api/admin/warmup").status_code == 409
    second = http.post("/api/admin/warmup?job=weekend").json["id"]
    assert http.post("/api/admin/warmup?job=intraday").status_code == 429
    assert len(pending) == 2
    for i in range(10):
        admin._RUNS[str(i)] = {"status": "success", "started_at": str(i)}
    with admin._RUNS_LOCK:
        admin._trim_runs()
    assert first in admin._RUNS and second in admin._RUNS
    assert len(admin._RUNS) == 4


def test_start_failure_rolls_back_phantom_and_job_exception_is_failed(client, monkeypatch):
    http, pending = client
    def fail():
        raise RuntimeError("provider offline")
    monkeypatch.setitem(sys.modules, "jobs.postmarket", SimpleNamespace(run=fail))
    run_id = http.post("/api/admin/warmup").json["id"]
    pending.pop()()
    assert http.get(f"/api/admin/warmup/status?id={run_id}").json["error"] == "provider offline"
    monkeypatch.setattr(admin.threading.Thread, "start", lambda self: fail())
    assert http.post("/api/admin/warmup").status_code == 503
    assert list(admin._RUNS) == [run_id]


@pytest.mark.parametrize("body", [[], ["postmarket"], 3, {"job": 42}, {"job": 0},
                                  {"job": False}, {"job": []}, {"job": None}])
def test_invalid_body_is_400_not_500(client, body):
    http, _ = client
    assert http.post("/api/admin/warmup", json=body).status_code == 400


@pytest.mark.parametrize("body", ['{"job":', 'null', 'garbage'])
def test_malformed_json_never_starts_default_job(client, body):
    http, pending = client
    assert http.post("/api/admin/warmup", data=body, content_type="application/json").status_code == 400
    assert not pending and not admin._RUNS


def test_manual_jobs_remain_available_when_scheduler_is_stopped(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(admin.scheduler_mod, "_sched", None)
    out = http.get("/api/admin/scheduler/jobs").json
    assert out["running"] is False
    assert out["valid_runs"] == list(admin._VALID_JOBS)
