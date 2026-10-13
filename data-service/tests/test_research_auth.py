"""Research gateway signature and object ownership regressions; no live service."""
import json
import re
from types import SimpleNamespace

import pytest
from flask import Flask
from pydantic import SecretStr

from config import settings
from core import research_auth as auth
import research_jobs as jobs
from api.research_jobs import bp

SECRET = "test-only-research-secret-0123456789abcdef"
NOW = 1_700_000_000
PATH = "/api/async/alphalab-backtest"


@pytest.mark.parametrize("method,path,body,expected", [
    ("POST", PATH, '{"expression":"rank(close)","top_n":5}',
     "5aaeb70038a5e0e51cc1a402a5496e6e399f28b55a328cb6bc93fb345c60aba3"),
    ("POST", PATH, '{"expression":"rank(close)","label":"中文策略"}',
     "20099cdacee0da5ce51e8656869218b16d03f572de60fdfbe439da3d24bc8239"),
    ("GET", "/api/async/jobs/RJ_20261012_0123456789abcdef0123456789abcdef", "",
     "8971f2e05b890ddf45b8a21453028a27d652e86973d95a26e9b06a0b1a9f2b0f"),
])
def test_cross_language_fixed_vectors(method, path, body, expected):
    # Identical constants also live in Java ResearchJobAuthTest.
    assert auth.sign_context(SECRET, 42, NOW, method, path, body.encode("utf-8")) == expected


def headers(owner=42, timestamp=NOW, method="POST", path=PATH, body=b"{}"):
    return {auth.OWNER_HEADER: str(owner), auth.TIME_HEADER: str(timestamp),
            auth.SIGNATURE_HEADER: auth.sign_context(SECRET, owner, timestamp, method, path, body)}


@pytest.mark.parametrize("secret", [None, "", "short", " " * 32, auth.PUBLIC_DEFAULT, " " + auth.PUBLIC_DEFAULT + "\n"])
def test_missing_short_and_public_default_keys_fail_closed(secret):
    with pytest.raises(auth.AuthUnavailable):
        auth.validate_secret(secret)


@pytest.mark.parametrize("change", ["owner", "timestamp", "method", "path", "body", "signature"])
def test_all_context_components_are_signed(change):
    signed = headers()
    method, path, body = "POST", PATH, b"{}"
    if change == "owner": signed[auth.OWNER_HEADER] = "43"
    elif change == "timestamp": signed[auth.TIME_HEADER] = str(NOW + 1)
    elif change == "method": method = "GET"
    elif change == "path": path = "/api/async/backtest"
    elif change == "body": body = b'{"owner_id":99}'
    else: signed[auth.SIGNATURE_HEADER] = "0" * 64
    with pytest.raises(auth.InvalidContext):
        auth.verify_context(SECRET, signed, method, path, body, now=NOW)


@pytest.mark.parametrize("offset", [-61, 61])
def test_expired_or_excessively_future_context_is_rejected(offset):
    with pytest.raises(auth.InvalidContext):
        auth.verify_context(SECRET, headers(timestamp=NOW + offset), "POST", PATH, b"{}", now=NOW)


@pytest.mark.parametrize("owner", [None, True, 0, -1, "42", 2**63])
def test_store_requires_a_real_positive_long_owner(owner, monkeypatch):
    monkeypatch.setattr(jobs, "_JOBS", {})
    with pytest.raises(auth.InvalidContext):
        jobs.submit("backtest", lambda: {}, owner_id=owner)
    with pytest.raises(auth.InvalidContext):
        jobs.get_job("missing", owner_id=owner)
    assert jobs._JOBS == {}


def test_store_has_no_ownerless_compatibility_overload():
    with pytest.raises(TypeError): jobs.submit("backtest", lambda: {})
    with pytest.raises(TypeError): jobs.get_job("missing")


@pytest.fixture
def client(monkeypatch):
    import api.research_jobs as api
    pending = []
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "_POOL", SimpleNamespace(submit=lambda work: pending.append(work)))
    monkeypatch.setattr(auth.time, "time", lambda: NOW)
    monkeypatch.setattr(settings.research_auth, "jwt_secret", SecretStr(SECRET))
    monkeypatch.setattr(api.importlib, "import_module", lambda _: SimpleNamespace(
        run_backtest_payload=lambda body: {"request": body}))
    app = Flask(__name__)
    app.register_blueprint(bp)
    return app.test_client(), pending


def request(client, method, path, owner=42, payload=None):
    raw = b"" if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return client.open(path, method=method, data=raw, content_type="application/json",
                       headers=headers(owner=owner, method=method, path=path, body=raw))


def test_unsigned_and_bare_owner_headers_cannot_bypass_java(client):
    http, pending = client
    for supplied in ({}, {auth.OWNER_HEADER: "42"}, {auth.OWNER_HEADER: "42", auth.SIGNATURE_HEADER: "0" * 64}):
        response = http.post("/api/async/backtest", json={}, headers=supplied)
        assert response.status_code == 401
    assert not pending and not jobs._JOBS


def test_body_owner_is_not_authority_and_foreign_reads_match_missing_reads(client):
    http, pending = client
    created = request(http, "POST", "/api/async/backtest", owner=42, payload={"owner_id": 99, "userId": 99})
    assert created.status_code == 200
    job_id = created.json["job_id"]
    assert re.fullmatch(r"RJ_[0-9]{8}_[0-9a-f]{32}", job_id)
    assert jobs._JOBS[job_id]["owner_id"] == 42
    pending.pop()()
    own = request(http, "GET", "/api/async/jobs/" + job_id, owner=42)
    assert own.status_code == 200 and own.json["status"] == "DONE"
    other = request(http, "GET", "/api/async/jobs/" + job_id, owner=99)
    missing = request(http, "GET", "/api/async/jobs/missing", owner=99)
    assert other.status_code == missing.status_code == 404
    assert other.json == missing.json
    assert "result" not in other.json and "owner_id" not in other.json


def test_legacy_ownerless_records_are_unreadable(client):
    http, _ = client
    job_id = jobs.submit("backtest", lambda: {}, owner_id=42)
    jobs._JOBS[job_id].pop("owner_id")
    assert request(http, "GET", "/api/async/jobs/" + job_id).status_code == 404


def test_queued_and_running_foreign_jobs_are_also_hidden(client):
    http, _ = client
    job_id = jobs.submit("backtest", lambda: {}, owner_id=42)
    for status in ("QUEUED", "RUNNING", "FAILED"):
        jobs._JOBS[job_id]["status"] = status
        if status == "FAILED": jobs._JOBS[job_id]["finished_at"] = NOW
        assert request(http, "GET", "/api/async/jobs/" + job_id, owner=7).status_code == 404


@pytest.mark.parametrize("secret", ["", auth.PUBLIC_DEFAULT])
def test_configuration_failure_is_explicit_503_without_secret_disclosure(client, monkeypatch, secret):
    http, pending = client
    monkeypatch.setattr(settings.research_auth, "jwt_secret", SecretStr(secret))
    response = http.post("/api/async/backtest", json={})
    assert response.status_code == 503
    assert response.json["code"] == "RESEARCH_AUTH_UNAVAILABLE"
    assert auth.PUBLIC_DEFAULT not in response.get_data(as_text=True)
    assert not pending


def test_signed_overlarge_request_is_rejected_without_enqueue(client):
    http, pending = client
    raw = b"x" * (auth.MAX_BODY_BYTES + 1)
    path = "/api/async/backtest"
    response = http.post(path, data=raw, headers=headers(method="POST", path=path, body=raw))
    assert response.status_code == 413
    assert not pending


def test_deeply_nested_signed_json_is_a_400_not_an_unhandled_500(client):
    http, pending = client
    raw = ("[" * 1200 + "0" + "]" * 1200).encode("utf-8")
    path = "/api/async/backtest"
    response = http.post(path, data=raw, headers=headers(method="POST", path=path, body=raw))
    assert response.status_code == 400
    assert response.json["code"] == "INVALID_PAYLOAD"
    assert not pending
