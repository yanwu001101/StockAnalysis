"""Node 7 — RiskManagerNode.

Picks one of three risk profiles and, importantly, a **position scale** that
the backtest engine actually honours when sizing the entry. A risk manager
whose opinion changes nothing would be decoration.
"""
from __future__ import annotations

from app.agents.nodes._progress import emit
from app.domain.models import AgentId, AgentStatus, DebateEntry, DebaterSide, RiskAssessment, RiskProfile

_AGGRESSIVE_VOLATILITY = 0.03
_CONSERVATIVE_VOLATILITY = 0.05
_BULLISH_NET = 0.30
_BEARISH_NET = -0.30


def risk_node(state: dict) -> dict:
    debate = state.get("debate", [])
    technical = state.get("technical")

    net_conviction = _net_conviction(debate)
    volatility = _relative_volatility(technical)

    if net_conviction > _BULLISH_NET and volatility < _AGGRESSIVE_VOLATILITY:
        profile = RiskProfile.AGGRESSIVE
        scale = 1.0
        rationale = (
            f"多空净信念 {net_conviction:+.2f} 偏多，且日内波动 "
            f"{volatility * 100:.2f}% 温和，按满仓执行"
        )
    elif net_conviction < _BEARISH_NET or volatility >= _CONSERVATIVE_VOLATILITY:
        profile = RiskProfile.CONSERVATIVE
        scale = 0.5
        rationale = (
            f"多空净信念 {net_conviction:+.2f}"
            + ("偏空" if net_conviction < _BEARISH_NET else "")
            + f"，波动 {volatility * 100:.2f}%，仓位减半以控制回撤"
        )
    else:
        profile = RiskProfile.NEUTRAL
        scale = 0.75
        rationale = (
            f"多空净信念 {net_conviction:+.2f}，波动 {volatility * 100:.2f}%，"
            "按七成仓位中性执行"
        )

    assessment = RiskAssessment(profile=profile, position_scale=scale, rationale=rationale)
    emit(state, AgentId.RISK, AgentStatus.COMPLETED, 0.90, rationale)
    return {"risk": assessment}


def _net_conviction(debate: list[DebateEntry]) -> float:
    bull = max((e.conviction for e in debate if e.side is DebaterSide.BULL), default=0.0)
    bear = max((e.conviction for e in debate if e.side is DebaterSide.BEAR), default=0.0)
    return round(bull - bear, 4)


def _relative_volatility(technical) -> float:
    if technical is None or technical.atr14 <= 0 or technical.last_close <= 0:
        return 0.0
    return round(technical.atr14 / technical.last_close, 4)
