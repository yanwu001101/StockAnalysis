import hashlib
import random
from datetime import datetime, time, timedelta
from typing import Optional

from qmt_data_platform.models import Adjust, Bar, Period
from qmt_data_platform.providers.base import MarketDataProvider


class MockMarketDataProvider(MarketDataProvider):
    name = "mock"

    def health(self) -> dict[str, object]:
        return {"provider": self.name, "ready": True, "mode": "simulation"}

    def get_bars(
        self,
        symbols: list[str],
        period: Period,
        start: Optional[datetime],
        end: Optional[datetime],
        adjust: Adjust,
    ) -> list[Bar]:
        del adjust
        end = end or datetime.now()
        start = start or end - timedelta(days=30)
        rows: list[Bar] = []
        for symbol in symbols:
            seed = int(hashlib.sha256(symbol.encode("ascii")).hexdigest()[:8], 16)
            randomizer = random.Random(seed)
            price = 8 + seed % 9000 / 100
            for timestamp in self._timestamps(start, end, period):
                change = randomizer.gauss(0, 0.012)
                open_price = price
                close = max(0.01, open_price * (1 + change))
                high = max(open_price, close) * (1 + randomizer.random() * 0.008)
                low = min(open_price, close) * (1 - randomizer.random() * 0.008)
                volume = float(randomizer.randint(50_000, 8_000_000))
                rows.append(
                    Bar(
                        symbol=symbol,
                        period=period,
                        timestamp=timestamp,
                        open=round(open_price, 4),
                        high=round(high, 4),
                        low=round(low, 4),
                        close=round(close, 4),
                        volume=volume,
                        amount=round(volume * (open_price + close) / 2, 2),
                        pre_close=round(price, 4),
                        source=self.name,
                    )
                )
                price = close
        return rows

    @staticmethod
    def _timestamps(start: datetime, end: datetime, period: Period) -> list[datetime]:
        if period == Period.D1:
            current = datetime.combine(start.date(), time(15))
            step = timedelta(days=1)
        else:
            minutes = {Period.M1: 1, Period.M5: 5, Period.M15: 15, Period.M30: 30, Period.H1: 60}
            if period not in minutes:
                raise ValueError(f"Mock provider does not support {period.value}")
            current = start.replace(second=0, microsecond=0)
            step = timedelta(minutes=minutes[period])
        timestamps = []
        while current <= end:
            if current.weekday() < 5:
                timestamps.append(current)
            current += step
        return timestamps
