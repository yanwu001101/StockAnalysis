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
            total += res.score * w
            weight_sum += w
            entry = {
                "id": cls.id, "name": cls.name,
                "score": round(res.score, 2), "signal": res.signal,
                "weight": w, "triggered": res.triggered, "details": res.details,
            }
            out_list.append(entry)
            out_dict[cls.id] = entry
        except Exception as e:
            err = {"id": cls.id, "name": cls.name, "score": 0,
                   "signal": "neutral", "error": str(e)}
            out_list.append(err)
            out_dict[cls.id] = err
    composite = (total / weight_sum) if weight_sum > 0 else 0.0
    signal = "bullish" if composite >= 60 else "bearish" if composite <= 25 else "neutral"
    return round(composite, 2), signal, out_dict, out_list


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


@bp.route("/stock/<code>/score")
def stock_score(code: str):
    code = str(code).zfill(6)
    ctx = _load_ctx(code)
    weights = _parse_weights(request.args.to_dict()) if request.args else None
    composite, signal, out_dict, out_list = _score_all(ctx, weights)
    return jsonify({
        # Legacy-compatible fields (front-end CompositeScore type)
        "total": composite,
        "signal": signal,
        "strategies": out_dict,
        # Extended fields for richer UI
        "code": code,
        "name": ctx.name,
        "industry": ctx.industry,
        "composite_score": composite,
        "composite_signal": signal,
        "strategies_list": out_list,
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

    # Universe: top by market cap from cached spot, capped at 200 codes so we
    # don't run 5000 strategy evaluations on every request.
    spot_df = spot_pipe.get_cached()
    if spot_df is None or spot_df.empty:
        # Fall back to legacy cache shape
        spot_df = cache.get("spot")
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
    universe = df.head(200)

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
        })

    results.sort(key=lambda x: x["compositeScore"], reverse=True)
    return jsonify(results[:limit])


@bp.route("/strategies")
def list_v2():
    from strategies import list_meta
    return jsonify(list_meta())
