"""Execution regressions use synthetic bars only; no DB, scheduler or orders."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from backtest import engine
import strategies


ZERO_COSTS = dict(commission_rate=0, commission_min=0, stamp_tax=0, slippage=0)


@pytest.fixture
def single_market(monkeypatch):
    dates = list(pd.bdate_range("2024-01-01", periods=70).date)
    history = pd.DataFrame({
        "trade_date": dates, "open": 10.0, "close": 10.0,
        "high": 10.5, "low": 9.5, "volume": 1_000_000.0,
    })
    signals = {}
    seen = []

    def score(ctx):
        date = ctx.daily_df["日期"].iloc[-1]
        seen.append(date)
        value = signals.get(date, (50.0, "neutral"))
        if isinstance(value, Exception):
            raise value
        return SimpleNamespace(score=value[0], signal=value[1])

    monkeypatch.setattr(strategies, "by_id", lambda _: SimpleNamespace(score=score))
    monkeypatch.setattr(engine, "_load_full_history", lambda _: (
        history.copy(deep=True), *(pd.DataFrame() for _ in range(4))))
    monkeypatch.setattr(engine, "_trading_days", lambda start, end: [
        d for d in dates if start <= d <= end])
    monkeypatch.setattr(engine, "_industry_of", lambda _: "")
    monkeypatch.setattr(engine, "_benchmark_close", lambda *_: None)

    def run(end=34, costs=None, capital=10_000):
        return engine.run_single("synthetic", "600000", dates[29], dates[end],
                                 initial_capital=capital, costs=costs or ZERO_COSTS)

    return dates, history, signals, seen, run


def test_single_signals_execute_at_next_open_with_reconcilable_costs(single_market):
    dates, history, signals, seen, run = single_market
    signals[dates[29]] = (80, "bullish")
    signals[dates[30]] = (20, "bearish")
    history.loc[30, ["open", "close"]] = [10.5, 10.7]
    history.loc[31, ["open", "close"]] = [10.4, 10.6]
    costs = dict(commission_rate=.00025, commission_min=5, stamp_tax=.0005, slippage=.001)
    result = run(costs=costs)
    buy, sell = result["trades"]
    assert (buy["signal_date"], buy["date"]) == (dates[29].isoformat(), dates[30].isoformat())
    assert (sell["signal_date"], sell["date"]) == (dates[30].isoformat(), dates[31].isoformat())
    assert buy["price"] == pytest.approx(10.5 * 1.001)
    assert sell["price"] == pytest.approx(10.4 * .999)
    expected_cost = buy["commission"] + sell["commission"] + sell["stamp_tax"]
    expected_cash = 10_000 + sell["amount"] - buy["amount"] - expected_cost
    assert result["final_cash"] == pytest.approx(expected_cash)
    assert result["equity_curve"][-1]["value"] == pytest.approx(expected_cash, abs=.005)
    assert result["metrics"]["total_costs"] == pytest.approx(expected_cost, abs=.0001)
    assert result["metrics"]["total_return"] == pytest.approx(expected_cash / 10_000 - 1, abs=.0001)
    assert sell["pnl"] == pytest.approx(expected_cash - 10_000, abs=.005)
    assert seen == dates[29:35]


def test_single_final_signal_has_no_execution_bar(single_market):
    dates, _, signals, _, run = single_market
    signals[dates[34]] = (80, "bullish")
    result = run()
    assert result["trades"] == []
    assert result["equity_curve"][-1]["value"] == 10_000
    assert result["unfilled_orders"][-1]["reason"] == "no_execution_bar"


def test_single_final_day_buy_stays_open_and_is_marked_to_market(single_market):
    dates, history, signals, _, run = single_market
    signals[dates[33]] = (80, "bullish")
    history.loc[34, ["open", "close"]] = [10, 10.5]
    result = run(costs=dict(ZERO_COSTS, commission_min=5))
    assert [t["side"] for t in result["trades"]] == ["buy"]
    assert result["open_position"]["shares"] == 900
    assert result["open_position"]["market_value"] == 9450
    assert result["final_cash"] == 995
    assert result["equity_curve"][-1]["value"] == 10_445
    assert result["metrics"]["total_costs"] == 5
    assert result["metrics"]["win_rate"] is None
    assert result["closed_trade_count"] == 0


@pytest.mark.parametrize("opening,closing,expected_trades", [(11, 10.5, 0), (10.5, 11, 1)])
def test_single_price_limit_is_checked_at_execution_open(single_market, opening, closing, expected_trades):
    dates, history, signals, _, run = single_market
    signals[dates[29]] = (80, "bullish")
    history.loc[30, ["open", "close"]] = [opening, closing]
    result = run()
    assert len(result["trades"]) == expected_trades
    if not expected_trades:
        assert result["unfilled_orders"][0]["reason"] == "limit_up"


def test_single_suspended_execution_expires_and_keeps_cash_curve(single_market):
    dates, history, signals, _, run = single_market
    signals[dates[29]] = (80, "bullish")
    history.loc[30, "volume"] = 0
    result = run()
    assert result["trades"] == []
    assert len(result["equity_curve"]) == 6
    assert result["unfilled_orders"][0]["reason"] == "untradeable"


def test_single_missing_execution_bar_does_not_delay_a_stale_signal(single_market):
    dates, history, signals, _, run = single_market
    signals[dates[29]] = (80, "bullish")
    history.drop(index=30, inplace=True)
    result = run()
    assert result["trades"] == []
    assert [r["date"] for r in result["equity_curve"]] == [d.isoformat() for d in dates[29:35]]


def test_single_suspended_final_day_never_force_closes(single_market):
    dates, history, signals, _, run = single_market
    signals[dates[29]] = (80, "bullish")
    history.loc[34, ["close", "volume"]] = [np.nan, 0]
    result = run()
    assert [t["side"] for t in result["trades"]] == ["buy"]
    assert result["equity_curve"][-1]["value"] == 10_000
    assert result["open_position"]["valuation_date"] == dates[33].isoformat()


def test_single_limit_down_sell_stays_open_without_forced_liquidation(single_market):
    dates, history, signals, _, run = single_market
    signals[dates[29]] = (80, "bullish")
    signals[dates[30]] = (20, "bearish")
    history.loc[31, ["open", "close"]] = [9, 9.5]
    result = run()
    assert [t["side"] for t in result["trades"]] == ["buy"]
    assert result["unfilled_orders"][0]["reason"] == "limit_down"
    assert result["open_position"]["shares"] == 1000


@pytest.mark.parametrize("bad_score", [RuntimeError("synthetic score failure"), (None, "bearish"), (np.nan, "bearish")])
def test_single_failed_score_is_null_and_never_becomes_a_sell(single_market, bad_score):
    dates, _, signals, _, run = single_market
    signals[dates[29]] = (80, "bullish")
    signals[dates[60]] = bad_score
    result = run(end=62)
    failed = next(r for r in result["signal_log"] if r["date"] == dates[60].isoformat())
    assert failed["score"] is None
    assert failed["status"] == "FAILED"
    assert failed["signal"] == "neutral"
    assert [t["side"] for t in result["trades"]] == ["buy"]


@pytest.mark.parametrize("cash,rate,minimum,expected", [
    (10_000, 0, 0, 1000),
    (10_000, 0, 5, 900),
    (10_005, 0, 5, 1000),
    (1000, 0, 5, 0),
    (10_000, .02, 5, 900),
])
def test_cash_budget_includes_minimum_and_rate_commission(cash, rate, minimum, expected):
    cost = dict(ZERO_COSTS, commission_rate=rate, commission_min=minimum)
    shares = engine._affordable_buy_shares(cash, 10, cost)
    assert shares == expected
    if shares:
        assert shares * 10 + engine._commission(shares * 10, cost) <= cash


def test_portfolio_cash_limited_buy_never_borrows_the_commission(monkeypatch):
    dates = list(pd.bdate_range("2024-01-01", periods=2).date)
    close = pd.DataFrame({"600000": [10.0, 10.0]}, index=dates)
    monkeypatch.setattr(engine, "_trading_days", lambda *_: dates)
    monkeypatch.setattr(engine, "_universe_ohlcv", lambda *_: {
        "close": close, "open": close, "volume": close * 100_000})
    monkeypatch.setattr(engine, "_load_panel", lambda *a, **kw: {"600000": {}})
    monkeypatch.setattr(engine, "_score_at_cached", lambda *a: 80)
    monkeypatch.setattr(engine, "_benchmark_close", lambda *_: None)
    monkeypatch.setattr(engine, "by_id", lambda _: SimpleNamespace(id="synthetic"))
    result = engine.run("synthetic", dates[0], dates[-1], initial_capital=10_000,
                        top_n=1, rebalance="daily", costs=dict(ZERO_COSTS, commission_min=5))
    buy, = result["trades"]
    assert buy["shares"] == 900
    assert 10_000 - buy["shares"] * buy["price"] - result["metrics"]["total_costs"] >= 0


def test_portfolio_unavailable_scores_do_not_create_orders(monkeypatch):
    dates = list(pd.bdate_range("2024-01-01", periods=2).date)
    close = pd.DataFrame({"600000": [10.0, 10.0]}, index=dates)
    monkeypatch.setattr(engine, "_trading_days", lambda *_: dates)
    monkeypatch.setattr(engine, "_universe_ohlcv", lambda *_: {
        "close": close, "open": close, "volume": close * 100_000})
    monkeypatch.setattr(engine, "_load_panel", lambda *a, **kw: {"600000": {}})
    monkeypatch.setattr(engine, "_score_at_cached", lambda *a: None)
    monkeypatch.setattr(engine, "_benchmark_close", lambda *_: None)
    monkeypatch.setattr(engine, "by_id", lambda _: SimpleNamespace(id="synthetic"))
    result = engine.run("synthetic", dates[0], dates[-1], initial_capital=10_000,
                        top_n=1, rebalance="daily", costs=ZERO_COSTS)
    assert result["trades"] == []
    assert result["picks"] == []
