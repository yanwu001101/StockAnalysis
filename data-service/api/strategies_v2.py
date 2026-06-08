# -*- coding: utf-8 -*-
"""Strategy evaluation blueprint (v2) — uses the new 10-strategy registry.

GET /api/v2/stock/<code>/score
  Loads daily K + fundamentals + northbound + LHB from MySQL and runs every
  registered strategy. Falls back to the legacy `/api/stock/<code>/strategies`
  route shape so the frontend can switch with minimal changes.

POST /api/v2/screen
  Runs the 10-strategy composite across the spot universe, applies filters,
  returns the top-N. This replaces the legacy `score_multi_factor`-only path.
"""
from __future__ import annotations
import threading
import time
from typing import Optional

import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, request
from sqlalchemy import text

import cache
import db
from pipelines import spot as spot_pipe
from strategies import REGISTRY
from strategies.base import StrategyContext


bp = Blueprint("strategies_v2", __name__, url_prefix="/api/v2")


# ---------------------------------------------------------------------------
# Sector rank cache: industry -> (rank_pct, rank_n)
# Refreshed every 5 minutes from the spot snapshot.
# ---------------------------------------------------------------------------

_SECTOR_RANK: dict[str, tuple[float, int]] = {}
_SECTOR_TS: float = 0.0
_SECTOR_LOCK = threading.Lock()


def _refresh_sector_rank() -> None:
    global _SECTOR_RANK, _SECTOR_TS
    # pandas DataFrames don't support truthy/falsy `or`, so probe explicitly.
    df = cache.get("spot")
    if df is None or (hasattr(df, "empty") and df.empty):
        df = cache.get("spot_v2")
    if df is None or not hasattr(df, "columns") or (hasattr(df, "empty") and df.empty):
        return
    if "行业" not in df.columns and "industry" not in df.columns:
        return
    ind_col = "行业" if "行业" in df.columns else "industry"
    chg_col = "涨跌幅" if "涨跌幅" in df.columns else "pct_change"
    if chg_col not in df.columns:
        return
    try:
        d = df[[ind_col, chg_col]].copy()
        d = d[d[ind_col].astype(str).str.strip().replace("-", pd.NA).notna()]
        d[chg_col] = pd.to_numeric(d[chg_col], errors="coerce")
        d = d.dropna(subset=[chg_col])
        if d.empty:
            return
        avg = d.groupby(ind_col)[chg_col].mean().sort_values(ascending=False)
        total = len(avg)
        mapping: dict[str, tuple[float, int]] = {}
        for i, (name, _v) in enumerate(avg.items()):
            mapping[str(name)] = (i / total if total else 0.5, total)
        with _SECTOR_LOCK:
            _SECTOR_RANK = mapping
            _SECTOR_TS = time.time()
    except Exception:
        pass


def _sector_rank(industry: str) -> tuple[Optional[float], int]:
    if not industry:
        return None, 0
    if time.time() - _SECTOR_TS > 300 or not _SECTOR_RANK:
        _refresh_sector_rank()
    rk = _SECTOR_RANK.get(str(industry))
    if rk is None:
        return None, 0
    return rk


def _load_ctx(code: str) -> StrategyContext:
    ctx = StrategyContext(code=code)
    eng = db.get_engine()
    if eng is None:
        return ctx
    with eng.connect() as conn:
        dk = pd.read_sql(
            text(
                "SELECT trade_date, open, close, high, low, volume "
                "FROM stock_kline_daily WHERE code=:c "
                "ORDER BY trade_date DESC LIMIT 260"
            ), conn, params={"c": code},
        )
        if not dk.empty:
            dk = dk.sort_values("trade_date").rename(columns={
                "trade_date": "日期", "open": "开盘", "close": "收盘",
                "high": "最高", "low": "最低", "volume": "成交量",
            })
            ctx.daily_df = dk
        f = pd.read_sql(
            text("SELECT * FROM stock_fundamental WHERE code=:c "
                 "ORDER BY report_date DESC LIMIT 12"),
            conn, params={"c": code},
        )
        if not f.empty:
            ctx.fundamental_df = f
        nb = pd.read_sql(
            text("SELECT * FROM stock_northbound WHERE code=:c "
                 "ORDER BY trade_date DESC LIMIT 60"),
            conn, params={"c": code},
        )
        if not nb.empty:
            ctx.northbound_df = nb
        lhb = pd.read_sql(
            text("SELECT * FROM stock_lhb WHERE code=:c "
                 "AND trade_date >= (CURDATE() - INTERVAL 60 DAY)"),
            conn, params={"c": code},
        )
        if not lhb.empty:
            ctx.lhb_df = lhb
        mf = pd.read_sql(
            text("SELECT trade_date, super_large_net, large_net, medium_net, small_net, main_net "
                 "FROM stock_moneyflow WHERE code=:c "
                 "AND trade_date >= (CURDATE() - INTERVAL 60 DAY) "
                 "ORDER BY trade_date DESC"),
            conn, params={"c": code},
        )
        if not mf.empty:
            ctx.moneyflow_df = mf
        si = pd.read_sql(
            text("SELECT name, industry, latest_price, market_cap "
                 "FROM stock_info WHERE code=:c LIMIT 1"),
            conn, params={"c": code},
        )
        if not si.empty:
            row = si.iloc[0]
            ctx.name = str(row.get("name") or "")
            ctx.industry = str(row.get("industry") or "")
            try:
                ctx.price = float(row.get("latest_price") or 0)
                ctx.market_cap_yi = float(row.get("market_cap") or 0)
            except Exception:
                pass

    # Industry fallback from cached spot snapshot when stock_info is sparse.
    if not ctx.industry:
        df = cache.get("spot")
        if df is None or (hasattr(df, "empty") and df.empty):
            df = cache.get("spot_v2")
        if df is not None and hasattr(df, "columns"):
            code_col = "代码" if "代码" in df.columns else ("code" if "code" in df.columns else None)
            ind_col = "行业" if "行业" in df.columns else ("industry" if "industry" in df.columns else None)
            cap_col = ("总市值_亿" if "总市值_亿" in df.columns
                       else ("market_cap_yi" if "market_cap_yi" in df.columns else None))
            name_col = "名称" if "名称" in df.columns else ("name" if "name" in df.columns else None)
            if code_col and ind_col:
                try:
                    series_code = df[code_col].astype(str).str.zfill(6)
                    matched = df[series_code == code]
                    if not matched.empty:
                        ctx.industry = str(matched.iloc[0].get(ind_col) or "")
                        if name_col and not ctx.name:
                            ctx.name = str(matched.iloc[0].get(name_col) or "")
                        if cap_col and not ctx.market_cap_yi:
                            try:
                                ctx.market_cap_yi = float(matched.iloc[0].get(cap_col) or 0)
                            except Exception:
                                pass
                except Exception:
                    pass

    # Sector rank (cross-cutting, derived from cached spot)
    rk, n = _sector_rank(ctx.industry)
    if rk is not None:
        ctx.sector_rank = rk
        ctx.sector_rank_n = n
    return ctx


def _score_all(ctx: StrategyContext, weights: Optional[dict] = None,
               params: Optional[dict[str, dict]] = None) -> tuple[float, str, dict, list]:
    """Run every registered strategy. Optional `weights` (id -> float) overrides
    the per-class default_weight. Strategies with weight ≤ 0 are skipped.

    `params` is {strategy_id: {param_name: value}} — applied via cls.Params(**user_overrides).
    """
    out_list: list[dict] = []
    out_dict: dict = {}
    total = 0.0
    weight_sum = 0.0
    params = params or {}
    # Markers a strategy can put in details when it cannot meaningfully score.
    # Their weight contribution is dropped from the composite so missing data
    # doesn't drag the average down toward zero.
    NO_DATA_KEYS = ("no_data", "insufficient_data", "no_lhb", "no_rank")

    for cls in REGISTRY:
        w = cls.default_weight if weights is None else weights.get(cls.id, 0.0)
        if w <= 0:
            entry = {"id": cls.id, "name": cls.name, "score": 0.0,
                     "signal": "neutral", "weight": 0.0, "triggered": False,
                     "details": {"disabled": True}}
            out_list.append(entry)
            out_dict[cls.id] = entry
            continue
        try:
            override = params.get(cls.id) or {}
            user_params = cls.Params(**override) if override else None
            s = cls(params=user_params)
            res = s.score(ctx)
            has_no_data = any(res.details.get(k) for k in NO_DATA_KEYS)
            if not has_no_data:
                total += res.score * w
                weight_sum += w
            entry = {
                "id": cls.id, "name": cls.name,
                "score": round(float(res.score), 2), "signal": str(res.signal),
                "weight": float(w), "triggered": bool(res.triggered), "details": _json_safe(res.details),
                "no_data": has_no_data,
            }
            out_list.append(entry)
            out_dict[cls.id] = entry
        except Exception as e:
            err = {"id": cls.id, "name": cls.name, "score": 0,
                   "signal": "neutral", "error": str(e), "no_data": True}
            out_list.append(err)
            out_dict[cls.id] = err
    composite = (total / weight_sum) if weight_sum > 0 else 0.0
    # Relaxed thresholds vs the legacy 60/25 because (a) some valid strategies
    # never reach 60 by design (e.g. low_volatility caps at ~75), and (b) the
    # composite is averaging more dimensions now so the extreme tails are rarer.
    signal = "bullish" if composite >= 55 else "bearish" if composite <= 30 else "neutral"
    return round(composite, 2), signal, out_dict, out_list


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        return None if pd.isna(v) else v
    if pd.isna(value) if not isinstance(value, (str, bytes, bool, int, float, type(None))) else False:
        return None
    return value


def _parse_weights(body: dict) -> Optional[dict[str, float]]:
    """Front-end may send weights as either:
        strategies: {id: {enabled: bool, weight: number (0-100)}}
      or
        strategyConfig: same shape
      or
        weights: {id: float}
    Returns a normalized {id: weight_0_1} dict, or None for "use defaults".
    """
    raw = body.get("strategies") or body.get("strategyConfig") or body.get("weights")
    if not raw or not isinstance(raw, dict):
        return None
    out: dict[str, float] = {}
    for sid, v in raw.items():
        if isinstance(v, (int, float)):
            w = float(v)
        elif isinstance(v, dict):
            if v.get("enabled") is False:
                w = 0.0
            else:
                w = float(v.get("weight", 0) or 0)
        else:
            continue
        # Treat values > 1 as percentage 0-100 (front-end style)
        if w > 1.5:
            w = w / 100.0
        out[sid] = max(0.0, w)
    # If everything was disabled, fall back to defaults so the page isn't empty
    if not any(w > 0 for w in out.values()):
        return None
    return out


@bp.route("/stock/<code>/score", methods=["GET", "POST"])
def stock_score(code: str):
    ctx = _load_ctx(code)
    body = request.get_json(silent=True) or {}
    source = body if request.method == "POST" else request.args
    weights = _parse_weights(source)
    strategy_params = body.get("strategyParams") or body.get("strategy_params") or {} if request.method == "POST" else {}
    composite, signal, out_dict, out_list = _score_all(ctx, weights, strategy_params)

    # Aggregate stats for the front-end "看多 N/M 触发 K" indicator.
    effective = [it for it in out_list if not it.get("no_data") and not (it.get("details") or {}).get("disabled")]
    bullish_n = sum(1 for it in effective if it.get("signal") == "bullish")
    bearish_n = sum(1 for it in effective if it.get("signal") == "bearish")
    triggered_n = sum(1 for it in effective if it.get("triggered"))

    return jsonify({
        "code": code,
        "name": ctx.name,
        "price": ctx.price,
        "total": composite,
        "composite_score": composite,
        "composite_signal": signal,
        "strategies": out_dict,
        "strategies_list": out_list,
        "aggregate": {
            "effective": len(effective),
            "total_strategies": len(out_list),
            "bullish": bullish_n,
            "bearish": bearish_n,
            "neutral": len(effective) - bullish_n - bearish_n,
            "triggered": triggered_n,
        },
        "industry": ctx.industry,
        "signal": signal,
    })


@bp.route("/screen", methods=["POST"])
def screen():
    """10-strategy composite screener.

    body: {
      limit?: int,
      filters?: {minScore?, minRoe?, maxDebtRatio?, minMarketCap?, industries?},
      strategies?: {id: {enabled, weight}} | {id: float}  # user-defined weights
    }
    """
    body = request.get_json(silent=True) or {}
    limit = int(body.get("limit") or 50)
    filters = body.get("filters") or {}
    min_score = float(filters.get("minScore", 50))
    min_market_cap_yi = float(filters.get("minMarketCap", 100))   # 亿
    industries: list = filters.get("industries") or []
    weights = _parse_weights(body)
    strategy_params = body.get("strategyParams") or body.get("strategy_params") or {}
    # Caller-controlled universe size. Default 200 keeps legacy callers fast;
    # set 0 / very large to scan the entire spot snapshot (~5000 codes, ~3 min).
    top_universe = body.get("topUniverse") or body.get("top_universe")
    try:
        top_universe = int(top_universe) if top_universe is not None else 200
    except (TypeError, ValueError):
        top_universe = 200
    if top_universe <= 0:
        top_universe = 10_000  # effectively "all"
    require_triggered: list = (
        body.get("requireTriggered") or body.get("require_triggered") or []
    )
    require_triggered = [str(x) for x in require_triggered if x]

    # Universe: top by market cap from cached spot, capped at 200 codes so we
    # don't run 5000 strategy evaluations on every request.
    spot_df = spot_pipe.get_cached()
    if spot_df is None or spot_df.empty:
        # Fall back to legacy cache shape
        spot_df = cache.get("spot")
    if spot_df is None or spot_df.empty:
        # Bootstrap on cold cache — see expression.py _load_universe for context.
        try:
            from app import fetch_spot
            spot_df = fetch_spot()
        except Exception:
            spot_df = None
    if spot_df is None or spot_df.empty:
        return jsonify([])

    df = spot_df.copy()
    cap_col = "market_cap_yi" if "market_cap_yi" in df.columns else (
        "总市值_亿" if "总市值_亿" in df.columns else None)
    code_col = "code" if "code" in df.columns else "代码"
    name_col = "name" if "name" in df.columns else "名称"
    ind_col = "industry" if "industry" in df.columns else "行业"
    price_col = "price" if "price" in df.columns else "最新价"
    chg_col = "pct_change" if "pct_change" in df.columns else "涨跌幅"

    if cap_col:
        df = df[pd.to_numeric(df[cap_col], errors="coerce") >= min_market_cap_yi]
    if industries and ind_col in df.columns:
        df = df[df[ind_col].astype(str).isin(industries)]
    if cap_col:
        df = df.sort_values(cap_col, ascending=False, na_position="last")
    universe = df.head(top_universe)

    results: list[dict] = []
    for _, row in universe.iterrows():
        code = str(row[code_col]).zfill(6)
        ctx = _load_ctx(code)
        # Inject quote fields the loader doesn't fetch
        try:
            if not ctx.industry and ind_col in row.index:
                ctx.industry = str(row[ind_col] or "")
            if not ctx.market_cap_yi and cap_col:
                ctx.market_cap_yi = float(row[cap_col] or 0)
        except Exception:
            pass
        composite, signal, _, out_list = _score_all(ctx, weights, strategy_params)
        if composite < min_score:
            continue
        triggered_map = {it["id"]: bool(it.get("triggered")) for it in out_list}
        if require_triggered and not all(triggered_map.get(sid) for sid in require_triggered):
            continue
        effective = [it for it in out_list if not it.get("no_data") and not (it.get("details") or {}).get("disabled")]
        bullish_count = sum(1 for it in effective if it.get("signal") == "bullish")
        bearish_count = sum(1 for it in effective if it.get("signal") == "bearish")
        triggered_count = sum(1 for it in effective if it.get("triggered"))
        results.append({
            "code": code,
            "name": str(row.get(name_col) or ctx.name or ""),
            "industry": str(row.get(ind_col) or ctx.industry or ""),
            "price": round(float(row.get(price_col) or 0), 2),
            "changePercent": round(float(row.get(chg_col) or 0), 2),
            "marketCap": round(ctx.market_cap_yi, 0),
            "compositeScore": composite,
            "signal": signal,
            "strategies": {it["id"]: it["score"] for it in out_list},
            "triggered": triggered_map,
            "strategyStats": {
                "effective": len(effective),
                "total": len(out_list),
                "bullish": bullish_count,
                "bearish": bearish_count,
                "triggered": triggered_count,
            },
        })

    results.sort(key=lambda x: x["compositeScore"], reverse=True)
    return jsonify(results[:limit])


@bp.route("/strategy-tops")
def strategy_tops():
    """Return top-N codes for every strategy from the pre-computed table.

    Query: ?limit=N (default 10)
    Response: {
      "strategies": [
        {"id": "piotroski_f", "name": "...", "rows": [
            {"code", "name", "industry", "price", "changePercent", "score", "signal", "triggered"}
        ]},
        ...
      ],
      "computed_at": "...",
      "row_count": int
    }

    Uses cached spot snapshot to enrich each row with name/industry/price.
    Falls back to live computation if the pre-score table is empty.
    """
    from repo import strategy_score_repo
    from strategies import REGISTRY

    limit = int(request.args.get("limit", 10))
    limit = max(1, min(limit, 50))

    tops = strategy_score_repo.top_n_all(limit)

    # Build code → quote map from cached spot for enrichment
    meta: dict[str, dict] = {}
    spot = cache.get("spot")
    if spot is not None and hasattr(spot, "columns") and "代码" in spot.columns:
        for _, r in spot.iterrows():
            c = str(r.get("代码", "")).zfill(6)
            if c:
                meta[c] = {
                    "name": str(r.get("名称", "")),
                    "industry": str(r.get("行业", "")),
                    "price": float(r.get("最新价") or 0),
                    "changePercent": float(r.get("涨跌幅") or 0),
                }

    by_strat: dict[str, list[dict]] = {cls.id: [] for cls in REGISTRY}
    if not tops.empty:
        # Sorted within partition already (ROW_NUMBER ORDER BY score DESC)
        for _, r in tops.iterrows():
            sid = str(r["strategy_id"])
            if sid not in by_strat:
                continue
            code = str(r["code"]).zfill(6)
            m = meta.get(code) or {}
            by_strat[sid].append({
                "code": code,
                "name": m.get("name", ""),
                "industry": m.get("industry", ""),
                "price": round(m.get("price", 0), 2),
                "changePercent": round(m.get("changePercent", 0), 2),
                "score": float(r["score"]),
                "signal": r.get("signal_type") or "neutral",
                "triggered": bool(r.get("triggered")),
            })

    strategies_out = []
    for cls in REGISTRY:
        strategies_out.append({
            "id": cls.id,
            "name": cls.name,
            "rows": by_strat.get(cls.id, []),
        })

    computed_at = strategy_score_repo.latest_computed_at()
    return jsonify({
        "strategies": strategies_out,
        "computed_at": computed_at.isoformat() if computed_at else None,
        "row_count": strategy_score_repo.row_count(),
    })


@bp.route("/strategies")
def list_v2():
    from strategies import list_meta
    return jsonify(list_meta())


@bp.route("/stock/<code>/prediction")
def stock_prediction(code: str):
    """Multi-signal up/down probability prediction for a single stock.

    Returns probability_up, probability_down, confidence, per-dimension
    breakdown, key drivers, and risk warnings.
    """
    code = str(code).zfill(6)
    ctx = _load_ctx(code)
    from predictor import predict
    result = predict(ctx)
    # Serialize dimensions
    dims = []
    for d in result.dimensions:
        dims.append({
            "name": d.name,
            "nameEn": d.name_en,
            "score": round(d.score, 4),
            "weight": d.weight,
            "detail": d.detail,
            "subSignals": d.sub_signals,
        })
    return jsonify({
        "code": result.code,
        "name": result.name,
        "price": result.price,
        "probabilityUp": result.probability_up,
        "probabilityDown": result.probability_down,
        "confidence": result.confidence,
        "signal": result.signal,
        "signalLabel": result.signal_label,
        "compositeDirection": result.composite_direction,
        "dimensions": dims,
        "keyDrivers": result.key_drivers,
        "riskWarnings": result.risk_warnings,
        "timeHorizon": result.time_horizon,
    })


@bp.route("/stock/<code>/pro-signal")
def stock_pro_signal(code: str):
    """Pro-grade leading-indicator short-term direction signal.

    Designed to be low-lag — uses Heikin-Ashi, DEMA/TEMA, TSI, VWAP deviation,
    Volume Profile POC, CMF, order-flow proxy, short EMA cross, and 5-day
    breadth. Returns a probability + key dimensions for the front-end pro page.
    """
    code = str(code).zfill(6)
    ctx = _load_ctx(code)
    from pro_signal import pro_signal as _pro
    result = _pro(ctx)
    dims = [{
        "name": d.name, "nameEn": d.name_en,
        "score": round(d.score, 4), "weight": d.weight,
        "detail": d.detail, "value": d.value,
    } for d in result.dimensions]
    return jsonify({
        "code": result.code,
        "name": result.name,
        "price": result.price,
        "probabilityUp": result.probability_up,
        "probabilityDown": result.probability_down,
        "confidence": result.confidence,
        "direction": result.direction,
        "label": result.label,
        "composite": result.composite,
        "dimensions": dims,
        "keySignals": result.key_signals,
        "risks": result.risks,
        "horizon": result.horizon,
    })
