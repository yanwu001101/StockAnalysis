"""Composition root.

The single place where concrete adapters are chosen and wired into the ports.
Everything above this file (api, agents, services) depends on abstractions;
everything below (infrastructure) knows about Redis/Mongo/AkShare.

Wiring rules enforced here:

* ``data_provider`` picks the market-data adapter; the caching decorator is
  always applied in front of it;
* ``persistence`` / ``cache_backend`` pick the store adapters, each with a
  safe fallback;
* exactly one ConnectionManager and one WebSocketProgressPublisher exist per
  process — FastAPI dependencies hand out references to them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import Settings, get_settings
from app.domain.ports import (
    CachePort,
    LLMPort,
    MarketDataPort,
    ProgressPublisherPort,
    TaskRepositoryPort,
)
from app.infrastructure.mongo_client import build_task_repository
from app.infrastructure.redis_client import build_cache
from app.services.analysis_service import AnalysisCommandService, AnalysisQueryService
from app.services.data_fetcher import (
    AkShareMarketDataAdapter,
    CachingMarketDataAdapter,
    SyntheticMarketDataAdapter,
)
from app.services.llm_factory import build_llm
from app.services.ws_manager import ConnectionManager, WebSocketProgressPublisher

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Container:
    """Everything the delivery layer needs, built once at startup."""

    settings: Settings
    market_data: MarketDataPort
    cache: CachePort
    llm: LLMPort
    repository: TaskRepositoryPort
    manager: ConnectionManager
    publisher: WebSocketProgressPublisher
    commands: AnalysisCommandService
    queries: AnalysisQueryService

    def health(self) -> dict[str, bool]:
        return {
            "redis": _safe_health(getattr(self.cache, "health", None)),
            "mongo": _safe_health(getattr(self.repository, "health", None)),
            "bus": _safe_health(getattr(self.publisher, "health", None)),
        }


def _safe_health(check) -> bool:  # type: ignore[no-untyped-def]
    if check is None:
        return True
    try:
        return bool(check())
    except Exception:  # noqa: BLE001
        return False


def build_container(settings: Settings | None = None) -> Container:
    resolved = settings or get_settings()

    cache = build_cache(resolved)

    if resolved.data_provider == "synthetic":
        market_data: MarketDataPort = SyntheticMarketDataAdapter()
        log.warning("data_provider=synthetic — deterministic offline market, do not use in prod")
    else:
        market_data = CachingMarketDataAdapter(
            inner=AkShareMarketDataAdapter(resolved), cache=cache, ttl_seconds=resolved.redis_ttl_seconds
        )

    llm = build_llm(resolved)
    repository = build_task_repository(resolved)
    manager = ConnectionManager(resolved)
    publisher = WebSocketProgressPublisher(manager=manager, settings=resolved)

    commands = AnalysisCommandService(
        repository=repository,
        market_data=market_data,
        llm=llm,
        progress=publisher,
        settings=resolved,
    )
    queries = AnalysisQueryService(repository=repository)

    return Container(
        settings=resolved,
        market_data=market_data,
        cache=cache,
        llm=llm,
        repository=repository,
        manager=manager,
        publisher=publisher,
        commands=commands,
        queries=queries,
    )


_container: Container | None = None


def init_container(settings: Settings | None = None) -> Container:
    """Build the process-wide container (called from the app lifespan)."""
    global _container
    _container = build_container(settings)
    return _container


def get_container() -> Container:
    if _container is None:
        return init_container()
    return _container


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


def get_command_service() -> AnalysisCommandService:
    return get_container().commands


def get_query_service() -> AnalysisQueryService:
    return get_container().queries


def get_manager() -> ConnectionManager:
    return get_container().manager


def get_publisher() -> ProgressPublisherPort:
    return get_container().publisher


def get_market_data() -> MarketDataPort:
    return get_container().market_data


def get_repository() -> TaskRepositoryPort:
    return get_container().repository
