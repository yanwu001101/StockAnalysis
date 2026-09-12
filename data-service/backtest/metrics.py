# -*- coding: utf-8 -*-
"""Performance metrics for backtest results."""
from __future__ import annotations
from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class Metrics:
    total_return: float
    annualized_return: float
    max_drawdown: float
    sharpe_ratio: float
    calmar_ratio: float
    win_rate: float
    trade_count: int
    # 以下为 P0 新增：基准对比 / 交易摩擦。None 表示该次回测不适用（无基准数据等）
    benchmark_return: float | None = None
    excess_return: float | None = None
    turnover_rate: float | None = None
    total_costs: float | None = None

    def as_dict(self) -> dict:
        out = {
            "total_return": round(self.total_return, 4),
            "annualized_return": round(self.annualized_return, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "win_rate": round(self.win_rate, 4),
            "trade_count": self.trade_count,
        }
        for k in ("benchmark_return", "excess_return", "turnover_rate", "total_costs"):
            v = getattr(self, k)
            if v is not None:
                out[k] = round(v, 4)
        return out


def compute(equity: pd.Series, trades: list[dict] | None = None,
            periods_per_year: int = 252, rf: float = 0.02,
            benchmark: pd.Series | None = None,
            turnover_rate: float | None = None,
            total_costs: float | None = None) -> Metrics:
    bench_ret: float | None = None
    if benchmark is not None and len(benchmark) >= 2:
        bench_ret = float(benchmark.iloc[-1] / benchmark.iloc[0] - 1)

    if equity is None or equity.empty or len(equity) < 2:
        return Metrics(0, 0, 0, 0, 0, 0, 0,
                       benchmark_return=bench_ret,
                       excess_return=None,
                       turnover_rate=turnover_rate,
                       total_costs=total_costs)
    equity = equity.astype(float)
    rets = equity.pct_change().dropna()

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1)
    n_periods = max(len(equity) - 1, 1)
    annualized = (1 + total_return) ** (periods_per_year / n_periods) - 1 if total_return > -1 else -1.0

    cummax = equity.cummax()
    dd = (equity / cummax) - 1.0
    max_dd = float(dd.min())

    if rets.std(ddof=0) > 0:
        ex = rets - rf / periods_per_year
        sharpe = float(np.sqrt(periods_per_year) * ex.mean() / rets.std(ddof=0))
    else:
        sharpe = 0.0

    calmar = float(annualized / abs(max_dd)) if max_dd < 0 else 0.0

    # WinRate has two meanings depending on the back-test mode:
    #   * Single-stock — closed trades carry a `pnl`, so we use the classical
    #     "winning trades / closed trades" definition.
    #   * Portfolio — rebalance rows in `trades` have no per-line pnl (each
    #     row is a delta in shares, not a realised exit). Fall back to the
    #     fraction of UP days in the equity curve, which is a meaningful
    #     proxy when the per-trade PnL isn't attributable.
    n_trades = len(trades) if trades else 0
    closed = [t for t in (trades or []) if t.get("pnl") is not None] if trades else []
    if closed:
        wins = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
        win_rate = wins / len(closed)
    elif len(rets) > 0:
        win_rate = float((rets > 0).sum() / len(rets))
    else:
        win_rate = 0.0

    return Metrics(
        total_return=total_return,
        annualized_return=float(annualized),
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        calmar_ratio=calmar,
        win_rate=win_rate,
        trade_count=n_trades,
        benchmark_return=bench_ret,
        excess_return=(total_return - bench_ret) if bench_ret is not None else None,
        turnover_rate=turnover_rate,
        total_costs=total_costs,
    )
