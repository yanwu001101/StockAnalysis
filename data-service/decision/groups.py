# -*- coding: utf-8 -*-
"""策略 → 因子组映射。

综合评分是 29 个策略的加权平均;用户看到排名变化时需要知道"变在哪一组",
所以把每个策略归入一个可解释的因子组。组分 = 组内策略按权重加权平均(排除
no_data 的策略)。组贡献 = Σ_{s∈组} w_s·score_s / Σ_all w,单位与综合分一致,
这样各组贡献之和恰好等于综合分,变动可直接相加解释。

注意:组内策略高度相关(如多个趋势类指标),组分不等于独立证据数量。
"""
from __future__ import annotations

from typing import Iterable

GROUP_ORDER = ["trend", "momentum", "volume_price", "fund", "sector", "quality", "risk"]

GROUP_LABEL = {
    "trend": "趋势",
    "momentum": "动量",
    "volume_price": "量价",
    "fund": "资金",
    "sector": "板块",
    "quality": "基本面",
    "risk": "低波/风险",
}

STRATEGY_GROUP: dict[str, str] = {
    # 趋势
    "ma_stack_breakout": "trend",
    "turtle_breakout": "trend",
    "hurst_trend": "trend",
    "trend_pullback_stop": "trend",
    "technical_resonance": "trend",
    "rsrs_timing": "trend",
    "fifty_two_week_high": "trend",
    # 动量 / 反转
    "momentum_12_1": "momentum",
    "multi_horizon_momentum": "momentum",
    "max_reversal": "momentum",
    "ashare_short_reversal": "momentum",
    "daily_momentum_reversal_t": "momentum",
    "pead": "momentum",
    # 量价
    "turnover_dryup": "volume_price",
    "chip_concentration": "volume_price",
    "boll_kdj_resonance": "volume_price",
    "macd_divergence": "volume_price",
    "fund_price_divergence": "volume_price",
    # 资金
    "northbound_smart_money": "fund",
    "lhb_followup": "fund",
    # 板块
    "sector_rotation": "sector",
    # 基本面
    "piotroski_f": "quality",
    "magic_formula": "quality",
    "quality_factor": "quality",
    "accruals_quality": "quality",
    "asset_growth": "quality",
    "growth_trend_accelerator": "quality",
    # 低波 / 风险
    "low_volatility": "risk",
    "conservative_formula": "risk",
}


def group_of(strategy_id: str) -> str:
    return STRATEGY_GROUP.get(strategy_id, "momentum")


def _effective(entries: Iterable[dict], weights: dict[str, float] | None):
    """产出 (id, score, weight) 三元组;跳过 no_data / disabled / 权重≤0。"""
    for it in entries:
        sid = it.get("id")
        if not sid:
            continue
        if it.get("no_data") or (it.get("details") or {}).get("disabled"):
            continue
        w = float(it.get("weight") or 0) if weights is None else float(weights.get(sid, 0) or 0)
        if w <= 0:
            continue
        yield sid, float(it.get("score") or 0), w


def composite_from(entries: list[dict], weights: dict[str, float] | None = None) -> float:
    """与 api.strategies_v2._score_all 完全一致的综合分口径(可用于快照重算)。"""
    total = 0.0
    wsum = 0.0
    for _sid, score, w in _effective(entries, weights):
        total += score * w
        wsum += w
    return round(total / wsum, 2) if wsum > 0 else 0.0


def group_scores(entries: list[dict], weights: dict[str, float] | None = None) -> dict:
    """返回 {group: {score, contrib, weight_share, n}}。

    score        组内加权平均分(0-100),无有效策略时为 None
    contrib      对综合分的贡献 = Σ w·score / Σ_all w,各组之和 = 综合分
    weight_share 组权重占总权重比例
    """
    acc: dict[str, dict] = {g: {"ws": 0.0, "w": 0.0, "n": 0} for g in GROUP_ORDER}
    wsum_all = 0.0
    for sid, score, w in _effective(entries, weights):
        g = group_of(sid)
        acc[g]["ws"] += score * w
        acc[g]["w"] += w
        acc[g]["n"] += 1
        wsum_all += w
    out = {}
    for g in GROUP_ORDER:
        a = acc[g]
        out[g] = {
            "score": round(a["ws"] / a["w"], 2) if a["w"] > 0 else None,
            "contrib": round(a["ws"] / wsum_all, 2) if wsum_all > 0 else 0.0,
            "weight_share": round(a["w"] / wsum_all, 4) if wsum_all > 0 else 0.0,
            "n": a["n"],
        }
    return out


def explain_delta(now_groups: dict, prev_groups: dict) -> list[dict]:
    """两份组分之间的贡献差,按绝对值降序;供"排名为什么变"展示。"""
    rows = []
    for g in GROUP_ORDER:
        a = (now_groups or {}).get(g) or {}
        b = (prev_groups or {}).get(g) or {}
        d = round(float(a.get("contrib") or 0) - float(b.get("contrib") or 0), 2)
        rows.append({"group": g, "label": GROUP_LABEL[g], "delta": d,
                     "now": a.get("score"), "prev": b.get("score")})
    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)
    return rows
