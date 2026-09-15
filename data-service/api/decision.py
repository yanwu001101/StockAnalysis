# -*- coding: utf-8 -*-
"""决策层 API。

  GET  /api/decision/snapshots?date=YYYY-MM-DD        当日(或最近)快照头列表
  GET  /api/decision/snapshot/<id>?limit=             某快照排名明细 + 相对上一快照的变化拆解
  GET  /api/decision/stock/<code>/history?n=          单只股票跨快照轨迹(排名/评分/因子组/买点)
  POST /api/decision/today  {positions, watchlist, with_t}   稳定候选池 + 最终决策(用户级)
  POST /api/decision/snapshot/run                     手动触发一次快照(交易时段外也可,用于冷启动)

所有数值都来自落库快照;同一 snapshot_id 下多次请求结果一致。
"""
from __future__ import annotations

import datetime as dt
import logging
import threading

from flask import Blueprint, jsonify, request

from decision import groups, pool, snapshot

bp = Blueprint("decision", __name__, url_prefix="/api/decision")
log = logging.getLogger(__name__)

_RUN_LOCK = threading.Lock()


def _json_safe(v):
    import math
    import numpy as np
    if isinstance(v, dict):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return str(v)
    return v


def rank_changes(now_items: list[dict], prev_items: list[dict] | None,
                 weights: dict | None = None) -> dict[str, dict]:
    """逐只对比两个快照:排名/综合分变化 + 因子组贡献差 + 行情差 + 数据口径差。

    weights 给定时(用户自定义权重),两侧综合分都按该权重从策略明细重算后再比。
    """
    if not prev_items:
        return {}
    prev = {it["code"]: it for it in prev_items}
    out: dict[str, dict] = {}
    for it in now_items:
        p = prev.get(it["code"])
        if not p:
            out[it["code"]] = {"prev_rank": None, "rank_delta": None, "new": True}
            continue
        if weights:
            g_now = groups.group_scores(it.get("strategies") or [], weights)
            g_prev = groups.group_scores(p.get("strategies") or [], weights)
            c_now = groups.composite_from(it.get("strategies") or [], weights)
            c_prev = groups.composite_from(p.get("strategies") or [], weights)
        else:
            g_now, g_prev = it.get("groups") or {}, p.get("groups") or {}
            c_now, c_prev = float(it.get("composite") or 0), float(p.get("composite") or 0)
        deltas = groups.explain_delta(g_now, g_prev)
        price_now, price_prev = it.get("price"), p.get("price")
        price_delta_pct = (round((price_now / price_prev - 1) * 100, 2)
                           if price_now and price_prev else None)
        reasons = []
        for d in deltas:
            if abs(d["delta"]) >= 0.05:
                reasons.append(f"{d['label']} {d['delta']:+.1f}")
        flags = []
        if it.get("kline_date") != p.get("kline_date"):
            flags.append(f"因子重算:日K更新 {p.get('kline_date')} → {it.get('kline_date')}")
        if price_delta_pct is not None and abs(price_delta_pct) >= 0.5:
            flags.append(f"行情变化 {price_delta_pct:+.2f}%")
        out[it["code"]] = {
            "prev_rank": p.get("rank"),
            "rank_delta": (p.get("rank") - it.get("rank")) if p.get("rank") and it.get("rank") else None,
            "composite_prev": c_prev,
            "composite_delta": round(c_now - c_prev, 2),
            "group_deltas": deltas,
            "price_prev": price_prev,
            "price_delta_pct": price_delta_pct,
            "reasons": reasons,
            "flags": flags,
            "new": False,
        }
    return out


def _prev_id(sid: str) -> str | None:
    ids = snapshot.recent_ids(1, before=sid)
    return ids[0] if ids else None


@bp.route("/snapshots")
def list_snapshots():
    date = request.args.get("date")
    if date:
        rows = snapshot.headers(trade_date=date)
    else:
        rows = snapshot.headers(limit=int(request.args.get("limit", 40)))
    return jsonify(_json_safe({"snapshots": rows, "latest_id": snapshot.latest_id()}))


@bp.route("/snapshot/<sid>")
def get_snapshot(sid: str):
    if sid == "latest":
        sid = snapshot.latest_id()
        if not sid:
            return jsonify({"error": "no snapshot yet", "snapshot": None, "items": []}), 404
    head = snapshot.header(sid)
    if not head:
        return jsonify({"error": "snapshot not found"}), 404
    limit = request.args.get("limit")
    items = snapshot.items(sid, int(limit) if limit else None)
    prev_id = _prev_id(sid)
    prev_items = snapshot.items_multi([prev_id], top_rank=None).get(prev_id) if prev_id else None
    changes = rank_changes(items, prev_items)
    prev_head = snapshot.header(prev_id) if prev_id else None
    slim = []
    for it in items:
        d = dict(it)
        d.pop("strategies", None)
        d["change"] = changes.get(it["code"])
        slim.append(d)
    return jsonify(_json_safe({"snapshot": head, "prev": prev_head, "items": slim}))


@bp.route("/stock/<code>/history")
def stock_history(code: str):
    n = int(request.args.get("n", 24))
    rows = snapshot.history(code, n)
    out = []
    prev = None
    for r in rows:
        d = {k: r.get(k) for k in ("snapshot_id", "slot", "trade_date", "computed_at", "quote_time",
                                    "quote_source", "price", "pct_change", "volume", "amount",
                                    "composite", "rank", "signal", "kline_date", "sector_rank_pct")}
        d["groups"] = r.get("groups")
        d["buy"] = r.get("buy")
        d["change"] = rank_changes([r], [prev]).get(r["code"]) if prev else None
        out.append(d)
        prev = r
    return jsonify(_json_safe({"code": str(code).zfill(6), "history": out}))


def _parse_positions(raw) -> list[dict]:
    """标准化持仓:计算可卖与今日锁定(T+1)。"""
    today = str(dt.date.today())
    out = []
    for p in raw or []:
        if not isinstance(p, dict) or not p.get("code"):
            continue
        shares = float(p.get("shares") or 0)
        locked = float(p.get("locked_today") or p.get("lockedShares") or 0)
        last_buy = p.get("last_buy_date") or p.get("lastBuyDate")
        if last_buy and str(last_buy)[:10] != today:
            locked = 0.0
        avail = p.get("available")
        if avail is None:
            avail = p.get("availableShares")
        avail = float(avail) if avail is not None else max(0.0, shares - locked)
        avail = max(0.0, min(avail, shares - locked))
        out.append({"code": str(p["code"]).zfill(6), "name": p.get("name"), "shares": shares,
                    "available": avail, "locked_today": locked,
                    "avg_cost": p.get("avg_cost") or p.get("avgCost"),
                    "last_buy_date": str(last_buy)[:10] if last_buy else None})
    return out


@bp.route("/today", methods=["GET", "POST"])
def today():
    body = request.get_json(silent=True) or {}
    positions = _parse_positions(body.get("positions"))
    watchlist = body.get("watchlist") or []
    with_t = bool(body.get("with_t", True))

    latest = snapshot.latest_id()
    if not latest:
        return jsonify({"status": "no_snapshot", "message": "尚无排名快照;交易时段每 15 分钟自动生成,或手动触发一次",
                        "snapshot": None})
    window_ids = snapshot.recent_ids(pool.WINDOW_N)
    head = snapshot.header(latest)
    p = pool.cached_pool(window_ids)

    # ② 可卖底仓的做T信号:仅对 available>0 的持仓算(lite 批量,分时数据实时抓取)
    t_signals: dict[str, dict] = {}
    sellable = [x for x in positions if x["available"] > 0]
    if with_t and sellable:
        try:
            import intraday_t
            sigs = intraday_t.batch([{"code": x["code"], "shares": x["shares"], "avg_cost": x["avg_cost"],
                                      "available": x["available"]} for x in sellable])
            for s in sigs or []:
                if s and s.get("code"):
                    t_signals[str(s["code"]).zfill(6)] = {
                        k: s.get(k) for k in ("action", "action_label", "strength", "price", "pct_change",
                                              "buy_zone", "sell_zone", "plan", "risks", "data_time",
                                              "has_position", "position", "t_mode", "t_shares")}
        except Exception as e:
            log.warning("[decision] intraday_t batch failed: %s", e)

    decision = pool.decide(p, positions, watchlist, t_signals)
    # 最新快照相对上一快照的变化(用于"排名为什么变")
    prev_id = _prev_id(latest)
    changes = {}
    if prev_id:
        pair = snapshot.items_multi([latest, prev_id], top_rank=pool.RANK_CAP)
        changes = rank_changes(pair.get(latest) or [], pair.get(prev_id) or [])
    for coll in ("focus", "new_entry_candidates", "watch_list", "pool", "alternates", "waiting"):
        for e in decision.get(coll) or []:
            e["change"] = changes.get(e["code"])
    if decision.get("buy_now"):
        decision["buy_now"]["change"] = changes.get(decision["buy_now"]["code"])

    return jsonify(_json_safe({
        "status": "ok",
        "snapshot": head,
        "prev_snapshot_id": prev_id,
        "window": p.get("window"),
        "sample_n": p.get("sample_n"),
        "sample_ok": p.get("sample_ok"),
        "sample_note": (None if p.get("sample_ok")
                        else f"当前仅 {p.get('sample_n')} 个快照,排名稳定度需要 ≥{pool.MIN_SAMPLES} 个快照才可评估"),
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "trade_date_today": str(dt.date.today()),
        "positions_n": len(positions),
        **decision,
    }))


@bp.route("/snapshot/run", methods=["POST"])
def run_snapshot():
    if not _RUN_LOCK.acquire(blocking=False):
        return jsonify({"status": "busy", "message": "已有快照任务在运行"}), 409
    try:
        body = request.get_json(silent=True) or {}
        sid = snapshot.build(note=body.get("note") or "manual")
        if not sid:
            return jsonify({"status": "failed", "message": "快照构建失败(无行情或无评分结果)"}), 500
        return jsonify(_json_safe({"status": "ok", "snapshot": snapshot.header(sid)}))
    finally:
        _RUN_LOCK.release()
