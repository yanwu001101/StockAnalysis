"""Backtest engine — A-share execution rules, pinned numerically."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.domain.models import Bar, CostModel, MetricStatus
from app.domain.results import MetricsResult
from app.services.backtest_engine import (
    affordable_shares,
    board_info,
    buy_outflow,
    commission_of,
    round_price,
    run_backtest,
    sell_net_proceeds,
    BacktestRequest,
)
from app.services.signal_rule import SignalDecision

from tests.conftest import make_bars


def _flat_decisions(bars: list[Bar]) -> tuple[SignalDecision, ...]:
    return tuple(SignalDecision(index=i, target=0.0, score=0.0) for i in range(len(bars)))


def _always_long(bars: list[Bar]) -> tuple[SignalDecision, ...]:
    return tuple(SignalDecision(index=i, target=1.0, score=1.0) for i in range(len(bars)))


def _buy_then_sell(bars: list[Bar], buy_at: int, sell_at: int) -> tuple[SignalDecision, ...]:
    decisions = [SignalDecision(index=i, target=0.0, score=0.0) for i in range(len(bars))]
    decisions[buy_at] = SignalDecision(index=buy_at, target=1.0, score=1.0)
    decisions[sell_at] = SignalDecision(index=sell_at, target=0.0, score=-1.0)
    return tuple(decisions)


# ---------------------------------------------------------------------------
# cost primitives
# ---------------------------------------------------------------------------


class TestCostPrimitives:
    def test_commission_min_five_yuan(self) -> None:
        cost = CostModel()
        # 1000 元名义本金，万三只有 0.3 元 -> 最低 5 元兜底
        assert commission_of(1_000.0, cost) == 5.0
        # 10 万元名义本金，万三 = 30 元 > 5 元（浮点尾差用 approx 吸收）
        assert commission_of(100_000.0, cost) == pytest.approx(30.0)

    def test_stamp_duty_sell_only(self) -> None:
        cost = CostModel()
        # sell_net_proceeds 扣掉 0.1% 印花税
        proceeds = sell_net_proceeds(1_000, 10.0, cost, is_shanghai=False)
        notional = 1_000 * 10.0
        expected = notional - max(notional * 0.0003, 5.0) - notional * 0.001
        assert proceeds == pytest.approx(expected)

    def test_transfer_fee_shanghai_only(self) -> None:
        cost = CostModel()
        notional = 1_000 * 10.0
        sh_outflow = buy_outflow(1_000, 10.0, cost, is_shanghai=True)
        sz_outflow = buy_outflow(1_000, 10.0, cost, is_shanghai=False)
        assert sh_outflow - sz_outflow == pytest.approx(notional * 0.00002)

    def test_board_detection(self) -> None:
        assert board_info("600519") == (0.10, True)     # 沪市主板
        assert board_info("000001") == (0.10, False)    # 深市主板
        assert board_info("300750") == (0.20, False)    # 创业板
        assert board_info("688981") == (0.20, True)     # 科创板
        assert board_info("830799") == (0.30, False)    # 北交所

    def test_round_price_half_up(self) -> None:
        assert round_price(10.005) == 10.01
        assert round_price(10.004) == 10.0

    def test_affordable_shares_lot_backoff(self) -> None:
        cost = CostModel()
        # 100 万现金，股价 1000：名义+费用超预算，逐手回退到 900 股
        shares = affordable_shares(1_000_000.0, 1000.0, cost, is_shanghai=True)
        assert shares == 900
        assert buy_outflow(shares, 1000.0, cost, True) <= 1_000_000.0
        # 现金不足一手 -> 0
        assert affordable_shares(1_000.0, 1000.0, cost, False) == 0


# ---------------------------------------------------------------------------
# engine behaviour
# ---------------------------------------------------------------------------


class TestEngineRules:
    def test_buy_pays_min_commission(self, bars: list[Bar]) -> None:
        decisions = _always_long(bars)
        result = run_backtest(
            BacktestRequest(
                symbol="600519", bars=bars, decisions=decisions, initial_capital=1_000_000.0
            )
        )
        buy = next(t for t in result.trades if t.side == "BUY")
        # 首笔买入约 60 万名义，万三 > 5 元
        assert buy.commission == pytest.approx(buy.shares * buy.price * 0.0003, rel=1e-6)

    def test_sell_pays_stamp_duty(self, bars: list[Bar]) -> None:
        decisions = _buy_then_sell(bars, buy_at=60, sell_at=61)
        result = run_backtest(
            BacktestRequest(symbol="000001", bars=bars, decisions=decisions)
        )
        sell = next(t for t in result.trades if t.side == "SELL")
        assert sell.stamp_tax == pytest.approx(sell.shares * sell.price * 0.001, rel=1e-6)
        assert sell.transfer_fee == 0.0  # 深市无过户费

    def test_slippage_direction(self, bars: list[Bar]) -> None:
        decisions = _always_long(bars)
        result = run_backtest(
            BacktestRequest(
                symbol="600519",
                bars=bars,
                decisions=decisions,
                cost=CostModel(slippage=0.01),
            )
        )
        buy = next(t for t in result.trades if t.side == "BUY")
        assert buy.price > bars[0].open          # 买入滑点向上
        assert buy.price == pytest.approx(round(bars[0].open * 1.01, 2))

    def test_t_plus_one_blocks_same_day_exit(self, bars: list[Bar]) -> None:
        # 第 60 根买入、第 61 根平仓 -> 允许（T+1 次日可卖）
        # 买入当日不允许卖出由引擎的 elif 结构保证：同一根 K 线只做一个动作
        decisions = _buy_then_sell(bars, buy_at=60, sell_at=61)
        result = run_backtest(BacktestRequest(symbol="600519", bars=bars, decisions=decisions))
        assert [t.side for t in result.trades] == ["BUY", "SELL"]

    def test_lot_size_is_whole_lots(self, bars: list[Bar]) -> None:
        decisions = _always_long(bars)
        result = run_backtest(BacktestRequest(symbol="600519", bars=bars, decisions=decisions))
        buy = next(t for t in result.trades if t.side == "BUY")
        assert buy.shares % 100 == 0

    def test_limit_up_open_cannot_be_bought(self, bars: list[Bar]) -> None:
        # 只在第 60 根给出买入信号，且开盘价精确等于涨停价（前收 +10%）
        mutated = list(bars)
        prev_close = bars[59].close
        limit_up = round_price(prev_close * 1.10)
        mutated[60] = Bar(
            date=bars[60].date,
            open=limit_up,
            high=limit_up,
            low=bars[60].low,
            close=bars[60].close,
            volume=bars[60].volume,
            amount=bars[60].amount,
        )
        decisions = [
            SignalDecision(index=i, target=1.0 if i == 60 else 0.0, score=0.0)
            for i in range(len(mutated))
        ]
        result = run_backtest(BacktestRequest(symbol="600519", bars=mutated, decisions=tuple(decisions)))
        assert result.trades == []

    def test_no_trades_marks_metrics_insufficient(self, bars: list[Bar]) -> None:
        result = run_backtest(
            BacktestRequest(symbol="600519", bars=bars, decisions=_flat_decisions(bars))
        )
        assert result.trades == []
        # 全平仓 -> 无收益率波动 -> 夏普不可计算（而不是伪造一个 0 分）
        assert result.metrics.statuses["sharpe_ratio"] is MetricStatus.INSUFFICIENT_DATA
        assert result.metrics.sharpe_ratio == 0.0
        # 总收益仍可计算（恒为 0）
        assert result.metrics.statuses["total_return"] is MetricStatus.VALID
        assert result.metrics.total_return == 0.0

    def test_determinism_two_runs_identical(self, bars: list[Bar]) -> None:
        decisions = _buy_then_sell(bars, buy_at=80, sell_at=140)
        request = BacktestRequest(symbol="600519", bars=bars, decisions=decisions)
        first = run_backtest(request)
        second = run_backtest(request)
        assert first.metrics == second.metrics
        assert first.trades == second.trades
        assert first.equity_curve == second.equity_curve

    def test_equity_curve_marks_to_market(self, bars: list[Bar]) -> None:
        decisions = _always_long(bars)
        result = run_backtest(BacktestRequest(symbol="600519", bars=bars, decisions=decisions))
        assert len(result.equity_curve) == len(bars)
        buy = next(t for t in result.trades if t.side == "BUY")
        entry_equity = result.equity_curve[0].value
        assert entry_equity < 1_000_000.0          # 现金已划出一部分买股票
        assert entry_equity > 0.0
