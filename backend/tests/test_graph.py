"""End-to-end: the whole LangGraph runs on the synthetic market."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from app.agents.runner import run_analysis
from app.agents.state import GraphDeps
from app.config import Settings
from app.domain.models import TaskStatus
from app.domain.ports import TaskRepositoryPort
from app.infrastructure.mongo_client import InMemoryTaskRepository
from app.services.data_fetcher import SyntheticMarketDataAdapter
from app.services.llm_factory import HeuristicLLMAdapter

from tests.conftest import RecordingPublisher


@pytest.mark.asyncio
async def test_graph_produces_verdict(settings: Settings, publisher: RecordingPublisher) -> None:
    repository: TaskRepositoryPort = InMemoryTaskRepository()
    deps = GraphDeps(
        market_data=SyntheticMarketDataAdapter(),
        llm=HeuristicLLMAdapter(),
        progress=publisher,
        settings=settings,
    )

    task = await run_analysis("task-e2e", "600519", deps, repository, settings)

    assert task.status is TaskStatus.COMPLETED
    assert task.verdict is not None
    payload = task.verdict
    # 契约字段齐全
    assert set(payload.raw_metrics.model_dump().keys()) == {
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "total_return",
        "alpha",
        "beta",
    }
    assert payload.human_verdict.reasons
    assert payload.human_verdict.color_class.value.startswith("text-")
    assert payload.symbol == "600519"
    # candles 与 dates 等长同序；markers 是其子集且日期必须能对上
    assert payload.candles
    assert len(payload.dates) == len(payload.candles)
    assert len(payload.chart_markers) <= len(payload.dates)
    date_set = set(payload.dates)
    assert all(marker.date in date_set for marker in payload.chart_markers)
    assert payload.metric_status is not None

    # 每个 agent 都推过进度
    agents = {frame.agent_id.value for frame in publisher.progress}
    assert {"fundamental", "sentiment", "technical", "risk"} <= agents
    assert not publisher.errors


@pytest.mark.asyncio
async def test_graph_survives_bad_symbol(settings: Settings, publisher: RecordingPublisher) -> None:
    repository = InMemoryTaskRepository()
    deps = GraphDeps(
        market_data=SyntheticMarketDataAdapter(),
        llm=HeuristicLLMAdapter(),
        progress=publisher,
        settings=settings,
    )
    task = await run_analysis("task-bad", "999999", deps, repository, settings)
    # 合成适配器对任何代码都返回数据 -> 正常完成（真实适配器才会 404/停牌）
    assert task.status is TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_publisher_frames_are_json_safe(publisher: RecordingPublisher) -> None:
    from app.domain.models import AgentProgressPayload, AgentId, AgentStatus

    publisher.publish_progress(
        AgentProgressPayload(
            task_id="t1",
            agent_id=AgentId.TECHNICAL,
            agent_name="技术面与回测",
            status=AgentStatus.RUNNING,
            progress=0.5,
            message="测试",
        )
    )
    frame = publisher.progress[0]
    assert frame.model_dump(by_alias=True)["agentId"] == "technical"
