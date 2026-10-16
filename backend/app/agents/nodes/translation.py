"""Node 9 — HumanReadableTranslationNode.

Turns professional metrics into a plain-language verdict. The scoring is the
strategy pattern in ``app.services.verdict``; this node only adds the
qualitative layer (debate + sentiment) and assembles the payload.
"""
from __future__ import annotations

from app.domain.models import (
    ColorClass,
    DebateDTO,
    HumanReadableVerdict,
    DebaterSide,
    QuantVerdictPayload,
    Signal,
    TradeDTO,
)
from app.domain.models import MetricStatus
from app.services.verdict import aggregate, color_class_for, signal_for

_QUALITATIVE_CAP = 15.0


def translation_node(state: dict) -> dict:
    backtest = state.get("backtest")
    if backtest is None:
        return {
            "failed": True,
            "error": "backtest result missing",
            "warnings": state.get("warnings", []) + ["回测结果缺失，无法生成结论"],
        }

    metrics = backtest.metrics
    metric_input = {
        "sharpe_ratio": (metrics.sharpe_ratio, metrics.statuses["sharpe_ratio"]),
        "max_drawdown": (metrics.max_drawdown, metrics.statuses["max_drawdown"]),
        "win_rate": (metrics.win_rate, metrics.statuses["win_rate"]),
        "total_return": (metrics.total_return, metrics.statuses["total_return"]),
        "alpha": (metrics.alpha, metrics.statuses["alpha"]),
        "beta": (metrics.beta, metrics.statuses["beta"]),
    }

    aggregated = aggregate(metric_input)
    qualitative = _qualitative_layer(state)
    score = _clamp(aggregated.score + qualitative.delta)

    verdict = HumanReadableVerdict(
        score=score,
        signal=Signal(signal_for(score)),
        reasons=aggregated.reasons + qualitative.reasons,
        color_class=ColorClass(color_class_for(score)),
    )

    payload = QuantVerdictPayload(
        raw_metrics=metrics.to_dto(),
        human_verdict=verdict,
        chart_markers=backtest.markers,
        metric_status=metrics.to_status_map(),
        symbol=state["symbol"],
        candles=backtest.candles,
        dates=backtest.dates,
        equity_curve=[point.value for point in backtest.equity_curve],
        trades=[
            TradeDTO(
                date=trade.date.isoformat(),
                side=trade.side,
                shares=trade.shares,
                price=trade.price,
                commission=trade.commission,
                stamp_tax=trade.stamp_tax,
                transfer_fee=trade.transfer_fee,
                pnl=trade.pnl,
            )
            for trade in backtest.trades
        ],
        debate=[
            DebateDTO(
                round=entry.round,
                side=entry.side.value,
                argument=entry.argument,
                conviction=entry.conviction,
            )
            for entry in state.get("debate", [])
        ],
        warnings=list(state.get("warnings", [])),
    )
    return {"verdict": payload}


class _Qualitative:
    __slots__ = ("delta", "reasons")

    def __init__(self, delta: float, reasons: list[str]) -> None:
        self.delta = delta
        self.reasons = reasons


def _qualitative_layer(state: dict) -> _Qualitative:
    """Debate + sentiment adjust the score by at most +/-15 points.

    They may only nudge the deterministic score. If a model could move it by
    fifty points, the verdict would be a coin flip wearing a lab coat.
    """
    debate = state.get("debate", [])
    bull = max((e.conviction for e in debate if e.side is DebaterSide.BULL), default=0.0)
    bear = max((e.conviction for e in debate if e.side is DebaterSide.BEAR), default=0.0)
    net = bull - bear

    sentiment = state.get("sentiment")
    polarity = sentiment.polarity if sentiment is not None and sentiment.available else 0.0

    delta = max(-_QUALITATIVE_CAP, min(_QUALITATIVE_CAP, net * 10.0 + polarity * 5.0))
    reasons: list[str] = []
    if net > 0:
        reasons.append(f"多空辩论后多方证据占优（净信念 {net:+.2f}）")
    elif net < 0:
        reasons.append(f"多空辩论后空方证据占优（净信念 {net:+.2f}）")
    else:
        reasons.append("多空双方均未形成压倒性证据，结论以量化指标为主")

    if sentiment is not None and sentiment.available:
        reasons.append(
            f"舆情极性 {polarity:+.2f}（{sentiment.buzz} 条信息），"
            + ("情绪偏暖" if polarity > 0.15 else "情绪偏冷" if polarity < -0.15 else "情绪中性")
        )
    return _Qualitative(round(delta, 2), reasons)


def _clamp(value: float) -> int:
    return int(max(0.0, min(100.0, round(value))))
