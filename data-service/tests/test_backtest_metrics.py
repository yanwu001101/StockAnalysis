"""Metric definitions, missing evidence and exact-date benchmark regression."""
import json

import numpy as np
import pandas as pd
import pytest

from backtest.metrics import Metrics, compute


def curve(values):
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)), dtype=float)


CORE = ("total_return", "annualized_return", "max_drawdown", "sharpe_ratio", "calmar_ratio", "win_rate")


@pytest.mark.parametrize("equity", [None, curve([]), curve([100])])
def test_empty_and_single_observation_are_not_zero_performance(equity):
    result = compute(equity, total_costs=0).as_dict()
    assert all(result[key] is None for key in CORE)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["trade_count"] == 0
    assert result["total_costs"] == 0
    assert result["benchmark_return"] is None
    assert result["turnover_rate"] is None
    assert result["sample_info"]["return_observations"] == 0


def test_flat_path_preserves_real_zero_but_undefined_ratios_are_null():
    result = compute(curve([100, 100, 100])).as_dict()
    assert result["total_return"] == result["annualized_return"] == result["max_drawdown"] == 0
    assert result["win_rate"] == 0
    assert result["sharpe_ratio"] is result["calmar_ratio"] is None
    assert result["metric_reasons"]["sharpe_ratio"] == "ZERO_RETURN_VOLATILITY"
    assert result["metric_reasons"]["calmar_ratio"] == "NO_DRAWDOWN"
    assert result["win_rate_basis"] == "EQUITY_UP_PERIODS"
    assert result["win_rate_sample_size"] == 2


def test_mathematically_defined_zero_sharpe_and_calmar_stay_zero():
    assert compute(curve([100, 90, 99]), rf=0).as_dict()["sharpe_ratio"] == 0
    assert compute(curve([100, 90, 100])).as_dict()["calmar_ratio"] == 0


def test_two_observations_have_return_but_no_volatility_sample():
    result = compute(curve([100, 110]))
    assert result.total_return == pytest.approx(.1)
    assert result.sharpe_ratio is None
    assert result.metric_reasons["sharpe_ratio"] == "NOT_ENOUGH_RETURN_OBSERVATIONS"


def test_finite_path_retains_original_formulas_and_samples():
    equity = curve([100, 105, 101, 108])
    result = compute(equity, periods_per_year=12, rf=.01)
    returns = np.array([.05, 101 / 105 - 1, 108 / 101 - 1])
    assert result.total_return == pytest.approx(.08)
    assert result.annualized_return == pytest.approx(1.08 ** 4 - 1)
    assert result.max_drawdown == pytest.approx(101 / 105 - 1)
    assert result.sharpe_ratio == pytest.approx(np.sqrt(12) * (returns.mean() - .01 / 12) / returns.std(ddof=0))
    assert result.sample_info["equity_observations"] == 4
    assert result.sample_info["return_observations"] == 3
    assert result.sample_info["annualization_basis"] == "OBSERVED_INTERVALS"


@pytest.mark.parametrize("value,status", [(np.nan, "INSUFFICIENT_DATA"), (np.inf, "FAILED"), (-np.inf, "FAILED")])
def test_incomplete_or_nonfinite_equity_is_not_filled_or_compressed(value, status):
    result = compute(curve([100, value, 120])).as_dict()
    assert all(result[key] is None for key in CORE)
    assert result["status"] == status
    assert result["sample_info"]["equity_observations"] == 3
    assert result["sample_info"]["valid_equity_observations"] == 2
    assert result["sample_info"]["return_observations"] == 0
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("values", [[0, 1, 2], [100, -1, 90]])
def test_invalid_wealth_is_failed(values):
    result = compute(curve(values))
    assert result.status == "FAILED"
    assert result.total_return is None


def test_terminal_total_loss_remains_a_real_minus_one():
    result = compute(curve([100, 90, 0]))
    assert result.total_return == result.annualized_return == result.max_drawdown == -1


def test_zero_denominator_does_not_create_a_fictitious_daily_win_rate():
    result = compute(curve([100, 0, 0]))
    assert result.total_return == -1
    assert result.sharpe_ratio is result.win_rate is None
    assert result.metric_reasons["win_rate"] == "INCOMPLETE_RETURN_OBSERVATIONS"


def test_overflow_cannot_leak_nonstandard_json():
    result = compute(curve([1, 1e200])).as_dict()
    assert result["annualized_return"] is None
    assert result["metric_status"]["annualized_return"] == "FAILED"
    json.dumps(result, allow_nan=False)
    manual = Metrics(np.nan, np.inf, None, None, None, None, 0).as_dict()
    assert manual["total_return"] is manual["annualized_return"] is None
    json.dumps(manual, allow_nan=False)


def test_benchmark_uses_equity_endpoints_not_its_own_wider_history():
    dates = pd.bdate_range("2024-01-01", periods=5)
    equity = pd.Series([100, 110, 120], index=dates[1:4])
    benchmark = pd.Series([5, 10, 20, 40, 80], index=dates)
    result = compute(equity, benchmark=benchmark)
    assert result.benchmark_return == pytest.approx(3)
    assert result.excess_return == pytest.approx(-2.8)
    assert result.benchmark_info["coverage_ratio"] == 1
    assert result.benchmark_info["start"] == dates[1].isoformat()
    assert result.benchmark_info["end"] == dates[3].isoformat()


@pytest.mark.parametrize("missing", [0, 2])
def test_benchmark_missing_endpoint_is_not_forward_or_backward_filled(missing):
    equity = curve([100, 110, 120])
    benchmark = curve([10, 11, 12]).drop(equity.index[missing])
    result = compute(equity, benchmark=benchmark)
    assert result.benchmark_return is result.excess_return is None
    assert result.benchmark_info["reason"] == "MISSING_BENCHMARK_ENDPOINT"
    assert result.benchmark_info["coverage_ratio"] == pytest.approx(2 / 3)


def test_benchmark_interior_gap_keeps_endpoint_return_and_discloses_coverage():
    result = compute(curve([100, 110, 120]), benchmark=curve([10, np.nan, 12]))
    assert result.benchmark_return == pytest.approx(.2)
    assert result.excess_return == pytest.approx(0)
    assert result.benchmark_info["observations"] == 2
    assert result.benchmark_info["expected_observations"] == 3
    assert result.benchmark_info["reason"] == "INTERIOR_BENCHMARK_GAPS"


@pytest.mark.parametrize("value", [0, np.nan, np.inf, -np.inf])
def test_invalid_benchmark_endpoint_is_not_a_return(value):
    result = compute(curve([100, 110, 120]), benchmark=curve([10, 11, value]))
    assert result.benchmark_return is result.excess_return is None
    json.dumps(result.as_dict(), allow_nan=False)


def test_benchmark_normalizes_actual_date_labels_but_not_row_numbers():
    equity = curve([100, 110, 120])
    benchmark = pd.Series([10, 11, 12], index=[d.date().isoformat() for d in equity.index])
    assert compute(equity, benchmark=benchmark).benchmark_return == pytest.approx(.2)
    assert compute(equity, benchmark=pd.Series([10, 11, 12])).benchmark_return is None


def test_duplicate_equity_dates_fail_instead_of_counting_extra_periods():
    equity = curve([100, 110, 120])
    equity.index = [equity.index[0], equity.index[0], equity.index[2]]
    result = compute(equity)
    assert result.status == "FAILED"
    assert result.metric_reasons["total_return"] == "DUPLICATE_EQUITY_INDEX"


def test_realized_pnl_precedes_daily_win_rate_and_declares_denominator():
    trades = [{"pnl": None}, {"pnl": 0}, {"pnl": 1}, {"pnl": -2}]
    result = compute(curve([100, 110, 120]), trades=trades)
    assert result.win_rate == pytest.approx(1 / 3)
    assert result.trade_count == 4
    assert result.win_rate_basis == "CLOSED_TRADES"
    assert result.win_rate_sample_size == 3
    assert result.sample_info["closed_trade_observations"] == 3


def test_invalid_reported_pnl_is_not_a_loss_or_a_switch_to_equity_basis():
    result = compute(curve([100, 110, 120]), trades=[{"pnl": np.nan}])
    assert result.win_rate is None
    assert result.win_rate_basis == "CLOSED_TRADES"
    assert result.win_rate_sample_size == 0
    assert result.metric_status["win_rate"] == "FAILED"


def test_explicit_closed_trade_basis_does_not_fall_back_when_position_is_open():
    result = compute(curve([100, 110, 120]), trades=[{"pnl": None}], win_rate_basis="CLOSED_TRADES")
    assert result.win_rate is None
    assert result.win_rate_basis == "CLOSED_TRADES"
    assert result.win_rate_sample_size == 0
    assert result.metric_reasons["win_rate"] == "NO_CLOSED_TRADES"


def test_paper_overview_preserves_missing_benchmark_endpoint(monkeypatch):
    from flask import Flask
    from api import paper

    dates = pd.bdate_range("2024-01-01", periods=3)
    rows = [{"trade_date": d.date(), "equity": 100 + i,
             "benchmark_close": 10 + i if i < 2 else None}
            for i, d in enumerate(dates)]
    monkeypatch.setattr(paper.paper_repo, "get_account", lambda: {
        "initial_capital": 100, "top_n": 5, "rebalance": "weekly", "cash": 102})
    monkeypatch.setattr(paper.paper_repo, "get_equity_curve", lambda: rows)
    monkeypatch.setattr(paper.paper_repo, "get_positions", lambda: [])
    monkeypatch.setattr(paper.paper_repo, "get_trades", lambda *_: [])
    monkeypatch.setattr("repo.base.engine", lambda: None)
    with Flask(__name__).app_context():
        result = paper.overview().get_json()
    assert result["metrics"]["benchmark_return"] is None
    assert result["metrics"]["excess_return"] is None
    assert result["metrics"]["benchmark_info"]["coverage_ratio"] == pytest.approx(2 / 3)
    assert result["equity_curve"][-1]["benchmark"] is None


def test_paper_series_keeps_missing_equity_rows():
    from api.paper import _pd_series
    rows = [{"trade_date": "2024-01-01", "equity": 100},
            {"trade_date": "2024-01-02", "equity": None},
            {"trade_date": "2024-01-03", "equity": 110}]
    result = compute(_pd_series(rows, "equity"))
    assert result.status == "INSUFFICIENT_DATA"
    assert result.total_return is None


def test_portfolio_benchmark_curve_keeps_missing_quotes_visible(monkeypatch):
    from types import SimpleNamespace
    from backtest import engine

    dates = list(pd.bdate_range("2024-01-01", periods=3).date)
    prices = pd.DataFrame({"600000": [10.0] * 3}, index=dates)
    monkeypatch.setattr(engine, "_trading_days", lambda *_: dates)
    monkeypatch.setattr(engine, "_universe_ohlcv", lambda *_: {
        "open": prices, "close": prices, "volume": prices * 100_000})
    monkeypatch.setattr(engine, "_load_panel", lambda *a, **kw: {"600000": {}})
    monkeypatch.setattr(engine, "_score_at_cached", lambda *a: None)
    monkeypatch.setattr(engine, "by_id", lambda _: SimpleNamespace(id="synthetic"))
    monkeypatch.setattr(engine, "_benchmark_close", lambda *_: curve([100, np.nan, 102]))
    result = engine.run("synthetic", dates[0], dates[-1], rebalance="daily")
    assert result["benchmark_curve"][1]["value"] is None
    assert result["metrics"]["benchmark_info"]["coverage_ratio"] == pytest.approx(2 / 3)
    assert result["win_rate_basis"] == result["metrics"]["win_rate_basis"] == "EQUITY_UP_PERIODS"
    assert result["win_rate_sample_size"] == 2
