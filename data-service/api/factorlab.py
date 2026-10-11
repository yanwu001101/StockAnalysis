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


def run_factorlab_payload(body: dict) -> dict:
    """payload 版检验入口：同步路由与异步任务（api/research_jobs）共用。"""
    strategy_id = body.get("strategy_id") or body.get("strategyId") or "quality_factor"
    end = _parse_date(body.get("end_date") or body.get("endDate"), dt.date.today())
    start = _parse_date(body.get("start_date") or body.get("startDate"),
                        end - dt.timedelta(days=365))
    rebalance = body.get("rebalance") or "monthly"
    layers = int(body.get("layers") or 5)
    max_codes = int(body.get("max_codes") or body.get("maxCodes") or 300)
    # 检验类错误（如评分覆盖不足）以 {"error": ...} 随正常返回，由前端展示原因
    return analyze(strategy_id, start, end,
                   rebalance=rebalance, layers=layers, max_codes=max_codes,
                   smoothing_days=int(body.get("smoothingDays", body.get("smoothing_days", 1))),
                   cap_diagnostic=body.get("capDiagnostic", body.get("cap_diagnostic", False)) is True)


@bp.route("/factorlab", methods=["POST"])
def run_factorlab():
    try:
        body = request.get_json(force=True, silent=True) or {}
        return jsonify(run_factorlab_payload(body))
    except Exception as e:
        return jsonify({"error": str(e), "error_kind": "compute"}), 500
