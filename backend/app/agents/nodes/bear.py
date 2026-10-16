"""Node 6 — BearResearcherNode.

Mirror of the bull node. Each round overwrites nothing — the full
``debate_history`` accumulates so the risk manager can see how the two sides
converged.
"""
from __future__ import annotations

from app.agents.nodes._progress import emit
from app.domain.models import AgentId, AgentStatus, DebateEntry, DebaterSide


def bear_node(state: dict) -> dict:
    round_no = state.get("debate_round", 1)
    max_rounds = state.get("debate_max_rounds", 2)

    points = _bear_points(state)
    conviction = _conviction(points)
    entry = DebateEntry(
        round=round_no,
        side=DebaterSide.BEAR,
        argument="；".join(points) if points else "暂未发现明确的空头证据",
        conviction=conviction,
    )
    emit(
        state,
        AgentId.TECHNICAL,
        AgentStatus.RUNNING,
        0.75,
        f"多空辩论 第 {round_no}/{max_rounds} 轮 · 空方观点：{entry.argument}",
    )
    return {"debate": state.get("debate", []) + [entry]}


def _bear_points(state: dict) -> list[str]:
    points: list[str] = []
    technical = state.get("technical")
    if technical is not None:
        if technical.macd_hist < 0:
            points.append(f"MACD 柱为负（{technical.macd_hist:+.2f}），动能偏弱")
        if technical.last_close < technical.ma20:
            points.append("现价失守 20 日均线，短期趋势向下")
        if technical.last_close >= technical.boll_upper:
            points.append("股价冲出布林上轨，短线过热有回落风险")
        if technical.rsi14 > 65:
            points.append(f"RSI {technical.rsi14:.1f} 接近超买区，追高性价比低")

    fundamentals = state.get("fundamentals")
    if fundamentals is not None:
        if fundamentals.roe is not None and fundamentals.roe < 8:
            points.append(f"ROE 仅 {fundamentals.roe:.1f}%，资本回报偏低")
        if fundamentals.pe is not None and fundamentals.pe > 40:
            points.append(f"PE {fundamentals.pe:.1f}，估值透支预期")
        if fundamentals.debt_ratio is not None and fundamentals.debt_ratio > 65:
            points.append(f"资产负债率 {fundamentals.debt_ratio:.1f}%，偿债压力偏大")
        if fundamentals.net_profit_yoy is not None and fundamentals.net_profit_yoy < 0:
            points.append(f"净利润同比 {fundamentals.net_profit_yoy:+.1f}%，盈利下滑")

    sentiment = state.get("sentiment")
    if sentiment is not None and sentiment.available and sentiment.polarity < -0.15:
        points.append(f"舆情极性 {sentiment.polarity:+.2f}，消息面偏冷")
    return points


def _conviction(points: list[str]) -> float:
    return round(min(1.0, 0.25 + 0.15 * len(points)), 2)
