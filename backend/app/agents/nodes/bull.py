"""Node 5 — BullResearcherNode.

Builds the long case from whatever the analysts produced. Deterministic: the
argument text is assembled from the same numbers the bear sees, so the two
sides cannot invent facts.
"""
from __future__ import annotations

from app.agents.nodes._progress import emit
from app.domain.models import AgentId, AgentStatus, DebateEntry, DebaterSide


def bull_node(state: dict) -> dict:
    round_no = state.get("debate_round", 0) + 1
    max_rounds = state.get("debate_max_rounds", 2)

    points = _bull_points(state)
    conviction = _conviction(points)
    entry = DebateEntry(
        round=round_no,
        side=DebaterSide.BULL,
        argument="；".join(points) if points else "暂未发现明确的多头证据",
        conviction=conviction,
    )
    emit(
        state,
        AgentId.TECHNICAL,
        AgentStatus.RUNNING,
        0.72,
        f"多空辩论 第 {round_no}/{max_rounds} 轮 · 多方观点：{entry.argument}",
    )
    return {
        "debate": state.get("debate", []) + [entry],
        "debate_round": round_no,
    }


def _bull_points(state: dict) -> list[str]:
    points: list[str] = []
    technical = state.get("technical")
    if technical is not None:
        if technical.macd_hist > 0:
            points.append(f"MACD 柱为正（{technical.macd_hist:+.2f}），动能偏多")
        if technical.last_close >= technical.ma20:
            points.append("现价站上 20 日均线，短期趋势向上")
        if technical.last_close <= technical.boll_lower:
            points.append("股价触及布林下轨，存在均值回归空间")
        if technical.rsi14 < 35:
            points.append(f"RSI {technical.rsi14:.1f} 进入超卖区，抛压衰减")

    fundamentals = state.get("fundamentals")
    if fundamentals is not None:
        if fundamentals.roe is not None and fundamentals.roe >= 12:
            points.append(f"ROE {fundamentals.roe:.1f}%，盈利能力扎实")
        if fundamentals.pe is not None and 0 < fundamentals.pe <= 25:
            points.append(f"PE {fundamentals.pe:.1f}，估值不贵")
        if fundamentals.debt_ratio is not None and fundamentals.debt_ratio <= 50:
            points.append(f"资产负债率 {fundamentals.debt_ratio:.1f}%，财务结构稳健")
        if fundamentals.net_profit_yoy is not None and fundamentals.net_profit_yoy > 0:
            points.append(f"净利润同比 {fundamentals.net_profit_yoy:+.1f}%，成长仍在")

    sentiment = state.get("sentiment")
    if sentiment is not None and sentiment.available and sentiment.polarity > 0.15:
        points.append(f"舆情极性 {sentiment.polarity:+.2f}，消息面偏暖")
    return points


def _conviction(points: list[str]) -> float:
    return round(min(1.0, 0.25 + 0.15 * len(points)), 2)
