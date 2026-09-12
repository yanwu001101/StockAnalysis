# -*- coding: utf-8 -*-
"""Factor lab: statistical validation for strategy scores.

Answers "does this strategy's score actually rank future returns?" with the
standard quant research toolkit:

  * IC / RankIC  — cross-sectional rank correlation between scores at t and
                   forward returns over the next period
  * Layered test — split the universe into N quantile baskets by score each
                   rebalance, hold to the next rebalance, compound each
                   basket's return; a working factor shows monotonic layers
  * Decay        — RankIC at +1/+5/+10/+20 trading-day horizons
  * Preprocessing— MAD-winsorize + z-score on the score cross-section before
                   any ranking, so outlier scores can't dominate

Research convention: layer baskets are paper portfolios (no costs, equal
weight) — this measures *ranking power*, not tradable PnL. Use the backtest
engine for tradable numbers.

Scoring reuses the backtest engine's as-of machinery (no look-ahead): each
rebalance date re-scores the universe with only data visible on that date
(fundamentals gated by ann_date / statutory deadline).
"""
from __future__ import annotations
import datetime as dt
import time

import numpy as np
import pandas as pd

from backtest import engine
from core.trace import logger
from strategies import by_id

DEFAULT_HORIZONS = (1, 5, 10, 20)


# ---- 面板缓存：连续检验多个策略时免掉重复的批量加载（TTL 10 分钟）----
_PANEL_CACHE: dict = {}
_PANEL_TTL_S = 600.0


def _get_panel(codes: list[str], end: dt.date) -> dict:
    key = (end.isoformat(), tuple(codes))
    now = time.time()
    hit = _PANEL_CACHE.get(key)
    if hit and now - hit[0] < _PANEL_TTL_S:
        return hit[1]
    panel = engine._load_panel(codes, end)
    if panel:
        _PANEL_CACHE.clear()   # 只保留最近一份，防止内存膨胀
        _PANEL_CACHE[key] = (now, panel)
    return panel

def _winsorize_zscore(scores: pd.Series) -> pd.Series:
    """MAD 去极值(3 倍) + z-score 标准化。截面至少要有几分散度，否则返回全 0。"""
    s = scores.astype(float).dropna()
    med = float(s.median())
    mad = float((s - med).abs().median())
    if mad > 0:
        lo, hi = med - 3 * 1.4826 * mad, med + 3 * 1.4826 * mad
        s = s.clip(lo, hi)
    std = float(s.std(ddof=0))
    if std <= 1e-12:
        return s * 0.0
    return (s - float(s.mean())) / std


def _rank_ic(a: pd.Series, b: pd.Series) -> float | None:
    """Spearman RankIC：秩相关；样本不足或零方差返回 None。"""
    common = a.index.intersection(b.index)
    if len(common) < 10:
        return None
    ra, rb = a.loc[common].rank(), b.loc[common].rank()
    if ra.std(ddof=0) <= 0 or rb.std(ddof=0) <= 0:
        return None
    return float(ra.corr(rb))


def _universe_codes(amount: pd.DataFrame | None, close: pd.DataFrame, max_codes: int) -> list[str]:
    """按日均成交额降序取前 max_codes 只（流动性代理），无 amount 则按代码序。"""
    codes = list(close.columns)
    if amount is not None and not amount.empty and max_codes and len(codes) > max_codes:
        mean_amt = amount.mean().sort_values(ascending=False)
        return mean_amt.head(max_codes).index.tolist()
    return codes[:max_codes] if max_codes else codes


def analyze(strategy_id: str, start: dt.date, end: dt.date,
            rebalance: str = "monthly", layers: int = 5,
            max_codes: int = 300, horizons=DEFAULT_HORIZONS) -> dict:
    strat = by_id(strategy_id)
    if strat is None:
        return {"error": f"unknown strategy_id: {strategy_id}"}
    layers = max(2, min(int(layers), 10))
    all_layers = list(range(1, layers + 1))
    horizons = tuple(sorted({int(h) for h in horizons if 1 <= int(h) <= 60}))

    trading_days = engine._trading_days(start, end)
    if len(trading_days) < 30:
        return {"error": "not enough trading days in range"}

    ohlcv = engine._universe_ohlcv(start, end)
    if not ohlcv:
        return {"error": "no price matrix; run postmarket job first"}
    close = ohlcv["close"]
    codes = _universe_codes(ohlcv.get("amount"), close, max_codes)
    val_close = close[codes].ffill()

    # 交易日位置索引，用于衰减分析的 +N 日前向窗口
    day_pos = {d: i for i, d in enumerate(trading_days)}

    panel = _get_panel(codes, end)
    if not panel:
        return {"error": "panel load failed"}

    rebal_dates = engine._rebalance_dates(trading_days, rebalance)
    if len(rebal_dates) < 3:
        return {"error": f"only {len(rebal_dates)} rebalance dates — widen the window"}

    ic_series: list[dict] = []
    decay_scores: dict[int, list[float]] = {h: [] for h in horizons}
    layer_period_rets: list[dict[int, float]] = []
    layer_dates: list[dt.date] = []

    for i, d in enumerate(rebal_dates[:-1]):
        d_next = rebal_dates[i + 1]
        if d not in val_close.index or d_next not in val_close.index:
            continue

        scores: dict[str, float] = {}
        for c in codes:
            s = engine._score_at(strat, panel[c], c, d)
            if s > 0:
                scores[c] = s
        if len(scores) < layers * 5:
            logger.info("[factorlab] %s: only %d scores, skipped", d, len(scores))
            continue
        s_norm = _winsorize_zscore(pd.Series(scores))

        # 当期前向收益（调仓日 → 下一调仓日）
        fwd_period = val_close.loc[d_next] / val_close.loc[d] - 1.0

        ic = _rank_ic(s_norm, fwd_period)
        if ic is not None:
            ic_series.append({"date": d.isoformat(), "ic": round(ic, 4)})

        # 衰减：+N 个交易日的 RankIC
        pos = day_pos[d]
        for h in horizons:
            if pos + h >= len(trading_days):
                continue
            d_h = trading_days[pos + h]
            if d_h not in val_close.index:
                continue
            fwd_h = val_close.loc[d_h] / val_close.loc[d] - 1.0
            ic_h = _rank_ic(s_norm, fwd_h)
            if ic_h is not None:
                decay_scores[h].append(ic_h)

        # 分层：按标准化得分 qcut 成 layers 组（1=最低 .. layers=最高）
        try:
            bins = pd.qcut(s_norm.rank(method="first"), q=layers, labels=range(1, layers + 1))
        except ValueError:
            continue
        layer_ret: dict[int, float] = {}
        codes_arr = s_norm.index.to_numpy()
        bin_arr = np.asarray(bins)
        for lv in all_layers:
            members = codes_arr[bin_arr == lv]
            if len(members) == 0:
                layer_ret[int(lv)] = 0.0
                continue
            basket = fwd_period.loc[members].dropna()
            layer_ret[int(lv)] = float(basket.mean()) if len(basket) else 0.0
        layer_period_rets.append(layer_ret)
        layer_dates.append(d_next)

    if len(ic_series) < 3:
        return {"error": "有效截面不足（评分覆盖太少或窗口太短）——试试放宽时间窗口或减小每期样本"}

    # ---- IC 汇总 ----
    ics = np.array([x["ic"] for x in ic_series], dtype=float)
    ic_mean, ic_std = float(ics.mean()), float(ics.std(ddof=1)) if len(ics) > 1 else 0.0
    icir = ic_mean / ic_std if ic_std > 0 else 0.0
    n = len(ics)
    t_stat = ic_mean / ic_std * np.sqrt(n) if ic_std > 0 else 0.0
    ic_summary = {
        "mean": round(ic_mean, 4),
        "std": round(ic_std, 4),
        "icir": round(icir, 3),
        "positive_ratio": round(float((ics > 0).sum()) / n, 3),
        "t_stat": round(float(t_stat), 2),
        "n": n,
    }

    # ---- 分层曲线与年化 ----
    curves = {lv: [1.0] for lv in all_layers}
    for rets in layer_period_rets:
        for lv in all_layers:
            curves[lv].append(curves[lv][-1] * (1.0 + rets.get(lv, 0.0)))
    n_periods = len(layer_period_rets)
    layer_stats = []
    for lv in all_layers:
        total = curves[lv][-1] - 1.0
        ann = curves[lv][-1] ** (252.0 / max(n_periods * 21, 1)) - 1.0 if curves[lv][-1] > 0 else -1.0
        layer_stats.append({"layer": lv, "total": round(total, 4), "annualized": round(ann, 4)})
    spread_ann = layer_stats[-1]["annualized"] - layer_stats[0]["annualized"]

    layer_curves_out = []
    for j, d in enumerate(layer_dates):
        row = {"date": d.isoformat()}
        for lv in all_layers:
            row[f"L{lv}"] = round(curves[lv][j + 1], 4)
        layer_curves_out.append(row)

    # ---- 衰减 ----
    decay_out = []
    for h in horizons:
        arr = np.array(decay_scores[h], dtype=float)
        if len(arr) == 0:
            continue
        m, sd = float(arr.mean()), float(arr.std(ddof=1)) if len(arr) > 1 else 0.0
        decay_out.append({
            "horizon": h,
            "ic_mean": round(m, 4),
            "icir": round(m / sd, 3) if sd > 0 else 0.0,
            "n": len(arr),
        })

    return {
        "strategy_id": strategy_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "rebalance": rebalance,
        "layers": layers,
        "codes_analyzed": len(codes),
        "periods": n_periods,
        "ic_series": ic_series,
        "ic_summary": ic_summary,
        "layer_curves": layer_curves_out,
        "layer_stats": layer_stats,
        "top_minus_bottom_annualized": round(spread_ann, 4),
        "decay": decay_out,
    }
