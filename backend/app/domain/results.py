"""Computation results produced by the application services.

Kept in the domain (hexagonal rule) so that the API layer can depend on
result objects without importing pandas/numpy-typed service internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.domain.models import (
    ChartMarker,
    MetricStatus,
    MetricStatusMap,
    QuantMetricsDTO,
    Trade,
)

_METRIC_KEYS = (
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "total_return",
    "alpha",
    "beta",
)


@dataclass(frozen=True, slots=True)
class EquityPoint:
    date: date
    value: float


@dataclass(frozen=True, slots=True)
class MetricsResult:
    """The six headline metrics plus their provenance.

    A metric that could not be computed carries 0.0 **and** a non-VALID
    status. Consumers must never read the number without the status.
    """

    total_return: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    statuses: dict[str, MetricStatus] = field(
        default_factory=lambda: {key: MetricStatus.VALID for key in _METRIC_KEYS}
    )
    trade_count: int = 0
    sample_size: int = 0
    benchmark_coverage: float = 0.0
    basis: str = "CLOSED_TRADES"

    def to_dto(self) -> QuantMetricsDTO:
        return QuantMetricsDTO(
            sharpe_ratio=self.sharpe_ratio,
            max_drawdown=self.max_drawdown,
            win_rate=self.win_rate,
            total_return=self.total_return,
            alpha=self.alpha,
            beta=self.beta,
        )

    def to_status_map(self) -> MetricStatusMap:
        return MetricStatusMap(**self.statuses)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    symbol: str
    trades: list[Trade]
    equity_curve: list[EquityPoint]
    candles: list[list[float]]  # [open, close, low, high] — ECharts order
    dates: list[str]
    markers: list[ChartMarker]
    metrics: MetricsResult

    @property
    def trade_count(self) -> int:
        return len(self.trades)
