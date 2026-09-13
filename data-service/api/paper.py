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


# ---------------------------------------------------------------------------
# 实盘半自动 · 里程碑 1：委托单生成器（只生成清单，绝不自动下单）
#
# 数据源 = 最近一个调仓日的 paper_trades。模拟盘以当日收盘价（含滑点）纸面
# 成交，这组买卖变动即目标持仓与当前实盘的差值 —— 人工在券商执行后自行
# 勾选标记。执行/回填状态只存前端 localStorage，服务端不感知。
# ---------------------------------------------------------------------------

_SIDES = {"buy": "买入", "sell": "卖出"}


def _latest_trade_date(conn, before: str | None):
    if before:
        row = conn.execute(text(
            "SELECT MAX(trade_date) FROM paper_trades "
            "WHERE account_id = :i AND trade_date <= :d"),
            {"i": paper_repo.ACCOUNT_ID, "d": before}).fetchone()
    else:
        row = conn.execute(text(
            "SELECT MAX(trade_date) FROM paper_trades WHERE account_id = :i"),
            {"i": paper_repo.ACCOUNT_ID}).fetchone()
    return None if not row or row[0] is None else str(row[0])


@bp.route("/orders", methods=["GET"])
def orders():
    """GET /api/paper/orders?date=YYYY-MM-DD — 最近一个(或指定日之前最近的)
    调仓日的委托清单 + 目标持仓。安全红线：本接口只读，不触发任何交易。"""
    d = request.args.get("date") or None
    eng = paper_repo.base.engine()
    if eng is None:
        return jsonify({"status": "no-db", "orders": [], "target_positions": []}), 200
    with eng.connect() as conn:
        trade_date = _latest_trade_date(conn, d)
        if not trade_date:
            return jsonify({"status": "no-trades", "trade_date": None,
                            "orders": [], "target_positions": []})
        trades = pd.read_sql(text(
            "SELECT code, side, shares, price, amount, cost, reason "
            "FROM paper_trades WHERE account_id = :i AND trade_date = :d "
            "ORDER BY id"),
            conn, params={"i": paper_repo.ACCOUNT_ID, "d": trade_date})
        positions = pd.read_sql(text(
            "SELECT code, shares, avg_cost, buy_date FROM paper_positions "
            "WHERE account_id = :i ORDER BY code"),
            conn, params={"i": paper_repo.ACCOUNT_ID})

    codes = sorted(set(trades["code"].astype(str)) | set(positions["code"].astype(str))) \
        if not trades.empty else sorted(set(positions["code"].astype(str)))
    name_map: dict[str, str] = {}
    if codes:
        with eng.connect() as conn:
            in_list = ",".join(f"'{str(c).zfill(6)}'" for c in codes)
            nm = pd.read_sql(text(
                f"SELECT code, name FROM stock_info WHERE code IN ({in_list})"), conn)
        name_map = {str(r["code"]).zfill(6): str(r["name"] or "")
                    for _, r in nm.iterrows()}

    out_orders = []
    for _, t in trades.iterrows():
        code = str(t["code"]).zfill(6)
        side = str(t["side"] or "")
        shares = abs(float(t["shares"] or 0))
        out_orders.append({
            "code": code,
            "name": name_map.get(code, ""),
            "side": side,
            "direction": _SIDES.get(side, side),
            # 模拟盘卖出记录为负股数，委托单按正股数+方向表达
            "shares": int(shares) if shares == int(shares) else round(shares, 2),
            "ref_price": round(float(t["price"] or 0), 3),
            "amount": round(abs(float(t["amount"] or 0)), 2),
            "reason": str(t.get("reason") or "") or ("调入组合" if side == "buy" else "调出组合"),
        })

    target = []
    if not positions.empty:
        in_list = ",".join(f"'{str(c).zfill(6)}'" for c in positions["code"].astype(str))
        with eng.connect() as conn:
            px = pd.read_sql(text(
                f"SELECT code, close FROM stock_kline_daily WHERE code IN ({in_list}) "
                f"AND trade_date = (SELECT MAX(trade_date) FROM stock_kline_daily)"), conn)
        px_map = {str(r["code"]).zfill(6): float(r["close"])
                  for _, r in px.iterrows() if pd.notna(r["close"])}
        for _, p in positions.iterrows():
            code = str(p["code"]).zfill(6)
            shares = float(p["shares"] or 0)
            target.append({
                "code": code,
                "name": name_map.get(code, ""),
                "shares": int(shares) if shares == int(shares) else round(shares, 2),
                "avg_cost": round(float(p["avg_cost"] or 0), 3),
                "last_close": round(px_map.get(code, 0.0), 3),
            })

    return jsonify({
        "status": "ok",
        "trade_date": trade_date,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "orders": out_orders,
        "target_positions": target,
        "note": "半自动：系统只生成清单，不自动下单。参考价为模拟盘纸面成交价（收盘价±滑点），"
                "实际委托请以盘口为准；执行后在页面勾选标记（存本机）。",
    })
