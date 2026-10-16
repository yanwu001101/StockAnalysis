"""WebSocket connection manager + the progress publisher that feeds it.

Responsibilities, per the architecture spec:

* **ConnectionManager** — per-task socket registry, max connections per task,
  heartbeat (server-side ping with timeout), clean disconnect, and fan-out of
  frames to every socket subscribed to a task.
* **WebSocketProgressPublisher** — implements ``ProgressPublisherPort`` on top
  of the Redis bus. Frames published by this worker are delivered locally
  without a Redis round-trip; frames from other workers arrive via pub/sub.

Reconnection is a *client* concern (exponential backoff in the Pinia store);
the server only has to survive it: a reconnect is just a fresh ``connect``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

from app.config import Settings, get_settings
from app.domain.errors import TooManyConnectionsError
from app.domain.models import (
    AgentProgressPayload,
    QuantVerdictPayload,
    WsEnvelope,
)
from app.domain.ports import ProgressPublisherPort
from app.infrastructure.redis_client import RedisProgressPublisher

log = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks live sockets per task and broadcasts frames to them."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._sockets: dict[str, set[WebSocket]] = {}
        self._heartbeats: dict[int, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            current = self._sockets.setdefault(task_id, set())
            if len(current) >= self._settings.ws_max_connections_per_task:
                raise TooManyConnectionsError(
                    f"task {task_id} already has {len(current)} connections"
                )
            current.add(websocket)
        self._start_heartbeat(task_id, websocket)

    async def disconnect(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self._sockets.get(task_id)
            if sockets is not None:
                sockets.discard(websocket)
                if not sockets:
                    self._sockets.pop(task_id, None)
        heartbeat = self._heartbeats.pop(id(websocket), None)
        if heartbeat is not None and not heartbeat.done():
            heartbeat.cancel()

    def subscribers(self, task_id: str) -> int:
        return len(self._sockets.get(task_id, ()))

    def tasks(self) -> list[str]:
        return list(self._sockets)

    async def broadcast(self, task_id: str, frame: str) -> None:
        """Fan one JSON frame out to every socket of a task. Never raises."""
        sockets = list(self._sockets.get(task_id, ()))
        if not sockets:
            return
        results = await asyncio.gather(
            *(self._send(ws, frame) for ws in sockets), return_exceptions=True
        )
        for websocket, result in zip(sockets, results):
            if isinstance(result, Exception):
                log.debug("dropping dead socket for task %s: %s", task_id, result)
                await self.disconnect(task_id, websocket)

    async def close_all(self) -> None:
        async with self._lock:
            sockets = [ws for group in self._sockets.values() for ws in group]
            self._sockets.clear()
            heartbeats = list(self._heartbeats.values())
            self._heartbeats.clear()
        for heartbeat in heartbeats:
            heartbeat.cancel()
        await asyncio.gather(*(ws.close() for ws in sockets), return_exceptions=True)

    # ------------------------------------------------------------ internals

    @staticmethod
    async def _send(websocket: WebSocket, frame: str) -> None:
        await websocket.send_text(frame)

    def _start_heartbeat(self, task_id: str, websocket: WebSocket) -> None:
        interval = self._settings.ws_server_ping_interval_s

        async def _beat() -> None:
            try:
                while True:
                    await asyncio.sleep(interval)
                    if websocket.client_state.name != "CONNECTED":
                        return
                    await websocket.send_text(
                        WsEnvelope(
                            type="heartbeat", task_id=task_id, payload={"server": "ping"}
                        ).model_dump_json(by_alias=True, exclude_none=True)
                    )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — dead socket, drop it
                log.debug("heartbeat failed for task %s: %s", task_id, exc)
                await self.disconnect(task_id, websocket)

        self._heartbeats[id(websocket)] = asyncio.create_task(_beat())


class WebSocketProgressPublisher:
    """``ProgressPublisherPort`` backed by the Redis bus + local manager."""

    name = "websocket"

    def __init__(
        self,
        manager: ConnectionManager,
        settings: Settings | None = None,
        bus: RedisProgressPublisher | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._manager = manager
        self._bus = bus or RedisProgressPublisher(
            self._settings, on_local=self._on_local_frame
        )
        self._unsubscribers: dict[str, Any] = {}
        # The publisher is built on the app's event loop (lifespan), but frames
        # are published from graph worker threads. Capturing the loop here lets
        # _dispatch hand work back from ANY thread — get_running_loop() would
        # raise inside a worker thread and silently drop the frame.
        try:
            self._loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    # ------------------------------------------------------------ interface

    def publish_progress(self, payload: AgentProgressPayload) -> None:
        self._bus.publish_progress(payload)

    def publish_verdict(self, task_id: str, payload: QuantVerdictPayload) -> None:
        self._bus.publish_verdict(task_id, payload)

    def publish_error(self, task_id: str, message: str) -> None:
        self._bus.publish_error(task_id, message)

    # ------------------------------------------------------------ lifecycle

    def watch(self, task_id: str) -> None:
        """Subscribe to the bus once per task (first WebSocket wins)."""
        if task_id in self._unsubscribers:
            return
        try:
            self._unsubscribers[task_id] = self._bus.subscribe(
                task_id, self._on_remote_frame
            )
        except Exception as exc:  # noqa: BLE001 — bus is optional
            log.debug("bus watch failed for %s: %s", task_id, exc)

    def unwatch(self, task_id: str) -> None:
        unsubscribe = self._unsubscribers.pop(task_id, None)
        if unsubscribe is None:
            return
        try:
            unsubscribe()
        except Exception as exc:  # noqa: BLE001
            log.debug("bus unwatch failed for %s: %s", task_id, exc)

    # ------------------------------------------------------------ internals

    def _on_local_frame(self, task_id: str, frame: str) -> None:
        """Frame published by this process — hand it straight to the sockets."""
        self._dispatch(task_id, frame)

    def _on_remote_frame(self, frame: str) -> None:
        """Frame published by another worker — parse the task id, then fan out."""
        try:
            envelope = WsEnvelope.model_validate_json(frame)
        except Exception as exc:  # noqa: BLE001
            log.debug("unparseable bus frame dropped: %s", exc)
            return
        self._dispatch(envelope.task_id, frame)

    def _dispatch(self, task_id: str, frame: str) -> None:
        manager = self._manager
        if not manager.subscribers(task_id):
            return

        async def _send() -> None:
            await manager.broadcast(task_id, frame)

        loop = self._loop
        if loop is None or loop.is_closed():
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return  # no loop reachable from this thread — nothing to do
        if loop is self._loop:
            loop.create_task(_send())
        else:
            asyncio.run_coroutine_threadsafe(_send(), loop)

    def health(self) -> bool:
        return self._bus.health()
