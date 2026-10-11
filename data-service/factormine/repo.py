# -*- coding: utf-8 -*-
"""因子挖掘持久层：fm_job / fm_factor / fm_factor_cache 三张表。

断点续跑（SKILL §20 批量/详情同源）：候选因子在生成阶段即落库（status=PENDING），
后续每阶段只 UPDATE 状态与统计列——MySQL 就是 checkpoint，进程崩溃后从库恢复，
不会从 0 重跑。fm_factor_cache 按 (表达式, 配置, 数据版本) 缓存完整检验结果。
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import time

import pandas as pd
from sqlalchemy import text

import db
from core.trace import logger

FM_TABLES_DDL = """CREATE TABLE IF NOT EXISTS `fm_job` (
    `id` VARCHAR(40) PRIMARY KEY,
    `status` VARCHAR(16) NOT NULL DEFAULT 'QUEUED',
    `config_json` LONGTEXT NOT NULL,
    `phase` VARCHAR(32) NULL,
    `progress_json` LONGTEXT NULL,
    `error` TEXT NULL,
    `note` VARCHAR(255) NULL,
    `data_version` VARCHAR(64) NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `started_at` DATETIME NULL,
    `finished_at` DATETIME NULL,
    INDEX `idx_fmjob_status` (`status`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS `fm_factor` (
    `id` VARCHAR(48) PRIMARY KEY,
    `job_id` VARCHAR(40) NOT NULL,
    `seq` INT NOT NULL,
    `expression` TEXT NOT NULL,
    `normalized_expression` VARCHAR(500) NOT NULL,
    `ast_json` LONGTEXT NULL,
    `params_json` TEXT NULL,
    `operator_list` VARCHAR(500) NULL,
    `source_factors` VARCHAR(500) NULL,
    `category` VARCHAR(32) NULL,
    `status` VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    `verdict` VARCHAR(16) NULL,
    `reject_reason` VARCHAR(64) NULL,
    `reject_detail` VARCHAR(255) NULL,
    `missing_rate` DOUBLE NULL,
    `quick_ic` DOUBLE NULL,
    `quick_rank_ic` DOUBLE NULL,
    `quick_icir` DOUBLE NULL,
    `rank_ic` DOUBLE NULL,
    `icir` DOUBLE NULL,
    `t_stat` DOUBLE NULL,
    `ic_positive_ratio` DOUBLE NULL,
    `is_rank_ic` DOUBLE NULL,
    `oos_rank_ic` DOUBLE NULL,
    `pearson_ic` DOUBLE NULL,
    `stability` VARCHAR(16) NULL,
    `stability_years_json` TEXT NULL,
    `cluster_id` INT NULL,
    `cluster_rep` TINYINT DEFAULT 0,
    `cluster_corr` DOUBLE NULL,
    `direction` VARCHAR(16) NULL,
    `in_library` TINYINT DEFAULT 0,
    `library_note` VARCHAR(255) NULL,
    `stats_json` LONGTEXT NULL,
    `data_version` VARCHAR(64) NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX `idx_fmf_job` (`job_id`, `seq`),
    INDEX `idx_fmf_status` (`status`, `quick_rank_ic`),
    INDEX `idx_fmf_lib` (`in_library`, `updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS `fm_factor_cache` (
    `cache_key` VARCHAR(64) PRIMARY KEY,
    `quick_json` TEXT NULL,
    `stats_json` LONGTEXT NULL,
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"""

_FACTOR_COLS = (
    "id", "job_id", "seq", "expression", "normalized_expression", "ast_json", "params_json",
    "operator_list", "source_factors", "category", "status", "verdict", "reject_reason",
    "reject_detail", "missing_rate", "quick_ic", "quick_rank_ic", "quick_icir", "rank_ic",
    "icir", "t_stat", "ic_positive_ratio", "is_rank_ic", "oos_rank_ic", "pearson_ic",
    "stability", "stability_years_json", "cluster_id", "cluster_rep", "cluster_corr",
    "direction", "in_library", "library_note", "stats_json", "data_version",
)

_DATA_VERSION_CACHE: tuple[float, str | None] = (0.0, None)


def ensure_tables() -> None:
    eng = db.get_engine()
    if eng is None:
        return
    with eng.begin() as conn:
        for stmt in [x.strip() for x in FM_TABLES_DDL.split(";") if x.strip()]:
            conn.execute(text(stmt))


# ---------------------------------------------------------------------------
# 数据版本：K 线/资金流的落库进度，同一版本下结果可复现
# ---------------------------------------------------------------------------

def data_version(ttl_s: float = 600.0) -> str | None:
    global _DATA_VERSION_CACHE
    now = time.time()
    if now - _DATA_VERSION_CACHE[0] < ttl_s and _DATA_VERSION_CACHE[1]:
        return _DATA_VERSION_CACHE[1]
    eng = db.get_engine()
    if eng is None:
        return None
    try:
        with eng.connect() as conn:
            k = conn.execute(text(
                "SELECT MAX(trade_date), COUNT(*) FROM stock_kline_daily")).first()
            m = conn.execute(text(
                "SELECT MAX(trade_date) FROM stock_moneyflow")).first()
        ver = f"K{k[1]//1000}k.{k[0].strftime('%Y%m%d') if k[0] else 'NA'}" \
              f".M{m[0].strftime('%Y%m%d') if m and m[0] else 'NA'}"
        _DATA_VERSION_CACHE = (now, ver)
        return ver
    except Exception as e:
        logger.warning("[factormine] data_version failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

def create_job(job_id: str, config: dict) -> None:
    eng = db.get_engine()
    with eng.begin() as conn:
        conn.execute(text(
            "INSERT INTO fm_job (id, status, config_json, phase, progress_json, data_version) "
            "VALUES (:i, 'QUEUED', :c, 'QUEUED', :p, :v)"),
            {"i": job_id, "c": json.dumps(config, ensure_ascii=False),
             "p": json.dumps(_empty_progress(), ensure_ascii=False),
             "v": data_version()})


def _empty_progress() -> dict:
    return {"generated": 0, "tested": 0, "errors": 0,
            "invalid_expr": 0, "leakage": 0, "data_missing": 0, "zero_variance": 0,
            "quick_rejected": 0, "quick_passed": 0,
            "dedup_removed": 0, "dedup_kept": 0,
            "full_validated": 0, "pass": 0, "watch": 0, "reject": 0,
            "library": 0}


def get_job(job_id: str) -> dict | None:
    eng = db.get_engine()
    with eng.connect() as conn:
        row = conn.execute(text("SELECT * FROM fm_job WHERE id=:i"), {"i": job_id}).mappings().first()
    return dict(row) if row else None


def update_job(job_id: str, **fields) -> None:
    if not fields:
        return
    eng = db.get_engine()
    sets, params = [], {"i": job_id}
    for k, v in fields.items():
        sets.append(f"{k}=:{k}")
        params[k] = v
    with eng.begin() as conn:
        conn.execute(text(f"UPDATE fm_job SET {', '.join(sets)} WHERE id=:i"), params)


def update_progress(job_id: str, progress: dict, phase: str | None = None) -> None:
    fields = {"progress_json": json.dumps(progress, ensure_ascii=False)}
    if phase:
        fields["phase"] = phase
    update_job(job_id, **fields)


def list_jobs(limit: int = 20) -> list[dict]:
    eng = db.get_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, status, phase, note, error, data_version, created_at, started_at, "
            "finished_at, progress_json FROM fm_job ORDER BY created_at DESC LIMIT :n"),
            {"n": int(limit)}).mappings().all()
    return [dict(r) for r in rows]


def mark_interrupted_jobs() -> int:
    """服务启动时调用：上次运行中遗留的 RUNNING → PAUSED（可从 checkpoint 继续）。"""
    eng = db.get_engine()
    try:
        with eng.begin() as conn:
            res = conn.execute(text(
                "UPDATE fm_job SET status='PAUSED', "
                "note='服务重启中断，可从断点继续' WHERE status='RUNNING'"))
            return res.rowcount or 0
    except Exception as e:
        logger.warning("[factormine] mark_interrupted_jobs failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# 候选因子
# ---------------------------------------------------------------------------

def next_factor_seq(job_id: str | None = None) -> int:
    """当日全局序号：factor_id 是全表主键，必须跨任务唯一（单 worker 串行，
    计数偏移无竞态）。"""
    eng = db.get_engine()
    prefix = f"FM_{dt.date.today().strftime('%Y%m%d')}_%"
    with eng.connect() as conn:
        n = conn.execute(text(
            "SELECT COUNT(*) FROM fm_factor WHERE id LIKE :p"), {"p": prefix}).scalar()
    return int(n or 0)


def make_factor_id(seq: int) -> str:
    return f"FM_{dt.date.today().strftime('%Y%m%d')}_{seq:06d}"


def insert_factors(rows: list[dict]) -> None:
    """批量落库候选（生成阶段 checkpoint）。rows 为 _FACTOR_COLS 子集。"""
    if not rows:
        return
    eng = db.get_engine()
    cols = [c for c in _FACTOR_COLS if any(c in r for r in rows)]
    with eng.begin() as conn:
        conn.execute(text(
            f"INSERT INTO fm_factor ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)}) "
            "ON DUPLICATE KEY UPDATE updated_at=updated_at"),
            [{c: r.get(c) for c in cols} for r in rows])


def _clean_val(v):
    """float NaN/Inf 不能写 MySQL → 统一转为 NULL。"""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def json_safe(o):
    """递归把 NaN/Inf 转为 None（json.dumps 输出 NaN 会让前端 JSON.parse 失败）。"""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    return o


def update_factor(factor_id: str, **fields) -> None:
    if not fields:
        return
    eng = db.get_engine()
    keys = [k for k in fields if k in _FACTOR_COLS]
    sets, params = [], {"i": factor_id}
    for k in keys:
        sets.append(f"{k}=:{k}")
        params[k] = _clean_val(fields[k])
    with eng.begin() as conn:
        conn.execute(text(f"UPDATE fm_factor SET {', '.join(sets)} WHERE id=:i"), params)


def update_factors_bulk(rows: list[dict]) -> None:
    """批量 UPDATE（快速筛选 checkpoint）：每行必须含 id。"""
    if not rows:
        return
    eng = db.get_engine()
    with eng.begin() as conn:
        for r in rows:
            keys = [k for k in r if k in _FACTOR_COLS and k != "id"]
            if not keys:
                continue
            sets, params = [], {"i": r["id"]}
            for k in keys:
                sets.append(f"{k}=:{k}")
                params[k] = _clean_val(r[k])
            conn.execute(text(f"UPDATE fm_factor SET {', '.join(sets)} WHERE id=:i"), params)


def list_factors(job_id: str | None = None, status: str | None = None,
                 in_library: bool | None = None, min_rank_ic: float | None = None,
                 verdict: str | None = None, limit: int = 200, offset: int = 0,
                 order: str = "seq") -> list[dict]:
    eng = db.get_engine()
    where, params = [], {"n": int(limit), "o": int(offset)}
    if job_id:
        where.append("job_id=:j")
        params["j"] = job_id
    if status:
        where.append("status=:s")
        params["s"] = status
    if verdict:
        where.append("verdict=:vd")
        params["vd"] = verdict
    if in_library is not None:
        where.append("in_library=:lib")
        params["lib"] = 1 if in_library else 0
    if min_rank_ic is not None:
        where.append("ABS(quick_rank_ic) >= :m")
        params["m"] = float(min_rank_ic)
    order_map = {"seq": "seq", "rank_ic": "ABS(quick_rank_ic) DESC", "updated": "updated_at DESC"}
    sql = ("SELECT * FROM fm_factor "
           + ("WHERE " + " AND ".join(where) if where else "")
           + f" ORDER BY {order_map.get(order, 'seq')} LIMIT :n OFFSET :o")
    with eng.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return [dict(r) for r in rows]


def get_factor(factor_id: str) -> dict | None:
    eng = db.get_engine()
    with eng.connect() as conn:
        row = conn.execute(text("SELECT * FROM fm_factor WHERE id=:i"),
                           {"i": factor_id}).mappings().first()
    return dict(row) if row else None


def count_factors(job_id: str, status: str | None = None) -> int:
    eng = db.get_engine()
    sql = "SELECT COUNT(*) FROM fm_factor WHERE job_id=:j"
    params: dict = {"j": job_id}
    if status:
        sql += " AND status=:s"
        params["s"] = status
    with eng.connect() as conn:
        return int(conn.execute(text(sql), params).scalar() or 0)


def funnel(job_id: str) -> dict:
    """研究过程漏斗的权威计数（直接来自 fm_factor，断点续跑后不漂移）。"""
    eng = db.get_engine()
    if eng is None:
        return {}
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT COUNT(*) AS `generated`, "
            "SUM(status='PENDING') AS `pending`, "
            "SUM(status='PENDING' AND reject_reason IS NULL) AS `unprocessed`, "
            "SUM(reject_reason='表达式无效') AS `invalid_expr`, "
            "SUM(reject_reason='未来函数') AS `leakage`, "
            "SUM(reject_reason='数据缺失率过高') AS `data_missing`, "
            "SUM(reject_reason='因子无区分度（零方差）') AS `zero_variance`, "
            "SUM(reject_reason='快速筛选未达标') AS `quick_rejected`, "
            "SUM(reject_reason='与高相关因子重复') AS `dedup_removed`, "
            "SUM(status='QUICK_PASS') + SUM(reject_reason='与高相关因子重复') "
            "+ SUM(status='VALIDATED') AS `quick_passed`, "
            "SUM(cluster_rep=1 AND status IN ('QUICK_PASS','VALIDATED')) AS `dedup_kept`, "
            "SUM(status='VALIDATED') AS `full_validated`, "
            "SUM(verdict='PASS') AS `pass`, "
            "SUM(verdict='WATCH') AS `watch`, "
            "SUM(verdict='REJECT') AS `reject`, "
            "SUM(in_library=1) AS `library` "
            "FROM fm_factor WHERE job_id=:j"), {"j": job_id}).mappings().first()
    out = {k: int(row[k] or 0) for k in row} if row else {}
    out["tested"] = out.get("generated", 0) - out.get("pending", 0)
    out["full_left"] = max(out.get("dedup_kept", 0) - out.get("full_validated", 0), 0)
    return out


def cluster_peers(factor_id: str, limit: int = 20) -> list[dict]:
    """同聚类的相关因子（含与已入库因子的重复标记 cluster_id=-1）。"""
    f = get_factor(factor_id)
    if not f or f.get("cluster_id") is None:
        return []
    eng = db.get_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, expression, cluster_corr, quick_rank_ic, verdict, status, in_library "
            "FROM fm_factor WHERE job_id=:j AND cluster_id=:c AND id != :i "
            "ORDER BY ABS(cluster_corr) DESC LIMIT :n"),
            {"j": f["job_id"], "c": f["cluster_id"], "i": factor_id, "n": int(limit)}).mappings().all()
    return [dict(r) for r in rows]



def screen_with_factor(factor_id: str, top_n: int = 20) -> dict:
    """用已注册因子做一次截面选股：最新调仓日因子值 Top-N。

    复用 alphalab.eval_expression（与检验/回测同一求值引擎）+ 流动性宇宙。
    只输出「因子分高」的名单，不生成买点/交易信号（SKILL §38）。"""
    import alphalab as al
    f = get_factor(factor_id)
    if not f:
        return {"error": "因子不存在"}
    if not f.get("in_library"):
        return {"error": "该因子尚未加入因子库"}
    end = dt.date.today()
    start = end - dt.timedelta(days=140)
    panel = atoms_mod_build_panel(start, end)
    if not panel:
        return {"error": "行情面板为空——请先运行数据刷新"}
    try:
        factor = al.eval_expression(f["expression"], panel)
    except al.AlphaExprError as e:
        return {"error": f"因子求值失败: {e}"}
    close, volume = panel["close"], panel["volume"]
    liq = (close * volume).mean().sort_values(ascending=False)
    universe = [c for c in liq.head(400).index if c in factor.columns]
    last_row = factor.iloc[-1].reindex(universe).dropna()
    if last_row.empty:
        return {"error": "最新交易日无有效因子值"}
    info = _stock_names()
    ranked = last_row.sort_values(ascending=False).head(int(top_n))
    reverse = (f.get("direction") == "reverse")
    items = []
    for rank_i, (code, val) in enumerate(ranked.items(), 1):
        items.append({
            "rank": rank_i,
            "code": code,
            "name": info.get(code, ""),
            "factor_value": round(float(val), 4),
        })
    return {
        "factor_id": factor_id, "expression": f["expression"],
        "as_of": str(factor.index[-1].date()),
        "universe_size": len(universe),
        "direction": f.get("direction") or "positive",
        "direction_note": "该因子为反向因子：因子值越低对应历史排序收益越优，"
                          "以下按原始因子值降序展示，使用时需按反向理解"
                          if reverse else "按因子值降序（值高 = 历史排序收益优）",
        "items": items,
    }


def atoms_mod_build_panel(start, end):
    import atoms
    return atoms.build_extended_panel(start, end)


def _stock_names() -> dict[str, str]:
    eng = db.get_engine()
    if eng is None:
        return {}
    try:
        with eng.connect() as conn:
            rows = conn.execute(text("SELECT code, name FROM stock_info")).fetchall()
        return {str(r[0]).zfill(6): (r[1] or "") for r in rows}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# 结果缓存：相同 (表达式, 配置, 数据版本) 直接复用检验结果
# ---------------------------------------------------------------------------

def cache_key(normalized_expr: str, config_hash: str, dv: str | None) -> str:
    raw = f"{normalized_expr}|{config_hash}|{dv or 'NA'}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cache_get(key: str) -> dict | None:
    eng = db.get_engine()
    try:
        with eng.connect() as conn:
            row = conn.execute(text("SELECT quick_json, stats_json FROM fm_factor_cache "
                                    "WHERE cache_key=:k"), {"k": key}).mappings().first()
        if not row:
            return None
        return {"quick": json.loads(row["quick_json"]) if row["quick_json"] else None,
                "stats": json.loads(row["stats_json"]) if row["stats_json"] else None}
    except Exception:
        return None


def cache_put(key: str, quick: dict | None, stats: dict | None) -> None:
    eng = db.get_engine()
    try:
        with eng.begin() as conn:
            conn.execute(text(
                "INSERT INTO fm_factor_cache (cache_key, quick_json, stats_json) "
                "VALUES (:k, :q, :s) ON DUPLICATE KEY UPDATE quick_json=VALUES(quick_json), "
                "stats_json=VALUES(stats_json), created_at=CURRENT_TIMESTAMP"),
                {"k": key,
                 "q": json.dumps(json_safe(quick), ensure_ascii=False) if quick else None,
                 "s": json.dumps(json_safe(stats), ensure_ascii=False) if stats else None})
    except Exception as e:
        logger.debug("[factormine] cache_put failed: %s", e)


# ---------------------------------------------------------------------------
# 因子库（注册表）
# ---------------------------------------------------------------------------

def set_library(factor_id: str, in_library: bool, note: str | None = None) -> dict | None:
    f = get_factor(factor_id)
    if not f:
        return None
    new_note = note if note is not None else \
        ("" if not in_library else (f.get("library_note") or ""))
    update_factor(factor_id, in_library=1 if in_library else 0, library_note=new_note)
    return get_factor(factor_id)


def library_stats() -> dict:
    eng = db.get_engine()
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN verdict='PASS' THEN 1 ELSE 0 END) AS pass_n, "
            "SUM(CASE WHEN verdict='WATCH' THEN 1 ELSE 0 END) AS watch_n, "
            "SUM(CASE WHEN in_library=1 THEN 1 ELSE 0 END) AS lib_n "
            "FROM fm_factor")).mappings().first()
    return dict(row) if row else {}
