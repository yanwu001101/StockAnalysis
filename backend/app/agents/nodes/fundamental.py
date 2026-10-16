"""Node 2 — FundamentalAnalystNode.

ROE / PE / PB / 负债率 / 增速。数值全部来自数据源，LLM 只负责把它们讲成人话。
"""
from __future__ import annotations

from app.domain.models import (
    AgentId,
    AgentStatus,
    FundamentalSnapshot,
)
from app.agents.nodes._progress import emit


def fundamental_node(state: dict) -> dict:
    deps = state["deps"]
    symbol = state["symbol"]

    emit(state, AgentId.FUNDAMENTAL, AgentStatus.RUNNING, 0.15, "正在读取财务报表与估值指标…")

    snapshot: FundamentalSnapshot
    try:
        snapshot = deps.market_data.fetch_fundamentals(symbol)
    except Exception as exc:  # noqa: BLE001 — one bad source must not abort
        emit(state, AgentId.FUNDAMENTAL, AgentStatus.FAILED, 0.15, f"基本面数据获取失败：{exc}")
        return {"fundamentals": None, "warnings": [f"基本面数据不可用：{exc}"]}

    message = _summarise(snapshot)
    emit(state, AgentId.FUNDAMENTAL, AgentStatus.COMPLETED, 0.25, message)
    return {"fundamentals": snapshot}


def _summarise(snapshot: FundamentalSnapshot) -> str:
    parts: list[str] = []
    if snapshot.roe is not None:
        parts.append(f"ROE {snapshot.roe:.2f}%")
    if snapshot.pe is not None:
        parts.append(f"PE {snapshot.pe:.1f}")
    if snapshot.pb is not None:
        parts.append(f"PB {snapshot.pb:.2f}")
    if snapshot.debt_ratio is not None:
        parts.append(f"资产负债率 {snapshot.debt_ratio:.1f}%")
    if snapshot.net_profit_yoy is not None:
        parts.append(f"净利润同比 {snapshot.net_profit_yoy:+.1f}%")
    if not parts:
        return "基本面数据源未返回有效指标，后续判断将以技术与风控为主"
    return "、".join(parts)
