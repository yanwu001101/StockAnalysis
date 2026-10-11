# -*- coding: utf-8 -*-
"""Backtest Flask blueprint.

POST /api/backtest
  body: {strategy_id, start_date, end_date, initial_capital, top_n, rebalance,
         code?, costs?: {commission_rate?, commission_min?, stamp_tax?, slippage?}}
  resp: {strategy_id, metrics, equity_curve, benchmark_curve?, trades, picks, costs}

run_backtest_payload 为纯 payload 入口，与异步任务（api/research_jobs）共用，
同步路由只是它的一层薄壳。
"""
from __future__ import annotations
import datetime as dt

from flask import Blueprint, jsonify, request

from backtest import engine


bp = Blueprint("backtest", __name__, url_prefix="/api")


def _parse_date(s: str | None, default: dt.date) -> dt.date:
    if not s:
        return default
    return dt.date.fromisoformat(s[:10])


def _parse_costs(body: dict) -> dict | None:
    """接受 camelCase / snake_case 的可选项，缺省由引擎默认值兜底。"""
    raw = body.get("costs") or {}
    if not isinstance(raw, dict) or not raw:
        return None
    keymap = {
        "commission_rate": "commission_rate", "commissionRate": "commission_rate",
        "commission_min": "commission_min", "commissionMin": "commission_min",
        "stamp_tax": "stamp_tax", "stampTax": "stamp_tax",
        "slippage": "slippage",
    }
    out = {k: raw[k] for k in keymap if k in raw}
    return out or None


def run_backtest_payload(body: dict) -> dict:
    strategy_id = body.get("strategy_id") or body.get("strategyId") or "quality_factor"
    end = _parse_date(body.get("end_date") or body.get("endDate"), dt.date.today())
    start = _parse_date(body.get("start_date") or body.get("startDate"),
                        end - dt.timedelta(days=365))
    capital = float(body.get("initial_capital") or body.get("initialCapital") or 1_000_000)
    code = body.get("code") or body.get("stockCode")
    costs = _parse_costs(body)

    if code:
        return engine.run_single(strategy_id, str(code).zfill(6), start, end,
                                 capital, costs=costs)
    top_n = int(body.get("top_n") or body.get("topN") or 10)
    rebal = body.get("rebalance") or "weekly"
    return engine.run(strategy_id, start, end, capital, top_n, rebal, costs=costs)


@bp.route("/backtest", methods=["POST"])
def run_backtest():
    try:
        body = request.get_json(force=True, silent=True) or {}
        return jsonify(run_backtest_payload(body))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
