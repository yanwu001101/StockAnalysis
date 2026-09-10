from dataclasses import dataclass
from typing import Optional

from qmt_data_platform.config import Settings, get_settings
from qmt_data_platform.providers import create_provider
from qmt_data_platform.providers.base import MarketDataProvider
from qmt_data_platform.service import MarketDataService
from qmt_data_platform.storage import MarketDataStore


@dataclass
class Runtime:
    settings: Settings
    provider: MarketDataProvider
    store: MarketDataStore
    service: MarketDataService


def build_runtime(settings: Optional[Settings] = None) -> Runtime:
    settings = settings or get_settings()
    settings.ensure_directories()
    provider = create_provider(settings)
    store = MarketDataStore(settings.database_path)
    return Runtime(settings, provider, store, MarketDataService(provider, store))
