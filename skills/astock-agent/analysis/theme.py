"""板块轮动模块 (设计文档 §3.6)。

板块强度 = 涨停数量 + 资金流入 + 持续时间 + 龙头表现
输出: 板块强度排名、主线判断、各板块状态(启动/发酵/分化提纯/持续/退潮)与风险。
"""
from __future__ import annotations


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _group(zt: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for s in zt:
        theme = (s.get("industry") or "").strip()
        if theme:
            groups.setdefault(theme, []).append(s)
    return groups


def _streak(theme: str, hist_counts: dict[str, dict[str, int]], min_count: int = 2) -> int:
    """近 N 日该板块连续保持板块效应(>=min_count家涨停)的天数, 从最近一天往前数。"""
    days = sorted(hist_counts.keys(), reverse=True)
    n = 0
    for d in days:
        if hist_counts[d].get(theme, 0) >= min_count:
            n += 1
        else:
            break
    return n


def analyze(
    zt: list[dict],
    flows: dict[str, dict],
    hist_counts: dict[str, dict[str, int]],
    prev_zt: list[dict],
) -> dict:
    groups = _group(zt)
    prev_groups = _group(prev_zt)
    if not groups:
        return {"themes": [], "mainline": None}

    max_count = max(len(v) for v in groups.values())
    max_height = max((s["height"] for s in zt), default=1)
    flow_vals = [f["net_inflow"] for f in flows.values() if f.get("net_inflow") is not None]
    flow_absmax = max((abs(v) for v in flow_vals), default=0)

    themes = []
    for name, stocks in groups.items():
        count = len(stocks)
        prev_count = len(prev_groups.get(name, []))
        leader = max(stocks, key=lambda s: (s["height"], s["amount"] or 0))
        prev_leader_h = max((s["height"] for s in prev_groups.get(name, [])), default=0)
        streak = _streak(name, hist_counts)

        flow = flows.get(name)
        net_inflow = flow.get("net_inflow") if flow else None
        if net_inflow is not None and flow_absmax:
            flow_sc = _clamp((net_inflow / flow_absmax + 1) / 2)
        else:
            flow_sc = 0.5  # 无当日资金流数据(历史日期), 取中性

        score = round(
            40 * count / max_count
            + 25 * flow_sc
            + 20 * min(streak, 5) / 5
            + 15 * leader["height"] / max_height
        )

        if prev_count == 0 and count >= 3:
            status = "启动"
        elif count >= prev_count and leader["height"] > prev_leader_h:
            status = "发酵"
        elif count < prev_count and leader["height"] > prev_leader_h:
            status = "分化提纯"
        elif prev_count and count <= prev_count * 0.5:
            status = "退潮"
        else:
            status = "持续"

        risks = []
        if streak >= 4:
            risks.append("板块连续走强多日, 谨防高位分化补跌")
        if status == "退潮":
            risks.append("涨停家数明显缩量, 资金撤离迹象")
        if count >= 8 and sum(1 for s in stocks if s["height"] == 1) / count >= 0.7:
            risks.append("首板跟风占比高, 谨防一日游")
        if net_inflow is not None and net_inflow < 0 and count >= 3:
            risks.append("板块涨停但主力资金净流出, 存在分歧")

        themes.append(
            {
                "name": name,
                "zt_count": count,
                "prev_count": prev_count,
                "leader": {"code": leader["code"], "name": leader["name"], "height": leader["height"]},
                "net_inflow": net_inflow,
                "streak": streak,
                "score": score,
                "status": status,
                "risks": risks,
            }
        )

    themes.sort(key=lambda x: -x["score"])
    top = themes[0]
    persistence = "较强" if top["streak"] >= 3 else ("一般" if top["streak"] == 2 else "存疑(新启动)")
    mainline = {
        "name": top["name"],
        "status": top["status"],
        "persistence": persistence,
        "leader": top["leader"],
        "risk": top["risks"][0] if top["risks"] else "暂无明显风险信号, 关注量能持续性",
    }
    return {"themes": themes, "mainline": mainline}


def theme_score_map(result: dict) -> dict[str, float]:
    return {t["name"]: t["score"] for t in result.get("themes", [])}
