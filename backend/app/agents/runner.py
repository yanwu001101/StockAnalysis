"""Task runner: drives one graph invocation to completion.

Runs the graph on a worker thread (AkShare and the backtest are blocking and
must never touch the request handler's event loop), keeps the task record in
the repository up to date, and streams progress through the publisher port.

``graph.stream`` is used instead of ``invoke`` so each node's completion is
observable; ``settings.debug_step_delay_ms`` (0 by default) inserts an
artificial pause between nodes — a frontend/dev aid for watching the progress
panel on fast synthetic runs. It is never set in production.
"""
from __future__ import annotations

import asyncio
import logging

from app.agents.graph import build_graph
from app.agents.state import GraphDeps, GraphState
from app.config import Settings, get_settings
from app.domain.models import AnalysisTask, TaskStatus
from app.domain.ports import ProgressPublisherPort, TaskRepositoryPort

log = logging.getLogger(__name__)

_graph = None


def _compiled():
    global _graph
    if _graph is None:
        _graph = build_graph()
    return _graph


async def run_analysis(
    task_id: str,
    symbol: str,
    deps: GraphDeps,
    repository: TaskRepositoryPort,
    settings: Settings | None = None,
) -> AnalysisTask:
    resolved = settings or get_settings()

    task = repository.get(task_id) or AnalysisTask(task_id=task_id, symbol=symbol)
    task.status = TaskStatus.RUNNING
    task = repository.save(task)

    initial = GraphState(
        task_id=task_id,
        symbol=symbol,
        deps=deps,
        bars=[],
        benchmark_bars=[],
        benchmark_closes={},
        news=[],
        debate=[],
        debate_round=0,
        debate_max_rounds=max(1, min(3, resolved.debate_rounds)),
        warnings=[],
        failed=False,
        backtest_overrides=deps.backtest_overrides,
    )

    final: dict = {}
    try:
        # stream_mode="values" yields the full state after every node.
        chunks = await asyncio.to_thread(
            lambda: list(_compiled().stream(initial, stream_mode="values"))
        )
        for chunk in chunks:
            final = chunk
            if resolved.debug_step_delay_ms > 0:
                await asyncio.sleep(resolved.debug_step_delay_ms / 1000.0)
    except Exception as exc:  # noqa: BLE001 — the task record must survive
        log.exception("graph failed for task %s", task_id)
        task.status = TaskStatus.FAILED
        task.error = str(exc)
        task = repository.save(task)
        deps.progress.publish_error(task_id, str(exc))
        return task

    verdict = final.get("verdict")
    if final.get("failed") or verdict is None:
        task.status = TaskStatus.FAILED
        task.error = final.get("error") or "analysis produced no verdict"
        task = repository.save(task)
        deps.progress.publish_error(task_id, task.error or "unknown failure")
        return task

    task.status = TaskStatus.COMPLETED
    task.verdict = verdict
    task.error = None
    task = repository.save(task)
    deps.progress.publish_verdict(task_id, verdict)
    return task
