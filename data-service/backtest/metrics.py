# -*- coding: utf-8 -*-
"""Finite-only metrics; no filled/dropped observations or mismatched benchmarks."""
from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


def _finite(value) -> float | None:
    try:
        number = float(value)
        return number if np.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _label(value) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


@dataclass
class Metrics:
    total_return: float | None
    annualized_return: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    calmar_ratio: float | None
    win_rate: float | None
    trade_count: int
    benchmark_return: float | None = None
    excess_return: float | None = None
    turnover_rate: float | None = None
    total_costs: float | None = None
    status: str = "VALID"
    metric_status: dict = field(default_factory=dict)
    metric_reasons: dict = field(default_factory=dict)
    sample_info: dict = field(default_factory=dict)
    win_rate_basis: str = "EQUITY_UP_PERIODS"
    win_rate_sample_size: int = 0
    benchmark_info: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {}
        for key in ("total_return", "annualized_return", "max_drawdown", "sharpe_ratio",
                    "calmar_ratio", "win_rate", "benchmark_return", "excess_return",
                    "turnover_rate", "total_costs"):
            value = _finite(getattr(self, key))
            out[key] = round(value, 4) if value is not None else None
        out.update(trade_count=self.trade_count, status=self.status,
                   metric_status=self.metric_status.copy(), metric_reasons=self.metric_reasons.copy(),
                   sample_info=self.sample_info.copy(), win_rate_basis=self.win_rate_basis,
                   win_rate_sample_size=self.win_rate_sample_size,
                   benchmark_info=self.benchmark_info.copy())
        return out


def _date_index(series: pd.Series) -> pd.Series | None:
    """Normalize daily dates; numeric row positions are never invented dates."""
    if pd.api.types.is_numeric_dtype(series.index.dtype):
        return None
    try:
        dates = pd.DatetimeIndex(pd.to_datetime(series.index, errors="coerce"))
        if dates.tz is not None:
            dates = dates.tz_localize(None)
        dates = dates.normalize()
        if dates.isna().any() or dates.has_duplicates:
            return None
        return pd.Series(pd.to_numeric(series, errors="coerce").to_numpy(dtype=float), index=dates).sort_index()
    except (TypeError, ValueError):
        return None


def _benchmark_return(equity: pd.Series, benchmark: pd.Series | None) -> tuple[float | None, dict]:
    info = {"status": "INSUFFICIENT_DATA", "reason": "BENCHMARK_UNAVAILABLE",
            "alignment": "EXACT_EQUITY_ENDPOINTS", "observations": 0,
            "expected_observations": len(equity), "coverage_ratio": None,
            "start": None, "end": None}
    dated_equity = _date_index(equity)
    if dated_equity is not None and len(dated_equity) >= 2:
        info.update(start=_label(dated_equity.index[0]), end=_label(dated_equity.index[-1]))
    if benchmark is None or benchmark.empty:
        return None, info
    dated_benchmark = _date_index(benchmark)
    if dated_equity is None or dated_benchmark is None:
        info["reason"] = "UNIQUE_DATE_INDEX_REQUIRED"
        return None, info
    aligned = dated_benchmark.reindex(dated_equity.index)  # no ffill/bfill
    available = np.isfinite(aligned) & (aligned > 0)
    info.update(observations=int(available.sum()),
                coverage_ratio=float(available.mean()) if len(aligned) else None)
    if len(aligned) < 2 or not (available.iloc[0] and available.iloc[-1]):
        info["reason"] = "MISSING_BENCHMARK_ENDPOINT"
        return None, info
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        result = _finite(aligned.iloc[-1] / aligned.iloc[0] - 1)
    if result is None:
        info.update(status="FAILED", reason="NONFINITE_BENCHMARK_RETURN")
    else:
        info.update(status="VALID", reason=None if bool(available.all()) else "INTERIOR_BENCHMARK_GAPS")
    return result, info


def compute(equity: pd.Series, trades: list[dict] | None = None,
            periods_per_year: int = 252, rf: float = 0.02,
            benchmark: pd.Series | None = None,
            turnover_rate: float | None = None,
            total_costs: float | None = None,
            win_rate_basis: str | None = None) -> Metrics:
    """Return None for missing/undefined metrics, preserving calculated zero.

    Annualization uses observed intervals (n-1), at periods_per_year. Incomplete
    equity paths are not compressed into a shorter, apparently complete sample.
    Default win-rate selection remains realized PnL first, else up-equity periods;
    metadata names its denominator. Single-stock callers can require CLOSED_TRADES.
    """
    if periods_per_year <= 0 or not np.isfinite(periods_per_year) or _finite(rf) is None:
        raise ValueError("periods_per_year must be positive and rf finite")
    if win_rate_basis not in (None, "CLOSED_TRADES", "EQUITY_UP_PERIODS"):
        raise ValueError("unsupported win_rate_basis")
    out = Metrics(None, None, None, None, None, None, len(trades or []))

    def set_metric(key, value=None, status="INSUFFICIENT_DATA", reason=None):
        finite = _finite(value)
        if finite is None and value is not None:
            status, reason = "FAILED", "NONFINITE_RESULT"
        setattr(out, key, finite)
        out.metric_status[key] = "VALID" if finite is not None else status
        out.metric_reasons[key] = None if finite is not None else reason

    for key, value in (("turnover_rate", turnover_rate), ("total_costs", total_costs)):
        set_metric(key, value, reason="NOT_PROVIDED")
    out.metric_status["trade_count"] = "VALID"
    out.metric_reasons["trade_count"] = None

    series = pd.Series(dtype=float) if equity is None else pd.to_numeric(equity, errors="coerce").astype(float)
    reason = None
    if not series.index.is_unique:
        out.status, reason = "FAILED", "DUPLICATE_EQUITY_INDEX"
    else:
        try:
            series = series.sort_index()
        except TypeError:
            out.status, reason = "FAILED", "INVALID_EQUITY_INDEX"
    if reason is None:
        if len(series) < 2:
            out.status, reason = "INSUFFICIENT_DATA", "NOT_ENOUGH_EQUITY_OBSERVATIONS"
        elif np.isinf(series.to_numpy()).any():
            out.status, reason = "FAILED", "NONFINITE_EQUITY_OBSERVATIONS"
        elif series.isna().any():
            out.status, reason = "INSUFFICIENT_DATA", "MISSING_EQUITY_OBSERVATIONS"
        elif series.iloc[0] <= 0 or (series < 0).any():
            out.status, reason = "FAILED", "INVALID_EQUITY_VALUES"

    returns = pd.Series(dtype=float)
    if out.status == "VALID":
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            # Explicit division avoids pandas' historical pct_change fill default.
            returns = (series / series.shift(1).where(series.shift(1) > 0) - 1).iloc[1:]
        returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
    out.sample_info = {
        "equity_observations": len(series),
        "valid_equity_observations": int(np.isfinite(series.to_numpy()).sum()),
        "return_observations": len(returns), "expected_return_observations": max(len(series) - 1, 0),
        "start": _label(series.index[0]) if len(series) else None,
        "end": _label(series.index[-1]) if len(series) else None,
        "periods_per_year": periods_per_year, "risk_free_rate": float(rf),
        "annualization_basis": "OBSERVED_INTERVALS",
    }
    for key in ("total_return", "annualized_return", "max_drawdown", "sharpe_ratio", "calmar_ratio"):
        set_metric(key, status=out.status, reason=reason)

    if out.status == "VALID":
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            total = series.iloc[-1] / series.iloc[0] - 1
            annualized = (1 + total) ** (periods_per_year / (len(series) - 1)) - 1
            drawdown = float((series / series.cummax() - 1).min())
        set_metric("total_return", total)
        set_metric("annualized_return", annualized)
        set_metric("max_drawdown", drawdown)
        if len(returns) != len(series) - 1:
            set_metric("sharpe_ratio", reason="INCOMPLETE_RETURN_OBSERVATIONS")
        elif len(returns) < 2:
            set_metric("sharpe_ratio", reason="NOT_ENOUGH_RETURN_OBSERVATIONS")
        else:
            std = float(returns.std(ddof=0))
            if std <= 1e-12:
                set_metric("sharpe_ratio", reason="ZERO_RETURN_VOLATILITY")
            else:
                set_metric("sharpe_ratio", np.sqrt(periods_per_year) * (returns.mean() - rf / periods_per_year) / std)
        if drawdown < 0 and out.annualized_return is not None:
            set_metric("calmar_ratio", out.annualized_return / abs(drawdown))
        else:
            set_metric("calmar_ratio", reason="NO_DRAWDOWN" if drawdown == 0 else "ANNUALIZED_RETURN_UNAVAILABLE")

    closed = [trade["pnl"] for trade in (trades or []) if trade.get("pnl") is not None]
    valid_closed = [value for value in (_finite(value) for value in closed) if value is not None]
    out.win_rate_basis = win_rate_basis or ("CLOSED_TRADES" if closed else "EQUITY_UP_PERIODS")
    out.sample_info.update(closed_trade_observations=len(closed), valid_closed_trade_observations=len(valid_closed))
    if out.win_rate_basis == "CLOSED_TRADES":
        out.win_rate_sample_size = len(valid_closed)
        if len(valid_closed) != len(closed):
            set_metric("win_rate", status="FAILED", reason="NONFINITE_REALIZED_PNL")
        elif valid_closed:
            set_metric("win_rate", sum(value > 0 for value in valid_closed) / len(valid_closed))
        else:
            set_metric("win_rate", reason="NO_CLOSED_TRADES")
    else:
        out.win_rate_sample_size = len(returns)
        if out.status == "VALID" and len(returns) != len(series) - 1:
            set_metric("win_rate", reason="INCOMPLETE_RETURN_OBSERVATIONS")
        elif len(returns):
            set_metric("win_rate", float((returns > 0).mean()))
        else:
            set_metric("win_rate", status=out.status if reason else "INSUFFICIENT_DATA",
                       reason=reason or "NOT_ENOUGH_RETURN_OBSERVATIONS")

    bench_ret, out.benchmark_info = _benchmark_return(series, benchmark)
    if out.status != "VALID":
        bench_ret = None
        out.benchmark_info.update(status=out.status, reason="EQUITY_NOT_VALID")
    set_metric("benchmark_return", bench_ret, status=out.benchmark_info["status"], reason=out.benchmark_info["reason"])
    if bench_ret is not None and out.total_return is not None:
        set_metric("excess_return", out.total_return - bench_ret)
    else:
        set_metric("excess_return", reason="ALIGNED_RETURNS_UNAVAILABLE")
    return out
