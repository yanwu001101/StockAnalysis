"""Strategy registry — single source of truth for the 10 strategies.

The screener, individual-stock evaluator, and backtest engine all iterate this
list. Adding a strategy means: write a `BaseStrategy` subclass, then register
it here.

`COMPOSITE_WEIGHTS` is the default weighting for the composite score — moved
out of `app.py` so it can be overridden via user_strategy.config_json later.
"""
from __future__ import annotations
from typing import Iterable

# Re-export legacy score_xxx functions so the un-migrated app.py routes still work.
# The new evaluator lives in api/strategies_v2.py and consumes the AbstractStrategy
# subclasses below.
from strategies.legacy import (  # noqa: F401
    score_macd_ma, score_multi_factor, score_momentum_breakout,
    score_rsi_rebound, score_bollinger_squeeze, score_chip_concentration,
    score_dividend_stability, score_northbound_flow, score_sector_rotation,
    score_kdj_rsi_resonance,
)

from strategies.base import AbstractStrategy, StrategyContext  # noqa: F401
from strategies.lhb_followup import LhbFollowup
from strategies.low_volatility import LowVolatility
from strategies.magic_formula import MagicFormula
from strategies.momentum_12_1 import Momentum12_1
from strategies.northbound_smart_money import NorthboundSmartMoney
from strategies.pead import Pead
from strategies.piotroski_f import PiotroskiF
from strategies.quality_factor import QualityFactor
from strategies.sector_rotation import SectorRotation
from strategies.technical_resonance import TechnicalResonance


REGISTRY: list[type[AbstractStrategy]] = [
    PiotroskiF,
    MagicFormula,
    QualityFactor,
    Momentum12_1,
    LowVolatility,
    Pead,
    NorthboundSmartMoney,
    LhbFollowup,
    SectorRotation,
    TechnicalResonance,
]


def all_strategies() -> list[AbstractStrategy]:
    return [cls() for cls in REGISTRY]


def by_id(strategy_id: str) -> AbstractStrategy | None:
    for cls in REGISTRY:
        if cls.id == strategy_id:
            return cls()
    return None


COMPOSITE_WEIGHTS: dict[str, float] = {cls.id: cls.default_weight for cls in REGISTRY}


# UI-facing tunable parameter spec. Each entry describes ONE slider on the
# strategy card. The runner reads these by id when applying user overrides.
STRATEGY_PARAM_SPECS: dict[str, list[dict]] = {
    "piotroski_f": [
        {"name": "bullish_threshold", "label": "看多阈值 (F-Score)", "default": 7, "min": 4, "max": 9, "step": 1, "desc": "F-Score >= 此值视为看多"},
        {"name": "bearish_threshold", "label": "看空阈值", "default": 3, "min": 1, "max": 5, "step": 1, "desc": "F-Score <= 此值视为看空"},
    ],
    "magic_formula": [
        {"name": "min_ebit", "label": "EBIT 下限 (亿)", "default": 1.0, "min": 0.1, "max": 50.0, "step": 0.1, "desc": "EBIT 低于此值不参与排名"},
    ],
    "quality_factor": [
        {"name": "min_roe", "label": "最低 ROE (%)", "default": 12, "min": 5, "max": 25, "step": 1},
        {"name": "max_debt_ratio", "label": "最大资产负债率 (%)", "default": 60, "min": 30, "max": 90, "step": 5},
    ],
    "momentum_12_1": [
        {"name": "lookback_days", "label": "回看交易日", "default": 220, "min": 60, "max": 250, "step": 10},
        {"name": "skip_days", "label": "跳过最近 N 日", "default": 20, "min": 0, "max": 30, "step": 5, "desc": "排除短期反转效应"},
    ],
    "low_volatility": [
        {"name": "lookback_days", "label": "波动率回看日", "default": 60, "min": 20, "max": 120, "step": 10},
    ],
    "pead": [
        {"name": "strong_growth_threshold", "label": "强增速线 (%)", "default": 30, "min": 10, "max": 60, "step": 5, "desc": "净利同比超过此值视为强信号"},
        {"name": "event_window_days", "label": "事件窗口 (日)", "default": 60, "min": 30, "max": 90, "step": 5},
    ],
    "northbound_smart_money": [
        {"name": "short_window", "label": "短期窗口", "default": 5, "min": 3, "max": 10, "step": 1},
        {"name": "mid_window", "label": "中期窗口", "default": 10, "min": 5, "max": 20, "step": 1},
        {"name": "long_window", "label": "长期窗口", "default": 20, "min": 15, "max": 40, "step": 5},
    ],
    "lhb_followup": [
        {"name": "window_days", "label": "查看天数", "default": 7, "min": 3, "max": 30, "step": 1},
        {"name": "strong_net", "label": "强净买额 (万)", "default": 5000, "min": 1000, "max": 20000, "step": 1000, "scale": 10000, "desc": "净买入超过此值视为强信号"},
    ],
    "sector_rotation": [
        {"name": "top_pct", "label": "板块前几分位算热", "default": 0.20, "min": 0.10, "max": 0.50, "step": 0.05},
        {"name": "bottom_pct", "label": "板块后几分位算冷", "default": 0.80, "min": 0.50, "max": 0.90, "step": 0.05},
    ],
    "technical_resonance": [
        {"name": "golden_cross_lookback", "label": "金叉回看", "default": 5, "min": 2, "max": 10, "step": 1},
        {"name": "volume_surge_factor", "label": "放量阈值倍数", "default": 1.5, "min": 1.0, "max": 3.0, "step": 0.1},
    ],
}


def list_meta() -> list[dict]:
    """Used by the Spring Boot ScreenerController to advertise available strategies."""
    return [
        {"id": cls.id, "name": cls.name, "weight": cls.default_weight,
         "params": STRATEGY_PARAM_SPECS.get(cls.id, [])}
        for cls in REGISTRY
    ]
