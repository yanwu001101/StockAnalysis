# -*- coding: utf-8 -*-
"""Strategy smoke tests — every strategy instantiates and returns a sane result
on synthetic input."""
from __future__ import annotations
import datetime as dt

import pandas as pd
import pytest

from strategies import REGISTRY, by_id
from strategies.base import StrategyContext


def _synthetic_daily(n: int = 300) -> pd.DataFrame:
    dates = [dt.date(2024, 1, 1) + dt.timedelta(days=i) for i in range(n)]
    base = 100.0
    closes = [base + i * 0.1 + (i % 7) * 0.5 for i in range(n)]
    return pd.DataFrame({
        "日期": [d.isoformat() for d in dates],
        "开盘": closes,
        "收盘": closes,
        "最高": [c * 1.02 for c in closes],
        "最低": [c * 0.98 for c in closes],
        "成交量": [1_000_000 + (i * 1000) for i in range(n)],
    })


def _synthetic_fund() -> pd.DataFrame:
    rows = []
    for i in range(8):
        rows.append({
            "report_date": dt.date(2024, 1, 1) - dt.timedelta(days=90 * i),
            "revenue": 1e9, "net_profit": 1.5e8, "op_cashflow": 1.8e8,
            "ebit": 2e8, "total_assets": 5e9, "total_liab": 2e9,
            "total_equity": 3e9, "current_assets": 2e9, "current_liab": 1e9,
            "fixed_assets": 1e9, "roe": 18 - i, "gross_margin": 40,
            "debt_ratio": 40 + i, "current_ratio": 1.8, "revenue_yoy": 12,
            "net_profit_yoy": 25, "eps": 1.2, "bvps": 12.0,
        })
    return pd.DataFrame(rows)


@pytest.mark.parametrize("strategy_cls", REGISTRY)
def test_strategy_runs(strategy_cls):
    s = strategy_cls()
    ctx = StrategyContext(
        code="600519",
        name="Test",
        market_cap_yi=2000.0,
        daily_df=_synthetic_daily(),
        fundamental_df=_synthetic_fund(),
        sector_rank=0.15, sector_rank_n=30,
    )
    res = s.score(ctx)
    assert 0 <= res.score <= 100
    assert res.signal in ("bullish", "bearish", "neutral")


def test_registry_size_matches_current_suite():
    assert len(REGISTRY) == 29


def test_by_id():
    assert by_id("piotroski_f") is not None
    assert by_id("magic_formula") is not None
    assert by_id("ashare_short_reversal") is not None
    assert by_id("conservative_formula") is not None
    assert by_id("fund_price_divergence") is not None
    assert by_id("rsrs_timing") is not None
    assert by_id("trend_pullback_stop") is not None
    assert by_id("daily_momentum_reversal_t") is not None
    assert by_id("growth_trend_accelerator") is not None
    assert by_id("nonexistent") is None
