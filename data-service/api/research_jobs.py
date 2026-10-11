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

from flask import Blueprint, jsonify, request

import research_jobs

bp = Blueprint("research_jobs", __name__, url_prefix="/api/async")

_KINDS = {
    "backtest": ("api.backtest", "run_backtest_payload"),
    "factorlab": ("api.factorlab", "run_factorlab_payload"),
    "alphalab-backtest": ("api.alphalab", "run_backtest_payload"),
    "alphalab-factorlab": ("api.alphalab", "run_factorlab_payload"),
}


@bp.route("/<kind>", methods=["POST"])
def submit(kind: str):
    target = _KINDS.get(kind)
    if not target:
        return jsonify({"error": f"unknown kind: {kind}"}), 404
    body = request.get_json(force=True, silent=True) or {}
    module_name, fn_name = target
    fn = getattr(importlib.import_module(module_name), fn_name)
    job_id = research_jobs.submit(kind, lambda: fn(body))
    return jsonify({"job_id": job_id, "status": "QUEUED"})


@bp.route("/jobs/<job_id>", methods=["GET"])
def job_status(job_id: str):
    job = research_jobs.get_job(job_id)
    if not job:
        return jsonify({"error": "任务不存在或已过期，请重新提交"}), 404
    return jsonify(job)
