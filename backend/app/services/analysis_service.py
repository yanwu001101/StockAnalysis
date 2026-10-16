"""CQRS split for the analysis lifecycle.

* ``AnalysisCommandService`` — the write side: validates the symbol, mints a
  task, persists it, and schedules the graph run on the shared executor. It
  never blocks the caller: ``submit`` returns as soon as the task exists.
* ``AnalysisQueryService`` — the read side: returns a task document, and
  enforces the "verdict only when completed" rule.

Both depend on ports only. The FastAPI layer is a thin adapter on top.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from app.agents.runner import run_analysis
from app.agents.state import GraphDeps
from app.config import Settings, get_settings
from app.domain.errors import TaskNotReadyError
from app.domain.models import (
    AnalysisTask,
    BacktestOverrides,
    QuantVerdictPayload,
    TaskStatus,
)
from app.domain.ports import LLMPort, MarketDataPort, ProgressPublisherPort, TaskRepositoryPort

log = logging.getLogger(__name__)


def _new_task_id() -> str:
    return uuid.uuid4().hex


class AnalysisCommandService:
    def __init__(
        self,
        repository: TaskRepositoryPort,
        market_data: MarketDataPort,
        llm: LLMPort,
        progress: ProgressPublisherPort,
        settings: Settings | None = None,
    ) -> None:
        self._repository = repository
        self._market_data = market_data
        self._llm = llm
        self._progress = progress
        self._settings = settings or get_settings()
        self._semaphore = asyncio.Semaphore(max(1, self._settings.max_concurrent_tasks))
        self._running: dict[str, asyncio.Task[AnalysisTask]] = {}

    def submit(self, symbol: str, overrides: BacktestOverrides | None = None) -> AnalysisTask:
        """Create the task and schedule its graph run. Returns immediately."""
        task = AnalysisTask(task_id=_new_task_id(), symbol=symbol)
        self._repository.create(task)

        deps = GraphDeps(
            market_data=self._market_data,
            llm=self._llm,
            progress=self._progress,
            settings=self._settings,
            backtest_overrides=overrides,
        )
        handle = asyncio.create_task(
            self._guarded_run(task.task_id, symbol, deps),
            name=f"analysis-{task.task_id}",
        )
        self._running[task.task_id] = handle
        handle.add_done_callback(lambda _: self._running.pop(task.task_id, None))
        return task

    async def _guarded_run(self, task_id: str, symbol: str, deps: GraphDeps) -> AnalysisTask:
        async with self._semaphore:
            return await run_analysis(task_id, symbol, deps, self._repository, self._settings)

    def running_count(self) -> int:
        return len(self._running)

    async def shutdown(self) -> None:
        """Cancel in-flight runs (used by the lifespan shutdown hook)."""
        handles = list(self._running.values())
        for handle in handles:
            handle.cancel()
        if handles:
            await asyncio.gather(*handles, return_exceptions=True)


class AnalysisQueryService:
    def __init__(self, repository: TaskRepositoryPort) -> None:
        self._repository = repository

    def get(self, task_id: str) -> AnalysisTask:
        task = self._repository.get(task_id)
        if task is None:
            from app.domain.errors import TaskNotFoundError

            raise TaskNotFoundError(f"task {task_id} does not exist")
        return task

    def get_verdict(self, task_id: str) -> QuantVerdictPayload:
        task = self.get(task_id)
        if task.status is not TaskStatus.COMPLETED or task.verdict is None:
            raise TaskNotReadyError(
                f"task {task_id} is {task.status.value}, verdict not available yet"
            )
        return task.verdict
