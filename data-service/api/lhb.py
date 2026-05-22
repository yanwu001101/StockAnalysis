# -*- coding: utf-8 -*-
"""Dragon-Tiger Board (龙虎榜) blueprint."""
from __future__ import annotations
import datetime as dt

from flask import Blueprint, jsonify, request
from sqlalchemy import text

import cache
import db


bp = Blueprint("lhb_v2", __name__, url_prefix="/api/lhb")


def _meta_map() -> dict[str, dict]:
    """code -> {name, industry} pulled from the spot cache (live names) and
    fallback merged with stock_info via DB."""
    out: dict[str, dict] = {}
    df = cache.get("spot")
    if df is not None and hasattr(df, "columns") and "代码" in df.columns:
        for _, r in df.iterrows():
            c = str(r.get("代码", "")).zfill(6)
            if not c:
                continue
            out[c] = {
                "name": str(r.get("名称", "")),
                "industry": str(r.get("行业", "")),
            }
    return out


def _enrich(rows: list[dict]) -> list[dict]:
    meta = _meta_map()
    for r in rows:
        if not r.get("name") and r.get("code") in meta:
            r["name"] = meta[r["code"]]["name"]
        if not r.get("industry") and r.get("code") in meta:
            r["industry"] = meta[r["code"]]["industry"]
    return rows


def _date_arg(name: str, default: dt.date) -> dt.date:
    v = request.args.get(name)
    if not v:
        return default
    try:
        return dt.date.fromisoformat(v[:10])
    except Exception:
        return default


@bp.route("/recent")
def recent():
    """Most recent LHB rows (per-seat). Filter by days + optional code."""
    days = int(request.args.get("days", 30))
    code = request.args.get("code")
    eng = db.get_engine()
    if eng is None:
        return jsonify([])
    sql = (
        "SELECT code, trade_date, reason, buy_amount, sell_amount, net_amount, "
        "seat_type, seat_name "
        "FROM stock_lhb "
        "WHERE trade_date >= (CURDATE() - INTERVAL :d DAY) "
    )
    params = {"d": days}
    if code:
        sql += "AND code = :c "
        params["c"] = str(code).zfill(6)
    sql += "ORDER BY trade_date DESC, ABS(net_amount) DESC LIMIT 3000"
    with eng.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
    meta = _meta_map()
    out = []
    for r in rows:
        c = r[0]
        out.append({
            "code": c,
            "name": meta.get(c, {}).get("name", ""),
            "industry": meta.get(c, {}).get("industry", ""),
            "tradeDate": r[1].isoformat() if r[1] else None,
            "reason": r[2] or "",
            "buyAmount": float(r[3]) if r[3] is not None else None,
            "sellAmount": float(r[4]) if r[4] is not None else None,
            "netAmount": float(r[5]) if r[5] is not None else None,
            "seatType": r[6] or "",
            "seatName": r[7] or "",
        })
    return jsonify(out)


@bp.route("/institution-rank")
def institution_rank():
    """Highest net-buy stocks by institutional seats (机构专用) in the LHB window."""
    days = int(request.args.get("days", 30))
    eng = db.get_engine()
    if eng is None:
        return jsonify([])
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT l.code, COUNT(*) AS appearances, "
            "  SUM(l.net_amount) AS net_sum, "
            "  SUM(l.buy_amount) AS buy_sum, "
            "  SUM(l.sell_amount) AS sell_sum, "
            "  MAX(l.trade_date) AS last_seen, "
            "  COALESCE(si.name, '') AS name, "
            "  COALESCE(si.industry, '') AS industry "
            "FROM stock_lhb l "
            "LEFT JOIN stock_info si ON si.code = l.code "
            "WHERE l.trade_date >= (CURDATE() - INTERVAL :d DAY) "
            "AND l.net_amount IS NOT NULL "
            "AND l.seat_type = '机构' "
            "GROUP BY l.code "
            "ORDER BY net_sum DESC LIMIT 50"
        ), {"d": days}).fetchall()
    out = []
    for r in rows:
        out.append({
            "code": r[0],
            "appearances": int(r[1] or 0),
            "netSum": float(r[2] or 0),
            "buySum": float(r[3] or 0),
            "sellSum": float(r[4] or 0),
            "lastSeen": r[5].isoformat() if r[5] else None,
            "name": r[6] or "",
            "industry": r[7] or "",
        })
    return jsonify(_enrich(out))


@bp.route("/stock-rank")
def stock_rank():
    """Stocks that appeared on LHB most often in the window."""
    days = int(request.args.get("days", 30))
    eng = db.get_engine()
    if eng is None:
        return jsonify([])
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT l.code, "
            "  COUNT(DISTINCT l.trade_date) AS appearances, "
            "  SUM(l.net_amount) AS net_sum, "
            "  GROUP_CONCAT(DISTINCT l.reason SEPARATOR ' | ') AS reasons, "
            "  MAX(l.trade_date) AS last_seen, "
            "  COALESCE(si.name, '') AS name, "
            "  COALESCE(si.industry, '') AS industry "
            "FROM stock_lhb l "
            "LEFT JOIN stock_info si ON si.code = l.code "
            "WHERE l.trade_date >= (CURDATE() - INTERVAL :d DAY) "
            "GROUP BY l.code "
            "ORDER BY appearances DESC, net_sum DESC LIMIT 50"
        ), {"d": days}).fetchall()
    out = []
    for r in rows:
        out.append({
            "code": r[0],
            "appearances": int(r[1] or 0),
            "netSum": float(r[2] or 0),
            "reasons": r[3] or "",
            "lastSeen": r[4].isoformat() if r[4] else None,
            "name": r[5] or "",
            "industry": r[6] or "",
        })
    return jsonify(_enrich(out))
