# -*- coding: utf-8 -*-
"""短线做 T 信号 blueprint。

  GET  /api/t/stock/<code>   单只做 T 建议
  POST /api/t/batch          批量(自选/持仓){"codes": [...]}

数据来自 intraday_t 引擎(东财当日分时,单只票单请求,无频控)。
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

import intraday_t

bp = Blueprint("t_signal", __name__, url_prefix="/api/t")


@bp.route("/stock/<code>")
def t_stock(code):
    return jsonify(intraday_t.signal(code))


@bp.route("/batch", methods=["POST"])
def t_batch():
    body = request.get_json(silent=True) or {}
    codes = body.get("codes")
    if not isinstance(codes, list) or not codes:
        return jsonify({"error": "codes must be a non-empty list"}), 400
    return jsonify(intraday_t.batch(codes))
