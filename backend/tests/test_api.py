"""HTTP smoke: analyze -> (not ready or ready) -> verdict, plus health."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from app.api import deps
from app.config import get_settings
from app.main import create_app


def _client() -> TestClient:
    get_settings.cache_clear()
    deps._container = None
    import os

    os.environ["DATA_PROVIDER"] = "synthetic"
    os.environ["PERSISTENCE"] = "memory"
    os.environ["CACHE_BACKEND"] = "memory"
    os.environ["LLM_PROVIDER"] = "heuristic"
    app = create_app()
    return TestClient(app)


def test_analyze_then_poll_verdict() -> None:
    with _client() as client:
        response = client.post("/api/v1/analyze", json={"symbol": "600519"})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["taskId"] and body["symbol"] == "600519"

        task_id = body["taskId"]
        verdict = None
        for _ in range(100):
            result = client.get(f"/api/v1/result/{task_id}")
            if result.status_code == 200:
                verdict = result.json()
                break
            assert result.status_code == 409
            time.sleep(0.1)
        assert verdict is not None, "analysis never completed"
        assert set(verdict["rawMetrics"].keys()) == {
            "sharpeRatio",
            "maxDrawdown",
            "winRate",
            "totalReturn",
            "alpha",
            "beta",
        }
        assert verdict["humanVerdict"]["colorClass"].startswith("text-")
        assert verdict["symbol"] == "600519"
        assert len(verdict["dates"]) == len(verdict["candles"])

        status = client.get(f"/api/v1/tasks/{task_id}")
        assert status.status_code == 200
        assert status.json()["status"] == "COMPLETED"


def test_result_unknown_task_is_404() -> None:
    with _client() as client:
        response = client.get("/api/v1/result/nope")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TASK_NOT_FOUND"


def test_symbol_normalisation() -> None:
    with _client() as client:
        for raw, expected in [
            ("600519", "600519"),
            ("sh600519", "600519"),
            ("sz000001", "000001"),
            ("600519.SH", "600519"),
        ]:
            response = client.post("/api/v1/analyze", json={"symbol": raw})
            assert response.status_code == 201, (raw, response.text)
            assert response.json()["symbol"] == expected

        bad = client.post("/api/v1/analyze", json={"symbol": "abc"})
        assert bad.status_code == 422


def test_health_and_ready() -> None:
    with _client() as client:
        assert client.get("/health").json() == {"status": "ok"}
        ready = client.get("/ready").json()
        assert ready["status"] in {"ready", "degraded"}


def test_analyze_accepts_backtest_overrides() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/analyze",
            json={
                "symbol": "600519",
                "backtest": {
                    "initialCapital": 50000,
                    "commissionRate": 0.001,
                    "slippage": 0.002,
                },
            },
        )
        # 注意：请求体按字段名（snake_case 或 camelCase 均可，populate_by_name）
        assert response.status_code == 201, response.text


def test_analyze_rejects_inverted_date_window() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/analyze",
            json={
                "symbol": "600519",
                "backtest": {
                    "startDate": "2025-06-01",
                    "endDate": "2025-01-01",
                },
            },
        )
        assert response.status_code == 422


def test_stats_endpoint() -> None:
    with _client() as client:
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        body = response.json()
        assert {"total", "running", "completed", "failed", "successRate"} <= set(body)


def test_market_overview_endpoint() -> None:
    with _client() as client:
        response = client.get("/api/v1/market/overview")
        assert response.status_code == 200
        body = response.json()
        assert body["benchmarkSymbol"]
        assert isinstance(body["breadthAvailable"], bool)
