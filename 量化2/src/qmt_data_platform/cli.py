from datetime import datetime
from typing import Optional

import typer

from qmt_data_platform.api import create_app
from qmt_data_platform.models import Adjust, Period, SyncRequest
from qmt_data_platform.runtime import build_runtime

app = typer.Typer(no_args_is_help=True, help="QMT/XtQuant data platform operations.")


@app.command()
def doctor() -> None:
    """Check provider and local storage readiness."""
    runtime = build_runtime()
    typer.echo({"provider": runtime.provider.health(), "storage": runtime.store.stats()})


@app.command("sync")
def sync_data(
    symbols: str = typer.Argument(..., help="Comma-separated symbols, e.g. 000001.SZ,600000.SH"),
    period: Period = Period.D1,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    adjust: Adjust = Adjust.NONE,
    incremental: bool = True,
) -> None:
    """Download and persist market bars."""
    runtime = build_runtime()
    request = SyncRequest(
        symbols=[symbol.strip() for symbol in symbols.split(",") if symbol.strip()],
        period=period,
        start=start,
        end=end,
        adjust=adjust,
    )
    typer.echo(runtime.service.sync(request, incremental=incremental).model_dump_json(indent=2))


@app.command()
def export() -> None:
    """Export all normalized bars to compressed Parquet."""
    runtime = build_runtime()
    typer.echo(runtime.store.export_parquet(runtime.settings.parquet_root).resolve())


@app.command()
def serve(
    host: Optional[str] = None,
    port: Optional[int] = None,
    reload: bool = False,
) -> None:
    """Start the REST API and Swagger UI."""
    import uvicorn

    runtime = build_runtime()
    uvicorn.run(
        create_app(runtime),
        host=host or runtime.settings.api_host,
        port=port or runtime.settings.api_port,
        reload=reload,
    )


if __name__ == "__main__":
    app()
