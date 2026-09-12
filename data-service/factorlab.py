# -*- coding: utf-8 -*-
"""Factor lab: statistical validation for strategy scores.

Answers "does this strategy's score actually rank future returns?" with a
multi-dimensional rating — a high RankIC alone is NOT enough:

  方向性  RankIC mean          — does the score point the right way?
  稳定性  ICIR                 — is the signal consistent period to period?
  显著性  t-stat               — can we rule out luck?
  分层表现 layered spread,
          monotonicity,
          top-layer drawdown,
          turnover & costs     — is the ranking worth money after friction?
  样本    periods covered      — how much evidence do we actually have?
  牛熊一致 IC split by CSI300
          above/below MA60     — does it work in both regimes?
  行业中性 within-industry
          demeaned IC          — is it a stock picker or an industry bet?

Output: per-dimension scores (0-100), a composite grade (A/B/C/D), and flags
(reverse factor / high turnover / cost erosion / deep drawdown / regime
inconsistent / insufficient coverage).

Research convention: layer baskets are paper portfolios (no costs, equal
weight) — this measures *ranking power*. Costs enter only as an estimated
drag on the top-bottom spread. Scoring reuses the backtest engine's as-of
machinery (no look-ahead; fundamentals gated by ann_date).
"""
from __future__ import annotations
import datetime as dt
import time

import numpy as np
import pandas as pd
from sqlalchemy import text

import db
from backtest import engine
from core.trace import logger
from strategies import by_id

BENCHMARK_CODE = "000300"
DEFAULT_HORIZONS = (1, 5, 10, 20)

# 交易成本假设：一个完整换手（买+卖）的摩擦，口径与回测引擎一致
COST_PER_TURNOVER = 2 * (0.00025 + 0.001) + 0.0005   # ≈ 0.35% / 100% 换手

# ---- 面板缓存：连续检验多个策略时免掉重复的批量加载（TTL 10 分钟）----
_PANEL_CACHE: dict = {}
_PANEL_TTL_S = 600.0

# ---- 行业映射缓存（当日有效）----
_INDUSTRY_CACHE: dict[str, str] | None = None
_INDUSTRY_TS = 0.0


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


def _industry_map() -> dict[str, str]:
    global _INDUSTRY_CACHE, _INDUSTRY_TS
    if _INDUSTRY_CACHE is not None and time.time() - _INDUSTRY_TS < 86400:
        return _INDUSTRY_CACHE
    eng = db.get_engine()
    m: dict[str, str] = {}
    if eng is not None:
        try:
            with eng.connect() as conn:
                rows = conn.execute(text(
                    "SELECT code, industry FROM stock_info "
                    "WHERE industry IS NOT NULL AND industry != '' "
                    "AND industry != '-' AND industry != '其他'"
                )).fetchall()
            m = {str(r[0]).zfill(6): str(r[1]) for r in rows}
        except Exception as e:
            logger.debug("[factorlab] industry map load failed: %s", e)
    _INDUSTRY_CACHE, _INDUSTRY_TS = m, time.time()
    return m


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


def _max_drawdown(curve: list[float]) -> float:
    s = pd.Series(curve, dtype=float)
    if len(s) < 2:
        return 0.0
    return float((s / s.cummax() - 1.0).min())


def _ic_summary_block(ics: np.ndarray) -> dict:
    n = len(ics)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "icir": 0.0, "positive_ratio": 0.0, "t_stat": 0.0, "n": 0}
    mean = float(ics.mean())
    std = float(ics.std(ddof=1)) if n > 1 else 0.0
    return {
        "mean": round(mean, 4),
        "std": round(std, 4),
        "icir": round(mean / std, 3) if std > 0 else 0.0,
        "positive_ratio": round(float((ics > 0).sum()) / n, 3),
        "t_stat": round(float(mean / std * np.sqrt(n)), 2) if std > 0 else 0.0,
        "n": n,
    }


def _rate(ic_summary: dict, spread_ann: float, monotonicity: float,
          turnover_ann: float, top_dd: float, n: int,
          regime_consistent: bool | None) -> dict:
    """多维评级：方向性/稳定性/显著性/分层/样本 → 综合分 + 等级 + 风险旗标。"""

    def clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    direction = clamp01(abs(ic_summary["mean"]) / 0.05) * 100
    stability = clamp01(abs(ic_summary["icir"]) / 0.5) * 100
    significance = clamp01(abs(ic_summary["t_stat"]) / 2.5) * 100
    layering = (0.6 * clamp01(abs(spread_ann) / 0.20) * 100
                + 0.4 * clamp01(max(monotonicity, 0.0)) * 100)
    sample = clamp01(n / 36) * 100
    composite = round(0.25 * direction + 0.25 * stability + 0.20 * significance
                      + 0.20 * layering + 0.10 * sample, 1)
    grade = "A" if composite >= 70 else "B" if composite >= 55 else "C" if composite >= 40 else "D"

    flags: list[str] = []
    if ic_summary["mean"] < 0 and abs(ic_summary["icir"]) >= 0.2:
        flags.append("反向因子：得分越高越差，适合做排除名单或反向使用")
    net_spread = spread_ann - turnover_ann * COST_PER_TURNOVER
    if turnover_ann >= 8:
        flags.append(f"高换手：年化换手 {turnover_ann:.1f}x，成本侵蚀明显")
    if net_spread < 0.3 * spread_ann:
        flags.append("成本侵蚀：扣除摩擦后多空价差大幅缩水")
    if top_dd <= -0.25:
        flags.append(f"回撤过大：最高分层最大回撤 {top_dd:.0%}")
    if regime_consistent is False:
        flags.append("牛熊不一致：两段市场方向相反")
    if n < 12:
        flags.append(f"样本不足：仅 {n} 期，结论置信度低")

    return {
        "grade": grade,
        "composite": composite,
        "dimensions": {
            "direction": round(direction),
            "stability": round(stability),
            "significance": round(significance),
            "layering": round(layering),
            "sample": round(sample),
        },
        "net_spread_ann": round(net_spread, 4),
        "cost_per_turnover": COST_PER_TURNOVER,
        "flags": flags,
    }


def analyze(strategy_id: str, start: dt.date, end: dt.date,
            rebalance: str = "monthly", layers: int = 5,
            max_codes: int = 300, horizons=DEFAULT_HORIZONS,
            neutralize: bool = True) -> dict:
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

    day_pos = {d: i for i, d in enumerate(trading_days)}

    panel = _get_panel(codes, end)
    if not panel:
        return {"error": "panel load failed"}

    rebal_dates = engine._rebalance_dates(trading_days, rebalance)
    if len(rebal_dates) < 3:
        return {"error": f"only {len(rebal_dates)} rebalance dates — widen the window"}

    industry_map = _industry_map()
    # 预热 120 天，让基准 MA60 在回测窗口起点就有效
    bench = engine._benchmark_close(start - dt.timedelta(days=120), end)
    bench_ma = bench.rolling(60).mean() if bench is not None and len(bench) >= 60 else None

    ic_series: list[dict] = []
    icn_series: list[dict] = []          # 行业中性化后的 IC
    decay_scores: dict[int, list[float]] = {h: [] for h in horizons}
    layer_period_rets: list[dict[int, float]] = []
    layer_turnovers: dict[int, list[float]] = {lv: [] for lv in all_layers}
    prev_members: dict[int, set] = {}
    layer_dates: list[dt.date] = []
    regime_rows: list[dict] = []         # {date, ic, spread, bull}

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

        fwd_period = val_close.loc[d_next] / val_close.loc[d] - 1.0

        ic = _rank_ic(s_norm, fwd_period)
        if ic is not None:
            ic_series.append({"date": d.isoformat(), "ic": round(ic, 4)})

        # 行业中性化 IC：行业内去均值后再算秩相关（行业覆盖不足则跳过）
        if neutralize:
            ind = pd.Series([industry_map.get(c, "未知") for c in s_norm.index],
                            index=s_norm.index)
            if (ind != "未知").mean() >= 0.5:
                s_neutral = s_norm.groupby(ind).transform(lambda x: x - x.mean())
                icn = _rank_ic(s_neutral, fwd_period)
                if icn is not None:
                    icn_series.append({"date": d.isoformat(), "ic": round(icn, 4)})

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

        # 分层
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
            cur = set(members.tolist())
            prev = prev_members.get(lv) or set()
            union = cur | prev
            if union:
                layer_turnovers[lv].append(1.0 - len(cur & prev) / len(union))
            prev_members[lv] = cur
        layer_period_rets.append(layer_ret)
        layer_dates.append(d_next)

        if ic is not None:
            regime_rows.append({
                "date": d, "ic": ic,
                "spread": float(layer_ret.get(layers, 0.0) - layer_ret.get(1, 0.0)),
            })

    if len(ic_series) < 3:
        return {"error": "有效截面不足（评分覆盖太少或窗口太短）——试试放宽时间窗口或减小每期样本"}

    # ---- IC 汇总（原始 + 行业中性化）----
    ics = np.array([x["ic"] for x in ic_series], dtype=float)
    ic_summary = _ic_summary_block(ics)

    icn_summary = None
    if len(icn_series) >= 3:
        icn_summary = _ic_summary_block(np.array([x["ic"] for x in icn_series], dtype=float))

    # ---- 分层曲线 / 年化 / 回撤 / 单调性 / 换手 ----
    curves = {lv: [1.0] for lv in all_layers}
    for rets in layer_period_rets:
        for lv in all_layers:
            curves[lv].append(curves[lv][-1] * (1.0 + rets.get(lv, 0.0)))
    n_periods = len(layer_period_rets)
    layer_stats = []
    layer_anns: dict[int, float] = {}
    for lv in all_layers:
        total = curves[lv][-1] - 1.0
        ann = curves[lv][-1] ** (252.0 / max(n_periods * 21, 1)) - 1.0 if curves[lv][-1] > 0 else -1.0
        layer_anns[lv] = ann
        layer_stats.append({
            "layer": lv,
            "total": round(total, 4),
            "annualized": round(ann, 4),
            "max_drawdown": round(_max_drawdown(curves[lv]), 4),
        })
    spread_ann = layer_anns[all_layers[-1]] - layer_anns[all_layers[0]]

    # 单调性：层数 vs 年化收益的 spearman（1.0 = 完美单调）
    mono_x = np.arange(1, layers + 1, dtype=float)
    mono_y = np.array([layer_anns[lv] for lv in all_layers], dtype=float)
    if np.std(mono_x) > 0 and np.std(mono_y) > 0:
        monotonicity = float(np.corrcoef(mono_x, mono_y)[0, 1])
    else:
        monotonicity = 0.0

    # 年化换手：分层成员的 Jaccard 距离均值 × 每年调仓次数
    n_years = max(n_periods * 21 / 252.0, 1e-6)
    rebal_per_year = n_periods / n_years
    layer_mean_turnover = {lv: (float(np.mean(v)) if v else 0.0) for lv, v in layer_turnovers.items()}
    turnover_ann = float(np.mean(list(layer_mean_turnover.values())) * rebal_per_year)

    # ---- 牛熊分阶段（沪深300 收盘相对 MA60）----
    regime_block = None
    if bench_ma is not None:
        bull_ics, bear_ics = [], []
        bull_spreads, bear_spreads = [], []
        for r in regime_rows:
            ts = pd.Timestamp(r["date"])
            b = bench.get(ts)
            ma = bench_ma.get(ts)
            if b is None or ma is None or pd.isna(b) or pd.isna(ma):
                continue
            if b >= ma:
                bull_ics.append(r["ic"]); bull_spreads.append(r["spread"])
            else:
                bear_ics.append(r["ic"]); bear_spreads.append(r["spread"])
        if len(bull_ics) >= 2 and len(bear_ics) >= 2:
            per_year = 12.0 if rebalance == "monthly" else 52.0
            regime_block = {
                "bull": {"ic_mean": round(float(np.mean(bull_ics)), 4), "n": len(bull_ics),
                         "spread_ann": round(float(np.mean(bull_spreads)) * per_year, 4)},
                "bear": {"ic_mean": round(float(np.mean(bear_ics)), 4), "n": len(bear_ics),
                         "spread_ann": round(float(np.mean(bear_spreads)) * per_year, 4)},
            }

    # ---- 评级 ----
    regime_consistent = None
    if regime_block:
        bs = np.sign(regime_block["bull"]["ic_mean"])
        rs = np.sign(regime_block["bear"]["ic_mean"])
        regime_consistent = (bs == rs) and bs != 0
    rating = _rate(ic_summary, spread_ann, monotonicity,
                   turnover_ann, layer_stats[-1]["max_drawdown"],
                   len(ics), regime_consistent)

    layer_curves_out = []
    for j, d in enumerate(layer_dates):
        row: dict = {"date": d.isoformat()}
        for lv in all_layers:
            row[f"L{lv}"] = round(curves[lv][j + 1], 4)
        layer_curves_out.append(row)

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
        "ic_neutral_summary": icn_summary,
        "rating": rating,
        "layer_curves": layer_curves_out,
        "layer_stats": layer_stats,
        "layer_monotonicity": round(monotonicity, 3),
        "turnover_annualized": round(turnover_ann, 2),
        "top_minus_bottom_annualized": round(spread_ann, 4),
        "decay": decay_out,
        "regime": regime_block,
    }
