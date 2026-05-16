"""Ten stock screening strategies."""
import math
import pandas as pd
import numpy as np
from indicators import calc_macd, calc_rsi, calc_kdj, calc_bollinger, calc_atr


def score_macd_ma(daily_df: pd.DataFrame, **_) -> dict:
    """Strategy 1: MACD + MA Trend Resonance."""
    if daily_df is None or len(daily_df) < 30:
        return {"score": 0, "signal": "neutral", "details": {}}
    close = daily_df["收盘"].astype(float)
    volume = daily_df["成交量"].astype(float)
    dif, dea, macd_hist = calc_macd(close)
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    score = 0
    details = {}

    # MACD golden cross within 5 days
    if len(dif) >= 5:
        for i in range(-5, 0):
            if i-1 >= -len(dif) and dif.iloc[i] > dea.iloc[i] and dif.iloc[i-1] <= dea.iloc[i-1]:
                score += 30
                details["macd_golden_cross"] = True
                break

    # MACD histogram turning positive
    if len(macd_hist) >= 2 and macd_hist.iloc[-1] > 0 and macd_hist.iloc[-2] <= 0:
        score += 20
        details["hist_positive"] = True

    # Price above MA20
    if pd.notna(ma20.iloc[-1]) and close.iloc[-1] > ma20.iloc[-1]:
        score += 15
        details["above_ma20"] = True

    # MA20 above MA60
    if pd.notna(ma20.iloc[-1]) and pd.notna(ma60.iloc[-1]) and ma20.iloc[-1] > ma60.iloc[-1]:
        score += 10

    # Volume > 1.2x 20-day avg
    if len(volume) >= 20:
        avg_vol = volume.iloc[-20:].mean()
        if volume.iloc[-1] > 1.2 * avg_vol:
            score += 15
            details["volume_surge"] = True

    # MA alignment
    if all(pd.notna(v.iloc[-1]) for v in [ma5, ma10, ma20, ma60]):
        if ma5.iloc[-1] > ma10.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1]:
            score += 10
            details["ma_aligned"] = True

    signal = "bullish" if score >= 60 else "bearish" if score <= 20 else "neutral"
    return {"score": min(score, 100), "signal": signal, "details": details}


def score_multi_factor(row: pd.Series, **_) -> dict:
    """Strategy 2: Multi-Factor Value Investment (from existing stock_screener.py)."""
    score = 0
    details = {}
    roe = float(row.get("净资产收益率", 0) or 0)
    raw_roe = float(row.get("净资产收益率_原始", 0) or 0)
    debt = float(row.get("资产负债率", 100) or 100)
    cash = float(row.get("经营现金流", 0) or 0)
    cap = float(row.get("总市值_亿", 0) or 0)
    profit_growth = float(row.get("净利润同比增长率", 0) or 0)
    revenue_growth = float(row.get("营收同比增长率", 0) or 0)
    gross_margin = float(row.get("销售毛利率", 0) or 0)

    # ROE
    if roe >= 30: score += 25
    elif roe >= 22: score += 20
    elif roe >= 15: score += 14
    if raw_roe >= 8: score += 8
    elif raw_roe >= 5: score += 5
    elif raw_roe >= 3: score += 3

    # Cash flow
    if cash >= 2.0: score += 15
    elif cash >= 1.0: score += 12
    elif cash > 0: score += 8

    # Debt ratio
    if debt <= 30: score += 15
    elif debt <= 45: score += 11
    elif debt <= 60: score += 6

    # Growth
    if profit_growth >= 30: score += 10
    elif profit_growth >= 10: score += 7
    elif profit_growth >= 0: score += 4
    elif profit_growth < -20: score -= 6

    if revenue_growth >= 20: score += 8
    elif revenue_growth >= 8: score += 5
    elif revenue_growth >= 0: score += 2

    if gross_margin >= 50: score += 8
    elif gross_margin >= 35: score += 6
    elif gross_margin >= 20: score += 3

    # Market cap
    if cap >= 1000: score += 15
    elif cap >= 500: score += 10
    elif cap >= 200: score += 5

    signal = "bullish" if score >= 60 else "bearish" if score <= 25 else "neutral"
    return {"score": max(0, min(score, 100)), "signal": signal, "details": details}


def score_momentum_breakout(daily_df: pd.DataFrame, **_) -> dict:
    """Strategy 3: Momentum Breakout."""
    if daily_df is None or len(daily_df) < 20:
        return {"score": 0, "signal": "neutral", "details": {}}
    close = daily_df["收盘"].astype(float)
    volume = daily_df["成交量"].astype(float)
    high = daily_df["最高"].astype(float)

    score = 0
    details = {}

    # 20-day high breakout
    high_20 = high.iloc[-21:-1].max()
    if close.iloc[-1] > high_20:
        score += 30
        details["breakout_20d"] = True

    # Volume surge
    if len(volume) >= 20:
        avg_vol = volume.iloc[-20:].mean()
        if volume.iloc[-1] > 2 * avg_vol:
            score += 25
            details["volume_surge"] = True

    # Above MA5/MA10
    ma5 = close.rolling(5).mean()
    ma10 = close.rolling(10).mean()
    if close.iloc[-1] > ma5.iloc[-1]: score += 10
    if close.iloc[-1] > ma10.iloc[-1]: score += 10

    # ATR expanding
    if len(daily_df) >= 34:
        atr = calc_atr(daily_df["最高"].astype(float), daily_df["最低"].astype(float), close)
        if pd.notna(atr.iloc[-1]) and pd.notna(atr.iloc[-20]):
            if atr.iloc[-1] > atr.iloc[-20]:
                score += 15

    # 60-day high
    if len(high) >= 61:
        high_60 = high.iloc[-61:-1].max()
        if close.iloc[-1] > high_60:
            score += 10

    signal = "bullish" if score >= 60 else "bearish" if score <= 20 else "neutral"
    return {"score": min(score, 100), "signal": signal, "details": details}


def score_rsi_rebound(daily_df: pd.DataFrame, **_) -> dict:
    """Strategy 4: RSI Oversold Rebound."""
    if daily_df is None or len(daily_df) < 20:
        return {"score": 0, "signal": "neutral", "details": {}}
    close = daily_df["收盘"].astype(float)
    volume = daily_df["成交量"].astype(float)
    rsi = calc_rsi(close)

    score = 0
    details = {}

    # RSI crossed above 30 in last 3 days
    if len(rsi) >= 4:
        for i in range(-3, 0):
            if i-1 >= -len(rsi) and rsi.iloc[i] > 30 and rsi.iloc[i-1] <= 30:
                score += 35
                details["rsi_cross_30"] = True
                break

    # RSI in early rebound zone
    if 30 <= rsi.iloc[-1] <= 40:
        score += 20
        details["rebound_zone"] = True

    # RSI turning upward
    if len(rsi) >= 2 and rsi.iloc[-1] > rsi.iloc[-2]:
        score += 15

    # Green candle
    if close.iloc[-1] > close.iloc[-2]:
        score += 15

    # Volume confirmation
    if len(volume) >= 10:
        avg_vol = volume.iloc[-10:].mean()
        if volume.iloc[-1] > 1.5 * avg_vol:
            score += 15

    signal = "bullish" if score >= 50 else "neutral"
    return {"score": min(score, 100), "signal": signal, "details": details}


def score_bollinger_squeeze(daily_df: pd.DataFrame, **_) -> dict:
    """Strategy 5: Bollinger Bands Squeeze Breakout."""
    if daily_df is None or len(daily_df) < 120:
        return {"score": 0, "signal": "neutral", "details": {}}
    close = daily_df["收盘"].astype(float)
    volume = daily_df["成交量"].astype(float)
    upper, middle, lower = calc_bollinger(close)

    score = 0
    details = {}

    # Bandwidth calculation
    bandwidth = (upper - lower) / middle
    bw_120 = bandwidth.iloc[-120:]
    current_bw = bandwidth.iloc[-1]

    # Squeeze detection
    if current_bw <= bw_120.quantile(0.2):
        score += 30
        details["squeeze_detected"] = True

    # Breakout above upper band
    if close.iloc[-1] > upper.iloc[-1]:
        score += 30
        details["upper_breakout"] = True

    # Above middle band
    if close.iloc[-1] > middle.iloc[-1]:
        score += 15

    # Volume on breakout
    if len(volume) >= 20:
        avg_vol = volume.iloc[-20:].mean()
        if volume.iloc[-1] > 1.3 * avg_vol:
            score += 15

    # Prior squeeze lasted >= 5 days
    squeeze_days = 0
    for i in range(-20, 0):
        if i >= -len(bw_120) and bandwidth.iloc[i] <= bw_120.quantile(0.2):
            squeeze_days += 1
    if squeeze_days >= 5:
        score += 10

    signal = "bullish" if score >= 50 else "neutral"
    return {"score": min(score, 100), "signal": signal, "details": details}


def score_chip_concentration(daily_df: pd.DataFrame = None, shareholder_data=None, **_) -> dict:
    """Strategy 6: Chip Concentration + Institutional Holding."""
    score = 0
    details = {}

    if shareholder_data is not None and len(shareholder_data) >= 2:
        counts = shareholder_data.get("股东人数", [])
        if len(counts) >= 2:
            if counts.iloc[-1] < counts.iloc[-2]:
                score += 25
                details["holder_decreasing"] = True
            if len(counts) >= 3 and counts.iloc[-2] < counts.iloc[-3]:
                score += 20
                details["holder_decreasing_consecutive"] = True

    # Default score if no data available
    if score == 0:
        score = 30  # Neutral baseline
        details["no_data"] = True

    signal = "bullish" if score >= 60 else "neutral"
    return {"score": min(score, 100), "signal": signal, "details": details}


def score_dividend_stability(daily_df: pd.DataFrame = None, dividend_data=None, price: float = 0, **_) -> dict:
    """Strategy 7: Dividend Yield + Stability."""
    score = 0
    details = {}

    if dividend_data is not None and price > 0:
        # Calculate dividend yield
        latest_dividend = dividend_data.get("每股股利", 0)
        if latest_dividend > 0:
            yield_pct = (latest_dividend / price) * 100
            if yield_pct > 5: score += 30
            elif yield_pct > 3: score += 20
            elif yield_pct > 1: score += 10
            details["dividend_yield"] = round(yield_pct, 2)

        # Consecutive years
        years = dividend_data.get("连续分红年数", 0)
        if years >= 5: score += 25
        elif years >= 3: score += 15
        details["consecutive_years"] = years
    else:
        score = 25
        details["no_data"] = True

    signal = "bullish" if score >= 50 else "neutral"
    return {"score": min(score, 100), "signal": signal, "details": details}


def score_northbound_flow(daily_df: pd.DataFrame = None, northbound_data=None, code: str = "", **_) -> dict:
    """Strategy 8: Northbound Capital Flow."""
    score = 0
    details = {}

    if northbound_data is not None:
        codes_5d = northbound_data.get("5日增仓", [])
        codes_10d = northbound_data.get("10日增仓", [])

        if code in codes_5d:
            score += 35
            details["top_5d_accumulation"] = True
        elif code in codes_10d:
            score += 20
            details["top_10d_accumulation"] = True

        if northbound_data.get("net_inflow_positive", False):
            score += 10
    else:
        score = 20
        details["no_data"] = True

    signal = "bullish" if score >= 40 else "neutral"
    return {"score": min(score, 100), "signal": signal, "details": details}


def score_sector_rotation(daily_df: pd.DataFrame = None, sector_data=None, industry: str = "", **_) -> dict:
    """Strategy 9: Sector Rotation."""
    score = 0
    details = {}

    if sector_data is not None and industry:
        ranked = sorted(sector_data, key=lambda x: x.get("change", 0), reverse=True)
        total = len(ranked)
        if total > 0:
            for i, s in enumerate(ranked):
                if s.get("name", "") == industry:
                    pct = i / total
                    if pct <= 0.1: score += 35
                    elif pct <= 0.2: score += 25
                    elif pct >= 0.8: score -= 15
                    details["sector_rank"] = i + 1
                    details["sector_total"] = total
                    break
    else:
        score = 20
        details["no_data"] = True

    signal = "bullish" if score >= 40 else "neutral"
    return {"score": min(max(score, 0), 100), "signal": signal, "details": details}


def score_kdj_rsi_resonance(daily_df: pd.DataFrame, **_) -> dict:
    """Strategy 10: KDJ + RSI Dual Indicator Resonance."""
    if daily_df is None or len(daily_df) < 20:
        return {"score": 0, "signal": "neutral", "details": {}}
    close = daily_df["收盘"].astype(float)
    high = daily_df["最高"].astype(float)
    low = daily_df["最低"].astype(float)
    volume = daily_df["成交量"].astype(float)

    k, d, j = calc_kdj(high, low, close)
    rsi = calc_rsi(close)

    score = 0
    details = {}

    # KDJ golden cross in last 5 days
    if len(k) >= 6:
        for i in range(-5, 0):
            if i-1 >= -len(k) and k.iloc[i] > d.iloc[i] and k.iloc[i-1] <= d.iloc[i-1]:
                score += 25
                details["kdj_golden_cross"] = True
                break

    # J < 20 within last 5 days
    if len(j) >= 5:
        recent_j = j.iloc[-5:]
        if (recent_j < 20).any():
            score += 20
            details["j_oversold"] = True

    # RSI crossed above 30 in last 5 days
    if len(rsi) >= 6:
        for i in range(-5, 0):
            if i-1 >= -len(rsi) and rsi.iloc[i] > 30 and rsi.iloc[i-1] <= 30:
                score += 25
                details["rsi_cross_30"] = True
                break

    # Resonance bonus
    if details.get("kdj_golden_cross") and details.get("rsi_cross_30"):
        score += 15
        details["resonance"] = True

    # Volume
    if len(volume) >= 20:
        avg_vol = volume.iloc[-20:].mean()
        if volume.iloc[-1] > 1.2 * avg_vol:
            score += 15

    signal = "bullish" if score >= 60 else "neutral"
    return {"score": min(score, 100), "signal": signal, "details": details}
