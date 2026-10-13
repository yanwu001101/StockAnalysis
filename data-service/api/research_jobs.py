# -*- coding: utf-8 -*-
"""Research jobs blueprint：回测/因子检验的异步提交与轮询。

POST /api/async/<kind>   body 与对应同步端点完全一致 → {job_id, status}
GET  /api/async/jobs/<id> → {status: QUEUED|RUNNING|DONE|FAILED, result?, error?, elapsed_s}

kind 白名单（→ payload 入口）：
  backtest           api.backtest.run_backtest_payload
  factorlab          api.factorlab.run_factorlab_payload
  alphalab-backtest  api.alphalab.run_backtest_payload
  alphalab-factorlab api.alphalab.run_factorlab_payload

同步端点全部保留（API 兼容 + curl 调试）；前端长计算一律走异步。
计算结果里的业务性 {"error": ...}（如覆盖不足）按 DONE 返回，由前端按原有
错误展示逻辑处理——与同步行为一致。
"""
from __future__ import annotations

import importlib
import json

from flask import Blueprint, g, jsonify, request

import research_jobs
from config import settings
from core import research_auth

bp = Blueprint("research_jobs", __name__, url_prefix="/api/async")

_KINDS = {
    "backtest": ("api.backtest", "run_backtest_payload"),
    "factorlab": ("api.factorlab", "run_factorlab_payload"),
    "alphalab-backtest": ("api.alphalab", "run_backtest_payload"),
    "alphalab-factorlab": ("api.alphalab", "run_factorlab_payload"),
}


@bp.before_request
def authenticated_owner():
    """Unsigned local/internal requests do not get a compatibility bypass."""
    secret = settings.research_auth.jwt_secret.get_secret_value()
    try:
        research_auth.validate_secret(secret)
        research_auth.parse_headers(request.headers)
        if request.content_length is not None and request.content_length > research_auth.MAX_BODY_BYTES:
            return jsonify({"error": "研究任务请求体过大", "code": "RESEARCH_PAYLOAD_TOO_LARGE"}), 413
        raw = request.stream.read(research_auth.MAX_BODY_BYTES + 1)
        if len(raw) > research_auth.MAX_BODY_BYTES:
            return jsonify({"error": "研究任务请求体过大", "code": "RESEARCH_PAYLOAD_TOO_LARGE"}), 413
        g.research_owner = research_auth.verify_context(secret, request.headers, request.method, request.path, raw)
        g.research_body = raw
    except research_auth.AuthUnavailable as error:
        return jsonify({"error": str(error), "code": "RESEARCH_AUTH_UNAVAILABLE"}), 503
    except research_auth.InvalidContext as error:
        return jsonify({"error": str(error), "code": "RESEARCH_AUTH_INVALID"}), 401


@bp.route("/<kind>", methods=["POST"])
def submit(kind: str):
    target = _KINDS.get(kind)
    if not target:
        return jsonify({"error": f"unknown kind: {kind}"}), 404
    try:
        body = json.loads(g.research_body)
    except (ValueError, UnicodeError, RecursionError):
        body = None
    if not isinstance(body, dict):
        return jsonify({"error": "请求体必须是 JSON 对象", "code": "INVALID_PAYLOAD"}), 400
    module_name, fn_name = target
    fn = getattr(importlib.import_module(module_name), fn_name)
    try:
        job_id = research_jobs.submit(kind, lambda: fn(body), owner_id=g.research_owner)
    except research_jobs.QueueFullError as exc:
        response = jsonify({"error": str(exc), "code": "RESEARCH_QUEUE_FULL"})
        response.headers["Retry-After"] = "5"
        return response, 429
    except RuntimeError:
        return jsonify({"error": "研究任务服务暂不可用，请稍后重试",
                        "code": "RESEARCH_UNAVAILABLE"}), 503
    return jsonify({"job_id": job_id, "status": "QUEUED"})


@bp.route("/jobs/<job_id>", methods=["GET"])
def job_status(job_id: str):
    job = research_jobs.get_job(job_id, owner_id=g.research_owner)
    if not job:
        return jsonify({"error": "任务不存在或已过期，请重新提交"}), 404
    return jsonify(job)
