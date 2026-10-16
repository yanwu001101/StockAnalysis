"""Node 8 — DecisionAggregatorNode.

Runs the deterministic layer: the no-look-ahead signal rule and the A-share
execution simulator. This is the only place where a number that ends up in
``rawMetrics`` is produced — no model ever touches it.
"""
from __future__ import annotations

from app.agents.nodes._progress import emit
from app.domain.models import AgentId, AgentStatus, MetricStatus
from app.domain.results import MetricsResult
from app.services.backtest_engine import BacktestRequest, run_backtest
from app.services.signal_rule import SignalRule

_STATUS_LABELS = {
    "sharpe_ratio": "夏普比率",
    "max_drawdown": "最大回撤",
    "win_rate": "胜率",
    "total_return": "总收益率",
    "alpha": "阿尔法",
    "beta": "贝塔",
}


def decision_node(state: dict) -> dict:
    deps = state["deps"]
    settings = deps.resolved()
    bars = state["bars"]
    risk = state.get("risk")
    overrides = state.get("backtest_overrides")

    emit(
        state,
        AgentId.TECHNICAL,
        AgentStatus.RUNNING,
        0.92,
        "正在按 A 股成本模型执行确定性回测（佣金/印花税/过户费/整手/T+1）…",
    )

    cost = settings.cost_model
    initial_capital = settings.initial_capital
    window_note = ""
    if overrides is not None:
        cost = overrides.apply_to(cost)
        if overrides.initial_capital is not None:
            initial_capital = overrides.initial_capital
        start, end = overrides.resolved_window()
        if start is not None or end is not None:
            bars = [
                bar
                for bar in bars
                if (start is None or bar.date >= start) and (end is None or bar.date <= end)
            ]
            window_note = f"，日期窗口 {start or '…'} ~ {end or '…'}"

    rule = SignalRule()
    decisions = rule.decide(bars)

    request = BacktestRequest(
        symbol=state["symbol"],
        bars=bars,
        decisions=decisions,
        benchmark_closes=dict(state.get("benchmark_closes") or {}),
        cost=cost,
        initial_capital=initial_capital,
        risk_free_rate=settings.risk_free_rate,
        periods_per_year=settings.trading_days_per_year,
        position_scale=risk.position_scale if risk is not None else 1.0,
    )
    result = run_backtest(request)

    warnings = list(state.get("warnings", []))
    warnings.extend(_metric_warnings(result.metrics))

    trades = len(result.trades)
    if trades == 0:
        warnings.append("区间内没有产生任何成交，指标可能不具备参考意义")

    emit(
        state,
        AgentId.TECHNICAL,
        AgentStatus.COMPLETED,
        1.0,
        f"回测完成{window_note}：{trades} 笔成交，{len(result.markers)} 个交易信号",
    )
    return {"decisions": decisions, "backtest": result, "warnings": warnings}


def _metric_warnings(metrics: MetricsResult) -> list[str]:
    warnings: list[str] = []
    for key, label in _STATUS_LABELS.items():
        status = metrics.statuses.get(key, MetricStatus.VALID)
        if status is not MetricStatus.VALID:
            warnings.append(f"{label}不可计算（{status.value}），已按中性处理")
    return warnings
