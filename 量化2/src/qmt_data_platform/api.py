from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from qmt_data_platform import __version__
from qmt_data_platform.models import Bar, Period, Quote, SyncRequest, SyncResult
from qmt_data_platform.runtime import Runtime, build_runtime


def create_app(runtime: Optional[Runtime] = None) -> FastAPI:
    runtime = runtime or build_runtime()
    app = FastAPI(
        title="QMT Data Platform",
        version=__version__,
        description="Local market-data gateway for QMT/XtQuant.",
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "provider": runtime.provider.health(),
            "storage": runtime.store.stats(),
        }

    @app.post("/v1/market/sync", response_model=SyncResult)
    def sync_market_data(request: SyncRequest, incremental: bool = True) -> SyncResult:
        try:
            return runtime.service.sync(request, incremental=incremental)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/market/quotes", response_model=list[Quote])
    def get_quotes(symbols: str) -> list[Quote]:
        if not hasattr(runtime.provider, "get_quotes"):
            raise HTTPException(status_code=400, detail="当前数据源不支持实时行情快照")
        try:
            requested = [item.strip() for item in symbols.split(",") if item.strip()]
            return runtime.provider.get_quotes(requested)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/market/bars", response_model=list[Bar])
    def get_bars(
        symbol: str,
        period: Period = Period.D1,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = Query(default=1000, ge=1, le=50_000),
    ) -> list[dict[str, object]]:
        normalized = runtime.service._normalize_symbol(symbol)
        rows = runtime.store.query_bars(normalized, period, start, end, limit)
        rows.reverse()
        return rows

    @app.post("/v1/storage/export")
    def export_parquet() -> dict[str, str]:
        path = runtime.store.export_parquet(runtime.settings.parquet_root)
        return {"path": str(path.resolve())}

    return app


app = create_app()
