"""MongoDB task repository (CQRS persistence) with an in-memory fallback.

The repository is deliberately dumb: it stores and returns ``AnalysisTask``
documents. All business rules stay in the services layer. MongoDB is reached
through the synchronous driver inside short-lived calls from worker threads
(the same rule as every other port).

``InMemoryTaskRepository`` is the fallback when Mongo is absent and the
default in tests — the API surface is identical, so callers cannot tell the
difference.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.domain.models import AnalysisTask, SystemStats, TaskStatus
from app.domain.ports import TaskRepositoryPort

log = logging.getLogger(__name__)

_COLLECTION = "analysis_tasks"


class InMemoryTaskRepository:
    """Process-local repository. Single worker only; never use in production."""

    name = "memory"

    def __init__(self) -> None:
        self._tasks: dict[str, AnalysisTask] = {}
        self._lock = threading.Lock()

    def create(self, task: AnalysisTask) -> AnalysisTask:
        with self._lock:
            self._tasks[task.task_id] = task
        return task

    def save(self, task: AnalysisTask) -> AnalysisTask:
        task.updated_at = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        with self._lock:
            self._tasks[task.task_id] = task
        return task

    def get(self, task_id: str) -> AnalysisTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def stats(self) -> SystemStats:
        with self._lock:
            tasks = list(self._tasks.values())
        return _stats_of(tasks)

    def count(self) -> int:
        with self._lock:
            return len(self._tasks)


def _stats_of(tasks: list[AnalysisTask]) -> SystemStats:
    total = len(tasks)
    completed = sum(1 for task in tasks if task.status is TaskStatus.COMPLETED)
    failed = sum(1 for task in tasks if task.status is TaskStatus.FAILED)
    running = sum(
        1
        for task in tasks
        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING)
    )
    finished = completed + failed
    success_rate = completed / finished if finished > 0 else 0.0
    return SystemStats(
        total=total,
        running=running,
        completed=completed,
        failed=failed,
        success_rate=round(success_rate, 4),
    )


class MongoTaskRepository:
    name = "mongo"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = self._connect()
        self._indexed = False

    def _connect(self):
        try:
            from pymongo import MongoClient

            client = MongoClient(
                self._settings.mongo_uri,
                serverSelectionTimeoutMS=self._settings.mongo_timeout_ms,
                uuidRepresentation="standard",
            )
            client.admin.command("ping")
            log.info("mongo connected: %s/%s", self._settings.mongo_uri, self._settings.mongo_db)
            self._ensure_index(client)
            return client
        except Exception as exc:  # noqa: BLE001 — persistence is required
            log.error("mongo unavailable (%s); falling back to memory", exc)
            return None

    def _ensure_index(self, client) -> None:
        if self._indexed:
            return
        database = client[self._settings.mongo_db]
        database[_COLLECTION].create_index("task_id", unique=True)
        database[_COLLECTION].create_index("created_at")
        self._indexed = True

    @property
    def _collection(self):
        return self._client[self._settings.mongo_db][_COLLECTION]

    # ------------------------------------------------------------ interface

    def create(self, task: AnalysisTask) -> AnalysisTask:
        if self._client is None:
            return self._memory.create(task)
        document = task.model_dump(mode="json")
        document["_id"] = task.task_id
        self._collection.insert_one(document)
        return task

    def save(self, task: AnalysisTask) -> AnalysisTask:
        task.updated_at = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        if self._client is None:
            return self._memory.save(task)
        document = task.model_dump(mode="json")
        self._collection.replace_one({"_id": task.task_id}, document, upsert=True)
        return task

    def get(self, task_id: str) -> AnalysisTask | None:
        if self._client is None:
            return self._memory.get(task_id)
        document = self._collection.find_one({"_id": task_id})
        if document is None:
            return None
        document.pop("_id", None)
        return AnalysisTask.model_validate(document)

    def stats(self) -> SystemStats:
        if self._client is None:
            return self._memory.stats()
        collection = self._collection
        total = int(collection.count_documents({}))
        completed = int(collection.count_documents({"status": TaskStatus.COMPLETED.value}))
        failed = int(collection.count_documents({"status": TaskStatus.FAILED.value}))
        running = total - completed - failed
        finished = completed + failed
        success_rate = completed / finished if finished > 0 else 0.0
        return SystemStats(
            total=total,
            running=max(running, 0),
            completed=completed,
            failed=failed,
            success_rate=round(success_rate, 4),
        )

    @property
    def _memory(self) -> InMemoryTaskRepository:
        if not hasattr(self, "_memory_repo"):
            self._memory_repo = InMemoryTaskRepository()
        return self._memory_repo

    def health(self) -> bool:
        if self._client is None:
            return False
        try:
            self._client.admin.command("ping")
            return True
        except Exception:  # noqa: BLE001
            return False


def build_task_repository(settings: Settings | None = None) -> TaskRepositoryPort:
    resolved = settings or get_settings()
    if resolved.persistence == "mongo":
        return MongoTaskRepository(resolved)
    return InMemoryTaskRepository()
