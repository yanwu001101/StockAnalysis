"""Pure prediction diagnostics. Scores, historical frequencies and risk are distinct."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

MODEL_VERSION = "prediction-2026-10-11-v2"
BASE_WEIGHTS = {
    "multi_momentum": .20, "technical_momentum": .15, "trend_structure": .18,
    "volume_price": .12, "smart_money": .13, "mean_reversion": .08,
    "volatility_regime": .09, "pattern": .05,
}
MIN_CORR_PAIRS = 12
CORR_THRESHOLD = .80


def finite(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def combine(scores: dict[str, float], history: pd.DataFrame) -> tuple[float | None, dict, dict]:
    """Past-only Spearman clusters; split base weights within correlated groups.

    Caller supplies observations strictly before the signal date. Missing pairs
    stay null; a constant series is not fabricated into an independent signal.
    """
    names = list(BASE_WEIGHTS)
    hist = history.reindex(columns=names).apply(pd.to_numeric, errors="coerce")
    hist = hist.replace([np.inf, -np.inf], np.nan).tail(60)
    corr = hist.corr(method="spearman", min_periods=MIN_CORR_PAIRS)
    counts = hist.notna().astype(int).T.dot(hist.notna().astype(int))
    active = {k: float(v) for k, v in scores.items() if k in BASE_WEIGHTS and finite(v) is not None}
    parent = {k: k for k in active}

    def root(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for i, a in enumerate(active):
        for b in list(active)[i + 1:]:
            rho = finite(corr.loc[a, b])
            if rho is not None and abs(rho) >= CORR_THRESHOLD:
                parent[root(b)] = root(a)
    groups: dict[str, list[str]] = {}
    for k in active:
        groups.setdefault(root(k), []).append(k)
    weights = {k: BASE_WEIGHTS[k] / len(groups[root(k)]) for k in active}
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()} if total else {}
    composite = sum(active[k] * weights[k] for k in active) if total else None
    report = {
        "names": names, "matrix": [[finite(corr.loc[a, b]) for b in names] for a in names],
        "pair_counts": counts.to_numpy().tolist(), "samples": len(hist),
        "threshold": CORR_THRESHOLD, "min_pairs": MIN_CORR_PAIRS,
        "clusters": list(groups.values()), "effective_weights": weights,
        "status": "AVAILABLE" if (counts.to_numpy() >= MIN_CORR_PAIRS).any() else "INSUFFICIENT_DATA",
        "method": "Spearman |ρ|≥0.80 连通分组；组内原权重/组大小，再全体归一。只用信号日前最多60个取样点。",
        "note": "指标可能相关，综合分不代表独立证据数量；资金历史缺失的相关项保留空值。",
    }
    return composite, weights, report


def layers(df: pd.DataFrame, composite: float, warnings: list[str]) -> dict:
    """Server-side entry/risk diagnostics, all anchored to the last completed bar."""
    from indicators import calc_atr
    close, high, low, volume = (df[c].astype(float) for c in ("收盘", "最高", "最低", "成交量"))
    price = float(close.iloc[-1])
    ma20 = finite(close.tail(20).mean())
    atr = finite(calc_atr(high, low, close, 14).iloc[-1])
    vol_sum = volume.tail(20).sum()
    # Typical-price volume-weighted proxy, not an intraday execution VWAP.
    vwap = finite((((high + low + close) / 3) * volume).tail(20).sum() / vol_sum) if vol_sum > 0 else None
    vol_base = finite(volume.tail(20).mean())
    volume_ratio = finite(volume.tail(5).mean() / vol_base) if vol_base and vol_base > 0 else None
    zone = [round(ma20 - atr * .5, 4), round(ma20 + atr * .5, 4)] if ma20 and atr and ma20 > atr * .5 else None
    gap = (price / zone[1] - 1) if zone and price > zone[1] else ((price / zone[0] - 1) if zone and price < zone[0] else 0.0 if zone else None)
    if composite < -.1:
        entry_state, entry_label = "BEARISH", "趋势偏弱，回踩区不构成买入信号"
    elif zone is None:
        entry_state, entry_label = "INSUFFICIENT_DATA", "买点参考数据不足"
    elif gap > .05:
        entry_state, entry_label = "EXTENDED", "远离参考区，追高风险"
    elif gap > 0:
        entry_state, entry_label = "WAIT", "参考区上方，等待回踩确认"
    elif gap < 0:
        entry_state, entry_label = "BELOW", "跌破参考区，等待企稳"
    else:
        entry_state, entry_label = "NEAR", "接近参考区，仍需价格与量能确认"
    returns = close.pct_change(fill_method=None).tail(20)
    realized = finite(returns.std(ddof=1) * np.sqrt(252)) if returns.notna().sum() >= 20 else None
    path = close.tail(20)
    drawdown = finite((path / path.cummax() - 1).min())
    as_of = str(pd.Timestamp(df["日期"].iloc[-1]).date())
    return {
        "status": "AVAILABLE", "as_of": as_of, "bars": len(df), "reference_price": price,
        "trend": {"score": round(composite * 100, 2), "scale": [-100, 100],
                  "method": "各维度方向分×去相关后权重；非上涨概率"},
        "entry": {"state": entry_state, "label": entry_label, "zone": zone,
                  "distance": finite(gap), "vwap20_proxy": vwap,
                  "vwap_deviation": price / vwap - 1 if vwap and vwap > 0 else None,
                  "volume_ratio_5_20": volume_ratio,
                  "method": "参考区=MA20±0.5ATR14；VWAP为20日典型价量加权近似，不是成交承诺"},
        "risk": {"volatility_20_annualized": realized, "max_drawdown_20": drawdown,
                 "atr14_ratio": atr / price if atr is not None and price > 0 else None,
                 "warnings": warnings,
                 "unmodeled": ["估值风险", "行业集中度", "公告事件", "涨跌停成交约束"]},
    }
