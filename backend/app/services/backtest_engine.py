"""A-share execution simulator.

Rules implemented (single source of truth for the whole product):

* **Commission** 0.03% of notional, minimum ¥5 per fill, charged both sides.
* **Stamp duty** 0.1% of notional, sell side only.
* **Transfer fee** 0.002% of notional, Shanghai-listed securities only (6/9xx).
* **Slippage** 0.1% per fill, configurable; buys fill higher, sells lower.
* **Lot size** 100 shares; buys are rounded DOWN to whole lots.
* **T+1** shares bought on day *t* cannot be sold before day *t+1*.
* **Price limits** 10% main board, 20% ChiNext/STAR (300/301/688/689),
  30% BSE (4/8/92x). A sealed-limit-up open cannot be bought into; a
  sealed-limit-down open cannot be sold. (ST's 5% band is not modelled —
  there is no reliable ST flag in the free data sources.)
* **Suspension** a bar with no volume or a missing OHLC is untradeable; the
  position is carried and marked at its last close.
* **No look-ahead** the exposure for bar *i* comes from ``SignalRule``, which
  only ever reads bars before *i*; the engine then fills at the *open* of
  bar *i*.

The engine is pure: it takes value objects and returns value objects. It
never touches the network, the clock (other than for nothing at all) or any
store. Two runs over identical inputs produce identical output.
"""
from __future__ import annotations

import math
import dataclasses
from dataclasses import dataclass
from datetime import date
from typing import Mapping, Sequence

from app.domain.models import Bar, ChartMarker, CostModel, MetricStatus, Trade
from app.domain.results import BacktestResult, EquityPoint, MetricsResult
from app.services.metrics import compute_metrics
from app.services.signal_rule import SignalDecision

# ---------------------------------------------------------------------------
# Board rules
# ---------------------------------------------------------------------------

_MAIN_BOARD_LIMIT = 0.10
_CHINEXT_STAR_LIMIT = 0.20
_BSE_LIMIT = 0.30


def board_info(symbol: str) -> tuple[float, bool]:
    """Return ``(price_limit_ratio, is_shanghai)`` for a 6-digit code.

    创业板/科创板 20%，北交所 30%，其余主板 10%。过户费只对沪市收取。
    """
    code = str(symbol).zfill(6)
    is_shanghai = code[0] in ("6", "9")
    if code.startswith(("300", "301", "688", "689")):
        return _CHINEXT_STAR_LIMIT, is_shanghai
    if code.startswith(("8", "4", "92")):
        return _BSE_LIMIT, is_shanghai
    return _MAIN_BOARD_LIMIT, is_shanghai


def round_price(value: float) -> float:
    """交易所按 0.01 四舍五入（floor(x+0.5)，避免银行家舍入）。"""
    if not math.isfinite(value):
        return 0.0
    return math.floor(value * 100.0 + 0.5) / 100.0


# ---------------------------------------------------------------------------
# Cost primitives — exposed so the unit tests can pin the arithmetic
# ---------------------------------------------------------------------------


def commission_of(notional: float, cost: CostModel) -> float:
    """佣金：费率与最低 5 元取大。"""
    return max(notional * cost.commission_rate, cost.commission_min)


def buy_outflow(quantity: int, price: float, cost: CostModel, is_shanghai: bool) -> float:
    notional = quantity * price
    transfer = notional * cost.transfer_fee_rate if is_shanghai else 0.0
    return notional + commission_of(notional, cost) + transfer


def sell_net_proceeds(
    quantity: int, price: float, cost: CostModel, is_shanghai: bool
) -> float:
    notional = quantity * price
    transfer = notional * cost.transfer_fee_rate if is_shanghai else 0.0
    return notional - commission_of(notional, cost) - notional * cost.stamp_tax_rate - transfer


def affordable_shares(
    cash: float, price: float, cost: CostModel, is_shanghai: bool
) -> int:
    """Largest whole-lot purchase whose notional AND fees fit in cash.

    约束同时含「最低佣金」与「费率佣金」两个上界，取较小者后再向下取整到
    整手；最后用逐手回退吸收浮点误差（边界处最容易多买一手）。
    """
    if cash <= 0.0 or price <= 0.0 or cost.lot_size <= 0:
        return 0
    fee_rate = cost.commission_rate + (cost.transfer_fee_rate if is_shanghai else 0.0)
    budget = min(cash / (1.0 + fee_rate), cash - cost.commission_min)
    if budget <= 0.0:
        return 0
    lots = int(budget // (price * cost.lot_size))
    quantity = max(lots, 0) * cost.lot_size
    while quantity > 0 and buy_outflow(quantity, price, cost, is_shanghai) > cash:
        quantity -= cost.lot_size
    return max(quantity, 0)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    symbol: str
    bars: Sequence[Bar]
    decisions: Sequence[SignalDecision]
    benchmark_closes: Mapping[date, float] | None = None
    cost: CostModel | None = None
    initial_capital: float = 1_000_000.0
    risk_free_rate: float = 0.02
    periods_per_year: int = 252
    # Position scale decided by the RiskManagerNode: 1.0 = full cash on entry.
    position_scale: float = 1.0


@dataclass(frozen=True, slots=True)
class EngineDiagnostics:
    skipped_bars: int = 0
    rejected_buys_limit_up: int = 0
    rejected_sells_limit_down: int = 0
    blocked_by_t_plus_1: int = 0
    insufficient_cash_bars: int = 0


def run_backtest(request: BacktestRequest) -> BacktestResult:
    cost = request.cost or CostModel()
    bars = list(request.bars)
    if not bars:
        return BacktestResult(
            symbol=request.symbol,
            trades=[],
            equity_curve=[],
            candles=[],
            dates=[],
            markers=[],
            metrics=MetricsResult(
                statuses={key: MetricStatus.INSUFFICIENT_DATA for key in _METRIC_KEYS}
            ),
        )

    limit_ratio, is_shanghai = board_info(request.symbol)
    slippage = cost.slippage
    lot = cost.lot_size

    cash = float(request.initial_capital)
    shares = 0
    avg_price = 0.0
    bought_today = 0

    trades: list[Trade] = []
    equity: list[EquityPoint] = []
    markers: list[ChartMarker] = []
    diag = EngineDiagnostics()

    decisions = request.decisions

    for index, bar in enumerate(bars):
        decision = decisions[index] if index < len(decisions) else None
        target = decision.target if decision is not None else 0.0

        prev_close = bars[index - 1].close if index > 0 else bar.open
        limit_up = round_price(prev_close * (1.0 + limit_ratio))
        limit_down = round_price(prev_close * (1.0 - limit_ratio))

        if bar.tradeable:
            # ---- exit first: a flat target frees capital for the next entry
            if target <= 0.0 and shares > 0:
                sellable = shares - bought_today  # T+1
                if sellable <= 0:
                    diag = _bump(diag, "blocked_by_t_plus_1")
                elif bar.open <= limit_down:
                    diag = _bump(diag, "rejected_sells_limit_down")
                else:
                    fill = round_price(bar.open * (1.0 - slippage))
                    quantity = sellable
                    notional = quantity * fill
                    commission = commission_of(notional, cost)
                    stamp = notional * cost.stamp_tax_rate
                    transfer = notional * cost.transfer_fee_rate if is_shanghai else 0.0
                    proceeds = notional - commission - stamp - transfer
                    gross_pnl = (fill - avg_price) * quantity
                    trades.append(
                        Trade(
                            date=bar.date,
                            side="SELL",
                            shares=quantity,
                            price=fill,
                            commission=round(commission, 4),
                            stamp_tax=round(stamp, 4),
                            transfer_fee=round(transfer, 4),
                            cash_flow=round(proceeds, 4),
                            pnl=round(gross_pnl - commission - stamp - transfer, 4),
                        )
                    )
                    markers.append(
                        ChartMarker(
                            date=bar.date.isoformat(),
                            price=round(fill, 2),
                            action="SELL",
                            reason=(
                                "；".join(decision.reasons)
                                if decision and decision.reasons
                                else "信号转为看空，平仓离场"
                            ),
                        )
                    )
                    cash += proceeds
                    shares = 0
                    avg_price = 0.0
                    bought_today = 0

            # ---- entry: full cash into the position, whole lots only
            elif target >= 1.0 and shares == 0:
                if bar.open >= limit_up:
                    diag = _bump(diag, "rejected_buys_limit_up")
                else:
                    fill = round_price(bar.open * (1.0 + slippage))
                    budget = cash * max(0.0, min(1.0, request.position_scale))
                    quantity = affordable_shares(budget, fill, cost, is_shanghai)
                    if quantity <= 0:
                        diag = _bump(diag, "insufficient_cash_bars")
                    else:
                        notional = quantity * fill
                        commission = commission_of(notional, cost)
                        transfer = notional * cost.transfer_fee_rate if is_shanghai else 0.0
                        outflow = notional + commission + transfer
                        cash -= outflow
                        shares = quantity
                        avg_price = fill
                        bought_today = quantity
                        trades.append(
                            Trade(
                                date=bar.date,
                                side="BUY",
                                shares=quantity,
                                price=fill,
                                commission=round(commission, 4),
                                stamp_tax=0.0,
                                transfer_fee=round(transfer, 4),
                                cash_flow=round(-outflow, 4),
                                pnl=None,
                            )
                        )
                        markers.append(
                            ChartMarker(
                                date=bar.date.isoformat(),
                                price=round(fill, 2),
                                action="BUY",
                                reason=(
                                    "；".join(decision.reasons)
                                    if decision and decision.reasons
                                    else "信号转为看多，全仓买入"
                                ),
                            )
                        )
        else:
            diag = _bump(diag, "skipped_bars")

        # Shares bought at today's open become sellable on the next bar only.
        bought_today = 0
        equity.append(EquityPoint(date=bar.date, value=cash + shares * bar.close))

    round_trips: list[tuple[float, float]] = []
    open_entry: float | None = None
    for trade in trades:
        if trade.side == "BUY":
            open_entry = trade.price
        elif trade.side == "SELL" and open_entry is not None:
            round_trips.append((open_entry, trade.price))
            open_entry = None

    metrics = compute_metrics(
        equity_curve=equity,
        trades=round_trips,
        benchmark_closes=dict(request.benchmark_closes or {}),
        risk_free_rate=request.risk_free_rate,
        periods_per_year=request.periods_per_year,
    )

    return BacktestResult(
        symbol=request.symbol,
        trades=trades,
        equity_curve=equity,
        candles=[[bar.open, bar.close, bar.low, bar.high] for bar in bars],
        dates=[bar.date.isoformat() for bar in bars],
        markers=markers,
        metrics=metrics,
    )


_METRIC_KEYS = (
    "sharpe_ratio",
    "max_drawdown",
    "win_rate",
    "total_return",
    "alpha",
    "beta",
)


def _bump(diag: EngineDiagnostics, field: str) -> EngineDiagnostics:
    return dataclasses.replace(
        diag, **{field: getattr(diag, field) + 1}
    )
