# -*- coding: utf-8 -*-
"""Money flow blueprint (main funds / northbound / industry rotation)."""
from __future__ import annotations
import time
from typing import Optional

from flask import Blueprint, jsonify, request
from sqlalchemy import text

import cache
import db


bp = Blueprint("moneyflow_v2", __name__, url_prefix="/api/moneyflow")


_META_CACHE: tuple[dict[str, dict], float] | None = None
_META_TTL = 30.0


def _meta_map() -> dict[str, dict]:
    global _META_CACHE
    now = time.time()
    if _META_CACHE is not None and now - _META_CACHE[1] < _META_TTL:
        return _META_CACHE[0]
    out: dict[str, dict] = {}
    df = cache.get("spot")
    if df is None or not hasattr(df, "columns"):
        # Bootstrap on cold cache so the very first request after a worker /
        # Redis restart still gets name/industry/price filled.
        try:
            from app import fetch_spot
            df = fetch_spot()
        except Exception:
            df = None
    if df is not None and hasattr(df, "columns") and "代码" in df.columns:
        for _, r in df.iterrows():
            c = str(r.get("代码", "")).zfill(6)
            if c:
                out[c] = {
                    "name": str(r.get("名称", "")),
                    "industry": str(r.get("行业", "")),
                    "price": float(r.get("最新价") or 0),
                    "changePercent": float(r.get("涨跌幅") or 0),
                }
    # Only memoize when we actually got rows; otherwise let the next request
    # retry the fetch instead of latching in an empty meta-map for 30s.
    if out:
        _META_CACHE = (out, now)
    return out


def _top_codes(limit: int = 120) -> list[str]:
    meta = _meta_map()
    if meta:
        return list(meta.keys())[:limit]
    eng = db.get_engine()
    if eng is None:
        return []
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT code FROM stock_info "
            "WHERE code IS NOT NULL ORDER BY market_cap DESC LIMIT :n"
        ), {"n": limit}).fetchall()
    return [str(r[0]).zfill(6) for r in rows]


def _latest_date(table: str):
    eng = db.get_engine()
    if eng is None:
        return None
    with eng.connect() as conn:
        row = conn.execute(text(f"SELECT MAX(trade_date) FROM {table}")).fetchone()
    return row[0] if row else None


def _needs_refresh(table: str, max_age_days: int) -> bool:
    import datetime as dt
    latest = _latest_date(table)
    if latest is None:
        return True
    if hasattr(latest, "date"):
        latest = latest.date()
    return (dt.date.today() - latest).days > max_age_days


def _warm_moneyflow(days: int, limit: int) -> None:
    if not _needs_refresh("stock_moneyflow", max(2, days)):
        return
    try:
        import asyncio
        from pipelines import moneyflow as mf_pipe
        codes = _top_codes(limit)
        if codes:
            asyncio.run(mf_pipe.run_batch(codes, days=max(days, 10)))
    except Exception as e:
        print(f"[moneyflow] warm moneyflow failed: {e}")


def _warm_northbound(days: int, limit: int) -> None:
    if not _needs_refresh("stock_northbound", max(7, days * 2)):
        return
    try:
        import asyncio
        from pipelines import northbound as nb_pipe
        codes = _top_codes(limit)
        if codes:
            asyncio.run(nb_pipe.run_batch(codes, days=max(days, 30)))
    except Exception as e:
        print(f"[moneyflow] warm northbound failed: {e}")


@bp.route("/main-rank")
def main_rank():
    """Rank by main_net (主力净额) accumulated over the window.

    direction=inflow → top inflow, direction=outflow → top outflow.
    """
    days = int(request.args.get("days", 5))
    limit = int(request.args.get("limit", 50))
    direction = request.args.get("direction", "inflow")
    eng = db.get_engine()
    if eng is None:
        return jsonify([])
    _warm_moneyflow(days, min(max(limit * 4, 80), 240))
    order = "DESC" if direction == "inflow" else "ASC"
    with eng.connect() as conn:
        rows = conn.execute(text(
            f"SELECT code, SUM(main_net) AS net_sum, "
            f"  SUM(super_large_net) AS sl_sum, "
            f"  SUM(large_net) AS l_sum, "
            f"  COUNT(*) AS d_count "
            f"FROM stock_moneyflow "
            f"WHERE trade_date >= (CURDATE() - INTERVAL :d DAY) "
            f"AND main_net IS NOT NULL "
            f"GROUP BY code "
            f"ORDER BY net_sum {order} LIMIT :n"
        ), {"d": days, "n": limit}).fetchall()
    meta = _meta_map()
    out = []
    for r in rows:
        c = r[0]
        m = meta.get(c, {})
        out.append({
            "code": c,
            "name": m.get("name", ""),
            "industry": m.get("industry", ""),
            "price": m.get("price", 0),
            "changePercent": round(m.get("changePercent", 0), 2),
            "mainNetSum": float(r[1] or 0),
            "superLargeSum": float(r[2] or 0),
            "largeSum": float(r[3] or 0),
            "days": int(r[4] or 0),
        })
    return jsonify(out)


@bp.route("/northbound-rank")
def northbound_rank():
    """Top northbound (Stock Connect) accumulation in the window."""
    days = int(request.args.get("days", 5))
    limit = int(request.args.get("limit", 50))
    eng = db.get_engine()
    if eng is None:
        return jsonify([])
    _warm_northbound(days, min(max(limit * 4, 80), 240))
    # Two simple JOINs against the per-code first/last trade_date pair —
    # avoids the implicit cross-join + CASE-WHEN MAX trick which is opaque
    # to the optimiser and forces a full scan.
    query = (
            "SELECT t1.code, "
            "  (t1.hold_shares - t0.hold_shares) AS shares_diff, "
            "  t1.hold_shares AS last_shares, "
            "  t1.hold_ratio AS last_ratio, "
            "  t0.trade_date AS first_date, "
            "  t1.trade_date AS last_date "
            "FROM ("
            "  SELECT code, MIN(trade_date) AS mind, MAX(trade_date) AS maxd "
            "  FROM stock_northbound "
            "  WHERE trade_date >= (CURDATE() - INTERVAL :d DAY) "
            "  GROUP BY code "
            ") m "
            "JOIN stock_northbound t0 ON t0.code = m.code AND t0.trade_date = m.mind "
            "JOIN stock_northbound t1 ON t1.code = m.code AND t1.trade_date = m.maxd "
            "WHERE t0.hold_shares IS NOT NULL AND t1.hold_shares IS NOT NULL "
            "ORDER BY shares_diff DESC LIMIT :n"
    )
    with eng.connect() as conn:
        rows = conn.execute(text(query), {"d": days, "n": limit}).fetchall()
        stale = False
        if not rows:
            latest = conn.execute(text("SELECT MAX(trade_date) FROM stock_northbound")).scalar()
            if latest:
                stale = True
                rows = conn.execute(text(query.replace(
                    "trade_date >= (CURDATE() - INTERVAL :d DAY)",
                    "trade_date >= (:latest - INTERVAL :d DAY) AND trade_date <= :latest"
                )), {"d": days, "n": limit, "latest": latest}).fetchall()
    meta = _meta_map()
    out = []
    for r in rows:
        c = r[0]
        m = meta.get(c, {})
        out.append({
            "code": c,
            "name": m.get("name", ""),
            "industry": m.get("industry", ""),
            "price": m.get("price", 0),
            "changePercent": round(m.get("changePercent", 0), 2),
            "sharesDiff": int(r[1] or 0),
            "currentShares": int(r[2] or 0),
            "currentRatio": float(r[3] or 0),
            "firstDate": r[4].isoformat() if r[4] else None,
            "lastDate": r[5].isoformat() if r[5] else None,
            "stale": stale,
        })
    return jsonify(out)


@bp.route("/sector")
def sector_flow():
    """Industry-level rotation: avg pct_change + count of stocks per industry,
    sourced from the spot cache (same data the dashboard uses)."""
    df = cache.get("spot")
    if df is None or not hasattr(df, "columns"):
        try:
            from app import fetch_spot
            df = fetch_spot()
        except Exception:
            df = None
        if df is None or not hasattr(df, "columns"):
            return jsonify([])
    ind_col = "行业" if "行业" in df.columns else None
    chg_col = "涨跌幅" if "涨跌幅" in df.columns else None
    if not ind_col or not chg_col:
        return jsonify([])
    import pandas as pd
    d = df[[ind_col, chg_col, "代码", "成交额"]].copy() if "成交额" in df.columns else df[[ind_col, chg_col, "代码"]].copy()
    d = d[d[ind_col].astype(str).str.strip().replace("-", pd.NA).notna()]
    d[chg_col] = pd.to_numeric(d[chg_col], errors="coerce")
    if "成交额" in d.columns:
        d["成交额"] = pd.to_numeric(d["成交额"], errors="coerce").fillna(0)
    d = d.dropna(subset=[chg_col])
    if d.empty:
        return jsonify([])
    agg_dict = {"avgChange": (chg_col, "mean"), "count": ("代码", "count")}
    if "成交额" in d.columns:
        agg_dict["amount"] = ("成交额", "sum")
    grouped = d.groupby(ind_col).agg(**agg_dict).reset_index().rename(columns={ind_col: "name"})
    grouped = grouped.sort_values("avgChange", ascending=False).reset_index(drop=True)
    out = []
    for i, row in grouped.iterrows():
        out.append({
            "rank": int(i) + 1,
            "name": str(row["name"]),
            "avgChange": round(float(row["avgChange"]), 2),
            "count": int(row["count"]),
            "amount": round(float(row.get("amount", 0)) / 1e8, 2),  # 亿
        })
    return jsonify(out)


@bp.route("/stock/<code>")
def stock_flow(code: str):
    """Per-stock multi-period money flow series."""
    days = int(request.args.get("days", 60))
    eng = db.get_engine()
    if eng is None:
        return jsonify([])
    code = str(code).zfill(6)
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT trade_date, super_large_net, large_net, medium_net, small_net, main_net "
            "FROM stock_moneyflow WHERE code=:c "
            "AND trade_date >= (CURDATE() - INTERVAL :d DAY) "
            "ORDER BY trade_date ASC"
        ), {"c": code, "d": days}).fetchall()
    out = []
    for r in rows:
        out.append({
            "date": r[0].isoformat() if r[0] else None,
            "superLargeNet": float(r[1] or 0),
            "largeNet": float(r[2] or 0),
            "mediumNet": float(r[3] or 0),
            "smallNet": float(r[4] or 0),
            "mainNet": float(r[5] or 0),
        })
    return jsonify(out)
