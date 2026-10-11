# -*- coding: utf-8 -*-
"""Alpha lab Flask blueprint: user-defined cross-sectional factor research.

POST /api/alphalab/factorlab — 自定义因子统计检验（IC/分层/衰减/评级，与内置
                               策略共用 factorlab 管线）
POST /api/alphalab/backtest  — 自定义因子组合回测（t 收盘信号 → t+1 开盘成交）
GET  /api/alphalab/help      — 字段/算子/示例目录（前端帮助面板）
"""
from __future__ import annotations
import datetime as dt

from flask import Blueprint, jsonify, request

import alphalab

bp = Blueprint("alphalab", __name__, url_prefix="/api/alphalab")


def _parse_date(s: str | None, default: dt.date) -> dt.date:
    if not s:
        return default
    return dt.date.fromisoformat(s[:10])


def _parse_costs(body: dict) -> dict | None:
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


def run_factorlab_payload(body: dict) -> dict:
    """payload 版自定义因子检验：同步路由与异步任务（api/research_jobs）共用。"""
    expr = str(body.get("expression") or "").strip()
    if not expr:
        raise ValueError("缺少 expression")
    end = _parse_date(body.get("end_date") or body.get("endDate"), dt.date.today())
    start = _parse_date(body.get("start_date") or body.get("startDate"),
                        end - dt.timedelta(days=365 * 2))
    rebalance = body.get("rebalance") or "weekly"
    layers = int(body.get("layers") or 5)
    max_codes = int(body.get("max_codes") or body.get("maxCodes") or 400)
    neutralize = bool(body.get("neutralize", True))
    return alphalab.analyze_expr(expr, start, end, rebalance=rebalance,
                                 layers=layers, max_codes=max_codes,
                                 neutralize=neutralize,
                                 smoothing_days=int(body.get("smoothingDays", body.get("smoothing_days", 1))),
                                 cap_diagnostic=body.get("capDiagnostic", body.get("cap_diagnostic", False)) is True)


@bp.route("/factorlab", methods=["POST"])
def factorlab():
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(run_factorlab_payload(body))
    except ValueError as e:
        return jsonify({"error": str(e), "error_kind": "expression"}), 400
    except Exception as e:
        return jsonify({"error": str(e), "error_kind": "compute"}), 500


def run_backtest_payload(body: dict) -> dict:
    """payload 版自定义因子回测：同步路由与异步任务（api/research_jobs）共用。"""
    expr = str(body.get("expression") or "").strip()
    if not expr:
        raise ValueError("缺少 expression")
    end = _parse_date(body.get("end_date") or body.get("endDate"), dt.date.today())
    start = _parse_date(body.get("start_date") or body.get("startDate"),
                        end - dt.timedelta(days=365 * 2))
    capital = float(body.get("initial_capital") or body.get("initialCapital") or 1_000_000)
    top_n = int(body.get("top_n") or body.get("topN") or 10)
    rebalance = body.get("rebalance") or "weekly"
    max_codes = int(body.get("max_codes") or body.get("maxCodes") or 500)
    return alphalab.backtest_expr(expr, start, end, initial_capital=capital,
                                  top_n=top_n, rebalance=rebalance,
                                  costs=_parse_costs(body),
                                  max_codes=max_codes)


@bp.route("/backtest", methods=["POST"])
def backtest():
    body = request.get_json(force=True, silent=True) or {}
    try:
        return jsonify(run_backtest_payload(body))
    except ValueError as e:
        return jsonify({"error": str(e), "error_kind": "expression"}), 400
    except Exception as e:
        return jsonify({"error": str(e), "error_kind": "compute"}), 500


@bp.route("/help", methods=["GET"])
def help_():
    return jsonify(alphalab.help_payload())
