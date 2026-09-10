from datetime import datetime, timedelta

from qmt_data_platform.models import SyncRequest, SyncResult
from qmt_data_platform.providers.base import MarketDataProvider
from qmt_data_platform.storage import MarketDataStore


class MarketDataService:
    def __init__(self, provider: MarketDataProvider, store: MarketDataStore) -> None:
        self.provider = provider
        self.store = store

    def sync(self, request: SyncRequest, incremental: bool = True) -> SyncResult:
        started_at = datetime.now()
        symbols = [self._normalize_symbol(symbol) for symbol in request.symbols]
        bars = []
        for symbol in symbols:
            start = request.start
            if incremental and start is None:
                latest = self.store.latest_timestamp(symbol, request.period)
                if latest:
                    start = latest - timedelta(days=3 if request.period.value == "1d" else 1)
            bars.extend(
                self.provider.get_bars(
                    [symbol], request.period, start, request.end, request.adjust
                )
            )
        written_rows = self.store.upsert_bars(bars)
        finished_at = datetime.now()
        self.store.record_sync(
            self.provider.name,
            request.period,
            len(symbols),
            len(bars),
            written_rows,
            started_at,
            finished_at,
        )
        return SyncResult(
            provider=self.provider.name,
            requested_symbols=len(symbols),
            received_rows=len(bars),
            written_rows=written_rows,
            started_at=started_at,
            finished_at=finished_at,
        )

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        from qmt_data_platform.models import Bar, Period

        return Bar(
            symbol=symbol,
            period=Period.D1,
            timestamp=datetime.now(),
            open=0,
            high=0,
            low=0,
            close=0,
            volume=0,
            amount=0,
        ).symbol

