# -*- coding: utf-8 -*-
"""Paper trading Flask blueprint.

GET  /api/paper        — 账户概览：净值曲线(含基准)、绩效、持仓、近期交易
POST /api/paper/reset  — 重置账户 {initial_capital, top_n}
POST /api/paper/run    — 手动触发一次当日流程（调试用）
"""
from __future__ import annotations
import datetime as dt

import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, request
from sqlalchemy import text

from backtest.metrics import compute
from jobs import paper_trade
from repo import paper_repo, index_kline_repo

bp = Blueprint("paper", __name__, url_prefix="/api/paper")


def _pd_series(rows: list[dict], col: str) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(
        [float(r[col]) if r.get(col) is not None else np.nan for r in rows],
        index=pd.to_datetime([r["trade_date"] for r in rows]),
    ).dropna()
    return s.sort_index()


@bp.route("", methods=["GET"])
def overview():
    acc = paper_repo.get_account()
    if not acc:
        return jsonify({"status": "not-started"})
    curve = paper_repo.get_equity_curve()
    equity = _pd_series(curve, "equity")
    bench_raw = _pd_series(curve, "benchmark_close")

    bench_aligned = None
    if len(equity) >= 2 and len(bench_raw) >= 2:
        bench = bench_raw.reindex(equity.index).ffill()
        base = bench.iloc[0]
        if base and not pd.isna(base):
            bench_aligned = bench / base * float(equity.iloc[0])

    metrics = compute(equity, benchmark=bench_aligned)
    positions = paper_repo.get_positions()

    # 持仓现价/市值
    eng = None
    from repo import base as _b
    eng = _b.engine()
    enriched = []
    if positions and eng is not None:
        codes = [p["code"] for p in positions]
        in_list = ",".join(f"'{c}'" for c in codes)
        with eng.connect() as conn:
            df = pd.read_sql(text(
                f"SELECT code, close FROM stock_kline_daily WHERE code IN ({in_list}) "
                f"AND trade_date = (SELECT MAX(trade_date) FROM stock_kline_daily)"
            ), conn)
        price_map = {str(r["code"]).zfill(6): float(r["close"])
                     for _, r in df.iterrows() if pd.notna(r["close"])}
        total_mv = sum(p["shares"] * price_map.get(p["code"], p["avg_cost"]) for p in positions) or 1.0
        for p in positions:
            code = p["code"]
            last = price_map.get(code, float(p["avg_cost"]))
            mv = p["shares"] * last
            enriched.append({
                "code": code,
                "shares": round(p["shares"], 2),
                "avg_cost": round(float(p["avg_cost"]), 3),
                "last_close": round(last, 3),
                "market_value": round(mv, 2),
                "weight": round(mv / total_mv * 100, 1),
                "pnl_pct": round((last / float(p["avg_cost"]) - 1) * 100, 2),
                "buy_date": str(p.get("buy_date") or ""),
            })
        enriched.sort(key=lambda x: x["market_value"], reverse=True)

    total_costs = 0.0
    trades = paper_repo.get_trades(100)
    for t in paper_repo.get_trades(10000):
        total_costs += float(t.get("cost") or 0)

    return jsonify({
        "account": {
            "initial_capital": float(acc["initial_capital"]),
            "top_n": int(acc["top_n"]),
            "rebalance": acc.get("rebalance"),
            "cash": float(acc["cash"]),
            "start_date": str(curve[0]["trade_date"]) if curve else None,
        },
        "metrics": metrics.as_dict(),
        "total_costs": round(total_costs, 2),
        "equity_curve": [
            {"date": str(r["trade_date"]),
             "equity": round(float(r["equity"]), 2) if r["equity"] is not None else None,
             "benchmark": (round(float(r["benchmark_close"]) / float(curve[0]["benchmark_close"])
                                 * float(curve[0]["equity"]), 2)
                           if r["benchmark_close"] and curve[0]["benchmark_close"] else None)}
            for r in curve
        ],
        "positions": enriched,
        "recent_trades": trades,
    })


@bp.route("/reset", methods=["POST"])
def reset():
    body = request.get_json(force=True, silent=True) or {}
    capital = float(body.get("initial_capital") or body.get("initialCapital") or 1_000_000)
    top_n = int(body.get("top_n") or body.get("topN") or 10)
    paper_repo.reset_account(capital, top_n)
    return jsonify({"status": "reset", "initial_capital": capital, "top_n": top_n})


@bp.route("/run", methods=["POST"])
def run_now():
    body = request.get_json(force=True, silent=True) or {}
    d = body.get("date")
    result = paper_trade.run(dt.date.fromisoformat(d) if d else dt.date.today())
    status = 500 if "error" in result else 200
    return jsonify(result), status
