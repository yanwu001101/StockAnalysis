"""Deterministic performance metrics.

Design rule borrowed from the sibling project and enforced here:
**a metric that cannot be computed is reported as uncomputable, not as 0.0.**
Because the wire contract forces a float, the "uncomputable" part travels in
``MetricsResult.statuses`` instead of being hidden inside the number.
"""
from __future__ import annotations

from datetime import date

import numpy as np

from app.domain.models import MetricStatus
from app.domain.results import EquityPoint, MetricsResult

_MIN_RETURN_OBSERVATIONS = 2
_MIN_BENCHMARK_OBSERVATIONS = 20
_MIN_BENCHMARK_COVERAGE = 0.6


def _finite(value: float) -> float | None:
    number = float(value)
    if not np.isfinite(number):
        return None
    return number


def _daily_returns(values: np.ndarray) -> np.ndarray:
    """Explicit division; never pct_change with its historical fill default."""
    if values.size < 2:
        return np.empty(0)
    prev = values[:-1]
    cur = values[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.where(prev > 0, cur / np.where(prev > 0, prev, 1.0) - 1.0, np.nan)
    return out


def compute_metrics(
    equity_curve: list[EquityPoint],
    trades: list[tuple[float, float]] | None = None,
    benchmark_closes: dict[date, float] | None = None,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> MetricsResult:
    """Compute the six headline metrics.

    Args:
        equity_curve: mark-to-market equity, ascending by date.
        trades: ``(entry_price, exit_price)`` pairs of closed round trips.
        benchmark_closes: benchmark close by date, used for alpha/beta only.
    """
    if periods_per_year <= 0 or not np.isfinite(risk_free_rate):
        raise ValueError("periods_per_year must be positive and risk_free_rate finite")

    statuses: dict[str, MetricStatus] = {
        "sharpe_ratio": MetricStatus.VALID,
        "max_drawdown": MetricStatus.VALID,
        "win_rate": MetricStatus.VALID,
        "total_return": MetricStatus.VALID,
        "alpha": MetricStatus.VALID,
        "beta": MetricStatus.VALID,
    }
    result = MetricsResult(statuses=statuses)

    values = np.asarray([point.value for point in equity_curve], dtype=np.float64)
    # `result` is frozen, so build the replacement instead of mutating.
    if values.size < 2 or not np.isfinite(values).all() or (values <= 0).any():
        for key in statuses:
            statuses[key] = MetricStatus.INSUFFICIENT_DATA
        return MetricsResult(
            statuses=statuses,
            trade_count=len(trades or []),
            sample_size=max(values.size, 0),
        )

    total_return = _finite(values[-1] / values[0] - 1.0)
    if total_return is None:
        statuses["total_return"] = MetricStatus.FAILED

    running_max = np.maximum.accumulate(values)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdowns = values / running_max - 1.0
    max_drawdown = _finite(float(drawdowns.min()))
    if max_drawdown is None:
        statuses["max_drawdown"] = MetricStatus.FAILED

    returns = _daily_returns(values)
    returns = returns[np.isfinite(returns)]

    rf_daily = risk_free_rate / periods_per_year
    sharpe = None
    if returns.size < _MIN_RETURN_OBSERVATIONS:
        statuses["sharpe_ratio"] = MetricStatus.INSUFFICIENT_DATA
    else:
        std = float(returns.std(ddof=0))
        if std <= 1e-12:
            statuses["sharpe_ratio"] = MetricStatus.INSUFFICIENT_DATA
        else:
            sharpe = _finite(
                float(np.sqrt(periods_per_year) * (returns.mean() - rf_daily) / std)
            )
            if sharpe is None:
                statuses["sharpe_ratio"] = MetricStatus.FAILED

    # ---- win rate: realised round trips first, up-days as the fallback ----
    closed = trades or []
    basis = "CLOSED_TRADES"
    win_rate = None
    if closed:
        wins = sum(1 for entry, exit_ in closed if exit_ - entry > 0)
        win_rate = wins / len(closed)
    else:
        basis = "EQUITY_UP_DAYS"
        if returns.size < 1:
            statuses["win_rate"] = MetricStatus.INSUFFICIENT_DATA
        else:
            win_rate = float((returns > 0).mean())

    # ---- alpha / beta: only over dates the benchmark actually covers ----
    beta = None
    alpha = None
    bench_pairs = _benchmark_pairs(equity_curve, benchmark_closes)
    coverage = bench_pairs[2]
    if bench_pairs[0].size < _MIN_BENCHMARK_OBSERVATIONS or coverage < _MIN_BENCHMARK_COVERAGE:
        statuses["beta"] = MetricStatus.INSUFFICIENT_DATA
        statuses["alpha"] = MetricStatus.INSUFFICIENT_DATA
    else:
        port, bench = bench_pairs[0], bench_pairs[1]
        var_bench = float(bench.var(ddof=0))
        if var_bench <= 1e-16:
            statuses["beta"] = MetricStatus.FAILED
            statuses["alpha"] = MetricStatus.FAILED
        else:
            cov = float(((port - port.mean()) * (bench - bench.mean())).mean())
            beta = _finite(cov / var_bench)
            alpha = _finite(
                ((port.mean() - rf_daily) - beta * (bench.mean() - rf_daily))
                * periods_per_year
            )
            if beta is None:
                statuses["beta"] = MetricStatus.FAILED
            if alpha is None:
                statuses["alpha"] = MetricStatus.FAILED

    return MetricsResult(
        total_return=total_return or 0.0,
        max_drawdown=max_drawdown or 0.0,
        sharpe_ratio=sharpe or 0.0,
        win_rate=win_rate or 0.0,
        alpha=alpha or 0.0,
        beta=beta or 0.0,
        statuses=statuses,
        trade_count=len(closed),
        sample_size=int(returns.size),
        benchmark_coverage=coverage,
        basis=basis,
    )


def _benchmark_pairs(
    equity_curve: list[EquityPoint], benchmark_closes: dict[date, float] | None
) -> tuple[np.ndarray, np.ndarray, float]:
    """Align portfolio and benchmark returns by date. No ffill, no bfill."""
    empty = np.empty(0)
    if not benchmark_closes or len(equity_curve) < 2:
        return empty, empty, 0.0

    port: list[float] = []
    bench: list[float] = []
    for prev, cur in zip(equity_curve, equity_curve[1:]):
        if prev.value <= 0:
            continue
        prev_b = benchmark_closes.get(prev.date)
        cur_b = benchmark_closes.get(cur.date)
        if prev_b is None or cur_b is None or prev_b <= 0 or cur_b <= 0:
            continue
        port.append(cur.value / prev.value - 1.0)
        bench.append(cur_b / prev_b - 1.0)

    total = max(len(equity_curve) - 1, 1)
    coverage = len(port) / total
    return np.asarray(port, dtype=np.float64), np.asarray(bench, dtype=np.float64), coverage
