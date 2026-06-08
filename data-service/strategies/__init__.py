"""Strategy registry — single source of truth for the strategy suite.

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
from strategies.turtle_breakout import TurtleBreakout
from strategies.boll_kdj_resonance import BollKdjResonance
from strategies.macd_divergence import MacdDivergence
from strategies.max_reversal import MaxReversal
from strategies.hurst_trend import HurstTrend
from strategies.turnover_dryup import TurnoverDryUp
from strategies.fifty_two_week_high import FiftyTwoWeekHigh
from strategies.accruals_quality import AccrualsQuality
from strategies.asset_growth import AssetGrowth
from strategies.chip_concentration import ChipConcentration
from strategies.ma_stack_breakout import MAStack
from strategies.multi_horizon_momentum import MultiHorizonMomentum
from strategies.ashare_short_reversal import AShareShortReversal
from strategies.conservative_formula import ConservativeFormula
from strategies.fund_price_divergence import FundPriceDivergence
from strategies.rsrs_timing import RsrsTiming
from strategies.trend_pullback_stop import TrendPullbackStop
from strategies.daily_momentum_reversal_t import DailyMomentumReversalT
from strategies.growth_trend_accelerator import GrowthTrendAccelerator


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
    TurtleBreakout,
    BollKdjResonance,
    MacdDivergence,
    MaxReversal,
    HurstTrend,
    TurnoverDryUp,
    FiftyTwoWeekHigh,
    AccrualsQuality,
    AssetGrowth,
    ChipConcentration,
    MAStack,
    MultiHorizonMomentum,
    AShareShortReversal,
    ConservativeFormula,
    FundPriceDivergence,
    RsrsTiming,
    TrendPullbackStop,
    DailyMomentumReversalT,
    GrowthTrendAccelerator,
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
    "turtle_breakout": [
        {"name": "channel_days", "label": "通道周期 (日)", "default": 20, "min": 10, "max": 60, "step": 5, "desc": "Donchian 通道天数"},
        {"name": "atr_period", "label": "ATR 周期", "default": 14, "min": 7, "max": 30, "step": 1},
        {"name": "atr_mult_min", "label": "ATR 最低占比倍数", "default": 0.8, "min": 0.5, "max": 2.0, "step": 0.1},
    ],
    "boll_kdj_resonance": [
        {"name": "boll_period", "label": "布林周期", "default": 20, "min": 10, "max": 40, "step": 5},
        {"name": "boll_std", "label": "布林标准差", "default": 2.0, "min": 1.5, "max": 3.0, "step": 0.5},
        {"name": "j_oversold", "label": "J 超卖线", "default": 20, "min": 0, "max": 40, "step": 5},
    ],
    "macd_divergence": [
        {"name": "lookback_days", "label": "扫描窗口 (日)", "default": 60, "min": 30, "max": 120, "step": 10},
        {"name": "pivot_window", "label": "枢轴半窗", "default": 5, "min": 3, "max": 10, "step": 1, "desc": "用于定位前后高低点"},
    ],
    "max_reversal": [
        {"name": "window_days", "label": "扫描天数", "default": 22, "min": 10, "max": 60, "step": 2},
        {"name": "top_k", "label": "看几个最大涨幅", "default": 5, "min": 1, "max": 10, "step": 1},
        {"name": "high_max_pct", "label": "高单日警戒线", "default": 0.09, "min": 0.03, "max": 0.20, "step": 0.01},
    ],
    "hurst_trend": [
        {"name": "lookback_days", "label": "回看长度 (日)", "default": 180, "min": 90, "max": 365, "step": 15},
        {"name": "trend_threshold", "label": "趋势阈值 H", "default": 0.55, "min": 0.50, "max": 0.65, "step": 0.01},
        {"name": "revert_threshold", "label": "反转阈值 H", "default": 0.45, "min": 0.35, "max": 0.50, "step": 0.01},
    ],
    "turnover_dryup": [
        {"name": "lookback_days", "label": "缩量观察日", "default": 30, "min": 10, "max": 60, "step": 5},
        {"name": "low_quantile", "label": "低量分位线", "default": 0.30, "min": 0.10, "max": 0.50, "step": 0.05},
        {"name": "near_low_pct", "label": "接近底部容差", "default": 0.05, "min": 0.01, "max": 0.10, "step": 0.01},
    ],
    "fifty_two_week_high": [
        {"name": "lookback_days", "label": "52周观察日", "default": 250, "min": 120, "max": 365, "step": 10},
        {"name": "high_proximity_pct", "label": "接近高点阈值", "default": 0.95, "min": 0.85, "max": 0.99, "step": 0.01},
        {"name": "very_close_pct", "label": "极近高点阈值", "default": 0.98, "min": 0.95, "max": 0.999, "step": 0.005},
    ],
    "accruals_quality": [
        {"name": "high_accrual_threshold", "label": "高应计阈值", "default": 0.10, "min": 0.05, "max": 0.20, "step": 0.01, "desc": "应计/资产 高于此值警示"},
        {"name": "low_accrual_threshold", "label": "低应计阈值", "default": 0.02, "min": 0.0, "max": 0.05, "step": 0.005},
    ],
    "asset_growth": [
        {"name": "healthy_low", "label": "健康增长下限", "default": 0.05, "min": 0.0, "max": 0.15, "step": 0.01},
        {"name": "healthy_high", "label": "健康增长上限", "default": 0.20, "min": 0.10, "max": 0.40, "step": 0.05},
        {"name": "explosive_threshold", "label": "扩张警示线", "default": 0.40, "min": 0.20, "max": 1.0, "step": 0.05},
    ],
    "chip_concentration": [
        {"name": "lookback_days", "label": "回看天数", "default": 60, "min": 20, "max": 120, "step": 5},
        {"name": "tight_band_pct", "label": "紧密带阈值", "default": 0.10, "min": 0.05, "max": 0.20, "step": 0.01},
        {"name": "very_tight_pct", "label": "极紧带阈值", "default": 0.06, "min": 0.02, "max": 0.10, "step": 0.01},
    ],
    "ma_stack_breakout": [
        {"name": "compression_threshold", "label": "粘合阈值", "default": 0.04, "min": 0.02, "max": 0.10, "step": 0.005},
        {"name": "very_compressed", "label": "强粘合阈值", "default": 0.025, "min": 0.01, "max": 0.05, "step": 0.005},
    ],
    "multi_horizon_momentum": [
        {"name": "short_days", "label": "短期窗口 (日)", "default": 5, "min": 3, "max": 10, "step": 1},
        {"name": "medium_days", "label": "中期窗口 (日)", "default": 21, "min": 15, "max": 30, "step": 1},
        {"name": "long_days", "label": "长期窗口 (日)", "default": 63, "min": 30, "max": 90, "step": 5},
        {"name": "skip_days", "label": "12-1 跳过近期 (日)", "default": 21, "min": 10, "max": 30, "step": 5},
        {"name": "consistency_min", "label": "一致性最低数", "default": 3, "min": 2, "max": 4, "step": 1, "desc": "几个时间窗口同向才加分"},
    ],
    "ashare_short_reversal": [
        {"name": "window_days", "label": "反转观察日", "default": 10, "min": 5, "max": 20, "step": 1},
        {"name": "oversold_return", "label": "超跌收益线", "default": -0.08, "min": -0.20, "max": -0.03, "step": 0.01},
        {"name": "overheat_return", "label": "过热收益线", "default": 0.15, "min": 0.08, "max": 0.30, "step": 0.01},
    ],
    "conservative_formula": [
        {"name": "vol_days", "label": "低波动观察日", "default": 60, "min": 30, "max": 120, "step": 5},
        {"name": "momentum_days", "label": "趋势观察日", "default": 63, "min": 30, "max": 120, "step": 5},
        {"name": "max_debt_ratio", "label": "最大负债率", "default": 65, "min": 35, "max": 90, "step": 5},
    ],
    "fund_price_divergence": [
        {"name": "window_days", "label": "资金窗口", "default": 5, "min": 3, "max": 20, "step": 1},
        {"name": "strong_inflow", "label": "强流入线", "default": 50000000, "min": 10000000, "max": 200000000, "step": 10000000},
        {"name": "strong_outflow", "label": "强流出线", "default": -50000000, "min": -200000000, "max": -10000000, "step": 10000000},
    ],
    "rsrs_timing": [
        {"name": "window_days", "label": "回归窗口", "default": 18, "min": 12, "max": 30, "step": 1},
        {"name": "zscore_days", "label": "标准化窗口", "default": 110, "min": 60, "max": 180, "step": 10},
        {"name": "bullish_z", "label": "突破确认线", "default": 0.7, "min": 0.3, "max": 1.5, "step": 0.1},
        {"name": "bearish_z", "label": "支撑转弱线", "default": -0.7, "min": -1.5, "max": -0.3, "step": 0.1},
    ],
    "trend_pullback_stop": [
        {"name": "fast_ma", "label": "短均线", "default": 20, "min": 10, "max": 30, "step": 5},
        {"name": "slow_ma", "label": "趋势均线", "default": 60, "min": 40, "max": 120, "step": 10},
        {"name": "trail_mult", "label": "ATR 止盈倍数", "default": 2.6, "min": 1.5, "max": 4.0, "step": 0.1},
    ],
    "daily_momentum_reversal_t": [
        {"name": "momentum_1d", "label": "日频动量线", "default": 0.018, "min": 0.005, "max": 0.05, "step": 0.001},
        {"name": "hot_3d", "label": "3日过热线", "default": 0.075, "min": 0.04, "max": 0.15, "step": 0.005},
        {"name": "hot_5d", "label": "5日过热线", "default": 0.12, "min": 0.06, "max": 0.25, "step": 0.01},
    ],
    "growth_trend_accelerator": [
        {"name": "min_profit_yoy", "label": "净利增速线", "default": 20, "min": 5, "max": 80, "step": 5},
        {"name": "min_revenue_yoy", "label": "营收增速线", "default": 10, "min": 0, "max": 50, "step": 5},
        {"name": "momentum_days", "label": "趋势观察日", "default": 63, "min": 30, "max": 120, "step": 5},
    ],
}


def list_meta() -> list[dict]:
    """Used by the Spring Boot ScreenerController to advertise available strategies."""
    return [
        {"id": cls.id, "name": cls.name, "weight": cls.default_weight,
         "params": STRATEGY_PARAM_SPECS.get(cls.id, [])}
        for cls in REGISTRY
    ]
