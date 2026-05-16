# -*- coding: utf-8 -*-
"""Backtest Flask blueprint.

POST /api/backtest
  body: {strategy_id, start_date, end_date, initial_capital, top_n, rebalance}
  resp: {strategy_id, metrics, equity_curve, trades, picks}
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


@bp.route("/backtest", methods=["POST"])
def run_backtest():
    try:
        body = request.get_json(force=True, silent=True) or {}
        strategy_id = body.get("strategy_id") or body.get("strategyId") or "quality_factor"
        end = _parse_date(body.get("end_date") or body.get("endDate"), dt.date.today())
        start = _parse_date(body.get("start_date") or body.get("startDate"),
                            end - dt.timedelta(days=365))
        capital = float(body.get("initial_capital") or body.get("initialCapital") or 1_000_000)
        code = body.get("code") or body.get("stockCode")

        if code:
            result = engine.run_single(strategy_id, str(code).zfill(6), start, end, capital)
        else:
            top_n = int(body.get("top_n") or body.get("topN") or 10)
            rebal = body.get("rebalance") or "weekly"
            result = engine.run(strategy_id, start, end, capital, top_n, rebal)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/strategies/list")
def list_strategies():
    from strategies import REGISTRY
    return jsonify([
        {"id": cls.id, "name": cls.name, "weight": cls.default_weight}
        for cls in REGISTRY
    ])
