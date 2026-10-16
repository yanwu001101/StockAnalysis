"""LangGraph state and the dependency bundle injected into it.

The state is a ``TypedDict`` — LangGraph's native shape, fully type-checkable,
and it keeps the graph free of ``Any``. Adapters live inside the state (they
are constructed once per task and never serialised), which lets every node be
a plain ``state -> partial-state`` function.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import TypedDict

from app.config import Settings, get_settings
from app.domain.models import (
    BacktestOverrides,
    Bar,
    DebateEntry,
    FundamentalSnapshot,
    NewsItem,
    QuantVerdictPayload,
    RiskAssessment,
    SentimentSnapshot,
    TechnicalSnapshot,
)
from app.domain.ports import LLMPort, MarketDataPort, ProgressPublisherPort
from app.domain.results import BacktestResult
from app.services.signal_rule import SignalDecision


@dataclass(frozen=True, slots=True)
class GraphDeps:
    """Everything a node is allowed to touch from the outside world."""

    market_data: MarketDataPort
    llm: LLMPort
    progress: ProgressPublisherPort
    settings: Settings | None = None
    backtest_overrides: BacktestOverrides | None = None

    def resolved(self) -> Settings:
        return self.settings or get_settings()


class GraphState(TypedDict, total=False):
    # ---- identity ----
    task_id: str
    symbol: str
    deps: GraphDeps

    # ---- market data ----
    bars: list[Bar]
    benchmark_bars: list[Bar]
    benchmark_closes: dict[date, float]
    fundamentals: FundamentalSnapshot | None
    news: list[NewsItem]

    # ---- analysts ----
    sentiment: SentimentSnapshot | None
    technical: TechnicalSnapshot | None
    debate: list[DebateEntry]
    debate_round: int
    debate_max_rounds: int
    risk: RiskAssessment | None

    # ---- deterministic layer ----
    decisions: tuple[SignalDecision, ...]
    backtest_overrides: BacktestOverrides | None
    backtest: BacktestResult | None

    # ---- output ----
    # Declared explicitly: LangGraph silently drops updates for keys that are
    # not part of the state schema, so a missing declaration here would make
    # translation_node's payload vanish without any error.
    verdict: QuantVerdictPayload | None
    warnings: list[str]
    failed: bool
    error: str | None
