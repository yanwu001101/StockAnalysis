# -*- coding: utf-8 -*-
"""短线做 T 信号 blueprint。

  GET  /api/t/stock/<code>?shares=&avg_cost=&available=   单只做 T 决策(可带持仓)
  POST /api/t/batch   批量:{"codes":[...]} 或 {"positions":[{code,shares,avg_cost,available}]}

数据来自 intraday_t 引擎(分时+逐笔+基准指数);持仓参数用于结合底仓做真 T。
指数上下文在引擎内复用 cache 全市场共享(30s),连续请求不重复拉取。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import intraday_t

bp = Blueprint("t_signal", __name__, url_prefix="/api/t")


def _num_arg(name):
    v = request.args.get(name)
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@bp.route("/stock/<code>")
def t_stock(code):
    return jsonify(intraday_t.signal(
        code,
        shares=_num_arg("shares"),
        avg_cost=_num_arg("avg_cost"),
        available=_num_arg("available"),
    ))


@bp.route("/batch", methods=["POST"])
def t_batch():
    body = request.get_json(silent=True) or {}
    positions = body.get("positions")
    if isinstance(positions, list) and positions:
        return jsonify(intraday_t.batch(positions))
    codes = body.get("codes")
    if isinstance(codes, list) and codes:
        return jsonify(intraday_t.batch(codes))
    return jsonify({"error": "codes or positions must be a non-empty list"}), 400
