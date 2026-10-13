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
from quant_stats import (finite_pairs, ic_summary, chronological_validation,
                         equal_weight_turnover, cap_bucket_demean)

BENCHMARK_CODE = "000300"
DEFAULT_HORIZONS = (1, 5, 10, 20)
ENGINE_VERSION = "factorlab-2026-10-12-v4"

# 交易成本假设：一个完整换手（买+卖）的摩擦，口径与回测引擎一致
COST_PER_TURNOVER = 2 * (0.00025 + 0.001) + 0.0005   # ≈ 0.35% / 100% 换手

# ---- 面板缓存：连续检验多个策略时免掉重复的批量加载（TTL 10 分钟）----
_PANEL_CACHE: dict = {}
_PANEL_TTL_S = 600.0

# ---- 行业映射缓存（当日有效）----
_INDUSTRY_CACHE: dict[str, str] | None = None
_INDUSTRY_TS = 0.0


def _get_panel(codes: list[str], end: dt.date,
               start: dt.date | None = None) -> dict:
    key = (end.isoformat(), start.isoformat() if start else "", tuple(codes))
    now = time.time()
    hit = _PANEL_CACHE.get(key)
    if hit and now - hit[0] < _PANEL_TTL_S:
        return hit[1]
    panel = engine._load_panel(codes, end, start=start)
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
    s = scores.astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    if s.empty:
        return s
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
    pairs = finite_pairs(a, b)
    if len(pairs) < 10:
        return None
    ra, rb = pairs["factor"].rank(), pairs["return"].rank()
    if ra.std(ddof=0) <= 0 or rb.std(ddof=0) <= 0:
        return None
    return float(ra.corr(rb))


def _pearson_ic(a: pd.Series, b: pd.Series) -> float | None:
    """Pearson IC：因子值与前瞻收益的线性相关；样本不足或零方差返回 None。"""
    pairs = finite_pairs(a, b)
    if len(pairs) < 10:
        return None
    xa, xb = pairs["factor"], pairs["return"]
    if xa.std(ddof=0) <= 0 or xb.std(ddof=0) <= 0:
        return None
    return float(xa.corr(xb))


def _universe_codes(amount: pd.DataFrame | None, close: pd.DataFrame,
                    max_codes: int, volume: pd.DataFrame | None = None,
                    as_of: dt.date | None = None) -> list[str]:
    """宇宙选择：优先 amount（日均成交额），缺失用 close×volume 代理；
    都没有则按原始列序。流动性排序的宇宙比代码序更有代表性。"""
    if as_of is not None:
        close = close.loc[pd.to_datetime(close.index) <= pd.Timestamp(as_of)].tail(60)
        if amount is not None:
            amount = amount.reindex(close.index)
        if volume is not None:
            volume = volume.reindex(close.index)
    codes = list(close.columns)
    if as_of is not None:
        codes = [c for c in codes if close[c].notna().any()]
        close = close[codes]
    if max_codes and len(codes) > max_codes:
        if amount is not None and not amount.empty:
            score = amount.mean()
        elif volume is not None:
            score = (close * volume).mean()
        else:
            return codes[:max_codes]
        score = score.replace([np.inf, -np.inf], np.nan).dropna()
        return score[score > 0].sort_values(ascending=False, kind="stable").head(max_codes).index.tolist()
    return codes[:max_codes] if max_codes else codes


def _max_drawdown(curve: list[float]) -> float:
    s = pd.Series(curve, dtype=float)
    if len(s) < 2:
        return 0.0
    return float((s / s.cummax() - 1.0).min())


def _rebalance_per_year(rebalance: str) -> float:
    """调仓频率 → 年化调仓次数（Nd 周期按 252/N 折算）。"""
    if rebalance == "monthly":
        return 12.0
    if rebalance.endswith("d") and rebalance[:-1].isdigit():
        return 252.0 / max(int(rebalance[:-1]), 1)
    return 52.0


def _ic_summary_block(ics: np.ndarray) -> dict:
    return ic_summary(ics)


def _rate(ic_summary: dict, spread_ann: float, monotonicity: float,
          turnover_ann: float, top_dd: float, n: int,
          regime_consistent: bool | None, icn_summary: dict | None = None,
          validation: dict | None = None) -> dict:
    """Transparent evidence grading. Missing checks earn no invented points."""
    def clamp(x):
        return max(0.0, min(1.0, float(x)))
    abs_ic = abs(ic_summary.get("mean") or 0)
    abs_icir = abs(ic_summary.get("icir") or 0)
    abs_t = abs(ic_summary.get("t_stat") or 0)
    sign = (validation or {}).get("direction_sign", -1 if (ic_summary.get("mean") or 0) < 0 else 1)
    direction = "reverse" if sign < 0 else "positive"
    mono = max(0.0, monotonicity * sign)
    strength = round(30 * clamp(abs_ic / .05) + 25 * clamp(abs_icir / .5)
                     + 25 * clamp(max(spread_ann * sign, 0) / .20) + 20 * clamp(mono), 1)
    confidence = round(60 * clamp(abs_t / 2.5) + 40 * clamp(n / 36), 1)
    cost = turnover_ann * COST_PER_TURNOVER
    net = spread_ann * sign - cost
    components = {}
    if regime_consistent is not None:
        components["regime"] = 100.0 if regime_consistent else 0.0
    if icn_summary and icn_summary.get("mean") is not None and abs_ic > 1e-12:
        components["industry_retention"] = 100 * clamp(icn_summary["mean"] * sign / abs_ic)
    if validation and validation.get("status") == "VALID":
        oos = validation["normalized_test"]
        components["out_of_sample"] = 100 * clamp(max(oos.get("mean") or 0, 0) / max(abs_ic, 1e-12))
    rolling = (validation or {}).get("rolling", [])
    valid_rolling = [r["icir"] for r in rolling if r.get("icir") is not None]
    if valid_rolling:
        components["rolling_consistency"] = 100 * float(np.mean(np.array(valid_rolling) * sign > 0))
    robustness = round(float(np.mean(list(components.values()))), 1) if components else None
    p = ic_summary.get("p_value")
    oos = (validation or {}).get("normalized_test", {})
    if n < 12 or ic_summary.get("icir") is None:
        code, status = "INSUFFICIENT_DATA", "样本不足"
    elif (n >= 36 and p is not None and p < .05 and abs_icir >= .3 and strength >= 55
          and net > 0 and (validation or {}).get("status") == "VALID"
          and oos.get("p_value") is not None and oos["p_value"] < .05
          and (oos.get("mean") or 0) > 0 and robustness is not None and robustness >= 60):
        code, status = "VALID", "有效"
    elif abs_icir >= .3 or abs_ic >= .03:
        code, status = "CANDIDATE", "候选"
    else:
        code, status = "INSIGNIFICANT", "不显著"
    flags = ["分层为排序研究，不代表可成交组合；未模拟融券、冲击成本、涨跌停成交或容量"]
    if n < 36:
        flags.append(f"有效调仓期仅 {n}，统计稳定性有限")
    if not validation or validation.get("status") != "VALID":
        flags.append("样本外期数不足；不得据此认定因子有效")
    if turnover_ann >= 8:
        flags.append(f"多空两腿年化换手 {turnover_ann:.1f}x，成本不可忽略")
    if spread_ann * sign > 0 and net <= 0:
        flags.append("成本侵蚀：方向调整后毛收益为正、净收益非正")
    if top_dd <= -.25:
        flags.append(f"多头分层最大回撤 {top_dd:.1%}")
    if regime_consistent is False:
        flags.append("牛熊方向不一致")
    return {
        "grade": "A" if strength >= 70 else "B" if strength >= 55 else "C" if strength >= 40 else "D",
        "strength": strength, "confidence": confidence, "direction": direction,
        "direction_sign": sign, "direction_source": "TRAIN_ONLY" if validation else "FULL_SAMPLE_EXPLORATORY",
        "status": status, "status_code": code,
        "dimensions": {"direction_ic": round(100 * clamp(abs_ic / .05)),
                       "stability": round(100 * clamp(abs_icir / .5)) if ic_summary.get("icir") is not None else None,
                       "significance": round(100 * clamp(abs_t / 2.5)) if p is not None else None,
                       "monotonicity": round(100 * clamp(mono)),
                       "spread": round(100 * clamp(max(spread_ann * sign, 0) / .20)),
                       "sample": round(100 * clamp(n / 36))},
        "net_spread_ann": round(spread_ann - cost, 8),
        "adjusted_gross_spread_ann": round(spread_ann * sign, 8),
        "adjusted_net_spread_ann": round(net, 8),
        "cost_annualized": round(cost, 8), "cost_per_turnover": COST_PER_TURNOVER,
        "robustness": robustness, "robustness_components": components,
        "tradability": None,
        "tradability_note": "未测容量/冲击/融券约束，不能用净收益冒充交易可行性评分",
        "flags": flags,
    }


def _failure(message: str, kind: str = "coverage") -> dict:
    return {"error": message, "error_kind": kind, "engine_version": ENGINE_VERSION,
            "status": "INSUFFICIENT_DATA" if kind == "coverage" else "FAILED",
            "ic_summary": _ic_summary_block([]), "ic_series": [], "layer_curves": [],
            "layer_stats": [], "decay": [], "rating": None, "periods": 0,
            "turnover_annualized": None, "top_minus_bottom_annualized": None,
            "sample_info": {"periods": 0, "avg_cross_section": None, "observations": 0}}


def _current_caps() -> pd.Series:
    eng = db.get_engine()
    if eng is None:
        return pd.Series(dtype=float)
    with eng.connect() as conn:
        rows = conn.execute(text("SELECT code, market_cap FROM stock_info WHERE market_cap > 0")).fetchall()
    return pd.Series({str(code).zfill(6): float(cap) for code, cap in rows})


def analyze(strategy_id: str, start: dt.date, end: dt.date,
            rebalance: str = "monthly", layers: int = 5,
            max_codes: int = 300, horizons=DEFAULT_HORIZONS,
            neutralize: bool = True, smoothing_days: int = 1,
            cap_diagnostic: bool = False) -> dict:
    """内置策略检验入口：把策略的 as-of 评分打包成 score_provider，
    统一走 analyze_scores 统计管线（与自定义因子共用同一引擎，Skill §20）。"""
    strat = by_id(strategy_id)
    if strat is None:
        return _failure(f"unknown strategy_id: {strategy_id}", "compute")
    if strategy_id == "magic_formula":
        return _failure("Magic Formula 缺少历史市值/企业价值，当前市值或市值=0的近似不能用于历史检验")

    trading_days = engine._trading_days(start, end)
    if len(trading_days) < 30:
        return _failure("not enough trading days in range")
    ohlcv = engine._universe_ohlcv(start - dt.timedelta(days=120), end)
    if not ohlcv:
        return _failure("no price matrix; run postmarket job first")
    codes = _universe_codes(ohlcv.get("amount"), ohlcv["close"], max_codes,
                            volume=ohlcv.get("volume"), as_of=start)

    panel = _get_panel(codes, end, start)
    if not panel:
        return _failure("panel load failed", "compute")

    def provider(d: dt.date, codes_list: list[str]) -> pd.Series:
        out: dict[str, float] = {}
        for c in codes_list:
            s = engine._score_at_cached(strat, panel.get(c, {}), c, d)
            if s is not None and np.isfinite(s):
                out[c] = s
        return pd.Series(out)

    result = analyze_scores(provider, start=start, end=end, rebalance=rebalance,
                            layers=layers, max_codes=max_codes,
                            horizons=horizons, neutralize=neutralize,
                            factor_name=strat.name, codes=codes, smoothing_days=smoothing_days,
                            cap_diagnostic=cap_diagnostic)
    if "error" not in result:
        result["strategy_id"] = strategy_id
    return result


def analyze_scores(score_provider, start: dt.date, end: dt.date,
                   rebalance: str = "monthly", layers: int = 5,
                   max_codes: int = 300, horizons=DEFAULT_HORIZONS,
                   neutralize: bool = True, factor_name: str = "因子",
                   codes: list[str] | None = None, include_pearson: bool = True,
                   smoothing_days: int = 1, cap_diagnostic: bool = False) -> dict:
    """One statistical engine for batch, detail, custom expressions and mining.

    Signal t close -> entry t+1 open -> exit next signal close. These are
    equal-weight ranking-study labels, not an executable trading backtest.
    """
    if start >= end:
        return _failure("开始日期必须早于结束日期", "compute")
    if rebalance not in ("daily", "weekly", "monthly") and not (
            rebalance.endswith("d") and rebalance[:-1].isdigit() and 1 <= int(rebalance[:-1]) <= 60):
        return _failure("不支持的调仓频率", "compute")
    layers = max(2, min(int(layers), 10))
    smoothing_days = max(1, min(int(smoothing_days), 60))
    horizons = tuple(sorted({int(h) for h in horizons if 1 <= int(h) <= 60}))
    days = engine._trading_days(start, end)
    if len(days) < 30:
        return _failure("区间内交易日不足30天")
    ohlcv = engine._universe_ohlcv(start - dt.timedelta(days=120), end)
    if not ohlcv or "open" not in ohlcv:
        return _failure("缺少开盘价面板，无法计算 t+1 执行收益")
    frames = {}
    for k, frame in ohlcv.items():
        f = frame.copy(deep=False)
        f.index = pd.to_datetime(f.index).date
        frames[k] = f.sort_index()
    close, opens = frames["close"], frames["open"]
    if codes is None:
        codes = _universe_codes(frames.get("amount"), close, max_codes,
                                frames.get("volume"), as_of=start)
    codes = [c for c in codes if c in close.columns and c in opens.columns]
    if len(codes) < layers * 5:
        return _failure("起点可知股票池不足，请扩大股票池或补齐历史数据")
    close, opens = close[codes], opens[codes]
    day_pos = {d: i for i, d in enumerate(days)}
    signal_days = engine._rebalance_dates(days, rebalance)
    industry = _industry_map() if neutralize else {}
    caps = _current_caps() if cap_diagnostic else pd.Series(dtype=float)
    bench = engine._benchmark_close(start - dt.timedelta(days=120), end)
    bench_ma = bench.rolling(60).mean() if bench is not None else None
    series, pearson, neutral, cap_series = [], [], [], []
    decay_scores = {h: [] for h in horizons}
    all_layers = list(range(1, layers + 1))
    curves = {lv: [1.0] for lv in all_layers}
    turns = {lv: [] for lv in all_layers}
    prev = {lv: {} for lv in all_layers}
    layer_rows, durations, cross_sizes, regime_rows = [], [], [], []
    skipped, missing_labels = 0, 0
    score_cache = {}

    def score(d):
        if d not in score_cache:
            values = pd.Series(score_provider(d, codes), dtype=float).reindex(codes)
            score_cache[d] = values.replace([np.inf, -np.inf], np.nan)
        return score_cache[d]

    def forward(d, last):
        pos = day_pos[d]
        if pos + 1 >= len(days) or last not in close.index:
            return pd.Series(dtype=float)
        entry = days[pos + 1]
        if entry not in opens.index:
            return pd.Series(dtype=float)
        price = opens.loc[entry].where(opens.loc[entry] > 0)
        vol = frames.get("volume")
        if vol is not None and entry in vol.index:
            price = price.where(vol.loc[entry].reindex(codes) > 0)
        return (close.loc[last].where(close.loc[last] > 0) / price - 1).replace([np.inf, -np.inf], np.nan)

    for i, d in enumerate(signal_days[:-1]):
        last = signal_days[i + 1]
        pos = day_pos[d]
        if pos < smoothing_days - 1:
            skipped += 1
            continue
        raw = pd.concat([score(x) for x in days[pos - smoothing_days + 1:pos + 1]], axis=1).mean(axis=1, skipna=False)
        s_norm = _winsorize_zscore(raw)
        fwd = forward(d, last)
        pairs = finite_pairs(s_norm, fwd)
        missing_labels += max(len(s_norm) - len(pairs), 0)
        ic = _rank_ic(pairs["factor"], pairs["return"])
        if len(pairs) < layers * 5 or ic is None:
            skipped += 1
            continue
        s_norm, fwd_valid = pairs["factor"], pairs["return"]
        series.append({"date": d.isoformat(), "execution_date": days[pos + 1].isoformat(),
                       "return_end": last.isoformat(), "ic": ic, "n": len(pairs)})
        cross_sizes.append(len(pairs))
        if include_pearson:
            value = _pearson_ic(s_norm, fwd_valid)
            if value is not None:
                pearson.append({"date": d.isoformat(), "ic": value})
        if neutralize:
            ind = pd.Series({c: industry.get(c) for c in s_norm.index}).dropna()
            ind = ind[ind.map(ind.value_counts()) >= 2]
            if len(ind) >= max(10, len(s_norm) * .5):
                x = s_norm.reindex(ind.index)
                residual = x - x.groupby(ind).transform("mean")
                value = _rank_ic(residual, fwd_valid)
                if value is not None:
                    neutral.append({"date": d.isoformat(), "ic": value})
        if cap_diagnostic:
            value = _rank_ic(cap_bucket_demean(s_norm, caps), fwd_valid)
            if value is not None:
                cap_series.append(value)
        for h in horizons:
            if pos + h < len(days):
                value = _rank_ic(s_norm, forward(d, days[pos + h]))
                if value is not None:
                    decay_scores[h].append(value)
        bins = pd.qcut(s_norm.rank(method="first"), layers, labels=all_layers)
        rets = {}
        for lv in all_layers:
            members = bins.index[bins == lv]
            weights = {c: 1 / len(members) for c in members}
            turns[lv].append(equal_weight_turnover(prev[lv], weights))
            r = float(fwd_valid.loc[members].mean())
            rets[lv] = r
            curves[lv].append(curves[lv][-1] * (1 + r))
            prev[lv] = {c: weights[c] * (1 + float(fwd_valid[c])) / (1 + r) for c in members} if r > -1 else {}
        duration = day_pos[last] - pos
        durations.append(duration)
        layer_rows.append({"date": last.isoformat(), **{f"L{lv}": round(curves[lv][-1], 8) for lv in all_layers}})
        if bench is not None and bench_ma is not None:
            b, ma = bench.get(pd.Timestamp(d)), bench_ma.get(pd.Timestamp(d))
            if b is not None and ma is not None and np.isfinite(b) and np.isfinite(ma):
                regime_rows.append({"bull": bool(b >= ma), "ic": ic,
                                    "spread": rets[layers] - rets[1], "days": duration})
    if len(series) < 3:
        return _failure("有效截面不足（至少3期、每层至少5只且因子需有离散度）；检查字段覆盖与时间范围")
    summary = _ic_summary_block([r["ic"] for r in series])
    neutral_summary = _ic_summary_block([r["ic"] for r in neutral]) if neutral else None
    validation = chronological_validation(series)
    years = sum(durations) / 252
    layer_stats = []
    for lv in all_layers:
        nav = curves[lv][-1]
        layer_stats.append({"layer": lv, "total": round(nav - 1, 8),
                            "annualized": round(nav ** (1 / years) - 1, 8) if nav > 0 else -1.0,
                            "max_drawdown": round(_max_drawdown(curves[lv]), 8),
                            "turnover_annualized": round(sum(turns[lv]) / years, 8)})
    spread = layer_stats[-1]["annualized"] - layer_stats[0]["annualized"]
    mono_y = pd.Series([r["annualized"] for r in layer_stats]).rank()
    monotonicity = float(pd.Series(all_layers).corr(mono_y)) if mono_y.std() > 0 else 0.0
    # Spread has one unit long AND one unit short: charge BOTH legs, not the average of all layers.
    turnover = (sum(turns[1]) + sum(turns[layers])) / years
    regime = None
    sides = {k: [r for r in regime_rows if r["bull"] == v] for k, v in (("bull", True), ("bear", False))}
    if all(len(v) >= 2 for v in sides.values()):
        regime = {k: {"ic_mean": float(np.mean([r["ic"] for r in v])), "n": len(v),
                      "spread_ann": sum(r["spread"] for r in v) * 252 / sum(r["days"] for r in v)} for k, v in sides.items()}
    consistent = (regime["bull"]["ic_mean"] * regime["bear"]["ic_mean"] > 0) if regime else None
    long_layer = 0 if validation["direction_sign"] < 0 else -1
    rating = _rate(summary, spread, monotonicity, turnover, layer_stats[long_layer]["max_drawdown"],
                   len(series), consistent, neutral_summary, validation)
    adjusted = _ic_summary_block([r["ic"] * validation["direction_sign"] for r in series])
    if skipped:
        rating["flags"].append(f"{skipped}期因覆盖/离散度不足被剔除；年化按有效持有交易日计算")
    return {"engine_version": ENGINE_VERSION, "strategy_id": None, "factor_name": factor_name,
            "status": rating["status_code"], "start": start.isoformat(), "end": end.isoformat(),
            "rebalance": rebalance, "layers": layers, "codes_analyzed": len(codes),
            "periods": len(series), "smoothing_days": smoothing_days,
            "sample_info": {"periods": len(series), "avg_cross_section": round(float(np.mean(cross_sizes))),
                            "observations": sum(cross_sizes), "skipped_periods": skipped,
                            "missing_forward_labels": missing_labels, "holding_trading_days": sum(durations)},
            "ic_summary": summary, "ic_adjusted_summary": adjusted, "ic_series": series,
            "ic_neutral_summary": neutral_summary,
            **({"ic_pearson_series": pearson, "ic_pearson_summary": _ic_summary_block([r["ic"] for r in pearson])} if include_pearson else {}),
            "market_cap_diagnostic": {"enabled": cap_diagnostic, "summary": _ic_summary_block(cap_series) if cap_diagnostic else None,
                                      "point_in_time": False, "used_in_rating": False,
                                      "note": "当前市值十分位去均值仅作敏感性诊断，含未来信息；不得用于历史评分或样本外结论"},
            "validation": validation, "rating": rating, "layer_curves": layer_rows,
            "layer_stats": layer_stats, "layer_monotonicity": round(monotonicity, 8),
            "turnover_annualized": round(turnover, 8), "top_minus_bottom_annualized": round(spread, 8),
            "decay": [{"horizon": h, "ic_mean": (block := _ic_summary_block(v))["mean"],
                       "icir": block["icir"], "p_value": block["p_value"], "n": block["n"],
                       "status": "EXPLORATORY", "note": "重叠持有期会降低有效样本量，p值为未校正探索值"} for h, v in decay_scores.items()],
            "regime": regime,
            "methodology": {"signal": "t日收盘", "execution": "t+1日开盘", "exit": "下一调仓信号日收盘",
                            "annualization": "有效持有交易日/252，不按固定21天折算",
                            "universe": "起点及之前60个交易日平均成交额代理(close*volume)", "universe_as_of": start.isoformat(),
                            "cost": "两腿等权权重变化(含漂移)累计/年数 × 单次完整换手摩擦；净价差=毛价差−成本",
                            "industry": "当前行业映射近似，缺历史分类；行业结果仅作敏感性诊断",
                            "limitations": ["仅包含已入库股票，仍有幸存者偏差", "财务缺原始公告日时采用法定披露期限近似，重述版本未复原", "分层年化价差不是多空组合的复利年化收益"]}}
