from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from qmt_data_platform.models import Adjust, Bar, Period


class MarketDataProvider(ABC):
    name: str

    @abstractmethod
    def health(self) -> dict[str, object]:
        """Return provider connectivity and installation state."""

    @abstractmethod
    def get_bars(
        self,
        symbols: list[str],
        period: Period,
        start: Optional[datetime],
        end: Optional[datetime],
        adjust: Adjust,
    ) -> list[Bar]:
        """Fetch normalized bars for the requested instruments."""
