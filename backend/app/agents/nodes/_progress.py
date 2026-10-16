"""Shared progress plumbing for the graph nodes.

The wire contract only names four agents (fundamental / sentiment / technical
/ risk). Stages that are not agents — data ingestion, the debate, the
backtest, the translation — stream their state as messages on the agent that
owns them, so the UI keeps a fixed four-card layout while still showing every
step of the run.
"""
from __future__ import annotations

from app.domain.models import AgentId, AgentProgressPayload, AgentStatus

AGENT_NAMES: dict[AgentId, str] = {
    AgentId.FUNDAMENTAL: "基本面分析师",
    AgentId.SENTIMENT: "舆情分析师",
    AgentId.TECHNICAL: "技术面与回测",
    AgentId.RISK: "风控经理",
}

AGENT_WEIGHTS: dict[AgentId, float] = {
    AgentId.FUNDAMENTAL: 0.25,
    AgentId.SENTIMENT: 0.50,
    AgentId.TECHNICAL: 0.75,
    AgentId.RISK: 0.90,
}


def emit(
    state: dict,
    agent: AgentId,
    status: AgentStatus,
    progress: float,
    message: str,
) -> None:
    """Publish one progress frame. Never raises — streaming must not kill a run."""
    deps = state.get("deps")
    if deps is None:
        return
    try:
        deps.progress.publish_progress(
            AgentProgressPayload(
                task_id=str(state.get("task_id", "")),
                agent_id=agent,
                agent_name=AGENT_NAMES[agent],
                status=status,
                progress=progress,
                message=message,
            )
        )
    except Exception:  # noqa: BLE001 — a broken socket must not abort analysis
        pass
