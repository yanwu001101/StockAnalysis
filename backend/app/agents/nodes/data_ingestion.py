"""Node 1 — DataIngestionNode.

Fetches adjusted (前复权) daily bars for the target and for the benchmark,
then applies the domain guards: empty, suspended, delisted, too short. Nothing
downstream ever sees a raw source frame.
"""
from __future__ import annotations

from app.domain.errors import AlphaForgeError
from app.domain.models import AgentId, AgentStatus, Bar
from app.services.data_fetcher import raise_unless_usable
from app.agents.nodes._progress import emit


def data_ingestion_node(state: dict) -> dict:
    deps = state["deps"]
    settings = deps.resolved()
    symbol = state["symbol"]

    # 数据采集不是一个"agent"，挂在第一个 agent 上占位，卡片立刻亮起呼吸灯。
    emit(state, AgentId.TECHNICAL, AgentStatus.PENDING, 0.0, "正在获取 A 股行情数据…")

    try:
        bars: list[Bar] = list(
            deps.market_data.fetch_daily_bars(symbol, settings.kline_lookback_days)
        )
        raise_unless_usable(
            bars, settings.min_bars_required, settings.stale_after_days
        )
        emit(
            state,
            AgentId.TECHNICAL,
            AgentStatus.RUNNING,
            0.05,
            f"已载入 {len(bars)} 根前复权日 K 线，正在获取基准指数…",
        )
        benchmark: list[Bar] = list(
            deps.market_data.fetch_benchmark_bars(
                settings.benchmark_symbol, settings.kline_lookback_days
            )
        )
    except AlphaForgeError as exc:
        emit(state, AgentId.TECHNICAL, AgentStatus.FAILED, 0.0, exc.message)
        return {"failed": True, "error": exc.message, "warnings": [exc.message]}

    benchmark_closes = {bar.date: bar.close for bar in benchmark}
    warnings: list[str] = []
    if not benchmark_closes:
        warnings.append("未获取到基准指数行情，alpha / beta 将标记为不可计算")

    emit(
        state,
        AgentId.TECHNICAL,
        AgentStatus.RUNNING,
        0.10,
        f"行情就绪：{symbol} × {len(bars)} 根，基准 × {len(benchmark_closes)} 根",
    )
    return {
        "bars": bars,
        "benchmark_bars": benchmark,
        "benchmark_closes": benchmark_closes,
        "warnings": warnings,
        "failed": False,
        "error": None,
    }
