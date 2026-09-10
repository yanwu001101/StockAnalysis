# -*- coding: utf-8 -*-
"""短线做 T(日内 T+0)信号引擎。

基于东财当日分时(trends2)判断个股的**日内相对位置**,给出:
  - 方向:正 T·低吸 / 反 T·高抛 / 观望
  - 建议买入区间、卖出区间(基于分时均价 VWAP、日内高低)
  - 信号强度 0-100
  - 理由与风控提示

数据仅来自 em_realtime.fetch_trends(单只票单请求,量小 → 无 IP 频控)。
分时序列本身即 1 分钟粒度,VWAP=分时均价黄线,是做 T 判断"贵/便宜"的锚。

免责:纯公开数据的概率化研究,不构成投资建议;做 T 盈亏自负。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

import em_realtime
from indicators import calc_ema

log = logging.getLogger(__name__)

DISCLAIMER = "仅供研究参考,不构成投资建议;做 T 盈亏自负"
MIN_AMPLITUDE = 0.02      # 日内振幅 < 2% → 做 T 空间不足
LOW_POS = 0.35           # 日内位置低于此 → 低位
HIGH_POS = 0.65          # 日内位置高于此 → 高位
LABELS = {"positive_t": "正T·低吸", "negative_t": "反T·高抛",
          "wait": "观望", "no_data": "无数据"}


def _r(v, n=2):
    try:
        f = float(v)
        return round(f, n) if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _empty(code: str, reason: str) -> dict:
    return {
        "code": str(code).zfill(6), "name": "", "price": None, "pct_change": None,
        "vwap": None, "day_high": None, "day_low": None, "day_open": None,
        "prev_close": None, "intraday_pos": None, "vwap_dev": None, "amplitude": None,
        "action": "no_data", "action_label": LABELS["no_data"], "strength": 0,
        "buy_zone": None, "sell_zone": None, "reasons": [reason], "risks": [],
        "data_time": None, "disclaimer": DISCLAIMER,
    }


def signal(code: str) -> dict:
    """单只票的日内做 T 建议。"""
    try:
        df, meta = em_realtime.fetch_trends(code)
    except Exception as e:
        log.warning("intraday_t.signal %s fetch 失败: %s", code, e)
        return _empty(code, "分时数据获取失败")
    if df is None or df.empty or len(df) < 5:
        return _empty(code, "未取到当日分时(可能非交易日/停牌/未开盘)")

    prices = df["价"].astype(float).reset_index(drop=True)
    avgs = df["均价"].astype(float).reset_index(drop=True)
    vols = df["量"].astype(float).reset_index(drop=True)

    price = float(prices.iloc[-1])
    vwap = float(avgs.iloc[-1]) if np.isfinite(avgs.iloc[-1]) else price
    high, low = float(prices.max()), float(prices.min())
    day_open = float(meta.get("day_open") or prices.iloc[0])
    prev_close = float(meta.get("prev_close") or day_open)
    rng = max(high - low, 1e-6)

    pos = (price - low) / rng                              # 日内位置 0..1
    vwap_dev = (price - vwap) / vwap if vwap else 0.0       # 相对均价偏离
    amplitude = (high - low) / prev_close if prev_close else 0.0
    pct = (price - prev_close) / prev_close if prev_close else 0.0

    # 近端动量:最后 5 分钟斜率 + 量能(近5 vs 之前均量)
    tail = prices.tail(5)
    slope = float(tail.iloc[-1] - tail.iloc[0])
    recent_vol = float(vols.tail(5).mean())
    base_vol = float(vols.iloc[:-5].mean()) if len(vols) > 5 else recent_vol
    vol_ratio = (recent_vol / base_vol) if base_vol else 1.0

    reasons: list[str] = []
    risks: list[str] = []

    action = "wait"
    if amplitude < MIN_AMPLITUDE:
        action = "wait"
        reasons.append(f"日内振幅仅 {amplitude*100:.1f}%,做 T 空间有限")
    elif pos < LOW_POS and price <= vwap:
        action = "positive_t"
        reasons.append(f"现价处日内低位(位置 {pos*100:.0f}%),低于分时均价 {vwap_dev*100:+.2f}%")
        if slope >= 0:
            reasons.append("近 5 分钟止跌企稳")
        if vol_ratio < 1:
            reasons.append("回踩缩量,抛压减轻")
    elif pos > HIGH_POS and price >= vwap:
        action = "negative_t"
        reasons.append(f"现价处日内高位(位置 {pos*100:.0f}%),高于分时均价 {vwap_dev*100:+.2f}%")
        if slope <= 0:
            reasons.append("冲高回落,上攻乏力")
        if vol_ratio > 1.2:
            reasons.append("高位放量,警惕滞涨")
    else:
        reasons.append(f"现价处日内中位(位置 {pos*100:.0f}%),做 T 信号不明确")

    # 点位建议:低吸靠近日内低/均价下方,高抛靠近日内高/均价上方
    buf = rng * 0.15
    buy_zone = sell_zone = None
    if action == "positive_t":
        buy_zone = [_r(max(low, price - buf)), _r(min(vwap, price))]
        sell_zone = [_r(vwap), _r(high)]
    elif action == "negative_t":
        sell_zone = [_r(max(vwap, price)), _r(high)]
        buy_zone = [_r(low), _r(min(vwap, price))]

    # 信号强度:偏离越大、位置越极端、振幅越足 → 越强
    strength = 0
    if action != "wait":
        pos_extreme = (LOW_POS - pos) if action == "positive_t" else (pos - HIGH_POS)
        strength = int(min(100, max(0,
            40 + abs(vwap_dev) * 1500 + max(0.0, pos_extreme) * 120
            + min(amplitude * 1000, 20))))

    # 风控
    if abs(pct) > 0.06:
        risks.append(f"个股日内{'大涨' if pct > 0 else '大跌'} {pct*100:+.1f}%,单边趋势中做 T 风险高")
    data_time = str(df["时间"].iloc[-1])
    try:
        if data_time.split(" ")[-1] >= "14:45":
            risks.append("已近尾盘,注意收盘不确定性")
    except Exception:
        pass

    return {
        "code": meta.get("code", str(code).zfill(6)),
        "name": meta.get("name") or "",
        "price": _r(price), "pct_change": _r(pct * 100),
        "vwap": _r(vwap), "day_high": _r(high), "day_low": _r(low),
        "day_open": _r(day_open), "prev_close": _r(prev_close),
        "intraday_pos": _r(pos, 3), "vwap_dev": _r(vwap_dev * 100),
        "amplitude": _r(amplitude * 100),
        "action": action, "action_label": LABELS[action], "strength": strength,
        "buy_zone": buy_zone, "sell_zone": sell_zone,
        "reasons": reasons, "risks": risks,
        "data_time": data_time, "disclaimer": DISCLAIMER,
    }


def batch(codes: list[str], max_workers: int = 8) -> list[dict]:
    """批量做 T 建议(自选/持仓)。并发受限,仍是小请求量。"""
    codes = [str(c).zfill(6) for c in (codes or [])][:100]
    if not codes:
        return []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(codes))) as ex:
        return list(ex.map(signal, codes))


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import json
    for c in ("600519", "000001"):
        print(json.dumps(signal(c), ensure_ascii=False, indent=2))
