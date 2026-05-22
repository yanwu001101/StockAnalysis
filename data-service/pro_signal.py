# -*- coding: utf-8 -*-
"""Pro Signal — leading-indicator real-time prediction engine.

Designed to complement the lagging-friendly `predictor.py`. Every dimension
here is engineered to react quickly to fresh price/volume information, using
indicators that institutional desks use for short-horizon directional reads:

  * Heikin-Ashi trend strength       (smoothed but fast)
  * DEMA(20) / TEMA(20) slope        (low-lag EMA variants)
  * TSI (True Strength Index, Blau 1991) — double-smoothed momentum
  * VWAP deviation                   (cost-basis anchor)
  * Volume Profile POC vs price      (auction-theory anchor)
  * Chaikin Money Flow (20)          (close-position + volume)
  * Order-flow proxy                 (close-to-high ratio × volume)
  * Short-term EMA cross + volume confirm
  * 5-day breadth (close - prior_close patterns)

Composite is converted to a probability via tanh + linear stretching with
explicit confidence reporting (signal agreement × data quality × strength).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from indicators import calc_ema, calc_atr


@dataclass
class ProDimension:
    name: str
    name_en: str
    score: float        # -1 to +1
    weight: float
    detail: str = ""
    value: str = ""     # short numeric/string value for UI chips


@dataclass
class ProSignalResult:
    code: str
    name: str
    price: float
    probability_up: float
    probability_down: float
    confidence: float
    direction: str             # "up" / "down" / "flat"
    label: str                 # 强烈看多 / 看多 / 偏多 / 中性 / 偏空 / 看空 / 强烈看空
    composite: float
    dimensions: list[ProDimension] = field(default_factory=list)
    key_signals: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    horizon: str = "T+1 ~ T+5 短期方向"


def _safe(v, default=0.0):
    try:
        x = float(v)
        return default if (pd.isna(x) or np.isinf(x)) else x
    except Exception:
        return default


# ---------------------------------------------------------------------------
# Indicator math
# ---------------------------------------------------------------------------

def _heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    o = df["开盘"].astype(float)
    c = df["收盘"].astype(float)
    h = df["最高"].astype(float)
    l = df["最低"].astype(float)
    ha_close = (o + h + l + c) / 4.0
    ha_open = ha_close.copy()
    ha_open.iloc[0] = (o.iloc[0] + c.iloc[0]) / 2
    for i in range(1, len(ha_close)):
        ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2
    return pd.DataFrame({"o": ha_open, "c": ha_close,
                          "h": pd.concat([ha_open, ha_close, h], axis=1).max(axis=1),
                          "l": pd.concat([ha_open, ha_close, l], axis=1).min(axis=1)})


def _dema(series: pd.Series, n: int) -> pd.Series:
    e1 = calc_ema(series, n)
    e2 = calc_ema(e1, n)
    return 2 * e1 - e2


def _tema(series: pd.Series, n: int) -> pd.Series:
    e1 = calc_ema(series, n)
    e2 = calc_ema(e1, n)
    e3 = calc_ema(e2, n)
    return 3 * e1 - 3 * e2 + e3


def _tsi(close: pd.Series, r: int = 25, s: int = 13) -> pd.Series:
    diff = close.diff()
    abs_diff = diff.abs()
    smooth1 = calc_ema(diff, r)
    smooth2 = calc_ema(smooth1, s)
    abs_smooth1 = calc_ema(abs_diff, r)
    abs_smooth2 = calc_ema(abs_smooth1, s)
    return 100 * (smooth2 / abs_smooth2.replace(0, np.nan))


def _vwap_proxy(df: pd.DataFrame, period: int) -> pd.Series:
    """Volume-weighted average price over the last `period` bars (rolling).
    Without intraday data we approximate using the typical price × volume.
    """
    typical = (df["最高"].astype(float) + df["最低"].astype(float) + df["收盘"].astype(float)) / 3.0
    vol = df["成交量"].astype(float)
    tpv = (typical * vol).rolling(period).sum()
    vol_sum = vol.rolling(period).sum().replace(0, np.nan)
    return tpv / vol_sum


def _volume_profile_poc(df: pd.DataFrame, bins: int = 20) -> tuple[float, float, float]:
    """Compute Volume-Profile POC (Point of Control), VAH, VAL from recent bars.

    POC = price bin with the highest traded volume in the lookback.
    VA = bins covering ~70% of the volume around POC.
    """
    close = df["收盘"].astype(float)
    vol = df["成交量"].astype(float)
    lo, hi = float(close.min()), float(close.max())
    if hi <= lo:
        return float(close.iloc[-1]), float(close.iloc[-1]), float(close.iloc[-1])
    edges = np.linspace(lo, hi, bins + 1)
    idx = np.clip(np.searchsorted(edges, close.values, side="right") - 1, 0, bins - 1)
    by_bin = np.zeros(bins)
    for i, v in zip(idx, vol.values):
        by_bin[i] += float(v)
    poc_bin = int(np.argmax(by_bin))
    centers = (edges[:-1] + edges[1:]) / 2
    poc = float(centers[poc_bin])
    # 70% volume area around POC
    total = by_bin.sum()
    if total <= 0:
        return poc, poc, poc
    cum = by_bin[poc_bin]
    lo_i = hi_i = poc_bin
    while cum / total < 0.70:
        ext_lo = by_bin[lo_i - 1] if lo_i > 0 else -1
        ext_hi = by_bin[hi_i + 1] if hi_i < bins - 1 else -1
        if ext_lo < 0 and ext_hi < 0:
            break
        if ext_hi >= ext_lo:
            hi_i += 1
            cum += by_bin[hi_i]
        else:
            lo_i -= 1
            cum += by_bin[lo_i]
    return poc, float(centers[hi_i]), float(centers[lo_i])


def _chaikin_money_flow(df: pd.DataFrame, period: int = 20) -> float:
    h = df["最高"].astype(float)
    l = df["最低"].astype(float)
    c = df["收盘"].astype(float)
    v = df["成交量"].astype(float)
    rng = (h - l).replace(0, np.nan)
    mfv = ((c - l) - (h - c)) / rng * v
    cmf = mfv.tail(period).sum() / v.tail(period).sum() if v.tail(period).sum() > 0 else 0
    return float(cmf) if pd.notna(cmf) else 0.0


# ---------------------------------------------------------------------------
# Dimensions
# ---------------------------------------------------------------------------

def _dim_heikin_ashi(df: pd.DataFrame) -> ProDimension:
    ha = _heikin_ashi(df)
    last7 = ha.tail(7)
    up = (last7["c"] > last7["o"]).sum()
    down = (last7["c"] < last7["o"]).sum()
    last3 = ha.tail(3)
    streak_up = all(last3["c"] > last3["o"])
    streak_down = all(last3["c"] < last3["o"])

    score = (up - down) / 7.0
    if streak_up:
        score = max(score, 0.6)
    if streak_down:
        score = min(score, -0.6)
    detail = f"近7日 HA {up}红/{down}绿"
    if streak_up:
        detail += " · 连3红实体"
    if streak_down:
        detail += " · 连3绿实体"
    return ProDimension(name="Heikin-Ashi 趋势", name_en="ha",
                        score=score, weight=0.14, detail=detail,
                        value=f"{up}/{7}")


def _dim_dema_tema(df: pd.DataFrame) -> ProDimension:
    close = df["收盘"].astype(float)
    if len(close) < 30:
        return ProDimension(name="DEMA/TEMA 趋势", name_en="dema_tema",
                            score=0, weight=0.13, detail="数据不足", value="-")
    dema = _dema(close, 20)
    tema = _tema(close, 20)
    last = float(close.iloc[-1])
    d_last = float(dema.iloc[-1])
    t_last = float(tema.iloc[-1])
    d_slope = (d_last - float(dema.iloc[-5])) / float(dema.iloc[-5]) if dema.iloc[-5] != 0 else 0
    t_slope = (t_last - float(tema.iloc[-5])) / float(tema.iloc[-5]) if tema.iloc[-5] != 0 else 0
    score = 0.0
    if last > t_last > d_last:
        score = 0.6
    elif last > d_last and last > t_last:
        score = 0.4
    elif last < t_last < d_last:
        score = -0.6
    elif last < d_last and last < t_last:
        score = -0.4
    score += np.sign(d_slope) * min(0.3, abs(d_slope) * 30)
    score = max(-1.0, min(1.0, score))
    detail = f"DEMA斜率 {d_slope*100:+.2f}% · TEMA斜率 {t_slope*100:+.2f}%"
    return ProDimension(name="DEMA/TEMA 趋势", name_en="dema_tema",
                        score=score, weight=0.13, detail=detail,
                        value=f"{d_slope*100:+.2f}%")


def _dim_tsi(df: pd.DataFrame) -> ProDimension:
    close = df["收盘"].astype(float)
    if len(close) < 50:
        return ProDimension(name="TSI 真实力度", name_en="tsi",
                            score=0, weight=0.12, detail="数据不足", value="-")
    tsi = _tsi(close)
    tsi_sig = calc_ema(tsi, 7)
    last = float(tsi.iloc[-1])
    prev = float(tsi.iloc[-2])
    sig = float(tsi_sig.iloc[-1])
    score = 0.0
    detail_parts = []
    # Zero-line cross
    if last > 0 and prev <= 0:
        score += 0.5
        detail_parts.append("TSI上穿0轴")
    elif last < 0 and prev >= 0:
        score -= 0.5
        detail_parts.append("TSI下穿0轴")
    # TSI vs signal
    if last > sig:
        score += 0.25
    else:
        score -= 0.25
    # Direction
    if last > prev:
        score += 0.15
    else:
        score -= 0.15
    score = max(-1.0, min(1.0, score))
    detail_parts.append(f"TSI={last:.1f}")
    return ProDimension(name="TSI 真实力度", name_en="tsi",
                        score=score, weight=0.12,
                        detail=" · ".join(detail_parts),
                        value=f"{last:.1f}")


def _dim_vwap(df: pd.DataFrame) -> ProDimension:
    if len(df) < 20:
        return ProDimension(name="VWAP 偏离", name_en="vwap",
                            score=0, weight=0.11, detail="数据不足", value="-")
    vwap20 = _vwap_proxy(df, 20)
    vwap60 = _vwap_proxy(df, 60)
    close = df["收盘"].astype(float)
    last = float(close.iloc[-1])
    v20 = float(vwap20.iloc[-1])
    v60 = float(vwap60.iloc[-1]) if not pd.isna(vwap60.iloc[-1]) else v20
    dev20 = (last / v20 - 1) if v20 > 0 else 0
    dev60 = (last / v60 - 1) if v60 > 0 else 0
    score = 0.0
    if 0 < dev20 < 0.05 and 0 < dev60 < 0.10:
        score = 0.6
    elif dev20 > 0.10:
        score = -0.2     # over-extended
    elif dev20 < -0.05 and dev60 < -0.05:
        score = -0.5
    elif dev20 < 0 and dev60 > 0:
        score = 0.2
    else:
        score = dev20 * 4
    score = max(-1.0, min(1.0, score))
    detail = f"现价 / VWAP20={dev20*100:+.2f}% · VWAP60={dev60*100:+.2f}%"
    return ProDimension(name="VWAP 偏离", name_en="vwap",
                        score=score, weight=0.11, detail=detail,
                        value=f"{dev20*100:+.2f}%")


def _dim_volume_profile(df: pd.DataFrame) -> ProDimension:
    if len(df) < 40:
        return ProDimension(name="量价分布 POC", name_en="vp",
                            score=0, weight=0.10, detail="数据不足", value="-")
    recent = df.tail(60)
    poc, vah, val = _volume_profile_poc(recent)
    last = float(recent["收盘"].astype(float).iloc[-1])
    score = 0.0
    detail = ""
    if poc <= 0:
        return ProDimension(name="量价分布 POC", name_en="vp",
                            score=0, weight=0.10, detail="POC 计算失败", value="-")
    if last > vah:
        score = 0.5
        detail = "价格突破 VAH 上沿"
    elif last < val:
        score = -0.5
        detail = "价格跌破 VAL 下沿"
    elif last > poc:
        score = 0.25
        detail = "价格站在 POC 上方"
    elif last < poc:
        score = -0.25
        detail = "价格位于 POC 下方"
    else:
        detail = "价格围绕 POC 震荡"
    detail += f" · POC={poc:.2f}"
    return ProDimension(name="量价分布 POC", name_en="vp",
                        score=score, weight=0.10, detail=detail,
                        value=f"{poc:.2f}")


def _dim_cmf(df: pd.DataFrame) -> ProDimension:
    if len(df) < 21:
        return ProDimension(name="CMF 资金流", name_en="cmf",
                            score=0, weight=0.10, detail="数据不足", value="-")
    cmf = _chaikin_money_flow(df, 20)
    score = max(-1.0, min(1.0, cmf * 5))    # CMF range typically [-0.3, 0.3]
    if cmf > 0.15:
        detail = "CMF 强势资金流入"
    elif cmf > 0.05:
        detail = "CMF 偏多"
    elif cmf < -0.15:
        detail = "CMF 强势资金流出"
    elif cmf < -0.05:
        detail = "CMF 偏空"
    else:
        detail = "CMF 中性"
    return ProDimension(name="CMF 资金流", name_en="cmf",
                        score=score, weight=0.10, detail=detail,
                        value=f"{cmf:+.3f}")


def _dim_order_flow(df: pd.DataFrame) -> ProDimension:
    if len(df) < 10:
        return ProDimension(name="盘口主动度", name_en="order_flow",
                            score=0, weight=0.10, detail="数据不足", value="-")
    last5 = df.tail(5)
    h = last5["最高"].astype(float)
    l = last5["最低"].astype(float)
    c = last5["收盘"].astype(float)
    v = last5["成交量"].astype(float)
    rng = (h - l).replace(0, np.nan)
    # close position in range: 1 = closed at high, 0 = at low
    pos = ((c - l) / rng).fillna(0.5)
    weighted = (pos * v).sum() / v.sum() if v.sum() > 0 else 0.5
    score = (weighted - 0.5) * 2     # map [0, 1] to [-1, +1]
    detail = f"5日均收盘相对位置 = {weighted:.0%}"
    return ProDimension(name="盘口主动度", name_en="order_flow",
                        score=score, weight=0.10, detail=detail,
                        value=f"{weighted:.0%}")


def _dim_short_ema_cross(df: pd.DataFrame) -> ProDimension:
    close = df["收盘"].astype(float)
    if len(close) < 15:
        return ProDimension(name="短EMA交叉", name_en="ema_cross",
                            score=0, weight=0.10, detail="数据不足", value="-")
    e5 = calc_ema(close, 5)
    e10 = calc_ema(close, 10)
    score = 0.0
    detail = ""
    # Recent cross
    cross_up = e5.iloc[-1] > e10.iloc[-1] and e5.iloc[-2] <= e10.iloc[-2]
    cross_dn = e5.iloc[-1] < e10.iloc[-1] and e5.iloc[-2] >= e10.iloc[-2]
    if cross_up:
        score += 0.6
        detail = "EMA5上穿EMA10"
    elif cross_dn:
        score -= 0.6
        detail = "EMA5下穿EMA10"
    elif e5.iloc[-1] > e10.iloc[-1]:
        score += 0.25
        detail = "EMA5 在 EMA10 之上"
    else:
        score -= 0.25
        detail = "EMA5 在 EMA10 之下"
    # Volume confirm
    if len(df) >= 10:
        v = df["成交量"].astype(float)
        v_last = float(v.iloc[-1])
        v_avg = float(v.tail(10).mean())
        if v_avg > 0 and v_last > 1.3 * v_avg:
            score += 0.15 * np.sign(score)
            detail += " · 放量确认"
    score = max(-1.0, min(1.0, score))
    return ProDimension(name="短EMA交叉", name_en="ema_cross",
                        score=score, weight=0.10, detail=detail,
                        value="↑" if score > 0 else "↓")


def _dim_breadth(df: pd.DataFrame) -> ProDimension:
    if len(df) < 10:
        return ProDimension(name="5日宽度", name_en="breadth",
                            score=0, weight=0.10, detail="数据不足", value="-")
    last5 = df.tail(5)
    c = last5["收盘"].astype(float).values
    diffs = np.diff(c)
    up_days = int((diffs > 0).sum())
    down_days = int((diffs < 0).sum())
    avg = float(np.mean(diffs / c[:-1])) if len(diffs) else 0
    score = ((up_days - down_days) / 4.0) * 0.7 + np.sign(avg) * min(0.3, abs(avg) * 30)
    score = max(-1.0, min(1.0, score))
    detail = f"近5日 {up_days}涨{down_days}跌 · 均日{avg*100:+.2f}%"
    return ProDimension(name="5日宽度", name_en="breadth",
                        score=score, weight=0.10, detail=detail,
                        value=f"{up_days}/{up_days+down_days}")


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def pro_signal(ctx) -> ProSignalResult:
    df = ctx.daily_df
    if df is None or len(df) < 25:
        return ProSignalResult(
            code=ctx.code, name=ctx.name, price=ctx.price,
            probability_up=50.0, probability_down=50.0, confidence=0.0,
            direction="flat", label="数据不足", composite=0.0,
            key_signals=["K线不足，无法做专业级预测"],
            risks=["历史数据少于25个交易日"],
        )
    df = df.sort_values("日期" if "日期" in df.columns else df.columns[0]).reset_index(drop=True)

    dims = [
        _dim_heikin_ashi(df),
        _dim_dema_tema(df),
        _dim_tsi(df),
        _dim_vwap(df),
        _dim_volume_profile(df),
        _dim_cmf(df),
        _dim_order_flow(df),
        _dim_short_ema_cross(df),
        _dim_breadth(df),
    ]

    # Weighted composite
    total_w = sum(d.weight for d in dims)
    composite = sum(d.score * d.weight for d in dims) / total_w if total_w > 0 else 0.0

    # tanh sharpens the middle; we use a steepness of 2.2
    prob_up_raw = 0.5 + 0.5 * math.tanh(composite * 2.2)
    prob_up = round(prob_up_raw * 100, 1)
    prob_down = round((1 - prob_up_raw) * 100, 1)

    # Confidence: agreement × data quality × strength
    scores = [d.score for d in dims]
    pos = sum(1 for s in scores if s > 0.15)
    neg = sum(1 for s in scores if s < -0.15)
    agreement = max(pos, neg) / len(scores) if scores else 0
    avg_strength = sum(abs(s) for s in scores) / len(scores) if scores else 0
    data_q = min(1.0, len(df) / 90)
    confidence = round((agreement * 0.45 + data_q * 0.20 + avg_strength * 0.35) * 100, 1)
    confidence = max(10.0, min(95.0, confidence))

    # Direction & label
    if prob_up >= 70:
        direction, label = "up", "强烈看多"
    elif prob_up >= 60:
        direction, label = "up", "看多"
    elif prob_up >= 53:
        direction, label = "up", "偏多"
    elif prob_up <= 30:
        direction, label = "down", "强烈看空"
    elif prob_up <= 40:
        direction, label = "down", "看空"
    elif prob_up <= 47:
        direction, label = "down", "偏空"
    else:
        direction, label = "flat", "中性"

    sorted_dims = sorted(dims, key=lambda d: abs(d.score), reverse=True)
    key_signals = []
    for d in sorted_dims[:4]:
        if abs(d.score) > 0.2:
            arrow = "看多" if d.score > 0 else "看空"
            key_signals.append(f"{d.name}: {d.detail} ({arrow})")
    if not key_signals:
        key_signals.append("各 leading 指标均不强")

    risks = []
    if confidence < 40:
        risks.append("信号分歧大，方向感不强")
    # Over-extension warning (VWAP > 10%)
    vwap_dim = next((d for d in dims if d.name_en == "vwap"), None)
    if vwap_dim and "+10" in (vwap_dim.value or ""):
        risks.append("价格已远离 VWAP，短期超买")
    if not risks:
        risks.append("暂无明显风险信号")

    return ProSignalResult(
        code=ctx.code, name=ctx.name, price=ctx.price,
        probability_up=prob_up, probability_down=prob_down,
        confidence=confidence, direction=direction, label=label,
        composite=round(composite, 4),
        dimensions=dims, key_signals=key_signals, risks=risks,
        horizon="T+1 ~ T+5 短期方向",
    )
