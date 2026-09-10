"""资金分析模块 (设计文档 §3.4 龙虎榜 / 游资行为)。

内置游资席位标签库 (民间统计的公开共识, 仅供参考, 不代表真实持仓人),
对龙虎榜席位分类: 机构 / 北向 / 散户通道 / 知名游资 / 普通席位,
并给出个股资金类型、资金态度与风险提示。
"""
from __future__ import annotations

from database import sqlite as db

# seat 字段用 "|" 分隔关键词, 席位全名同时包含全部关键词即命中。
# 风格标签来自市场公开的民间统计, 存在误差, 仅作行为参考。
TRADER_SEEDS = [
    {"name": "华鑫上海分公司", "seat": "华鑫|上海分公司", "style": "顶级游资聚集席位, 短线龙头/接力", "history": "偏好热门题材核心股, 龙头战法"},
    {"name": "国泰君安上海江苏路", "seat": "国泰君安|江苏路", "style": "大资金龙头中军风格", "history": "偏好主线龙头, 锁仓打法"},
    {"name": "银河证券绍兴", "seat": "银河|绍兴", "style": "一线打板游资", "history": "偏好连板接力与强势股"},
    {"name": "国盛宁波桑田路", "seat": "国盛|桑田路", "style": "一线短线游资", "history": "偏好低位首板与连板加速"},
    {"name": "中信上海溧阳路", "seat": "中信|溧阳路", "style": "知名游资/大户混合席位", "history": "偏好情绪龙头, 进出较快"},
    {"name": "财通杭州上塘路", "seat": "财通|上塘路", "style": "短线情绪龙头风格", "history": "偏好高辨识度题材股"},
    {"name": "华泰深圳益田路荣超", "seat": "华泰|益田路", "style": "知名游资席位", "history": "偏好龙头卡位与半路"},
    {"name": "招商深圳蛇口工业七路", "seat": "招商|蛇口", "style": "大资金短线席位", "history": "偏好主流题材核心股"},
    {"name": "中信上海分公司", "seat": "中信证券|上海分公司", "style": "游资/量化混合席位", "history": "偏好高流动性题材股"},
    {"name": "国泰君安南京太平南路", "seat": "国泰君安|太平南路", "style": "知名短线游资", "history": "偏好连板妖股"},
    {"name": "东财拉萨军团", "seat": "东方财富|拉萨", "style": "散户大本营(东财网络端)", "history": "买入分散, 代表散户人气而非主力行为"},
]


def seed_database() -> None:
    db.seed_traders(TRADER_SEEDS)


def classify_seat(seat: str) -> dict:
    """席位名 -> {kind, label, style}。kind: 机构/北向/散户通道/知名游资/普通席位。"""
    seat = seat or ""
    if "机构专用" in seat:
        return {"kind": "机构", "label": "机构专用", "style": "公募/私募等机构资金"}
    if "沪股通" in seat or "深股通" in seat:
        return {"kind": "北向", "label": "北向资金", "style": "外资通道"}
    if "拉萨" in seat:
        return {"kind": "散户通道", "label": "东财拉萨(散户)", "style": "散户集中通道"}
    for t in db.all_traders() or TRADER_SEEDS:
        tokens = str(t["seat"]).split("|")
        if all(tok in seat for tok in tokens):
            return {"kind": "知名游资", "label": t["name"], "style": t["style"]}
    return {"kind": "普通席位", "label": seat[:20], "style": ""}


def _analyze_stock(row: dict) -> dict:
    seats = row.get("seats") or {}
    buys = seats.get("buy") or []
    sells = seats.get("sell") or []

    buy_cls = [classify_seat(s["seat"]) for s in buys[:5]]
    sell_cls = [classify_seat(s["seat"]) for s in sells[:5]]
    famous_buy = [c["label"] for c in buy_cls if c["kind"] == "知名游资"]
    famous_sell = [c["label"] for c in sell_cls if c["kind"] == "知名游资"]
    inst_buy = sum(1 for c in buy_cls if c["kind"] == "机构")
    inst_sell = sum(1 for c in sell_cls if c["kind"] == "机构")
    north = any(c["kind"] == "北向" for c in buy_cls)
    retail = sum(1 for c in buy_cls if c["kind"] == "散户通道")

    if inst_buy >= 2 and not famous_buy:
        capital_type = "机构主导"
    elif inst_buy and famous_buy:
        capital_type = "机构+游资混合"
    elif famous_buy:
        capital_type = "游资接力"
    elif north:
        capital_type = "北向参与"
    elif retail >= 2:
        capital_type = "散户博弈"
    else:
        capital_type = "普通游资"

    net = row.get("net_buy") or 0
    if net > 0 and famous_buy:
        attitude = "积极做多"
    elif net > 0:
        attitude = "偏多"
    elif net < 0 and (famous_sell or inst_sell >= 2):
        attitude = "主力兑现"
    elif net < 0:
        attitude = "偏空/出货"
    else:
        attitude = "多空分歧"

    risks: list[str] = []
    total_buy = sum(s["buy"] for s in buys) or 0
    if buys and total_buy:
        top1_ratio = buys[0]["buy"] / total_buy
        if top1_ratio >= 0.4:
            risks.append("买入高度集中于单一席位, 次日走势依赖该资金动向")
    if famous_sell:
        risks.append(f"卖方出现知名席位兑现: {'、'.join(famous_sell[:2])}")
    if net < 0:
        risks.append("龙虎榜净卖出, 存在兑现压力")

    return {
        **{k: row.get(k) for k in ("code", "name", "pct", "net_buy", "lhb_amount", "reason")},
        "capital_type": capital_type,
        "attitude": attitude,
        "famous_buy": famous_buy,
        "famous_sell": famous_sell,
        "inst_buy": inst_buy,
        "inst_sell": inst_sell,
        "risks": risks,
    }


def analyze(lhb: list[dict]) -> dict:
    """龙虎榜整体 + 有席位明细个股的逐一解读。"""
    detailed = [_analyze_stock(r) for r in lhb if r.get("seats")]

    famous_map: dict[str, list[str]] = {}
    for s in detailed:
        for label in s["famous_buy"]:
            famous_map.setdefault(label, []).append(s["name"])
    famous_hits = sum(len(v) for v in famous_map.values())
    activity_level = "高" if famous_hits >= 6 else ("中" if famous_hits >= 3 else "低")

    total_net = sum(r.get("net_buy") or 0 for r in lhb)
    return {
        "stocks": detailed,
        "top_net_buy": [
            {k: r.get(k) for k in ("code", "name", "pct", "net_buy", "reason")}
            for r in sorted(lhb, key=lambda x: -(x.get("net_buy") or 0))[:10]
        ],
        "summary": {
            "count": len(lhb),
            "total_net_buy": total_net,
            "famous_active": [{"trader": k, "stocks": v} for k, v in famous_map.items()],
            "hot_money_activity": activity_level,
        },
    }


def famous_by_code(capital_result: dict) -> dict[str, list[str]]:
    return {s["code"]: s["famous_buy"] for s in capital_result.get("stocks", []) if s["famous_buy"]}
