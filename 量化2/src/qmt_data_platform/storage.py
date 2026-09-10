from datetime import datetime
from pathlib import Path
from typing import Optional

import duckdb

from qmt_data_platform.models import Bar, Period


class MarketDataStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def connect(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.database_path))

    def _initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS market_bars (
                    symbol VARCHAR NOT NULL,
                    period VARCHAR NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    open DOUBLE NOT NULL,
                    high DOUBLE NOT NULL,
                    low DOUBLE NOT NULL,
                    close DOUBLE NOT NULL,
                    volume DOUBLE NOT NULL,
                    amount DOUBLE NOT NULL,
                    pre_close DOUBLE,
                    source VARCHAR NOT NULL,
                    ingested_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
                    PRIMARY KEY (symbol, period, timestamp)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id UUID PRIMARY KEY DEFAULT uuid(),
                    provider VARCHAR NOT NULL,
                    period VARCHAR NOT NULL,
                    symbol_count INTEGER NOT NULL,
                    received_rows BIGINT NOT NULL,
                    written_rows BIGINT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    finished_at TIMESTAMP NOT NULL
                )
                """
            )

    def upsert_bars(self, bars: list[Bar]) -> int:
        if not bars:
            return 0
        values = [
            (
                bar.symbol,
                bar.period.value,
                bar.timestamp,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                bar.amount,
                bar.pre_close,
                bar.source,
            )
            for bar in bars
        ]
        with self.connect() as connection:
            before = connection.execute("SELECT count(*) FROM market_bars").fetchone()[0]
            connection.executemany(
                """
                INSERT INTO market_bars (
                    symbol, period, timestamp, open, high, low, close,
                    volume, amount, pre_close, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (symbol, period, timestamp) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    amount = excluded.amount,
                    pre_close = excluded.pre_close,
                    source = excluded.source,
                    ingested_at = now()
                """,
                values,
            )
            after = connection.execute("SELECT count(*) FROM market_bars").fetchone()[0]
        return after - before

    def query_bars(
        self,
        symbol: str,
        period: Period,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 5000,
    ) -> list[dict[str, object]]:
        filters = ["symbol = ?", "period = ?"]
        parameters: list[object] = [symbol, period.value]
        if start:
            filters.append("timestamp >= ?")
            parameters.append(start)
        if end:
            filters.append("timestamp <= ?")
            parameters.append(end)
        parameters.append(limit)
        query = f"""
            SELECT symbol, period, timestamp, open, high, low, close,
                   volume, amount, pre_close, source
            FROM market_bars
            WHERE {' AND '.join(filters)}
            ORDER BY timestamp DESC
            LIMIT ?
        """
        with self.connect() as connection:
            cursor = connection.execute(query, parameters)
            columns = [description[0] for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def latest_timestamp(self, symbol: str, period: Period) -> Optional[datetime]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT max(timestamp) FROM market_bars WHERE symbol = ? AND period = ?",
                [symbol, period.value],
            ).fetchone()
        return row[0]

    def record_sync(
        self,
        provider: str,
        period: Period,
        symbol_count: int,
        received_rows: int,
        written_rows: int,
        started_at: datetime,
        finished_at: datetime,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO sync_runs (
                    provider, period, symbol_count, received_rows, written_rows,
                    started_at, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    provider,
                    period.value,
                    symbol_count,
                    received_rows,
                    written_rows,
                    started_at,
                    finished_at,
                ],
            )

    def stats(self) -> dict[str, object]:
        with self.connect() as connection:
            bars, symbols, earliest, latest = connection.execute(
                """
                SELECT count(*), count(DISTINCT symbol), min(timestamp), max(timestamp)
                FROM market_bars
                """
            ).fetchone()
        return {
            "database": str(self.database_path),
            "bars": bars,
            "symbols": symbols,
            "earliest": earliest,
            "latest": latest,
        }

    def export_parquet(self, root: Path) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        target = root / "market_bars.parquet"
        escaped = str(target).replace("'", "''")
        with self.connect() as connection:
            connection.execute(
                f"COPY (SELECT * FROM market_bars ORDER BY symbol, period, timestamp) "
                f"TO '{escaped}' (FORMAT PARQUET, COMPRESSION ZSTD)"
            )
        return target
