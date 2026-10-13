"""Deterministic queue/expiry tests: no worker threads, DB, or live calculations."""
import json
from types import SimpleNamespace
from pydantic import SecretStr
from config import settings
from core import research_auth

import pytest
from flask import Flask

import research_jobs as jobs
from api.research_jobs import bp


TEST_SECRET = "test-only-research-secret-0123456789abcdef"


def submit(kind, fn):
    return jobs.submit(kind, fn, owner_id=1)


def get_job(job_id):
    return jobs.get_job(job_id, owner_id=1)


class PendingExecutor:
    def __init__(self):
        self.pending = []

    def submit(self, fn):
        self.pending.append(fn)

    def run_next(self):
        self.pending.pop(0)()


@pytest.fixture
def runner(monkeypatch):
    clock = [100.0]
    pool = PendingExecutor()
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "_POOL", pool)
    monkeypatch.setattr(jobs, "_KEEP", 2)
    monkeypatch.setattr(jobs, "_MAX_ACTIVE", 3)
    monkeypatch.setattr(jobs, "_TTL_S", 60)
    monkeypatch.setattr(jobs.time, "time", lambda: clock[0])
    return clock, pool


def test_capacity_rejects_without_orphan_or_executor_submission(runner):
    _, pool = runner
    ids = [submit("factorlab", lambda: {}) for _ in range(3)]
    with pytest.raises(jobs.QueueFullError):
        submit("backtest", lambda: {})
    assert set(jobs._JOBS) == set(ids)
    assert len(pool.pending) == 3
    pool.run_next()
    assert get_job(submit("backtest", lambda: {}))["status"] == "QUEUED"


def test_active_job_survives_ttl_and_completed_retention(runner):
    clock, pool = runner
    active = submit("backtest", lambda: {})
    # Keep the first job queued while other jobs complete and exceed result retention.
    for i in range(4):
        submit("factorlab", lambda: {"ic": 0})
        pool.pending.pop()()
        clock[0] += 30
    assert get_job(active)["status"] == "QUEUED"
    assert len(jobs._JOBS) <= 3
    pool.run_next()
    assert get_job(active)["status"] == "DONE"


def test_running_job_is_not_expired_and_ttl_starts_at_completion(runner):
    clock, pool = runner

    def work():
        clock[0] += 100
        assert get_job(job_id)["status"] == "RUNNING"
        return {"ic": None, "error": "coverage insufficient"}

    job_id = submit("factorlab", work)
    pool.run_next()
    result = get_job(job_id)
    assert result["status"] == "DONE"
    assert result["elapsed_s"] == 100
    assert result["result"]["ic"] is None
    clock[0] += 59
    assert get_job(job_id) is not None
    clock[0] += 1
    assert get_job(job_id) is None  # reads enforce expiry even without new submits


def test_failed_job_preserves_error_and_releases_capacity(runner):
    _, pool = runner

    def fail():
        raise ValueError("calculation failed")

    job_id = submit("factorlab", fail)
    pool.run_next()
    result = get_job(job_id)
    assert result["status"] == "FAILED"
    assert result["error"] == "calculation failed"
    assert result["result"] is None


def test_executor_rejection_rolls_back_registry(runner, monkeypatch):
    def reject(fn):
        raise RuntimeError("executor shut down")

    monkeypatch.setattr(jobs._POOL, "submit", reject)
    with pytest.raises(RuntimeError):
        submit("backtest", lambda: {})
    assert jobs._JOBS == {}


@pytest.fixture
def client(runner, monkeypatch):
    import api.research_jobs as api
    monkeypatch.setattr(api.importlib, "import_module", lambda _: SimpleNamespace(
        run_backtest_payload=lambda body: {"request": body}))
    app = Flask(__name__)
    app.register_blueprint(bp)
    monkeypatch.setattr(settings.research_auth, "jwt_secret", SecretStr(TEST_SECRET))
    raw_client = app.test_client()
    def signed(method, path, **kwargs):
        raw = json.dumps(kwargs.pop("json"), ensure_ascii=False).encode("utf-8") if "json" in kwargs else kwargs.pop("data", b"")
        if isinstance(raw, str): raw = raw.encode("utf-8")
        timestamp = int(jobs.time.time())
        headers = {research_auth.OWNER_HEADER: "1", research_auth.TIME_HEADER: str(timestamp),
                   research_auth.SIGNATURE_HEADER: research_auth.sign_context(TEST_SECRET, 1, timestamp, method, path, raw)}
        kwargs.setdefault("content_type", "application/json")
        return raw_client.open(path, method=method, data=raw, headers=headers, **kwargs)
    return SimpleNamespace(post=lambda path, **kw: signed("POST", path, **kw),
                           get=lambda path, **kw: signed("GET", path, **kw))


def test_api_reports_capacity_with_retry_after(client):
    for _ in range(3):
        assert client.post("/api/async/backtest", json={}).status_code == 200
    response = client.post("/api/async/backtest", json={})
    assert response.status_code == 429
    assert response.json["code"] == "RESEARCH_QUEUE_FULL"
    assert response.headers["Retry-After"] == "5"


@pytest.mark.parametrize("body", ["[]", "null", "false", "123", "{broken"])
def test_api_rejects_non_object_payload_without_enqueue(client, body):
    response = client.post("/api/async/backtest", data=body, content_type="application/json")
    assert response.status_code == 400
    assert jobs._JOBS == {}


def test_api_service_failure_and_missing_job(client, monkeypatch):
    def reject(fn):
        raise RuntimeError("executor shut down")
    monkeypatch.setattr(jobs._POOL, "submit", reject)
    assert client.post("/api/async/backtest", json={}).status_code == 503
    assert client.get("/api/async/jobs/missing").status_code == 404
    assert client.post("/api/async/unknown", json={}).status_code == 404


def test_api_result_contract_preserves_zero_and_null(client, runner):
    _, pool = runner
    response = client.post("/api/async/backtest", json={"zero": 0, "missing": None})
    pool.run_next()
    result = client.get("/api/async/jobs/" + response.json["job_id"])
    assert result.json["status"] == "DONE"
    assert result.json["result"]["request"] == {"zero": 0, "missing": None}
