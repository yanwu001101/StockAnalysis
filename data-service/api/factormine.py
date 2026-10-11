# -*- coding: utf-8 -*-
"""因子挖掘 API 蓝图（/api/factormine/*）。

任务接口（长任务不阻塞 Web 请求）：
  POST /mine                 创建挖掘任务（校验配置，入队）
  GET  /job/<id>             任务状态 + 研究过程漏斗（权威计数来自 fm_factor）
  GET  /jobs                 最近任务列表
  POST /job/<id>/pause       暂停（当前候选完成后停下，checkpoint 已落库）
  POST /job/<id>/resume      从断点继续（PAUSED / FAILED）
  POST /job/<id>/cancel      取消

候选/因子接口：
  GET  /factors              候选列表（按 job/状态/入库过滤，分页）
  GET  /factor/<id>          因子详情（stats_json：IC/分层/衰减/中性/牛熊/WF/成本表）
  POST /factor/<id>/library  加入 / 移出 因子库
  POST /factor/<id>/revalidate  重新运行完整检验（相同配置+数据版本 → 可复现）
  POST /factor/<id>/screen   用已入库因子做截面 Top-N 选股（只输出排序，不生成买点）
  GET  /library              因子库列表

目录接口：
  GET  /atoms                原子因子目录（含数据可得性探查）
  GET  /operators            算子注册表（元数据；晋级阈值口径见前端高级参数区与 stats）
"""
from __future__ import annotations

import datetime as dt
import json

from flask import Blueprint, jsonify, request

from core.trace import logger
from factormine import jobs, repo
from factormine.pipeline import REASON_DEDUP, REASON_FULL, REASON_INVALID, \
    REASON_LEAKAGE, REASON_MISSING, REASON_QUICK, REASON_ZEROVAR
from factormine.registry import operators_payload

bp = Blueprint("factormine", __name__, url_prefix="/api/factormine")

# 服务启动：建表 + 遗留 RUNNING 标记为 PAUSED（断点续跑）+ 唤醒 worker 接管排队任务
try:
    repo.ensure_tables()
    _n = repo.mark_interrupted_jobs()
    if _n:
        logger.info("[factormine] marked %d interrupted job(s) as PAUSED", _n)
    from factormine import jobs as _jobs
    _jobs.ensure_worker()
except Exception as _e:
    logger.warning("[factormine] startup init failed: %s", _e)


def _err(msg: str, code: int = 400, kind: str | None = None):
    body = {"error": msg}
    if kind:
        body["error_kind"] = kind
    return jsonify(body), code


def _job_payload(row: dict) -> dict:
    cfg = {}
    try:
        cfg = json.loads(row.get("config_json") or "{}")
    except Exception:
        pass
    out = {
        "job_id": row["id"], "status": row["status"], "phase": row.get("phase"),
        "note": row.get("note"), "error": row.get("error"),
        "data_version": row.get("data_version"),
        "created_at": str(row.get("created_at") or ""),
        "started_at": str(row.get("started_at") or "") or None,
        "finished_at": str(row.get("finished_at") or "") or None,
        "config": cfg,
        "funnel": repo.funnel(row["id"]),
    }
    created = row.get("created_at")
    started = row.get("started_at")
    finished = row.get("finished_at")
    if started:
        now = dt.datetime.now()
        if row["status"] in ("RUNNING", "PAUSED"):
            out["elapsed_s"] = int((now - started).total_seconds())
        elif finished:
            out["elapsed_s"] = int((finished - started).total_seconds())
    return out


@bp.route("/mine", methods=["POST"])
def mine():
    body = request.get_json(force=True, silent=True) or {}
    job_id, error = jobs.submit(body)
    if error:
        return _err(error)
    return jsonify({"job_id": job_id, "status": "QUEUED"})


@bp.route("/job/<job_id>", methods=["GET"])
def job_status(job_id: str):
    row = repo.get_job(job_id)
    if not row:
        return _err("任务不存在", 404)
    return jsonify(_job_payload(row))


@bp.route("/jobs", methods=["GET"])
def job_list():
    limit = min(int(request.args.get("limit") or 20), 100)
    return jsonify([_job_payload(r) for r in repo.list_jobs(limit)])


@bp.route("/job/<job_id>/pause", methods=["POST"])
def job_pause(job_id: str):
    ok, err = jobs.pause(job_id)
    return jsonify({"ok": ok}) if ok else _err(err or "无法暂停", 409)


@bp.route("/job/<job_id>/resume", methods=["POST"])
def job_resume(job_id: str):
    ok, err = jobs.resume(job_id)
    return jsonify({"ok": ok}) if ok else _err(err or "无法继续", 409)


@bp.route("/job/<job_id>/cancel", methods=["POST"])
def job_cancel(job_id: str):
    ok, err = jobs.cancel(job_id)
    return jsonify({"ok": ok}) if ok else _err(err or "无法取消", 409)


@bp.route("/factors", methods=["GET"])
def factors():
    job_id = request.args.get("job_id")
    status = request.args.get("status") or None
    verdict = request.args.get("verdict") or None
    in_library = request.args.get("in_library")
    min_rank_ic = request.args.get("min_rank_ic")
    limit = min(int(request.args.get("limit") or 100), 500)
    offset = max(int(request.args.get("offset") or 0), 0)
    order = request.args.get("order") or ("seq" if job_id else "updated")
    rows = repo.list_factors(job_id=job_id, status=status, verdict=verdict,
                             in_library=None if in_library is None else in_library == "true",
                             min_rank_ic=float(min_rank_ic) if min_rank_ic else None,
                             limit=limit, offset=offset, order=order)
    for r in rows:
        r.pop("stats_json", None)
        r.pop("ast_json", None)
        r.pop("stability_years_json", None)
    return jsonify(rows)


@bp.route("/factor/<factor_id>", methods=["GET"])
def factor_detail(factor_id: str):
    f = repo.get_factor(factor_id)
    if not f:
        return _err("因子不存在", 404)
    out = {k: v for k, v in f.items() if k != "ast_json"}
    if f.get("stability_years_json"):
        try:
            out["stability_years"] = json.loads(f["stability_years_json"])
        except Exception:
            out["stability_years"] = []
    if f.get("stats_json"):
        try:
            out["stats"] = json.loads(f["stats_json"])
        except Exception:
            out["stats"] = None
    if f.get("ast_json"):
        try:
            out["ast"] = json.loads(f["ast_json"])
        except Exception:
            out["ast"] = None
    out["cluster_peers"] = repo.cluster_peers(factor_id)
    return jsonify(out)


@bp.route("/factor/<factor_id>/library", methods=["POST"])
def factor_library(factor_id: str):
    body = request.get_json(force=True, silent=True) or {}
    in_lib = bool(body.get("in_library", True))
    f = repo.get_factor(factor_id)
    if not f:
        return _err("因子不存在", 404)
    if in_lib and f.get("status") != "VALIDATED":
        return _err("只有完整检验通过（VALIDATED）的因子才能加入因子库", 409)
    updated = repo.set_library(factor_id, in_lib, note=body.get("note"))
    if not updated:
        return _err("更新失败", 500)
    updated.pop("stats_json", None)
    updated.pop("ast_json", None)
    return jsonify(updated)


@bp.route("/factor/<factor_id>/revalidate", methods=["POST"])
def factor_revalidate(factor_id: str):
    """重新运行：相同表达式 + 相同配置 + 相同数据版本 → 结果可复现。"""
    from factormine.pipeline import Control, MiningConfig, MiningPipeline
    f = repo.get_factor(factor_id)
    if not f:
        return _err("因子不存在", 404)
    if not f.get("job_id"):
        return _err("缺少原始任务配置，无法复现", 409)
    job = repo.get_job(f["job_id"])
    if not job:
        return _err("原始任务已删除，无法复现", 409)
    try:
        cfg = MiningConfig(json.loads(job["config_json"]))
        pipe = MiningPipeline(f["job_id"], cfg, Control())
        pipe.prepare()
        pipe._full_validate(f)
    except Exception as e:
        return _err(f"重新检验失败: {e}", 500)
    return jsonify(repo.get_factor(factor_id) or {})


@bp.route("/factor/<factor_id>/screen", methods=["POST"])
def factor_screen(factor_id: str):
    body = request.get_json(force=True, silent=True) or {}
    top_n = min(max(int(body.get("top_n") or 20), 1), 100)
    return jsonify(repo.screen_with_factor(factor_id, top_n))


@bp.route("/library", methods=["GET"])
def library():
    rows = repo.list_factors(in_library=True, limit=200, order="updated")
    for r in rows:
        r.pop("stats_json", None)
        r.pop("ast_json", None)
        r.pop("stability_years_json", None)
    return jsonify({"items": rows, "stats": repo.library_stats()})


@bp.route("/atoms", methods=["GET"])
def atoms_catalog():
    from atoms import ATOM_CATEGORIES, ATOMS, availability
    avail = availability()
    items = []
    for cat in ATOM_CATEGORIES:
        for s in ATOMS.values():
            if s.category != cat:
                continue
            st = avail["atoms"].get(s.name, {"status": "unsupported", "missing": list(s.needs)})
            items.append({
                "name": s.name, "category": s.category, "desc": s.desc,
                "window": s.window, "needs": list(s.needs),
                "status": st["status"],
                "status_note": "当前数据源不支持该因子" if st["status"] == "unsupported"
                else (f"数据覆盖有限（{','.join(st.get('missing') or [])}）"
                      if st["status"] == "limited" else None),
                "coverage": st.get("coverage"),
            })
    return jsonify({"atoms": items, "capabilities": avail["capabilities"],
                    "note": "unsupported = 当前数据源无该字段（不做伪造）；"
                            "limited = 有数据但覆盖不足，挖掘时会被缺失率检查如实淘汰"})


@bp.route("/operators", methods=["GET"])
def operators():
    return jsonify(operators_payload())


    return jsonify(THRESHOLDS_DOC)
