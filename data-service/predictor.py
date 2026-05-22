# -*- coding: utf-8 -*-
"""Multi-signal stock prediction engine.

Produces an up/down probability with confidence by combining 8 signal dimensions:
  1. Multi-Horizon Momentum — 5d/21d/63d/12-1m returns + Sharpe + consistency
                              (Carhart / AQR / Moskowitz time-series momentum)
  2. Technical Momentum     — MACD, RSI, KDJ multi-indicator convergence
  3. Trend Structure        — MA alignment + ADX trend strength
  4. Volume-Price           — OBV trend, volume-price divergence
  5. Smart Money            — northbound + main fund flow
  6. Mean Reversion         — RSI extremes, Bollinger band deviation
  7. Volatility Regime      — ATR squeeze → expansion, Bollinger bandwidth
  8. Candlestick Pattern    — key reversal/continuation patterns

Each dimension outputs a direction score ∈ [-1, +1].
Final probability is a weighted sigmoid of the composite direction.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from indicators import calc_macd, calc_rsi, calc_kdj, calc_bollinger, calc_atr, calc_ema


# ---------------------------------------------------------------------------
# Output data models
# ---------------------------------------------------------------------------

@dataclass
class SignalDimension:
    name: str
    name_en: str
    score: float          # -1.0 (bearish) to +1.0 (bullish)
    weight: float         # relative weight (normalized internally)
    detail: str = ""      # human-readable explanation
    sub_signals: dict = field(default_factory=dict)


@dataclass
class PredictionResult:
    code: str
    name: str
    price: float
    probability_up: float       # 0-100
    probability_down: float     # 0-100
    confidence: float           # 0-100
    signal: str                 # "bullish" | "bearish" | "neutral"
    signal_label: str           # Chinese label
    composite_direction: float  # -1 to +1
    dimensions: list[SignalDimension] = field(default_factory=list)
    key_drivers: list[str] = field(default_factory=list)
    risk_warnings: list[str] = field(default_factory=list)
    time_horizon: str = "短期 (3-5个交易日)"


# ---------------------------------------------------------------------------
# Individual signal dimension calculators
# ---------------------------------------------------------------------------

def _safe_float(val, default=0.0) -> float:
    try:
        v = float(val)
        return default if (pd.isna(v) or np.isinf(v)) else v
    except Exception:
        return default


def _calc_multi_horizon_momentum(df: pd.DataFrame) -> SignalDimension:
    """Multi-horizon momentum factor — institutional-grade composite.

    Combines four classic momentum specifications (1w / 1m / 3m / 12-1m)
    plus a Sharpe-adjusted return and a cross-horizon consistency check.
    This is the single most predictive direction signal in cross-sectional
    equity research (Jegadeesh-Titman 1993, Carhart 1997, Moskowitz 2012).
    """
    close = df["收盘"].astype(float)
    n = len(close)
    subs: dict = {}

    if n < 30:
        return SignalDimension(
            name="多维度动量", name_en="multi_momentum",
            score=0.0, weight=0.20, detail="K线不足，无法计算多周期动量",
            sub_signals={"insufficient": True},
        )

    def ret(days: int):
        if n <= days:
            return None
        a, b = float(close.iloc[-1]), float(close.iloc[-1 - days])
        return (a / b - 1.0) if b > 0 else None

    r_1w = ret(5)
    r_1m = ret(21)
    r_3m = ret(63)
    r_12_1 = None
    if n > 252:
        a, b = float(close.iloc[-1 - 21]), float(close.iloc[-1 - 252])
        if b > 0:
            r_12_1 = (a / b - 1.0)

    # Sharpe (annualised) over 63 days
    ret_s = close.pct_change().dropna().tail(63)
    if not ret_s.empty and ret_s.std() > 0:
        sharpe = float(ret_s.mean() * 252 / (ret_s.std() * np.sqrt(252)))
    else:
        sharpe = 0.0

    score = 0.0

    # 1-week (Jegadeesh 1990 short-term reversal — small +ve OK, big spike fades)
    if r_1w is not None:
        if r_1w > 0.10:
            score -= 0.3
            subs["1w"] = f"周涨{r_1w*100:+.1f}% 短期反转风险"
        elif r_1w > 0.02:
            score += 0.2
            subs["1w"] = f"周涨{r_1w*100:+.1f}%"
        elif r_1w < -0.05:
            score += 0.2
            subs["1w"] = f"周跌{r_1w*100:+.1f}% 反弹机会"
        elif r_1w < -0.02:
            score -= 0.1
            subs["1w"] = f"周跌{r_1w*100:+.1f}%"
        else:
            subs["1w"] = f"周持平{r_1w*100:+.1f}%"

    # 1-month
    if r_1m is not None:
        if r_1m > 0.15:
            score += 0.5
            subs["1m"] = f"月涨{r_1m*100:+.1f}% 强势"
        elif r_1m > 0.05:
            score += 0.3
            subs["1m"] = f"月涨{r_1m*100:+.1f}%"
        elif r_1m < -0.15:
            score -= 0.5
            subs["1m"] = f"月跌{r_1m*100:+.1f}% 弱势"
        elif r_1m < -0.05:
            score -= 0.3
            subs["1m"] = f"月跌{r_1m*100:+.1f}%"
        else:
            subs["1m"] = f"月持平{r_1m*100:+.1f}%"

    # 3-month
    if r_3m is not None:
        if r_3m > 0.30:
            score += 0.6
            subs["3m"] = f"季涨{r_3m*100:+.1f}% 强趋势"
        elif r_3m > 0.10:
            score += 0.4
            subs["3m"] = f"季涨{r_3m*100:+.1f}%"
        elif r_3m < -0.30:
            score -= 0.6
            subs["3m"] = f"季跌{r_3m*100:+.1f}%"
        elif r_3m < -0.10:
            score -= 0.4
            subs["3m"] = f"季跌{r_3m*100:+.1f}%"
        else:
            subs["3m"] = f"季震荡{r_3m*100:+.1f}%"

    # 12-1 month (Carhart / JT)
    if r_12_1 is not None:
        if r_12_1 > 0.30:
            score += 0.5
            subs["12_1"] = f"12-1动量{r_12_1*100:+.1f}% 强"
        elif r_12_1 > 0.10:
            score += 0.3
            subs["12_1"] = f"12-1动量{r_12_1*100:+.1f}%"
        elif r_12_1 < -0.30:
            score -= 0.5
            subs["12_1"] = f"12-1动量{r_12_1*100:+.1f}% 弱"
        elif r_12_1 < -0.10:
            score -= 0.3
            subs["12_1"] = f"12-1动量{r_12_1*100:+.1f}%"
        else:
            subs["12_1"] = f"12-1动量{r_12_1*100:+.1f}%"

    # Sharpe contribution
    if sharpe >= 1.5:
        score += 0.25
        subs["sharpe"] = f"风险调整后强 Sharpe={sharpe:.2f}"
    elif sharpe >= 0.8:
        score += 0.12
        subs["sharpe"] = f"Sharpe={sharpe:.2f}"
    elif sharpe <= -0.8:
        score -= 0.20
        subs["sharpe"] = f"风险调整后弱 Sharpe={sharpe:.2f}"
    else:
        subs["sharpe"] = f"Sharpe={sharpe:.2f}"

    # Cross-horizon consistency
    valid = [s for s in [r_1w, r_1m, r_3m, r_12_1] if s is not None]
    if len(valid) >= 3:
        pos = sum(1 for s in valid if s > 0)
        neg = sum(1 for s in valid if s < 0)
        if pos == len(valid):
            score += 0.30
            subs["consistency"] = f"全部 {len(valid)} 周期同向看多"
        elif neg == len(valid):
            score -= 0.30
            subs["consistency"] = f"全部 {len(valid)} 周期同向看空"
        elif max(pos, neg) >= 3:
            bias = 1 if pos > neg else -1
            score += 0.10 * bias
            subs["consistency"] = f"{max(pos, neg)}/{len(valid)} 方向一致"
        else:
            subs["consistency"] = "时间窗口信号分歧"

    # Normalize: theoretical max ≈ 2.5 with everything firing
    combined = max(-1.0, min(1.0, score / 2.5))

    if combined > 0.30:
        detail = "多周期动量看多，趋势延续概率高"
    elif combined < -0.30:
        detail = "多周期动量看空，弱势延续概率高"
    else:
        detail = "多周期动量信号混合"

    return SignalDimension(
        name="多维度动量", name_en="multi_momentum",
        score=combined, weight=0.20, detail=detail, sub_signals=subs,
    )


def _calc_technical_momentum(df: pd.DataFrame) -> SignalDimension:
    """Multi-indicator technical convergence: MACD + RSI + KDJ."""
    close = df["收盘"].astype(float)
    high = df["最高"].astype(float)
    low = df["最低"].astype(float)
    n = len(close)
    subs: dict = {}

    # MACD signal
    dif, dea, hist = calc_macd(close)
    macd_score = 0.0
    if n >= 2:
        # Golden cross / dead cross in last 3 bars
        for i in range(-3, 0):
            if i - 1 < -len(dif):
                continue
            if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
                macd_score = 0.6
                subs["macd"] = "MACD金叉"
                break
            if dif.iloc[i] < dea.iloc[i] and dif.iloc[i - 1] >= dea.iloc[i - 1]:
                macd_score = -0.6
                subs["macd"] = "MACD死叉"
                break
        # Histogram momentum
        if macd_score == 0 and len(hist) >= 3:
            h = hist.iloc[-3:].values
            if h[-1] > h[-2] > h[-3]:
                macd_score = 0.3
                subs["macd"] = "MACD柱放大"
            elif h[-1] < h[-2] < h[-3]:
                macd_score = -0.3
                subs["macd"] = "MACD柱缩小"
        if "macd" not in subs:
            macd_score = 0.1 if hist.iloc[-1] > 0 else -0.1
            subs["macd"] = "MACD柱为正" if hist.iloc[-1] > 0 else "MACD柱为负"

    # RSI signal
    rsi = calc_rsi(close, 14)
    rsi_val = _safe_float(rsi.iloc[-1], 50)
    if rsi_val > 70:
        rsi_score = -0.5  # overbought → bearish
        subs["rsi"] = f"RSI={rsi_val:.1f} 超买"
    elif rsi_val < 30:
        rsi_score = 0.5  # oversold → bullish
        subs["rsi"] = f"RSI={rsi_val:.1f} 超卖"
    elif rsi_val > 55:
        rsi_score = 0.2
        subs["rsi"] = f"RSI={rsi_val:.1f} 偏强"
    elif rsi_val < 45:
        rsi_score = -0.2
        subs["rsi"] = f"RSI={rsi_val:.1f} 偏弱"
    else:
        rsi_score = 0.0
        subs["rsi"] = f"RSI={rsi_val:.1f} 中性"

    # KDJ signal
    k, d, j = calc_kdj(high, low, close)
    k_val = _safe_float(k.iloc[-1], 50)
    d_val = _safe_float(d.iloc[-1], 50)
    j_val = _safe_float(j.iloc[-1], 50)
    kdj_score = 0.0
    if k_val > d_val and j_val > 80:
        kdj_score = -0.3  # overbought
        subs["kdj"] = f"KDJ高位 K={k_val:.0f} D={d_val:.0f} J={j_val:.0f}"
    elif k_val < d_val and j_val < 20:
        kdj_score = 0.3  # oversold rebound
        subs["kdj"] = f"KDJ低位金叉 K={k_val:.0f} D={d_val:.0f} J={j_val:.0f}"
    elif k_val > d_val:
        kdj_score = 0.15
        subs["kdj"] = f"KDJ多头排列"
    else:
        kdj_score = -0.15
        subs["kdj"] = f"KDJ空头排列"

    combined = macd_score * 0.45 + rsi_score * 0.30 + kdj_score * 0.25
    combined = max(-1.0, min(1.0, combined))

    if combined > 0.3:
        detail = "技术指标共振偏多"
    elif combined < -0.3:
        detail = "技术指标共振偏空"
    else:
        detail = "技术指标信号分歧"

    return SignalDimension(
        name="技术动量", name_en="technical_momentum",
        score=combined, weight=0.25, detail=detail, sub_signals=subs,
    )


def _calc_trend_structure(df: pd.DataFrame) -> SignalDimension:
    """Moving average alignment + trend strength via ADX proxy."""
    close = df["收盘"].astype(float)
    high = df["最高"].astype(float)
    low = df["最低"].astype(float)
    n = len(close)
    subs: dict = {}

    # MA alignment score
    periods = [5, 10, 20, 60]
    if n >= 120:
        periods.append(120)
    mas = {}
    for p in periods:
        if n >= p:
            mas[p] = close.rolling(p).mean().iloc[-1]

    current = close.iloc[-1]
    ma_score = 0.0
    ma_vals = sorted(mas.items())
    above_count = sum(1 for _, v in ma_vals if pd.notna(v) and current > v)
    total_mas = len(ma_vals)
    if total_mas > 0:
        ma_score = (above_count / total_mas) * 2 - 1  # maps to [-1, 1]
    subs["ma_position"] = f"价格在{above_count}/{total_mas}条均线之上"

    # MA slope (trend direction)
    if n >= 20:
        ma20 = close.rolling(20).mean()
        slope = (ma20.iloc[-1] - ma20.iloc[-5]) / ma20.iloc[-5] * 100 if pd.notna(ma20.iloc[-5]) and ma20.iloc[-5] != 0 else 0
        if slope > 0.5:
            subs["ma_slope"] = f"MA20上行 ({slope:+.2f}%)"
        elif slope < -0.5:
            subs["ma_slope"] = f"MA20下行 ({slope:+.2f}%)"
        else:
            subs["ma_slope"] = f"MA20走平 ({slope:+.2f}%)"

    # ADX-like trend strength (simplified)
    adx_score = 0.0
    if n >= 20:
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr14 = tr.rolling(14).mean()
        # Directional movement
        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
        plus_di = 100 * calc_ema(plus_dm, 14) / atr14
        minus_di = 100 * calc_ema(minus_dm, 14) / atr14
        dx = (plus_di - minus_di).abs() / (plus_di + minus_di).abs() * 100
        adx = calc_ema(dx, 14)
        adx_val = _safe_float(adx.iloc[-1], 20)
        if adx_val > 25:
            adx_score = 0.4 if _safe_float(plus_di.iloc[-1]) > _safe_float(minus_di.iloc[-1]) else -0.4
            subs["trend_strength"] = f"趋势强 (ADX={adx_val:.0f})"
        else:
            subs["trend_strength"] = f"趋势弱 (ADX={adx_val:.0f})"

    # Price vs long-term MA (60-day, 120-day)
    long_score = 0.0
    if n >= 60:
        ma60 = close.rolling(60).mean().iloc[-1]
        if pd.notna(ma60):
            pct = (current - ma60) / ma60 * 100
            if pct > 5:
                long_score = min(0.3, pct / 30)
            elif pct < -5:
                long_score = max(-0.3, pct / 30)
            subs["ma60_deviation"] = f"偏离MA60 {pct:+.1f}%"

    combined = ma_score * 0.4 + adx_score * 0.35 + long_score * 0.25
    combined = max(-1.0, min(1.0, combined))

    if combined > 0.2:
        detail = "趋势结构偏多，均线多头排列"
    elif combined < -0.2:
        detail = "趋势结构偏空，均线空头排列"
    else:
        detail = "趋势结构中性，均线交织"

    return SignalDimension(
        name="趋势结构", name_en="trend_structure",
        score=combined, weight=0.20, detail=detail, sub_signals=subs,
    )


def _calc_volume_price(df: pd.DataFrame) -> SignalDimension:
    """Volume-price relationship: OBV trend, accumulation/distribution."""
    close = df["收盘"].astype(float)
    volume = df["成交量"].astype(float)
    high = df["最高"].astype(float)
    low = df["最低"].astype(float)
    n = len(close)
    subs: dict = {}

    # OBV (On-Balance Volume) trend
    obv_score = 0.0
    if n >= 20:
        direction = close.diff().apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
        obv = (volume * direction).cumsum()
        obv_ma10 = obv.rolling(10).mean()
        obv_ma20 = obv.rolling(20).mean()
        if pd.notna(obv_ma10.iloc[-1]) and pd.notna(obv_ma20.iloc[-1]):
            if obv.iloc[-1] > obv_ma10.iloc[-1] > obv_ma20.iloc[-1]:
                obv_score = 0.5
                subs["obv"] = "OBV上行，量价配合"
            elif obv.iloc[-1] < obv_ma10.iloc[-1] < obv_ma20.iloc[-1]:
                obv_score = -0.5
                subs["obv"] = "OBV下行，资金流出"
            else:
                obv_score = 0.0
                subs["obv"] = "OBV震荡"

    # Volume trend (5-day vs 20-day average)
    vol_score = 0.0
    if n >= 20:
        vol5 = volume.tail(5).mean()
        vol20 = volume.tail(20).mean()
        if vol20 > 0:
            ratio = vol5 / vol20
            if ratio > 1.5:
                # Volume surge - check price direction
                price_chg_5d = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100 if close.iloc[-5] != 0 else 0
                if price_chg_5d > 0:
                    vol_score = 0.4
                    subs["vol_trend"] = f"放量上涨 (量比={ratio:.1f})"
                else:
                    vol_score = -0.3
                    subs["vol_trend"] = f"放量下跌 (量比={ratio:.1f})"
            elif ratio < 0.6:
                vol_score = -0.1
                subs["vol_trend"] = f"缩量 (量比={ratio:.1f})"
            else:
                subs["vol_trend"] = f"量能平稳 (量比={ratio:.1f})"

    # Accumulation/Distribution line
    ad_score = 0.0
    if n >= 10:
        clv = ((close - low) - (high - close)) / (high - low).replace(0, np.nan)
        clv = clv.fillna(0)
        ad = (clv * volume).cumsum()
        ad_ma = ad.rolling(10).mean()
        if pd.notna(ad.iloc[-1]) and pd.notna(ad_ma.iloc[-1]):
            if ad.iloc[-1] > ad.iloc[-10] and ad.iloc[-1] > ad_ma.iloc[-1]:
                ad_score = 0.3
                subs["ad_line"] = "A/D线上升，资金积累"
            elif ad.iloc[-1] < ad.iloc[-10] and ad.iloc[-1] < ad_ma.iloc[-1]:
                ad_score = -0.3
                subs["ad_line"] = "A/D线下降，资金派发"

    combined = obv_score * 0.40 + vol_score * 0.35 + ad_score * 0.25
    combined = max(-1.0, min(1.0, combined))

    if combined > 0.2:
        detail = "量价配合，资金流入"
    elif combined < -0.2:
        detail = "量价背离，资金流出"
    else:
        detail = "量价关系中性"

    return SignalDimension(
        name="量价关系", name_en="volume_price",
        score=combined, weight=0.15, detail=detail, sub_signals=subs,
    )


def _calc_smart_money(ctx) -> SignalDimension:
    """Smart money flow: northbound + main fund."""
    subs: dict = {}
    nb_score = 0.0
    mf_score = 0.0

    # Northbound flow
    nb = ctx.northbound_df
    if nb is not None and not nb.empty and "hold_shares" in nb.columns:
        try:
            nb_sorted = nb.sort_values("trade_date", ascending=False).reset_index(drop=True)
            if len(nb_sorted) >= 5:
                cur = _safe_float(nb_sorted["hold_shares"].iloc[0])
                d5 = _safe_float(nb_sorted["hold_shares"].iloc[5]) if len(nb_sorted) > 5 else cur
                d10 = _safe_float(nb_sorted["hold_shares"].iloc[10]) if len(nb_sorted) > 10 else cur
                d20 = _safe_float(nb_sorted["hold_shares"].iloc[20]) if len(nb_sorted) > 20 else cur
                if d5 > 0:
                    chg5 = (cur - d5) / d5 * 100
                    chg10 = (cur - d10) / d10 * 100 if d10 > 0 else 0
                    chg20 = (cur - d20) / d20 * 100 if d20 > 0 else 0
                    if chg5 > 0 and chg10 > 0:
                        nb_score = min(0.8, (chg5 + chg10) / 10)
                        subs["northbound"] = f"北向连续加仓 5日{chg5:+.1f}% 10日{chg10:+.1f}%"
                    elif chg5 < 0 and chg10 < 0:
                        nb_score = max(-0.8, (chg5 + chg10) / 10)
                        subs["northbound"] = f"北向连续减仓 5日{chg5:+.1f}% 10日{chg10:+.1f}%"
                    else:
                        subs["northbound"] = f"北向持仓波动 5日{chg5:+.1f}%"
        except Exception:
            pass

    # Main fund flow (moneyflow_df)
    mf = ctx.moneyflow_df
    if mf is not None and not mf.empty:
        try:
            mf_sorted = mf.sort_values("trade_date", ascending=False).reset_index(drop=True)
            if "main_net" in mf_sorted.columns and len(mf_sorted) >= 3:
                main_net = mf_sorted["main_net"].astype(float)
                recent_sum = main_net.head(5).sum()
                prev_sum = main_net.iloc[5:10].sum() if len(mf_sorted) > 5 else 0
                if recent_sum > 0:
                    mf_score = min(0.6, recent_sum / 1e8)  # normalize to 亿
                    subs["main_fund"] = f"主力资金净流入 {recent_sum/1e4:.0f}万"
                elif recent_sum < 0:
                    mf_score = max(-0.6, recent_sum / 1e8)
                    subs["main_fund"] = f"主力资金净流出 {abs(recent_sum)/1e4:.0f}万"
                else:
                    subs["main_fund"] = "主力资金平衡"
        except Exception:
            pass

    # LHB bonus
    lhb = ctx.lhb_df
    if lhb is not None and not lhb.empty:
        try:
            lhb_recent = lhb.sort_values("trade_date", ascending=False).head(5)
            if "seat_type" in lhb_recent.columns:
                inst_rows = lhb_recent[lhb_recent["seat_type"].astype(str).str.contains("机构", na=False)]
                if len(inst_rows) > 0:
                    nb_score += 0.15
                    subs["lhb"] = f"近5日有{len(inst_rows)}次机构上龙虎榜"
            elif len(lhb_recent) > 0:
                nb_score += 0.05
                subs["lhb"] = f"近期上龙虎榜{len(lhb_recent)}次"
        except Exception:
            pass

    combined = nb_score * 0.55 + mf_score * 0.45
    combined = max(-1.0, min(1.0, combined))

    if combined > 0.15:
        detail = "聪明资金流入"
    elif combined < -0.15:
        detail = "聪明资金流出"
    else:
        detail = "聪明资金信号不明显"

    return SignalDimension(
        name="聪明资金", name_en="smart_money",
        score=combined, weight=0.15, detail=detail, sub_signals=subs,
    )


def _calc_mean_reversion(df: pd.DataFrame) -> SignalDimension:
    """Mean reversion signal: extreme RSI + Bollinger band deviation."""
    close = df["收盘"].astype(float)
    n = len(close)
    subs: dict = {}

    # RSI extreme
    rsi_score = 0.0
    if n >= 14:
        rsi = calc_rsi(close, 14)
        rsi_val = _safe_float(rsi.iloc[-1], 50)
        if rsi_val > 80:
            rsi_score = -0.8  # extreme overbought
            subs["rsi_extreme"] = f"RSI={rsi_val:.1f} 极度超买"
        elif rsi_val > 70:
            rsi_score = -0.4
            subs["rsi_extreme"] = f"RSI={rsi_val:.1f} 超买"
        elif rsi_val < 20:
            rsi_score = 0.8  # extreme oversold
            subs["rsi_extreme"] = f"RSI={rsi_val:.1f} 极度超卖"
        elif rsi_val < 30:
            rsi_score = 0.4
            subs["rsi_extreme"] = f"RSI={rsi_val:.1f} 超卖"
        else:
            subs["rsi_extreme"] = f"RSI={rsi_val:.1f} 正常区间"

    # Bollinger band position
    bb_score = 0.0
    if n >= 20:
        upper, middle, lower = calc_bollinger(close, 20, 2.0)
        cur = close.iloc[-1]
        if pd.notna(upper.iloc[-1]) and pd.notna(lower.iloc[-1]):
            bw = upper.iloc[-1] - lower.iloc[-1]
            if bw > 0:
                pos = (cur - lower.iloc[-1]) / bw  # 0 = lower band, 1 = upper band
                if pos > 1.05:
                    bb_score = -0.6
                    subs["bollinger"] = f"突破布林上轨 (位置={pos:.2f})"
                elif pos > 0.85:
                    bb_score = -0.3
                    subs["bollinger"] = f"接近布林上轨 (位置={pos:.2f})"
                elif pos < -0.05:
                    bb_score = 0.6
                    subs["bollinger"] = f"跌破布林下轨 (位置={pos:.2f})"
                elif pos < 0.15:
                    bb_score = 0.3
                    subs["bollinger"] = f"接近布林下轨 (位置={pos:.2f})"
                else:
                    subs["bollinger"] = f"布林带中间区域 (位置={pos:.2f})"

    combined = rsi_score * 0.55 + bb_score * 0.45
    combined = max(-1.0, min(1.0, combined))

    if combined > 0.3:
        detail = "均值回归信号：超卖反弹预期"
    elif combined < -0.3:
        detail = "均值回归信号：超买回调预期"
    else:
        detail = "均值回归信号不明显"

    return SignalDimension(
        name="均值回归", name_en="mean_reversion",
        score=combined, weight=0.10, detail=detail, sub_signals=subs,
    )


def _calc_volatility_regime(df: pd.DataFrame) -> SignalDimension:
    """Volatility regime: ATR squeeze → expansion, Bollinger bandwidth."""
    close = df["收盘"].astype(float)
    high = df["最高"].astype(float)
    low = df["最低"].astype(float)
    n = len(close)
    subs: dict = {}

    vol_score = 0.0

    # ATR regime
    if n >= 20:
        atr = calc_atr(high, low, close, 14)
        atr_val = _safe_float(atr.iloc[-1])
        atr_ma = atr.rolling(20).mean()
        atr_ma_val = _safe_float(atr_ma.iloc[-1])
        if atr_ma_val > 0:
            atr_ratio = atr_val / atr_ma_val
            if atr_ratio < 0.6:
                # Squeeze — breakout imminent, direction = recent price trend
                price_trend = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100 if close.iloc[-5] != 0 else 0
                vol_score = 0.3 if price_trend > 0 else -0.3
                subs["atr_regime"] = f"波动率压缩 (ATR比={atr_ratio:.2f})，可能突破"
            elif atr_ratio > 1.5:
                # Expansion — trend in progress
                price_trend = (close.iloc[-1] - close.iloc[-5]) / close.iloc[-5] * 100 if close.iloc[-5] != 0 else 0
                vol_score = 0.2 if price_trend > 0 else -0.2
                subs["atr_regime"] = f"波动率扩张 (ATR比={atr_ratio:.2f})"
            else:
                subs["atr_regime"] = f"波动率正常 (ATR比={atr_ratio:.2f})"

    # Bollinger bandwidth squeeze
    if n >= 20:
        upper, middle, lower = calc_bollinger(close, 20, 2.0)
        bw = (upper - lower) / middle * 100
        bw_val = _safe_float(bw.iloc[-1])
        bw_ma = bw.rolling(20).mean()
        bw_ma_val = _safe_float(bw_ma.iloc[-1])
        if bw_ma_val > 0:
            bw_ratio = bw_val / bw_ma_val
            if bw_ratio < 0.6:
                subs["bb_squeeze"] = f"布林收窄 (带宽比={bw_ratio:.2f})"
                vol_score += 0.15  # squeeze adds directional bias
            elif bw_ratio > 1.4:
                subs["bb_squeeze"] = f"布林张口 (带宽比={bw_ratio:.2f})"
            else:
                subs["bb_squeeze"] = f"布林带宽正常"

    # 20-day realized volatility vs historical
    if n >= 60:
        ret = close.pct_change()
        vol_20 = ret.tail(20).std() * np.sqrt(252) * 100
        vol_60 = ret.tail(60).std() * np.sqrt(252) * 100
        if vol_60 > 0:
            vol_ratio = vol_20 / vol_60
            subs["realized_vol"] = f"20日波动率{vol_20:.1f}% (vs 60日{vol_60:.1f}%)"
            if vol_ratio < 0.7:
                vol_score += 0.1  # low vol → mean reversion setup
            elif vol_ratio > 1.3:
                vol_score -= 0.05  # high vol → caution

    combined = max(-1.0, min(1.0, vol_score))

    if combined > 0.15:
        detail = "波动率压缩，看多突破方向"
    elif combined < -0.15:
        detail = "波动率扩张，空头趋势延续"
    else:
        detail = "波动率信号中性"

    return SignalDimension(
        name="波动率", name_en="volatility_regime",
        score=combined, weight=0.10, detail=detail, sub_signals=subs,
    )


def _calc_pattern_signal(df: pd.DataFrame) -> SignalDimension:
    """Key candlestick patterns and support/resistance."""
    close = df["收盘"].astype(float)
    open_ = df["开盘"].astype(float)
    high = df["最高"].astype(float)
    low = df["最低"].astype(float)
    n = len(close)
    subs: dict = {}

    pattern_score = 0.0

    if n >= 5:
        # Last 3 candles analysis
        c1, c2, c3 = close.iloc[-3], close.iloc[-2], close.iloc[-1]
        o1, o2, o3 = open_.iloc[-3], open_.iloc[-2], open_.iloc[-1]
        h1, h2, h3 = high.iloc[-3], high.iloc[-2], high.iloc[-1]
        l1, l2, l3 = low.iloc[-3], low.iloc[-2], low.iloc[-1]

        # Bullish engulfing
        if c2 < o2 and c3 > o3 and c3 > o2 and o3 < c2:
            pattern_score += 0.5
            subs["pattern"] = "看涨吞没形态"

        # Bearish engulfing
        elif c2 > o2 and c3 < o3 and c3 < o2 and o3 > c2:
            pattern_score -= 0.5
            subs["pattern"] = "看跌吞没形态"

        # Morning star
        elif c1 < o1 and abs(c2 - o2) < (h2 - l2) * 0.3 and c3 > o3 and c3 > (c1 + o1) / 2:
            pattern_score += 0.4
            subs["pattern"] = "早晨之星"

        # Evening star
        elif c1 > o1 and abs(c2 - o2) < (h2 - l2) * 0.3 and c3 < o3 and c3 < (c1 + o1) / 2:
            pattern_score -= 0.4
            subs["pattern"] = "黄昏之星"

        # Three white soldiers
        elif c1 > o1 and c2 > o2 and c3 > o3 and c2 > c1 and c3 > c2:
            pattern_score += 0.3
            subs["pattern"] = "三连阳"

        # Three black crows
        elif c1 < o1 and c2 < o2 and c3 < o3 and c2 < c1 and c3 < c2:
            pattern_score -= 0.3
            subs["pattern"] = "三连阴"

        # Hammer (bullish)
        elif (l3 < min(o3, c3) - 2 * abs(c3 - o3)) and (h3 - max(o3, c3)) < abs(c3 - o3):
            if close.iloc[-4] < close.iloc[-3]:  # in downtrend
                pattern_score += 0.35
                subs["pattern"] = "锤子线（潜在反转）"

        # Shooting star (bearish)
        elif (h3 > max(o3, c3) + 2 * abs(c3 - o3)) and (min(o3, c3) - l3) < abs(c3 - o3):
            if close.iloc[-4] > close.iloc[-3]:  # in uptrend
                pattern_score -= 0.35
                subs["pattern"] = "射击之星（潜在反转）"

        if "pattern" not in subs:
            subs["pattern"] = "无明显K线形态"

    # Support/resistance proximity
    if n >= 20:
        recent_high = high.tail(20).max()
        recent_low = low.tail(20).min()
        cur = close.iloc[-1]
        range_pct = (recent_high - recent_low) / recent_low * 100 if recent_low > 0 else 0
        pos_in_range = (cur - recent_low) / (recent_high - recent_low) if (recent_high - recent_low) > 0 else 0.5

        if pos_in_range > 0.9:
            pattern_score -= 0.2
            subs["sr_position"] = f"接近20日高点 (位置={pos_in_range:.0%})"
        elif pos_in_range < 0.1:
            pattern_score += 0.2
            subs["sr_position"] = f"接近20日低点 (位置={pos_in_range:.0%})"
        else:
            subs["sr_position"] = f"20日区间中间 (位置={pos_in_range:.0%})"

    combined = max(-1.0, min(1.0, pattern_score))

    if combined > 0.2:
        detail = "K线形态偏多"
    elif combined < -0.2:
        detail = "K线形态偏空"
    else:
        detail = "K线形态中性"

    return SignalDimension(
        name="K线形态", name_en="pattern",
        score=combined, weight=0.05, detail=detail, sub_signals=subs,
    )


# ---------------------------------------------------------------------------
# Main prediction function
# ---------------------------------------------------------------------------

def predict(ctx) -> PredictionResult:
    """Run all signal dimensions on a StrategyContext and produce probability.

    Args:
        ctx: StrategyContext with daily_df at minimum.

    Returns:
        PredictionResult with probability, confidence, and per-dimension breakdown.
    """
    df = ctx.daily_df
    if df is None or len(df) < 20:
        return PredictionResult(
            code=ctx.code, name=ctx.name, price=ctx.price,
            probability_up=50.0, probability_down=50.0, confidence=0.0,
            signal="neutral", signal_label="数据不足",
            composite_direction=0.0, time_horizon="短期 (3-5个交易日)",
            key_drivers=["K线数据不足，无法进行分析"],
            risk_warnings=["历史数据少于20个交易日，分析可靠性低"],
        )

    # Ensure sorted ascending
    df = df.sort_values("日期" if "日期" in df.columns else df.columns[0]).reset_index(drop=True)

    # Calculate all dimensions
    dimensions = [
        _calc_multi_horizon_momentum(df),
        _calc_technical_momentum(df),
        _calc_trend_structure(df),
        _calc_volume_price(df),
        _calc_smart_money(ctx),
        _calc_mean_reversion(df),
        _calc_volatility_regime(df),
        _calc_pattern_signal(df),
    ]
    # Re-weight: multi-horizon momentum is the strongest single direction
    # signal in equity research; bump weight while trimming pure indicator
    # convergence which is more lagging.
    REWEIGHT = {
        "multi_momentum": 0.20,
        "technical_momentum": 0.15,
        "trend_structure": 0.18,
        "volume_price": 0.12,
        "smart_money": 0.13,
        "mean_reversion": 0.08,
        "volatility_regime": 0.09,
        "pattern": 0.05,
    }
    for d in dimensions:
        if d.name_en in REWEIGHT:
            d.weight = REWEIGHT[d.name_en]

    # Weighted composite direction
    total_weight = sum(d.weight for d in dimensions)
    composite = sum(d.score * d.weight for d in dimensions) / total_weight if total_weight > 0 else 0

    # Transform to probability via sigmoid-like function
    # composite ∈ [-1, 1] → probability_up ∈ [0, 100]
    # Using a tunable steepness factor
    steepness = 3.5
    prob_up_raw = 1 / (1 + math.exp(-steepness * composite))
    prob_up = round(prob_up_raw * 100, 1)
    prob_down = round((1 - prob_up_raw) * 100, 1)

    # Confidence: based on signal agreement + data quality
    scores = [d.score for d in dimensions]
    # Signal agreement: how much do dimensions agree on direction?
    positive = sum(1 for s in scores if s > 0.1)
    negative = sum(1 for s in scores if s < -0.1)
    total_dims = len(scores)
    agreement = max(positive, negative) / total_dims if total_dims > 0 else 0.5

    # Data quality: how many dimensions have enough data?
    data_quality = min(1.0, len(df) / 60)  # full confidence at 60+ bars

    # Strength of signals: average absolute score
    avg_strength = sum(abs(s) for s in scores) / total_dims if total_dims > 0 else 0

    confidence = round((agreement * 0.45 + data_quality * 0.25 + avg_strength * 0.30) * 100, 1)
    confidence = max(10.0, min(95.0, confidence))  # clamp

    # Signal classification — slightly relaxed thresholds vs the 65/35
    # original since the 8-dimension composite is more robust.
    if prob_up >= 62:
        signal = "bullish"
        signal_label = "看多"
    elif prob_up <= 38:
        signal = "bearish"
        signal_label = "看空"
    elif prob_up >= 53:
        signal = "bullish"
        signal_label = "偏多"
    elif prob_up <= 47:
        signal = "bearish"
        signal_label = "偏空"
    else:
        signal = "neutral"
        signal_label = "中性"

    # Key drivers: top 2 positive and top 2 negative dimensions
    sorted_dims = sorted(dimensions, key=lambda d: abs(d.score), reverse=True)
    key_drivers: list[str] = []
    for d in sorted_dims[:3]:
        if abs(d.score) > 0.15:
            direction = "看多" if d.score > 0 else "看空"
            key_drivers.append(f"{d.name}: {d.detail} ({direction})")

    # Risk warnings
    risk_warnings: list[str] = []
    if confidence < 40:
        risk_warnings.append("信号分歧较大，建议观望")
    # Check for extreme RSI
    rsi_dim = next((d for d in dimensions if d.name_en == "mean_reversion"), None)
    if rsi_dim and "rsi_extreme" in rsi_dim.sub_signals:
        rsi_text = rsi_dim.sub_signals["rsi_extreme"]
        if "极度" in rsi_text:
            risk_warnings.append(rsi_text)
    # Low volume
    vol_dim = next((d for d in dimensions if d.name_en == "volume_price"), None)
    if vol_dim and "vol_trend" in vol_dim.sub_signals:
        if "缩量" in vol_dim.sub_signals["vol_trend"]:
            risk_warnings.append("成交量萎缩，趋势持续性存疑")

    if not key_drivers:
        key_drivers.append("各维度信号均不明显")
    if not risk_warnings:
        risk_warnings.append("暂无明显风险信号")

    return PredictionResult(
        code=ctx.code,
        name=ctx.name,
        price=ctx.price,
        probability_up=prob_up,
        probability_down=prob_down,
        confidence=confidence,
        signal=signal,
        signal_label=signal_label,
        composite_direction=round(composite, 4),
        dimensions=dimensions,
        key_drivers=key_drivers,
        risk_warnings=risk_warnings,
        time_horizon="短期 (3-5个交易日)",
    )
