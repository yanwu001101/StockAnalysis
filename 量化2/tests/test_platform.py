from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from qmt_data_platform.api import create_app
from qmt_data_platform.config import Settings
from qmt_data_platform.models import Period, SyncRequest
from qmt_data_platform.runtime import build_runtime


def make_runtime(tmp_path: Path):
    settings = Settings(
        provider="mock",
        database_path=tmp_path / "market.duckdb",
        parquet_root=tmp_path / "parquet",
    )
    return build_runtime(settings)


def test_sync_is_idempotent(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    request = SyncRequest(
        symbols=["000001"],
        period=Period.D1,
        start=datetime(2025, 1, 1),
        end=datetime(2025, 1, 10, 23, 59),
    )

    first = runtime.service.sync(request, incremental=False)
    second = runtime.service.sync(request, incremental=False)

    assert first.received_rows == 8
    assert first.written_rows == 8
    assert second.received_rows == 8
    assert second.written_rows == 0
    assert runtime.store.stats()["bars"] == 8


def test_api_sync_and_query(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    client = TestClient(create_app(runtime))

    response = client.post(
        "/v1/market/sync?incremental=false",
        json={
            "symbols": ["600000"],
            "period": "1d",
            "start": "2025-01-01T00:00:00",
            "end": "2025-01-05T23:59:59",
            "adjust": "none",
        },
    )
    assert response.status_code == 200
    assert response.json()["written_rows"] == 3

    response = client.get("/v1/market/bars", params={"symbol": "600000", "period": "1d"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 3
    assert rows[0]["symbol"] == "600000.SH"
    assert rows[0]["timestamp"] < rows[-1]["timestamp"]


def test_export_parquet(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path)
    runtime.service.sync(
        SyncRequest(
            symbols=["000001.SZ"],
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 2, 23, 59),
        ),
        incremental=False,
    )

    target = runtime.store.export_parquet(runtime.settings.parquet_root)
    assert target.exists()
    assert target.stat().st_size > 0

