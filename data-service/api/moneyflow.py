# -*- coding: utf-8 -*-
"""Money flow blueprint (main funds / northbound / industry rotation)."""
from __future__ import annotations
from typing import Optional

from flask import Blueprint, jsonify, request
from sqlalchemy import text

import cache
import db


bp = Blueprint("moneyflow_v2", __name__, url_prefix="/api/moneyflow")


def _meta_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    df = cache.get("spot")
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
    return out


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
    # Use first/last hold_shares diff over the window to capture accumulation.
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT t.code, t.shares_diff, t.last_shares, t.last_ratio, t.first_date, t.last_date "
            "FROM ("
            "  SELECT code,"
            "    MAX(trade_date) AS last_date, MIN(trade_date) AS first_date,"
            "    MAX(CASE WHEN trade_date = m.maxd THEN hold_shares END) AS last_shares,"
            "    MAX(CASE WHEN trade_date = m.maxd THEN hold_ratio END) AS last_ratio,"
            "    MAX(CASE WHEN trade_date = m.maxd THEN hold_shares END) -"
            "      MAX(CASE WHEN trade_date = m.mind THEN hold_shares END) AS shares_diff"
            "  FROM stock_northbound n,"
            "       (SELECT MIN(trade_date) AS mind, MAX(trade_date) AS maxd"
            "        FROM stock_northbound"
            "        WHERE trade_date >= (CURDATE() - INTERVAL :d DAY)) m"
            "  WHERE trade_date IN (m.mind, m.maxd)"
            "  GROUP BY code"
            ") t "
            "WHERE t.shares_diff IS NOT NULL "
            "ORDER BY t.shares_diff DESC LIMIT :n"
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
            "sharesDiff": int(r[1] or 0),
            "currentShares": int(r[2] or 0),
            "currentRatio": float(r[3] or 0),
            "firstDate": r[4].isoformat() if r[4] else None,
            "lastDate": r[5].isoformat() if r[5] else None,
        })
    return jsonify(out)


@bp.route("/sector")
def sector_flow():
    """Industry-level rotation: avg pct_change + count of stocks per industry,
    sourced from the spot cache (same data the dashboard uses)."""
    df = cache.get("spot")
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
