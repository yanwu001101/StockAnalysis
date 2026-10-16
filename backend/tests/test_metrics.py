"""Metrics — sharpe / drawdown / win rate / alpha / beta arithmetic."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.domain.models import MetricStatus
from app.domain.results import EquityPoint
from app.services.metrics import compute_metrics


def _curve(values: list[float], start: dt.date | None = None) -> list[EquityPoint]:
    day = start or dt.date(2025, 1, 2)
    points: list[EquityPoint] = []
    for value in values:
        while day.weekday() >= 5:
            day += dt.timedelta(days=1)
        points.append(EquityPoint(date=day, value=value))
        day += dt.timedelta(days=1)
    return points


class TestMetrics:
    def test_total_return_and_max_drawdown(self) -> None:
        # 100 -> 120 -> 90 -> 100: 总收益 0%，最大回撤 90/120-1 = -25%
        result = compute_metrics(_curve([100.0, 120.0, 90.0, 100.0]))
        assert result.total_return == 0.0
        assert result.max_drawdown == -0.25
        assert result.statuses["max_drawdown"] is MetricStatus.VALID

    def test_win_rate_from_closed_trades(self) -> None:
        result = compute_metrics(
            _curve([100.0, 110.0, 105.0]),
            trades=[(10.0, 12.0), (11.0, 10.5)],
        )
        assert result.win_rate == 0.5
        assert result.basis == "CLOSED_TRADES"

    def test_win_rate_falls_back_to_up_days(self) -> None:
        # 100 -> 101 -> 100.5 -> 99：3 个日收益中 1 正 2 负
        result = compute_metrics(_curve([100.0, 101.0, 100.5, 99.0]))
        assert result.basis == "EQUITY_UP_DAYS"
        assert result.win_rate == pytest.approx(1 / 3)

    def test_alpha_beta_requires_benchmark(self) -> None:
        result = compute_metrics(_curve([100.0, 101.0, 102.0, 103.0]))
        assert result.statuses["alpha"] is MetricStatus.INSUFFICIENT_DATA
        assert result.statuses["beta"] is MetricStatus.INSUFFICIENT_DATA
        assert result.alpha == 0.0  # 数值为 0 但状态说明不可计算

    def test_alpha_beta_with_benchmark(self) -> None:
        # 30+ 个观测点，且基准逐日单调上行 -> beta/alpha 可计算
        values = [100.0 + index * 1.5 for index in range(30)]
        curve = _curve(values)
        benchmark = {
            point.date: 1000.0 + index * 10.0 for index, point in enumerate(curve)
        }
        result = compute_metrics(curve, benchmark_closes=benchmark)
        assert result.statuses["beta"] is MetricStatus.VALID
        assert result.beta > 0.0
        assert result.statuses["alpha"] is MetricStatus.VALID

    def test_flat_equity_marks_sharpe_insufficient(self) -> None:
        result = compute_metrics(_curve([100.0, 100.0, 100.0]))
        assert result.statuses["sharpe_ratio"] is MetricStatus.INSUFFICIENT_DATA

    def test_negative_equity_is_rejected(self) -> None:
        result = compute_metrics(_curve([100.0, -5.0, 100.0]))
        assert all(
            status is MetricStatus.INSUFFICIENT_DATA for status in result.statuses.values()
        )
