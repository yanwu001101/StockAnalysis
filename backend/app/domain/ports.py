"""Hexagonal ports.

The domain depends on these protocols and nothing else. Adapters in
``app.services`` / ``app.infrastructure`` implement them; the composition
root (``app.api.deps``) wires the implementations in.

All ports are synchronous on purpose: the domain (including the backtest
engine) is deterministic CPU/IO-bound code and must never know about the
event loop. The adapters bridge to asyncio where needed.
"""
from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from app.domain.models import (
    AgentProgressPayload,
    AnalysisTask,
    Bar,
    FundamentalSnapshot,
    MarketOverview,
    NewsItem,
    QuantVerdictPayload,
    SystemStats,
)


@runtime_checkable
class MarketDataPort(Protocol):
    """Read-only view of the market. The only way the domain touches AkShare."""

    def fetch_daily_bars(self, symbol: str, lookback_days: int) -> Sequence[Bar]:
        """Adjusted (qfq) daily bars, ascending by date, volumes in shares."""
        ...

    def fetch_benchmark_bars(self, symbol: str, lookback_days: int) -> Sequence[Bar]:
        ...

    def fetch_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        ...

    def fetch_news(self, symbol: str, limit: int) -> Sequence[NewsItem]:
        ...

    def fetch_market_overview(self, benchmark_symbol: str) -> MarketOverview:
        """Benchmark snapshot + breadth; unavailable fields stay None."""
        ...


@runtime_checkable
class LLMPort(Protocol):
    """Qualitative reasoning only. Never called for a number."""

    def complete(self, system: str, user: str) -> str:
        """Return free-form text. Implementations must be side-effect free."""
        ...


@runtime_checkable
class ProgressPublisherPort(Protocol):
    """Streams agent progress to whoever is subscribed to a task."""

    def publish_progress(self, payload: AgentProgressPayload) -> None:
        ...

    def publish_verdict(self, task_id: str, payload: QuantVerdictPayload) -> None:
        ...

    def publish_error(self, task_id: str, message: str) -> None:
        ...


@runtime_checkable
class TaskRepositoryPort(Protocol):
    """CQRS write side (commands) and read side (queries) both land here."""

    def create(self, task: AnalysisTask) -> AnalysisTask:
        ...

    def save(self, task: AnalysisTask) -> AnalysisTask:
        ...

    def get(self, task_id: str) -> AnalysisTask | None:
        ...

    def stats(self) -> SystemStats:
        """Fleet counters for the command center."""
        ...


@runtime_checkable
class CachePort(Protocol):
    """Small, bounded, TTL-scoped key/value store for market data."""

    def get(self, key: str) -> str | None:
        ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        ...
