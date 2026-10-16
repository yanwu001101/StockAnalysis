"""WebSocket endpoint: /ws/v1/progress/{taskId}.

Protocol (every frame is a ``WsEnvelope`` JSON):

* server -> client: ``progress`` | ``verdict`` | ``heartbeat`` | ``error``
* client -> server: ``{"type": "ping"}`` -> answered with a ``heartbeat``
  frame, so the frontend's 30s heartbeat has a server-side counterpart.

On connect the endpoint replays the current state: if the task already
finished, the verdict is pushed immediately (a late subscriber must not have
to poll). Otherwise the connection joins the task's socket group and the
publisher starts watching the Redis bus for it.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.deps import get_manager, get_publisher, get_query_service
from app.domain.errors import TaskNotFoundError
from app.domain.models import WsEnvelope

log = logging.getLogger(__name__)

router = APIRouter()

_WS_CLOSE_TASK_NOT_FOUND = 4404


@router.websocket("/ws/v1/progress/{task_id}")
async def progress_socket(websocket: WebSocket, task_id: str) -> None:
    manager = get_manager()
    publisher = get_publisher()
    queries = get_query_service()

    # Validate before accepting: an unknown task must fail fast, not as a
    # silent black hole the frontend has to time out on.
    try:
        queries.get(task_id)
    except TaskNotFoundError:
        await websocket.close(code=_WS_CLOSE_TASK_NOT_FOUND, reason="unknown task id")
        return

    await websocket.accept()
    try:
        await manager.connect(task_id, websocket)
    except Exception as exc:  # noqa: BLE001 — TooManyConnectionsError and friends
        log.debug("ws connect refused for %s: %s", task_id, exc)
        await websocket.close(code=1013, reason=str(exc))
        return

    publisher.watch(task_id)
    await _replay_state(websocket, queries, task_id)

    try:
        while True:
            message = await websocket.receive_text()
            if _is_ping(message):
                await websocket.send_text(
                    WsEnvelope(
                        type="heartbeat", task_id=task_id, payload={"server": "pong"}
                    ).model_dump_json(by_alias=True, exclude_none=True)
                )
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.debug("ws receive loop ended for %s: %s", task_id, exc)
    finally:
        await manager.disconnect(task_id, websocket)
        if not manager.subscribers(task_id):
            publisher.unwatch(task_id)


async def _replay_state(websocket: WebSocket, queries, task_id: str) -> None:  # type: ignore[no-untyped-def]
    """Push the verdict immediately if the task already completed."""
    try:
        verdict = queries.get_verdict(task_id)
    except Exception:  # noqa: BLE001 — TaskNotFoundError / TaskNotReadyError
        return
    await websocket.send_text(
        WsEnvelope(type="verdict", task_id=task_id, payload=verdict).model_dump_json(
            by_alias=True, exclude_none=True
        )
    )


def _is_ping(message: str) -> bool:
    return '"ping"' in message or message.strip().lower() == "ping"
