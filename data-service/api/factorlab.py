# -*- coding: utf-8 -*-
"""Factor lab Flask blueprint.

POST /api/factorlab
  body: {strategy_id, start_date, end_date, rebalance?, layers?, max_codes?}
  resp: {ic_summary, ic_series, layer_curves, layer_stats, decay, ...}
"""
from __future__ import annotations
import datetime as dt

from flask import Blueprint, jsonify, request

from factorlab import analyze

bp = Blueprint("factorlab", __name__, url_prefix="/api")


def _parse_date(s: str | None, default: dt.date) -> dt.date:
    if not s:
        return default
    return dt.date.fromisoformat(s[:10])


@bp.route("/factorlab", methods=["POST"])
def run_factorlab():
    try:
        body = request.get_json(force=True, silent=True) or {}
        strategy_id = body.get("strategy_id") or body.get("strategyId") or "quality_factor"
        end = _parse_date(body.get("end_date") or body.get("endDate"), dt.date.today())
        start = _parse_date(body.get("start_date") or body.get("startDate"),
                            end - dt.timedelta(days=365))
        rebalance = body.get("rebalance") or "monthly"
        layers = int(body.get("layers") or 5)
        max_codes = int(body.get("max_codes") or body.get("maxCodes") or 300)
        result = analyze(strategy_id, start, end,
                         rebalance=rebalance, layers=layers, max_codes=max_codes)
        status = 500 if "error" in result else 200
        return jsonify(result), status
    except Exception as e:
        return jsonify({"error": str(e)}), 500
