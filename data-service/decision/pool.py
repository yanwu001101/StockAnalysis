# -*- coding: utf-8 -*-
"""稳定候选池 + 最终决策。

输入:最近 K 个排名快照(时间升序)。
输出:每只候选股的
  rank_series      各快照中的排名(跌出窗口上限记 None)
  rank_stability   排名稳定度 0-100 = 100 − 3·σ(排名) − 0.5·(平均排名 − 1)
                   缺席的快照按上限排名计入;快照数 < 3 时标记样本不足
  trend_stability  趋势稳定度 0-100 = 60·近20日收盘在MA20上方比例 + 40·趋势组分跨快照一致性
                   MA20 向下时封顶 50
  buy_quality      买点质量 0-100(见 snapshot.buy_state;与综合评分无关)
  sector_strength  板块强度 0-100 = 窗口内 (1 − 板块涨幅分位) 的均值 ×100
  risk             风险 0-100(越高越危险):波动率/当日涨跌/回撤/流动性/ST/临近涨停/市值
  decision         最终决策分 = 0.30·综合分 + 0.25·排名稳定度 + 0.15·趋势稳定度
                              + 0.15·买点质量 + 0.10·板块强度 + 0.05·(100 − 风险)

"评分高"与"现在可以买"分离:决策分决定"今天重点看谁",买点状态决定"现在能不能买"。
按 A 股 T+1:今日买入的仓位当日不可卖 → 不生成任何卖出/做T 信号。
"""
from __future__ import annotations

import datetime as dt
import logging
import statistics
from typing import Optional

import cache
from decision import groups, snapshot

log = logging.getLogger(__name__)

WINDOW_N = 8          # 参与稳定度计算的快照个数
POOL_TOP = 40         # 进入候选池的排名门槛(最新快照排名 ≤ POOL_TOP,或窗口内 ≥50% 快照排名 ≤ POOL_TOP)
RANK_CAP = 150        # 加载与缺席排名上限
FOCUS_N = 3
MIN_SAMPLES = 3

DECISION_WEIGHTS = {
    "composite": 0.30, "rank_stability": 0.25, "trend_stability": 0.15,
    "buy_quality": 0.15, "sector_strength": 0.10, "safety": 0.05,
}

STATE_ORDER = {  # 用于同分排序:越"可操作"越靠前
    "in_zone": 0, "near_above": 1, "wait_pullback": 2, "below_zone": 3,
    "no_zone": 4, "extended": 5, "bearish": 6, "invalidated": 7,
}


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _grade_stability(v: Optional[float]) -> str:
    if v is None:
        return "样本不足"
    if v >= 85:
        return "稳定"
    if v >= 65:
        return "较稳"
    if v >= 45:
        return "波动"
    return "不稳定"


def _level5(v: Optional[float]) -> int:
    """0-100 → 1..5 档(用于紧凑的五段计量条,非评分本身)。"""
    if v is None:
        return 0
    return int(_clamp(round(v / 20 + 0.5), 1, 5))


def _risk_level(r: float) -> str:
    return "低" if r < 30 else ("中" if r < 55 else "高")


def risk_score(item: dict) -> tuple[float, list[str]]:
    ex = item.get("extra") or {}
    why = []
    r = 0.0
    atr = ex.get("atr_pct")
    if atr is not None:
        if atr <= 2:
            r += 10; why.append(f"ATR {atr:.1f}%(低波动)")
        elif atr <= 4:
            r += 25; why.append(f"ATR {atr:.1f}%")
        elif atr <= 6:
            r += 40; why.append(f"ATR {atr:.1f}%(高波动)")
        else:
            r += 55; why.append(f"ATR {atr:.1f}%(极高波动)")
    else:
        r += 25
    chg = item.get("pct_change")
    if chg is not None:
        if abs(chg) > 8:
            r += 25; why.append(f"今日 {chg:+.1f}%(大幅波动)")
        elif abs(chg) > 5:
            r += 15; why.append(f"今日 {chg:+.1f}%")
        if chg >= 9.0:
            r += 10; why.append("临近涨停,追买滑点大")
    dd = ex.get("dd20_pct")
    if dd is not None and dd <= -15:
        r += 10; why.append(f"近20日回撤 {dd:.0f}%")
    amt = ex.get("amt20_yi")
    if amt is not None:
        if amt < 1:
            r += 15; why.append(f"日均成交 {amt:.1f} 亿(流动性弱)")
        elif amt < 3:
            r += 5; why.append(f"日均成交 {amt:.1f} 亿")
    if ex.get("is_st"):
        r += 25; why.append("ST 股")
    cap = item.get("market_cap_yi")
    if cap is not None and cap < 100:
        r += 5; why.append(f"市值 {cap:.0f} 亿(偏小)")
    return _clamp(round(r, 1)), why


def _series_stats(ranks: list[Optional[int]]) -> tuple[Optional[float], Optional[float], Optional[float], int]:
    """(stability, mean, std, present_n)。缺席按 RANK_CAP 计。"""
    if not ranks:
        return None, None, None, 0
    filled = [RANK_CAP if r is None else r for r in ranks]
    present = sum(1 for r in ranks if r is not None)
    mean = statistics.fmean(filled)
    std = statistics.pstdev(filled) if len(filled) > 1 else 0.0
    if len(ranks) < MIN_SAMPLES:
        return None, round(mean, 1), round(std, 2), present
    stab = _clamp(100 - 3 * std - 0.5 * (mean - 1))
    return round(stab, 1), round(mean, 1), round(std, 2), present


def _trend_stability(item: dict, trend_scores: list[Optional[float]]) -> tuple[Optional[float], list[str]]:
    ex = item.get("extra") or {}
    above = ex.get("above_ma20_pct")
    why = []
    if above is None:
        return None, ["日K不足,无法评估趋势持续性"]
    vals = [v for v in trend_scores if v is not None]
    if len(vals) >= 2:
        std = statistics.pstdev(vals)
        consistency = _clamp(1 - std / 25, 0, 1)
        why.append(f"趋势组分跨 {len(vals)} 个快照波动 σ={std:.1f}")
    else:
        consistency = 0.5
        why.append("趋势组分样本不足,按中性计")
    ts = 60 * above + 40 * consistency
    why.insert(0, f"近 20 日 {above*100:.0f}% 收盘在 MA20 上方")
    slope = ex.get("ma20_slope_pct")
    if slope is not None:
        why.append(f"MA20 五日斜率 {slope:+.2f}%")
        if slope < 0:
            ts = min(ts, 50)
            why.append("MA20 向下,趋势稳定度封顶 50")
    return round(_clamp(ts), 1), why


def compute_pool(window_ids: list[str], latest_items: list[dict] | None = None) -> dict:
    """基于窗口快照计算候选池(不含用户持仓信息,可全局缓存)。"""
    if not window_ids:
        return {"window": [], "entries": []}
    latest_id = window_ids[-1]
    by_snap = snapshot.items_multi(window_ids, top_rank=RANK_CAP)
    latest = by_snap.get(latest_id) or []
    if latest_items:
        latest = latest_items
    latest_map = {it["code"]: it for it in latest}

    # 候选:最新 top 或窗口内多数快照 top
    appear: dict[str, int] = {}
    for sid in window_ids:
        for it in by_snap.get(sid) or []:
            if it["rank"] <= POOL_TOP:
                appear[it["code"]] = appear.get(it["code"], 0) + 1
    cand = {c for c, it in latest_map.items() if it["rank"] <= POOL_TOP}
    cand |= {c for c, n in appear.items() if n >= max(2, len(window_ids) / 2) and c in latest_map}

    headers = {h["snapshot_id"]: h for h in snapshot.headers(limit=200)}
    slots = [{"snapshot_id": s, "slot": (headers.get(s) or {}).get("slot"),
              "trade_date": (headers.get(s) or {}).get("trade_date")} for s in window_ids]

    entries = []
    for code in cand:
        it = latest_map[code]
        ranks, trend_scores, sector_pcts = [], [], []
        for sid in window_ids:
            row = next((x for x in (by_snap.get(sid) or []) if x["code"] == code), None)
            ranks.append(row["rank"] if row else None)
            g = (row or {}).get("groups") or {}
            trend_scores.append((g.get("trend") or {}).get("score") if row else None)
            sp = (row or {}).get("sector_rank_pct") if row else None
            if sp is not None:
                sector_pcts.append(sp)
        stab, mean_r, std_r, present = _series_stats(ranks)
        trend_stab, trend_why = _trend_stability(it, trend_scores)
        buy = it.get("buy") or {}
        bq = buy.get("quality")
        sector = round((1 - statistics.fmean(sector_pcts)) * 100, 1) if sector_pcts else None
        risk, risk_why = risk_score(it)

        comp = float(it.get("composite") or 0)
        parts = {
            "composite": comp,
            "rank_stability": stab if stab is not None else 50.0,
            "trend_stability": trend_stab if trend_stab is not None else 50.0,
            "buy_quality": float(bq) if bq is not None else 40.0,
            "sector_strength": sector if sector is not None else 50.0,
            "safety": 100 - risk,
        }
        decision = round(sum(DECISION_WEIGHTS[k] * parts[k] for k in DECISION_WEIGHTS), 1)
        missing = [k for k, v in (("rank_stability", stab), ("trend_stability", trend_stab),
                                  ("buy_quality", bq), ("sector_strength", sector)) if v is None]

        state = buy.get("state") or ("no_zone" if it.get("buy") is None else "no_zone")
        entries.append({
            "code": code, "name": it.get("name"), "industry": it.get("industry"),
            "price": it.get("price"), "pct_change": it.get("pct_change"),
            "volume": it.get("volume"), "amount": it.get("amount"),
            "composite": comp, "rank": it.get("rank"), "signal": it.get("signal"),
            "kline_date": it.get("kline_date"),
            "rank_series": ranks, "rank_mean": mean_r, "rank_std": std_r, "present_n": present,
            "rank_stability": stab, "rank_stability_grade": _grade_stability(stab),
            "rank_stability_level": _level5(stab),
            "trend_stability": trend_stab, "trend_why": trend_why,
            "trend_group": (it.get("groups") or {}).get("trend"),
            "buy_state": state, "buy_label": buy.get("label") or snapshot.BUY_STATE_LABEL.get(state, "观察"),
            "buy_quality": bq, "buy_zone": buy.get("buy_ref"), "sell_zone": buy.get("sell_ref"),
            "invalid_level": buy.get("invalid_level"), "invalidation": buy.get("invalidation"),
            "dist_pct": buy.get("dist_pct"), "direction": buy.get("direction"),
            "direction_label": buy.get("label"), "expected_target": buy.get("expected_target"),
            "sector_strength": sector, "sector_rank_pct": it.get("sector_rank_pct"),
            "risk": risk, "risk_level": _risk_level(risk), "risk_why": risk_why,
            "decision": decision, "decision_parts": parts, "decision_missing": missing,
            "groups": it.get("groups"), "extra": it.get("extra"),
        })

    entries.sort(key=lambda e: (-e["decision"], STATE_ORDER.get(e["buy_state"], 9), e["rank"]))
    for i, e in enumerate(entries, 1):
        e["priority"] = i
    return {"window": slots, "entries": entries, "latest_id": latest_id,
            "sample_n": len(window_ids), "sample_ok": len(window_ids) >= MIN_SAMPLES}


def cached_pool(window_ids: list[str]) -> dict:
    key = "decision:pool:" + ",".join(window_ids)
    try:
        return cache.get_or_fetch(key, 120, lambda: compute_pool(window_ids))
    except Exception:
        return compute_pool(window_ids)


# ---------------------------------------------------------------------------
# 决策:重点关注 / 当前可买 / 等待 / 三类清单
# ---------------------------------------------------------------------------

ACTIONABLE = ("in_zone",)
WAITING = ("near_above", "wait_pullback", "below_zone")


def _explain(e: dict) -> list[str]:
    out = []
    series = "·".join(str(r) if r is not None else f">{RANK_CAP}" for r in e["rank_series"])
    if e["rank_stability"] is not None:
        out.append(f"排名序列 {series}(近 {len(e['rank_series'])} 个快照),稳定度 {e['rank_stability']:.0f}·{e['rank_stability_grade']}")
    else:
        out.append(f"排名序列 {series},快照不足 {MIN_SAMPLES} 个,稳定度暂不可评")
    tg = e.get("trend_group") or {}
    if e["trend_stability"] is not None:
        out.append(f"趋势稳定度 {e['trend_stability']:.0f}:" + ";".join(e["trend_why"][:2])
                   + (f";趋势组分 {tg.get('score'):.0f}" if tg.get("score") is not None else ""))
    bz = e.get("buy_zone")
    if bz:
        d = e.get("dist_pct")
        pos = "位于区内" if e["buy_state"] == "in_zone" else (f"高于区上沿 {d:+.1f}%" if d and d > 0 else f"低于区下沿 {d:+.1f}%" if d is not None else "")
        out.append(f"买点区 {bz[0]}–{bz[1]},现价 {e['price']},{pos} → {e['buy_label']}")
    else:
        out.append("未计算买点区(排名在买点计算范围之外)" if e.get("buy_quality") is None else e["buy_label"])
    if e["sector_strength"] is not None:
        out.append(f"板块「{e['industry']}」强度 {e['sector_strength']:.0f}(窗口内涨幅分位均值)")
    out.append(f"风险 {e['risk_level']}({e['risk']:.0f}):" + ("、".join(e["risk_why"][:3]) or "无显著风险项"))
    return out


def _wait_text(e: dict) -> Optional[str]:
    bz = e.get("buy_zone")
    st = e["buy_state"]
    if st in ("near_above", "wait_pullback") and bz:
        return f"等待回踩 {bz[0]}–{bz[1]}"
    if st == "below_zone" and bz:
        return f"等待重回 {bz[0]}–{bz[1]} 并企稳(失效位 {e.get('invalid_level')})"
    if st == "extended" and bz:
        return f"远离买点(高于 {bz[1]} 达 {e.get('dist_pct'):+.1f}%),不追高,等回踩 {bz[0]}–{bz[1]}"
    if st == "invalidated":
        return f"已跌破失效位 {e.get('invalid_level')},买点失效"
    if st == "bearish":
        return "模型方向偏空,不建仓"
    return None


def decide(pool: dict, positions: list[dict] | None = None, watchlist: list[str] | None = None,
           t_signals: dict[str, dict] | None = None) -> dict:
    """把候选池 + 用户持仓翻译成最终决策(用户级,不缓存)。

    positions: [{code, shares, available, locked_today, avg_cost, last_buy_date}]
    t_signals: {code: intraday_t 信号}(可卖底仓的做T候选,由调用方按需计算)
    """
    positions = positions or []
    watchlist = [str(c).zfill(6) for c in (watchlist or [])]
    pos_map = {str(p.get("code")).zfill(6): p for p in positions if p.get("code")}
    entries = pool.get("entries") or []
    for e in entries:
        p = pos_map.get(e["code"])
        e["held"] = bool(p)
        e["position"] = p
        e["explain"] = _explain(e)
        e["wait_text"] = _wait_text(e)
        e["is_actionable"] = e["buy_state"] in ACTIONABLE and e["risk_level"] != "高"
        if e["buy_state"] in ACTIONABLE and e["risk_level"] == "高":
            e["state_note"] = "已进入买点区,但风险评级为高,不作为首选"

    focus = [e for e in entries if e["buy_state"] not in ("bearish", "invalidated")][:FOCUS_N]
    focus_codes = {e["code"] for e in focus}

    # 当前可买:优先未持有的、进入买点且风险非高;都没有则允许加仓已持有的
    actionable = [e for e in entries if e["is_actionable"]]
    buy_now = next((e for e in actionable if not e["held"]), None) or (actionable[0] if actionable else None)
    alternates = [e for e in actionable if buy_now and e["code"] != buy_now["code"]][:2]
    waiting = [e for e in entries if e["buy_state"] in WAITING][:4]

    failover = None
    if buy_now:
        inv = buy_now.get("invalid_level")
        nxt = alternates[0] if alternates else (waiting[0] if waiting else None)
        failover = {
            "trigger": f"{buy_now['name']} 收盘有效跌破失效位 {inv}" if inv else f"{buy_now['name']} 买点状态变为失效",
            "next": ({"code": nxt["code"], "name": nxt["name"], "state": nxt["buy_label"],
                      "zone": nxt.get("buy_zone"), "wait_text": nxt.get("wait_text")} if nxt else None),
        }

    # ① 今日新建仓候选:未持有、非偏空/失效、买点状态可操作或等待中
    new_entry = [e for e in entries if not e["held"] and e["buy_state"] in ACTIONABLE + WAITING]
    # ③ 观察名单:其余(远离买点/失效/偏空/未计算买点)+ 自选中在最新快照但未入池的
    watch = [e for e in entries if e["code"] not in {x["code"] for x in new_entry} and not e["held"]]
    pool_codes = {e["code"] for e in entries}
    extra_watch = [c for c in watchlist if c not in pool_codes and c not in pos_map]

    # ② 做T候选:已持有且有可卖底仓;今日买入锁定的单独列出
    t_cands, locked = [], []
    for code, p in pos_map.items():
        e = next((x for x in entries if x["code"] == code), None)
        avail = float(p.get("available") or 0)
        lock = float(p.get("locked_today") or 0)
        base = {"code": code, "name": p.get("name") or (e or {}).get("name") or code,
                "shares": p.get("shares"), "available": avail, "locked_today": lock,
                "avg_cost": p.get("avg_cost"), "last_buy_date": p.get("last_buy_date"),
                "pool": ({k: e[k] for k in ("priority", "decision", "rank", "rank_series", "rank_stability",
                                           "buy_state", "buy_label", "buy_zone", "sell_zone",
                                           "invalid_level", "risk_level", "price")} if e else None)}
        if avail > 0:
            sig = (t_signals or {}).get(code)
            base["t_signal"] = sig
            base["t_note"] = "可卖底仓 = 昨日及更早买入部分;今日买入部分不参与卖出腿" if lock > 0 else None
            t_cands.append(base)
        else:
            base["t_note"] = ("持仓全部为今日买入,T+1 锁定:今日不生成任何卖出/做T 信号,下一交易日再评估"
                              if lock > 0 or p.get("last_buy_date") == str(dt.date.today())
                              else "可卖股数为 0:今日无卖出腿")
            locked.append(base)

    def _slim(e: dict) -> dict:
        keep = ("priority", "code", "name", "industry", "price", "pct_change", "composite", "rank",
                "rank_series", "rank_stability", "rank_stability_grade", "rank_stability_level",
                "trend_stability", "buy_state", "buy_label", "buy_quality", "buy_zone", "sell_zone",
                "invalid_level", "invalidation", "dist_pct", "direction_label", "expected_target",
                "sector_strength", "risk", "risk_level", "risk_why", "decision", "decision_parts",
                "decision_missing", "explain", "wait_text", "held", "is_actionable", "state_note",
                "kline_date", "amount", "volume")
        return {k: e.get(k) for k in keep}

    return {
        "focus": [_slim(e) for e in focus],
        "buy_now": _slim(buy_now) if buy_now else None,
        "alternates": [_slim(e) for e in alternates],
        "waiting": [_slim(e) for e in waiting],
        "failover": failover,
        "new_entry_candidates": [_slim(e) for e in new_entry],
        "t_candidates": t_cands,
        "locked_today": locked,
        "watch_list": [_slim(e) for e in watch],
        "watch_extra_codes": extra_watch,
        "pool": [_slim(e) for e in entries],
        "weights": DECISION_WEIGHTS,
        "rules": [
            "决策分 = 0.30×综合评分 + 0.25×排名稳定度 + 0.15×趋势稳定度 + 0.15×买点质量 + 0.10×板块强度 + 0.05×(100−风险)",
            "排名稳定度 = 100 − 3×排名标准差 − 0.5×(平均排名−1),窗口为最近 %d 个快照,跌出前 %d 名按 %d 计" % (WINDOW_N, RANK_CAP, RANK_CAP),
            "评分高 ≠ 当前可买:只有买点状态为「进入买点」且风险非高的才列为当前买入候选;远离买点的强势股列为观察、不追高",
            "A 股 T+1:今日买入部分当日不可卖,不生成任何卖出/做T 信号;做T 仅针对昨日及更早买入的可卖底仓",
            "以上为模型评分与规则输出,不构成投资建议;买点区来自日K价值区/POC/ATR 结构,请结合盘口自行确认",
        ],
    }
