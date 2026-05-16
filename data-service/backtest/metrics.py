# -*- coding: utf-8 -*-
"""Performance metrics for backtest results."""
from __future__ import annotations
from dataclasses import dataclass

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

    def as_dict(self) -> dict:
        return {
            "total_return": round(self.total_return, 4),
            "annualized_return": round(self.annualized_return, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 4),
            "calmar_ratio": round(self.calmar_ratio, 4),
            "win_rate": round(self.win_rate, 4),
            "trade_count": self.trade_count,
        }


def compute(equity: pd.Series, trades: list[dict] | None = None,
            periods_per_year: int = 252, rf: float = 0.02) -> Metrics:
    if equity is None or equity.empty or len(equity) < 2:
        return Metrics(0, 0, 0, 0, 0, 0, 0)
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

    wins = 0
    n_trades = 0
    if trades:
        n_trades = len(trades)
        wins = sum(1 for t in trades if (t.get("pnl") or 0) > 0)
    win_rate = (wins / n_trades) if n_trades > 0 else 0.0

    return Metrics(
        total_return=total_return,
        annualized_return=float(annualized),
        max_drawdown=max_dd,
        sharpe_ratio=sharpe,
        calmar_ratio=calmar,
        win_rate=win_rate,
        trade_count=n_trades,
    )
