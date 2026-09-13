# -*- coding: utf-8 -*-
"""短线做 T(日内 T+0)决策引擎 v2。

从"无状态的日内位置计"升级为**多源实时数据驱动、结合持仓、可解释**的做 T 决策:
  数据 = 当日分时(trends2)+ 逐笔明细(details,主动买卖/大单)+ 基准指数分时(大盘闸门)
  结构 = 量加权分位去毛刺 + 成交量分布(POC/Value Area)定支撑压力
  量能 = 主动买占比 / 大单净额 / 量价配合(pv_pattern)
  大盘 = 个股所属基准指数的日内强弱,弱市低吸降级(防接飞刀)
  持仓 = 结合 available(可卖底仓)做真 T:反T·高抛(先卖后买,当日落袋)/ 正T·补仓降本
  评分 = 位置0.35 + 量能0.30 + 动量0.20 + 大盘0.15,子分全部暴露(替代魔法公式)

A 股 T+1 关键:当日买入份额当日不可卖,当日 T 的卖腿股数 ≤ available(不是 shares)。

免责:纯公开数据的概率化研究,不构成投资建议;做 T 盈亏自负。
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

import em_realtime
from indicators import calc_ema

try:
    import cache
except Exception:  # pragma: no cover - 缓存不可用时降级为无缓存
    cache = None

try:
    from sector_data import fetch_sector_rotation_from_db
except Exception:  # pragma: no cover - 板块数据不可用时降级
    fetch_sector_rotation_from_db = None

log = logging.getLogger(__name__)

DISCLAIMER = "仅供研究参考,不构成投资建议;做 T 盈亏自负"

# ---- 阈值(去魔法数字后集中可调,便于回测校准) ----
LOW_POS = 0.35            # 量加权位置低于此 → 日内低位
HIGH_POS = 0.65           # 量加权位置高于此 → 日内高位
MIN_AMPLITUDE = {"main": 0.020, "cyb": 0.025, "kc": 0.025, "bj": 0.030, "st": 0.015}
WEIGHTS = {"position": 0.35, "volume": 0.30, "momentum": 0.20, "index": 0.15}
BIG_ORDER_AMT = 200_000   # 大单金额下限(元)
BIG_ORDER_SIG = 0.02      # 大单净额显著性:≥ 当日成交额的 2%
INDEX_TTL = 30            # 指数上下文缓存秒数
SPOT_TTL = 120            # batch 全市场快照缓存秒数
T_SELL_RATIO = (0.15, 0.40)   # 反T卖腿占 available 比例区间
T_ADD_RATIO = (0.10, 0.30)    # 正T补仓占 shares 比例区间

LABELS = {"positive_t": "正T·低吸", "negative_t": "反T·高抛",
          "wait": "观望", "no_data": "无数据"}
PV_DESC = {
    "up_vol_up": "价升量增,多头占优",
    "down_vol_up": "价跌量增,抛压/恐慌盘涌出",
    "up_vol_dry": "价升量缩,上攻乏力(利于高抛)",
    "down_vol_dry": "价跌量缩,抛压衰竭(利于低吸企稳)",
    "flat": "量价平稳",
}


# ============================ 小工具 ============================
def _r(v, n=2):
    try:
        f = float(v)
        return round(f, n) if np.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _lerp(x, x0, x1, y0, y1):
    if x1 == x0:
        return y0
    t = _clamp((x - x0) / (x1 - x0), 0.0, 1.0)
    return y0 + t * (y1 - y0)


def _sign(x):
    return 1 if x > 0 else -1 if x < 0 else 0


def _roundlot(x):
    """A 股整手:向下取整到 100 股。"""
    try:
        return int(max(0.0, float(x)) // 100 * 100)
    except (TypeError, ValueError):
        return 0


def _dist_to(levels, price):
    return min((abs(price - x) for x in levels), default=1e9)


def _weighted_quantile(vals, weights, q):
    vals = np.asarray(vals, dtype=float)
    weights = np.asarray(weights, dtype=float)
    m = np.isfinite(vals) & np.isfinite(weights) & (weights > 0)
    vals, weights = vals[m], weights[m]
    if vals.size == 0:
        return float("nan")
    order = np.argsort(vals)
    vals, weights = vals[order], weights[order]
    cw = np.cumsum(weights)
    if cw[-1] <= 0:
        return float(np.median(vals))
    cdf = (cw - 0.5 * weights) / cw[-1]   # 中点法,抗端点偏差
    return float(np.interp(q, cdf, vals))


# ============================ 数据结构 ============================
@dataclass
class TrendFeatures:
    price: float
    vwap: float
    prev_close: float
    day_open: float
    day_high: float
    day_low: float
    robust_hi: float
    robust_lo: float
    pos_pctile: float          # 量加权 CDF 位置 0..1(主用,抗毛刺)
    vwap_dev: float            # 相对均价偏离(比例)
    amplitude: float           # 日内振幅(比例)
    pct_change: float          # 相对昨收(比例)
    slope_5m: float
    slope_15m: float
    poc: float
    va_low: float
    va_high: float
    supports: list             # 近→远
    resists: list
    vol_ratio: float
    n_bars: int
    data_time: str


@dataclass
class VolumeFeatures:
    active_buy_ratio: float | None
    big_order_net: float | None
    big_order_dir: int
    inout_ratio: float | None
    pv_pattern: str
    liangbi: float | None
    degraded: bool


@dataclass
class PositionCtx:
    has_position: bool
    shares: float
    available: float
    avg_cost: float
    pnl_pct: float | None
    available_capped: bool


# ============================ (a) 去毛刺结构 ============================
def _volume_profile(prices, vols, n_bins):
    """成交量分布:返回 poc(最密集价) / value area(70%量价带) / 局部密集峰。"""
    lo, hi = float(np.min(prices)), float(np.max(prices))
    if hi <= lo:
        return {"poc": lo, "va_low": lo, "va_high": hi, "peaks": []}
    edges = np.linspace(lo, hi, n_bins + 1)
    idx = np.clip(np.digitize(prices, edges) - 1, 0, n_bins - 1)
    binvol = np.zeros(n_bins)
    np.add.at(binvol, idx, vols)
    mids = (edges[:-1] + edges[1:]) / 2.0
    poc_i = int(np.argmax(binvol))
    total = binvol.sum()
    target = 0.7 * total if total > 0 else 0
    lo_i = hi_i = poc_i
    acc = binvol[poc_i]
    while acc < target and (lo_i > 0 or hi_i < n_bins - 1):
        left = binvol[lo_i - 1] if lo_i > 0 else -1
        right = binvol[hi_i + 1] if hi_i < n_bins - 1 else -1
        if right >= left:
            hi_i += 1
            acc += binvol[hi_i]
        else:
            lo_i -= 1
            acc += binvol[lo_i]
    mx = binvol.max() if binvol.size else 0
    peaks = []
    for i in range(n_bins):
        l = binvol[i - 1] if i > 0 else 0
        rr = binvol[i + 1] if i < n_bins - 1 else 0
        if mx > 0 and binvol[i] >= l and binvol[i] >= rr and binvol[i] >= 0.6 * mx:
            peaks.append(float(mids[i]))
    return {"poc": float(mids[poc_i]), "va_low": float(mids[lo_i]),
            "va_high": float(mids[hi_i]), "peaks": peaks}


def _merge_levels(levels, eps_ratio, price):
    xs = sorted({round(float(x), 3) for x in levels if x and np.isfinite(x)})
    merged = []
    for x in xs:
        if merged and abs(x - merged[-1]) <= eps_ratio * price:
            merged[-1] = (merged[-1] + x) / 2.0
        else:
            merged.append(x)
    return merged


def _trend_features(df, meta) -> TrendFeatures:
    prices = df["价"].astype(float).reset_index(drop=True)
    avgs = df["均价"].astype(float).reset_index(drop=True)
    vols = df["量"].astype(float).fillna(0.0).reset_index(drop=True)

    price = float(prices.iloc[-1])
    last_avg = avgs.iloc[-1]
    vwap = float(last_avg) if np.isfinite(last_avg) else price
    day_high, day_low = float(prices.max()), float(prices.min())
    day_open = float(meta.get("day_open") or prices.iloc[0])
    prev_close = float(meta.get("prev_close") or day_open)

    w = vols.to_numpy()
    if w.sum() <= 0:
        w = np.ones(len(prices))
    parr = prices.to_numpy()
    robust_hi = _weighted_quantile(parr, w, 0.98)
    robust_lo = _weighted_quantile(parr, w, 0.02)
    if not np.isfinite(robust_hi):
        robust_hi = day_high
    if not np.isfinite(robust_lo):
        robust_lo = day_low

    pos_pctile = float((w * (parr <= price)).sum() / w.sum())
    vwap_dev = (price - vwap) / vwap if vwap else 0.0
    amplitude = (day_high - day_low) / prev_close if prev_close else 0.0
    pct = (price - prev_close) / prev_close if prev_close else 0.0

    ema = calc_ema(prices, span=5)

    def _slope(n):
        if len(ema) <= n or not price:
            return 0.0
        return float((ema.iloc[-1] - ema.iloc[-1 - n]) / price)

    slope_5m, slope_15m = _slope(5), _slope(15)

    recent_vol = float(vols.tail(5).mean())
    base_vol = float(vols.iloc[:-5].mean()) if len(vols) > 5 else recent_vol
    vol_ratio = (recent_vol / base_vol) if base_vol else 1.0

    span = robust_hi - robust_lo
    if span > 0:
        tick = max(span / 30.0, price * 0.0005, 0.01)
        n_bins = int(min(40, max(12, span / tick)))
    else:
        n_bins = 12
    prof = _volume_profile(parr, w, n_bins)

    cands = list(prof["peaks"]) + [prof["poc"], prof["va_low"], prof["va_high"],
                                   vwap, day_open, prev_close]
    cands = _merge_levels(cands, 0.003, price)
    supports = sorted([x for x in cands if x < price], reverse=True)
    resists = sorted([x for x in cands if x > price])

    return TrendFeatures(
        price=price, vwap=vwap, prev_close=prev_close, day_open=day_open,
        day_high=day_high, day_low=day_low, robust_hi=float(robust_hi),
        robust_lo=float(robust_lo), pos_pctile=pos_pctile, vwap_dev=vwap_dev,
        amplitude=amplitude, pct_change=pct, slope_5m=slope_5m, slope_15m=slope_15m,
        poc=prof["poc"], va_low=prof["va_low"], va_high=prof["va_high"],
        supports=supports, resists=resists, vol_ratio=vol_ratio,
        n_bars=len(prices), data_time=str(df["时间"].iloc[-1]),
    )


# ============================ (b) 量能因子 ============================
def _pv_pattern(slope, vol_ratio):
    if slope > 0 and vol_ratio > 1.2:
        return "up_vol_up"
    if slope < 0 and vol_ratio > 1.2:
        return "down_vol_up"
    if slope > 0 and vol_ratio < 0.8:
        return "up_vol_dry"
    if slope < 0 and vol_ratio < 0.8:
        return "down_vol_dry"
    return "flat"


def _volume_features(details, tf: TrendFeatures, spot_row=None) -> VolumeFeatures:
    liangbi = None
    if spot_row is not None:
        lb = spot_row.get("量比")
        try:
            liangbi = float(lb) if lb is not None and np.isfinite(float(lb)) else None
        except (TypeError, ValueError):
            liangbi = None
    pv = _pv_pattern(tf.slope_5m, tf.vol_ratio)

    if details is None or getattr(details, "empty", True):
        return VolumeFeatures(None, None, 0, None, pv, liangbi, True)

    nat = details["性质"]
    vol = details["量"].astype(float)
    price = details["价"].astype(float)
    buy = float(vol[nat == 1].sum())
    sell = float(vol[nat == 2].sum())
    active_buy_ratio = buy / (buy + sell) if (buy + sell) > 0 else None
    inout_ratio = buy / sell if sell > 0 else None

    amt = (price * vol * 100.0)
    total_amt = float(amt.sum())
    if len(amt) >= 10:
        thr = max(BIG_ORDER_AMT, float(np.nanquantile(amt.to_numpy(), 0.90)))
    else:
        thr = BIG_ORDER_AMT
    big = amt >= thr
    big_net = float(amt[big & (nat == 1)].sum() - amt[big & (nat == 2)].sum())
    big_dir = 0
    if total_amt > 0 and abs(big_net) >= BIG_ORDER_SIG * total_amt:
        big_dir = 1 if big_net > 0 else -1

    return VolumeFeatures(
        active_buy_ratio=active_buy_ratio, big_order_net=big_net,
        big_order_dir=big_dir, inout_ratio=inout_ratio, pv_pattern=pv,
        liangbi=liangbi, degraded=False,
    )


# ============================ (c) 大盘闸门 ============================
def _build_index_ctx(key):
    df, meta = em_realtime.fetch_index_trends(key)
    if df is None or df.empty or len(df) < 5:
        return None
    prices = df["价"].astype(float).reset_index(drop=True)
    avgs = df["均价"].astype(float).reset_index(drop=True)
    vols = df["量"].astype(float).fillna(0.0).reset_index(drop=True)
    price = float(prices.iloc[-1])
    last_avg = avgs.iloc[-1]
    vwap = float(last_avg) if np.isfinite(last_avg) else price
    prev = float(meta.get("prev_close") or prices.iloc[0])
    w = vols.to_numpy()
    if w.sum() <= 0:
        w = np.ones(len(prices))
    pos = float((w * (prices.to_numpy() <= price)).sum() / w.sum())
    pct = (price - prev) / prev * 100 if prev else 0.0
    vwap_dev = (price - vwap) / vwap * 100 if vwap else 0.0
    ema = calc_ema(prices, span=10)
    slope30 = float((ema.iloc[-1] - ema.iloc[-31]) / price) if len(ema) > 31 and price else 0.0
    trend = "up" if slope30 > 0.0005 else "down" if slope30 < -0.0005 else "flat"
    if pct > 0.3 and trend == "up" and pos > 0.6:
        regime = "strong"
    elif pct < -0.3 and trend == "down" and pos < 0.4:
        regime = "weak"
    else:
        regime = "neutral"
    return {"key": key, "name": meta.get("name") or key, "pct_change": round(pct, 2),
            "pos": round(pos, 3), "vwap_dev": round(vwap_dev, 2),
            "slope_30m": round(slope30 * 100, 3), "trend": trend, "regime": regime}


def get_index_ctx(keys) -> dict:
    """批量取基准指数上下文,复用 cache(Redis+内存两级,全市场共享,30s TTL)。"""
    out = {}
    for k in set(keys):
        if not k:
            continue
        try:
            if cache is not None:
                out[k] = cache.get_or_fetch("t:idx:" + k, INDEX_TTL,
                                            lambda k=k: _build_index_ctx(k))
            else:
                out[k] = _build_index_ctx(k)
        except Exception as e:
            log.debug("get_index_ctx %s 失败: %s", k, e)
            out[k] = None
    return out


def _build_sector_ctx():
    """全市场板块强弱 {行业: {change, up_ratio, rank_pct}}。复用 app 缓存的 spot(冷则 None)。"""
    if fetch_sector_rotation_from_db is None or cache is None:
        return None
    spot = cache.get("spot")
    if spot is None or getattr(spot, "empty", True):
        return None
    try:
        sectors = fetch_sector_rotation_from_db(spot)
    except Exception as e:
        log.debug("板块数据计算失败: %s", e)
        return None
    if not sectors:
        return None
    changes = sorted(s["change"] for s in sectors)
    n = len(changes)
    out = {}
    for s in sectors:
        rank_pct = sum(1 for c in changes if c <= s["change"]) / n
        out[s["name"]] = {"change": s["change"], "up_ratio": s.get("upRatio", 0.0),
                          "rank_pct": round(rank_pct, 3)}
    return out


def get_sector_ctx() -> dict:
    """带缓存(120s)的板块强弱表;不可用(无 DB/spot 冷)时返回 {}。"""
    if cache is None:
        return _build_sector_ctx() or {}
    try:
        return cache.get_or_fetch("t:sectors", 120, _build_sector_ctx) or {}
    except Exception:
        return {}


def _stock_industry(code):
    """从 app 缓存的 spot 取个股所属行业(不额外查库/请求);无则 None。"""
    if cache is None:
        return None
    spot = cache.get("spot")
    if spot is None or getattr(spot, "empty", True) or "行业" not in getattr(spot, "columns", []):
        return None
    hit = spot[spot["代码"] == str(code).zfill(6)]
    if hit.empty:
        return None
    ind = hit.iloc[0].get("行业")
    return str(ind) if ind and str(ind) not in ("", "-", "nan", "其他") else None


def _env_gate(ictx, direction):
    """大盘对做 T 方向的调节:返回 (sizing 乘子, 风险语)。只影响 T 股数与降级。"""
    risks = []
    if not ictx:
        return 1.0, risks
    regime = ictx.get("regime")
    mult = 1.0
    if direction == "positive_t":
        if regime == "strong":
            mult = 1.10
        elif regime == "weak":
            mult = 0.60
            risks.append("大盘弱势,低吸有接飞刀风险,建议轻仓分批")
    elif direction == "negative_t":
        if regime == "strong":
            mult = 0.70
            risks.append("大盘强势,高抛留足底仓防踏空")
        elif regime == "weak":
            mult = 1.15
    return mult, risks


# ============================ A 股规则闸门 ============================
def _price_limit(prev_close, board, is_st, price):
    if is_st:
        pct = 0.05
    elif board == "bj":
        pct = 0.30
    elif board in ("cyb", "kc"):
        pct = 0.20
    else:
        pct = 0.10
    up = prev_close * (1 + pct)
    down = prev_close * (1 - pct)
    return {"limit_pct": round(pct * 100, 1), "up": _r(up), "down": _r(down),
            "near_limit_up": price >= up * 0.99, "near_limit_down": price <= down * 1.01}


# ============================ (d) 持仓 + 真 T ============================
def _position_ctx(shares, avg_cost, available, price) -> PositionCtx:
    try:
        shares = float(shares) if shares is not None else 0.0
        avg_cost = float(avg_cost) if avg_cost is not None else 0.0
    except (TypeError, ValueError):
        shares, avg_cost = 0.0, 0.0
    if shares <= 0 or avg_cost <= 0:
        return PositionCtx(False, 0.0, 0.0, 0.0, None, False)
    capped = False
    if available is None:
        available = shares
        capped = True
    else:
        try:
            available = float(available)
        except (TypeError, ValueError):
            available = shares
            capped = True
    pnl = (price - avg_cost) / avg_cost if avg_cost else None
    return PositionCtx(True, shares, max(0.0, available), avg_cost, pnl, capped)


def _empty_plan():
    return {"t_mode": "none", "t_side": None, "t_shares": 0, "cover_price": None,
            "est_profit": None, "est_profit_pct": None, "new_avg_cost": None,
            "cost_impact": None}


def _plan_trade(direction, tf: TrendFeatures, pos: PositionCtx, strength, gate_mult):
    plan = _empty_plan()
    price = tf.price
    sup = tf.supports[0] if tf.supports else (tf.va_low or tf.robust_lo)
    res = tf.resists[0] if tf.resists else (tf.va_high or tf.robust_hi)

    if direction == "negative_t":
        if not pos.has_position:
            plan["t_mode"] = "none"
            return plan
        if pos.available <= 0:
            plan["t_mode"] = "blocked_no_available"
            return plan
        ratio = _lerp(strength, 0, 100, *T_SELL_RATIO) * gate_mult
        qty = _roundlot(ratio * pos.available)
        if qty == 0 and pos.available >= 100:
            qty = 100   # 至少动一手(卖出降风险,且卖出不必凑整手预算)
        qty = min(qty, _roundlot(pos.available) or int(pos.available))
        plan.update(t_mode="reverse_t", t_side="sell_first", t_shares=qty)
        if qty > 0 and sup and sup < price:
            plan["cover_price"] = _r(sup)
            plan["est_profit"] = _r((price - sup) * qty)
            plan["est_profit_pct"] = _r((price - sup) / price * 100)
    elif direction == "positive_t":
        if not pos.has_position:
            plan["t_mode"] = "build"
            plan["t_side"] = "build"
            return plan
        ratio = _lerp(strength, 0, 100, *T_ADD_RATIO) * gate_mult
        if pos.pnl_pct is not None and pos.pnl_pct < 0:
            # 套牢补仓降本(买入持有,T+1 不闭环)
            add = _roundlot(ratio * pos.shares)
            if add > 0:
                new_cost = (pos.shares * pos.avg_cost + add * price) / (pos.shares + add)
                plan.update(t_mode="positive_t_add", t_side="buy_first", t_shares=add,
                            new_avg_cost=_r(new_cost), cost_impact=_r(new_cost - pos.avg_cost),
                            cover_price=_r(res if res > price else tf.vwap))
        else:
            # 盈利盘正 T 闭环:先低吸买入,反弹卖等量可用底仓(卖腿 ≤ available)
            add = _roundlot(min(ratio * pos.shares, pos.available))
            if add > 0:
                plan.update(t_mode="positive_t_roundtrip", t_side="buy_first",
                            t_shares=add, cover_price=_r(res if res > price else tf.vwap))
    return plan


# ============================ (e) 可解释评分 ============================
def _score_position(direction, tf: TrendFeatures):
    price = tf.price
    if direction == "positive_t":
        deep = _clamp((LOW_POS - min(tf.pos_pctile, LOW_POS)) / LOW_POS, 0, 1)
        near = 1 - _clamp(_dist_to(tf.supports, price) / (0.01 * price), 0, 1) if tf.supports else 0.3
        below = _clamp(-tf.vwap_dev / 0.01, 0, 1)
        return 100 * (0.5 * deep + 0.3 * near + 0.2 * below)
    high = _clamp((max(tf.pos_pctile, HIGH_POS) - HIGH_POS) / (1 - HIGH_POS), 0, 1)
    near = 1 - _clamp(_dist_to(tf.resists, price) / (0.01 * price), 0, 1) if tf.resists else 0.3
    above = _clamp(tf.vwap_dev / 0.01, 0, 1)
    return 100 * (0.5 * high + 0.3 * near + 0.2 * above)


def _score_volume(direction, vf: VolumeFeatures):
    if vf.degraded or vf.active_buy_ratio is None:
        base = 50.0
        if direction == "positive_t":
            if vf.pv_pattern == "down_vol_dry":
                base += 12
            elif vf.pv_pattern == "down_vol_up":
                base -= 12
            if vf.liangbi is not None and vf.liangbi < 0.8:
                base += 6
        else:
            if vf.pv_pattern == "up_vol_dry":
                base += 12
            elif vf.pv_pattern == "up_vol_up":
                base -= 12
            if vf.liangbi is not None and vf.liangbi > 1.5:
                base += 6
        return _clamp(base, 35, 65)
    r = vf.active_buy_ratio
    if direction == "positive_t":
        s = 50 + 25 * _clamp((r - 0.5) / 0.2, 0, 1) + 20 * (vf.big_order_dir == 1)
        s += 20 if vf.pv_pattern == "down_vol_dry" else (-25 if vf.pv_pattern == "down_vol_up" else 0)
    else:
        s = 50 + 25 * _clamp((0.5 - r) / 0.2, 0, 1) + 20 * (vf.big_order_dir == -1)
        s += 20 if vf.pv_pattern == "up_vol_dry" else (-25 if vf.pv_pattern == "up_vol_up" else 0)
    return _clamp(s, 0, 100)


def _score_momentum(direction, tf: TrendFeatures):
    if direction == "positive_t":
        s = 50 + 30 * _clamp(tf.slope_5m / 0.003, 0, 1) + 20 * (tf.slope_5m >= 0 and tf.slope_15m < 0)
    else:
        s = 50 + 30 * _clamp(-tf.slope_5m / 0.003, 0, 1) + 20 * (tf.slope_5m <= 0 and tf.slope_15m > 0)
    return _clamp(s, 0, 100)


def _score_index(direction, ictx, sector_adj=0):
    if not ictx:
        return _clamp(50.0 + sector_adj, 0, 100)
    strong = ictx.get("regime") == "strong"
    weak = ictx.get("regime") == "weak"
    sl = ictx.get("slope_30m", 0) or 0
    if direction == "positive_t":
        s = 50 + (25 if strong else -25 if weak else 0) + 10 * _sign(sl) + sector_adj
    else:
        s = 50 + (25 if weak else -25 if strong else 0) - 10 * _sign(sl) + sector_adj
    return _clamp(s, 0, 100)


# ============================ 决策 & 组装 ============================
def _decide_direction(tf: TrendFeatures, pos: PositionCtx):
    low = tf.pos_pctile <= LOW_POS and tf.price <= tf.vwap * 1.001
    high = tf.pos_pctile >= HIGH_POS and tf.price >= tf.vwap * 0.999
    if pos.has_position and pos.pnl_pct is not None:
        if pos.pnl_pct > 0 and high:
            return "negative_t"
        if pos.pnl_pct < 0 and low:
            return "positive_t"
    if low:
        return "positive_t"
    if high:
        return "negative_t"
    return "wait"


def _zones(direction, tf: TrendFeatures):
    price = tf.price
    buf = max(0.003 * price, (tf.robust_hi - tf.robust_lo) * 0.05)
    sup = tf.supports[0] if tf.supports else tf.va_low
    res = tf.resists[0] if tf.resists else tf.va_high
    buy_zone = sell_zone = None
    if direction == "positive_t":
        base = sup if sup else tf.robust_lo
        lo = base - buf
        hi = min(price, base + buf, tf.vwap)
        buy_zone = [_r(min(lo, hi)), _r(max(lo, hi))]
        sell_zone = [_r(tf.vwap), _r(res if res else tf.robust_hi)]
    elif direction == "negative_t":
        base = res if res else tf.robust_hi
        lo = max(price, base - buf, tf.vwap)
        hi = base + buf
        sell_zone = [_r(min(lo, hi)), _r(max(lo, hi))]
        b_lo = sup if sup else tf.robust_lo
        b_hi = min(price, tf.vwap)
        buy_zone = [_r(min(b_lo, b_hi)), _r(max(b_lo, b_hi))]
    return buy_zone, sell_zone


def _operation_plan(direction, tf, buy_zone, sell_zone):
    """把方向+区间翻译成用户可直接执行的操作计划:先做哪一步、什么价格、
    什么时候放弃。卖出/接回区间全部为明确价格,前端不做二次推断。"""
    sup = tf.supports[0] if tf.supports else tf.va_low
    res = tf.resists[0] if tf.resists else tf.va_high
    buf = max(0.003 * tf.price, (tf.robust_hi - tf.robust_lo) * 0.05)

    if direction == "negative_t" and sell_zone and buy_zone:
        invalid_up = _r((res if res and res > sell_zone[1] else sell_zone[1]) + buf)
        invalid_down = _r((min(sup, buy_zone[0]) if sup else buy_zone[0]) - buf)
        return {
            "mode": "sell_first",
            "title": "先卖后接(反T)",
            "sell_zone": sell_zone,
            "buyback_zone": buy_zone,
            "size_hint": "建议卖出底仓的 1/3~1/2,接回等量",
            "rules": "① 在卖出区分笔卖出部分持仓;② 等待回落到接回区买回等量;"
                     "③ 未到接回区不追接,14:50 仍未接回则按当时价格处理,不拖到收盘竞价。",
            "invalidation": (f"向上有效突破 {invalid_up}:强势不回落,停止等回落,"
                             "已卖部分回踩分时均价时接回;向下有效跌破 "
                             f"{invalid_down}:弱势确认,取消接回计划,重新评估趋势。"),
            "invalid_levels": [invalid_up, invalid_down],
        }
    if direction == "positive_t" and buy_zone and sell_zone:
        invalid_down = _r((min(sup, buy_zone[0]) if sup else buy_zone[0]) - buf)
        return {
            "mode": "buy_first",
            "title": "先买后卖(正T)",
            "buy_zone": buy_zone,
            "sellback_zone": sell_zone,
            "size_hint": "买入与卖出等量(当日闭环,不留新增隔夜仓)",
            "rules": "① 在低吸区分笔买入计划仓位;② 反弹至卖出区卖出等量;"
                     "③ 14:50 前未反弹到卖出区,按纪律卖出当日新买部分,不侥幸过夜。",
            "invalidation": f"有效跌破 {invalid_down}:低吸逻辑失效,不接;已有仓位反弹到压力位先减。",
            "invalid_levels": [invalid_down],
        }
    # wait:方向不明,给出重新评估的触发价格
    return {
        "mode": "wait",
        "title": "今日观望,暂不做 T",
        "sell_zone": None,
        "buyback_zone": None,
        "size_hint": None,
        "rules": "现价处日内中位、多空方向不明,按区间操作大概率两边止损;宁可错过,不做没有优势的交易。",
        "invalidation": None,
        "invalid_levels": [],
        "watch_hint": (f"回落到 {_r(sup)} 附近缩量企稳可重新评估低吸;"
                       f"放量升破 {_r(res)} 再评估反T。"),
    }


def _reasons(direction, tf, vf, ictx, pos, plan, subs):
    out = []
    pos_desc = "低位" if tf.pos_pctile <= LOW_POS else "高位" if tf.pos_pctile >= HIGH_POS else "中位"
    out.append(f"现价处日内{pos_desc}(量加权位置 {tf.pos_pctile*100:.0f}%),"
               f"{'低于' if tf.vwap_dev < 0 else '高于'}分时均价 {tf.vwap_dev*100:+.2f}%")
    if not vf.degraded and vf.active_buy_ratio is not None:
        out.append(f"主动买盘占比 {vf.active_buy_ratio*100:.0f}%"
                   + (f",大单净{'流入' if vf.big_order_dir > 0 else '流出'}"
                      if vf.big_order_dir else ""))
    if vf.pv_pattern != "flat":
        out.append(PV_DESC[vf.pv_pattern])
    if ictx:
        out.append(f"大盘{ictx['name']} {ictx['pct_change']:+.2f}%"
                   f"({ {'strong':'强势','weak':'弱势','neutral':'中性'}[ictx['regime']] })")
    if direction == "negative_t" and plan.get("t_mode") == "reverse_t" and plan.get("t_shares"):
        line = f"反T·先高抛:可卖出可用底仓约 {plan['t_shares']} 股"
        if plan.get("cover_price"):
            line += f",回补参考 {plan['cover_price']}"
        if plan.get("est_profit"):
            line += f",预计兑现价差约 {plan['est_profit']} 元"
        out.append(line)
    elif direction == "positive_t" and plan.get("t_mode") == "positive_t_add" and plan.get("t_shares"):
        out.append(f"正T·补仓降本:可补 {plan['t_shares']} 股,"
                   f"摊薄成本至 {plan['new_avg_cost']}(降 {abs(plan['cost_impact'])})")
    elif direction == "positive_t" and plan.get("t_mode") == "positive_t_roundtrip" and plan.get("t_shares"):
        out.append(f"正T·日内闭环:低吸买入约 {plan['t_shares']} 股,"
                   f"反弹至 {plan.get('cover_price')} 卖出等量可用底仓")
    elif direction == "positive_t" and plan.get("t_mode") == "build":
        out.append("当前无底仓,当日买入 T+1 不可卖;可低吸轻仓建仓,非当日做 T")
    return out


def _empty(code: str, reason: str) -> dict:
    return {
        "code": str(code).zfill(6), "name": "", "price": None, "pct_change": None,
        "vwap": None, "day_high": None, "day_low": None, "day_open": None,
        "prev_close": None, "intraday_pos": None, "vwap_dev": None, "amplitude": None,
        "action": "no_data", "action_label": LABELS["no_data"], "strength": 0,
        "buy_zone": None, "sell_zone": None, "plan": None, "reasons": [reason], "risks": [],
        "data_time": None, "disclaimer": DISCLAIMER,
        # 新增字段默认值
        "subscores": {"position": 0, "volume": 0, "momentum": 0, "index": 0},
        "weights": WEIGHTS, "poc": None, "value_area": None, "supports": [], "resists": [],
        "pv_pattern": None, "active_buy_ratio": None, "big_order_net": None,
        "big_order_dir": 0, "liangbi": None, "index_ctx": None,
        "has_position": False, "position": None, "t_mode": "none", "t_side": None,
        "t_shares": 0, "cover_price": None, "est_profit": None, "est_profit_pct": None,
        "new_avg_cost": None, "cost_impact": None, "available_capped": False,
        "price_limit": None, "degraded": True, "trend": None,
    }


def _spot_lookup(code, spot_df):
    if spot_df is None or getattr(spot_df, "empty", True) or "代码" not in getattr(spot_df, "columns", []):
        return None
    hit = spot_df[spot_df["代码"] == str(code).zfill(6)]
    if hit.empty:
        return None
    return hit.iloc[0].to_dict()


# ============================ 主入口 ============================
def signal(code, shares=None, avg_cost=None, available=None,
           index_ctx=None, spot_df=None, detail_level="full") -> dict:
    """单只票的日内做 T 决策。

    shares/avg_cost/available: 持仓数量/成本价/可卖股数(做真 T);
    index_ctx: 预算好的 {key: ctx}(batch 共享),None 则自行拉取;
    spot_df: 全市场快照(batch 共享,取量比);
    detail_level: 'full'=拉逐笔+指数+分时序列; 'lite'=仅分时+快照量比(batch 用)。
    """
    try:
        df, meta = em_realtime.fetch_trends(code)
    except Exception as e:
        log.warning("intraday_t.signal %s fetch 失败: %s", code, e)
        return _empty(code, "分时数据获取失败")
    if df is None or df.empty or len(df) < 5:
        return _empty(code, "未取到当日分时(可能非交易日/停牌/未开盘)")

    name = meta.get("name") or ""
    board = em_realtime.board_of(code)
    spot_row = _spot_lookup(code, spot_df)
    if not name and spot_row is not None:
        name = str(spot_row.get("名称") or "")
    is_st = "ST" in name.upper()

    tf = _trend_features(df, meta)

    details = None
    if detail_level == "full":
        try:
            details = em_realtime.fetch_details(code)
        except Exception as e:
            log.debug("fetch_details %s 失败: %s", code, e)
    vf = _volume_features(details, tf, spot_row)

    bkey = em_realtime.benchmark_key(code)
    if index_ctx is None:
        index_ctx = get_index_ctx({bkey})
    ictx = (index_ctx or {}).get(bkey)

    pos = _position_ctx(shares, avg_cost, available, tf.price)
    lim = _price_limit(tf.prev_close, board, is_st, tf.price)

    reasons, risks = [], []
    min_amp = MIN_AMPLITUDE.get("st" if is_st else board, 0.020)
    if tf.amplitude < min_amp:
        direction = "wait"
        reasons.append(f"日内振幅仅 {tf.amplitude*100:.1f}%,做 T 空间有限")
    else:
        direction = _decide_direction(tf, pos)

    subs = {"position": 0, "volume": 0, "momentum": 0, "index": 0}
    strength = 0
    gate_mult = 1.0
    sector_note = None
    if direction != "wait":
        # 板块闸门(仅 full):所属板块强势 → 低吸加分/高抛减分,弱势反之
        sector_adj = 0
        if detail_level == "full":
            ind = _stock_industry(code)
            info = get_sector_ctx().get(ind) if ind else None
            if info:
                rp = info["rank_pct"]
                if rp >= 0.7:
                    sector_adj = 10 if direction == "positive_t" else -10
                    sector_note = f"所属板块「{ind}」今日强势(板块涨幅居前 {round((1 - rp) * 100)}%)"
                elif rp <= 0.3:
                    sector_adj = -10 if direction == "positive_t" else 10
                    sector_note = f"所属板块「{ind}」今日弱势(板块涨幅居后 {round(rp * 100)}%)"
                else:
                    sector_note = f"所属板块「{ind}」强弱中性"
        subs = {
            "position": round(_score_position(direction, tf)),
            "volume": round(_score_volume(direction, vf)),
            "momentum": round(_score_momentum(direction, tf)),
            "index": round(_score_index(direction, ictx, sector_adj)),
        }
        w = dict(WEIGHTS)
        if vf.degraded:
            w["volume"] *= 0.5
            tot = sum(w.values())
            w = {k: v / tot for k, v in w.items()}
        strength = int(round(sum(subs[k] * w[k] for k in w)))
        if vf.degraded:
            strength = min(strength, 85)

        gate_mult, env_risks = _env_gate(ictx, direction)
        risks += env_risks

        # 极端环境降级:大盘弱 + 个股放量下杀时暂避低吸
        if (direction == "positive_t" and ictx and ictx.get("regime") == "weak"
                and vf.pv_pattern == "down_vol_up" and tf.pct_change < -0.01):
            direction = "wait"
            strength = int(strength * 0.5)
            risks.append("大盘弱势 + 个股放量下杀,暂避低吸")

        # 涨跌停闸门
        if direction == "positive_t" and lim["near_limit_up"]:
            direction = "wait"
            risks.append("近涨停,追买滑点大,等回踩")
        elif direction == "negative_t" and lim["near_limit_down"]:
            risks.append("近跌停,卖单难成交,注意流动性")

    plan = _plan_trade(direction, tf, pos, strength, gate_mult) if direction != "wait" else _empty_plan()
    if plan.get("t_mode") == "blocked_no_available":
        risks.append("有底仓但无可用(可卖)份额,T+1 当日不可高抛,仅可低吸")

    if direction != "wait":
        reasons += _reasons(direction, tf, vf, ictx, pos, plan, subs)
        if sector_note:
            reasons.append(sector_note)
    elif not reasons:
        reasons.append(f"现价处日内中位(位置 {tf.pos_pctile*100:.0f}%),做 T 信号不明确")

    if pos.available_capped and pos.has_position:
        risks.append("未提供可卖股数,已按总持仓估算,请以券商可用余额为准")
    if abs(tf.pct_change) > 0.06:
        risks.append(f"个股日内{'大涨' if tf.pct_change > 0 else '大跌'} "
                     f"{tf.pct_change*100:+.1f}%,单边趋势中做 T 风险高")
    tail = tf.data_time.split(" ")[-1] if tf.data_time else ""
    if tail >= "14:57":
        risks.append("已进入尾盘集合竞价时段")
    elif tail >= "14:45":
        risks.append("已近尾盘,注意收盘不确定性")

    buy_zone, sell_zone = _zones(direction, tf)
    operation_plan = _operation_plan(direction, tf, buy_zone, sell_zone)

    trend = None
    if detail_level == "full":
        trend = [
            {"t": str(t).split(" ")[-1], "price": _r(p), "avg": _r(a),
             "vol": int(v) if np.isfinite(v) else 0}
            for t, p, a, v in zip(df["时间"], df["价"], df["均价"], df["量"].fillna(0))
        ]

    return {
        # ---- 向后兼容字段(单位与旧版一致) ----
        "code": meta.get("code", str(code).zfill(6)),
        "name": name,
        "price": _r(tf.price), "pct_change": _r(tf.pct_change * 100),
        "vwap": _r(tf.vwap), "day_high": _r(tf.day_high), "day_low": _r(tf.day_low),
        "day_open": _r(tf.day_open), "prev_close": _r(tf.prev_close),
        "intraday_pos": _r(tf.pos_pctile, 3), "vwap_dev": _r(tf.vwap_dev * 100),
        "amplitude": _r(tf.amplitude * 100),
        "action": direction, "action_label": LABELS[direction], "strength": strength,
        "buy_zone": buy_zone, "sell_zone": sell_zone,
        "plan": operation_plan,
        "reasons": reasons, "risks": risks,
        "data_time": tf.data_time, "disclaimer": DISCLAIMER,
        # ---- 新增:可解释评分 ----
        "subscores": subs, "weights": WEIGHTS,
        # ---- 新增:日内结构 ----
        "poc": _r(tf.poc), "value_area": [_r(tf.va_low), _r(tf.va_high)],
        "supports": [_r(x) for x in tf.supports[:4]],
        "resists": [_r(x) for x in tf.resists[:4]],
        # ---- 新增:量能 ----
        "pv_pattern": vf.pv_pattern,
        "active_buy_ratio": _r(vf.active_buy_ratio, 3) if vf.active_buy_ratio is not None else None,
        "big_order_net": _r(vf.big_order_net) if vf.big_order_net is not None else None,
        "big_order_dir": vf.big_order_dir, "liangbi": _r(vf.liangbi),
        # ---- 新增:大盘 ----
        "index_ctx": ictx,
        # ---- 新增:持仓真 T ----
        "has_position": pos.has_position,
        "position": ({"shares": pos.shares, "available": pos.available,
                      "avg_cost": _r(pos.avg_cost), "pnl_pct": _r(pos.pnl_pct * 100) if pos.pnl_pct is not None else None}
                     if pos.has_position else None),
        "t_mode": plan["t_mode"], "t_side": plan["t_side"], "t_shares": plan["t_shares"],
        "cover_price": plan["cover_price"], "est_profit": plan["est_profit"],
        "est_profit_pct": plan["est_profit_pct"], "new_avg_cost": plan["new_avg_cost"],
        "cost_impact": plan["cost_impact"], "available_capped": pos.available_capped,
        # ---- 新增:A 股规则 & 元信息 ----
        "price_limit": lim, "degraded": vf.degraded, "trend": trend,
    }


def batch(items, max_workers: int = 8) -> list[dict]:
    """批量做 T 建议(自选/持仓)。

    items = [code, ...] 或 [{code, shares, avg_cost, available}, ...]。
    全批只拉一次基准指数(共享缓存);每只走 lite(仅分时,不拉逐笔/全市场快照)
    以保证批量响应速度(量比缺失时量价形态由分时斜率判定)。
    """
    parsed = []
    for it in (items or [])[:120]:
        if isinstance(it, dict):
            c = str(it.get("code") or "").zfill(6)
            if c and c != "000000":
                parsed.append((c, it.get("shares"), it.get("avg_cost"), it.get("available")))
        else:
            c = str(it).zfill(6)
            if c and c != "000000":
                parsed.append((c, None, None, None))
    if not parsed:
        return []

    bkeys = {em_realtime.benchmark_key(c) for c, *_ in parsed}
    index_ctx = get_index_ctx(bkeys)

    def _one(p):
        c, sh, ac, av = p
        try:
            return signal(c, shares=sh, avg_cost=ac, available=av,
                          index_ctx=index_ctx, detail_level="lite")
        except Exception as e:
            log.warning("batch signal %s 失败: %s", c, e)
            return _empty(c, "计算失败")

    with ThreadPoolExecutor(max_workers=min(max_workers, len(parsed))) as ex:
        return list(ex.map(_one, parsed))


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import json
    logging.basicConfig(level=logging.WARNING)
    # 无持仓
    print("=== 无持仓 600519 ===")
    print(json.dumps(signal("600519"), ensure_ascii=False, indent=2))
    # 带持仓(盈利,测反T高抛)
    print("=== 持仓 000001 shares=1000 available=1000 cost=9.0 ===")
    print(json.dumps(signal("000001", shares=1000, avg_cost=9.0, available=1000),
                     ensure_ascii=False, indent=2))
