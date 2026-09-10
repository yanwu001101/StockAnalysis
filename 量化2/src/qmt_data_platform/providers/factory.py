import importlib.util

from qmt_data_platform.config import Settings
from qmt_data_platform.providers.astock import AStockDataProvider
from qmt_data_platform.providers.base import MarketDataProvider
from qmt_data_platform.providers.mock import MockMarketDataProvider
from qmt_data_platform.providers.xtquant import XtQuantMarketDataProvider


def create_provider(settings: Settings) -> MarketDataProvider:
    if settings.provider == "mock":
        return MockMarketDataProvider()
    if settings.provider == "astock":
        return AStockDataProvider()
    if settings.provider == "xtquant":
        return XtQuantMarketDataProvider(settings.qmt_path)
    if importlib.util.find_spec("xtquant") is not None:
        return XtQuantMarketDataProvider(settings.qmt_path)
    return AStockDataProvider()
