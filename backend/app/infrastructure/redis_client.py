"""Redis client: cache adapter + cross-worker progress bus.

Two adapters live here, both behind domain ports:

* ``RedisCacheAdapter`` — the ``CachePort`` used by the caching market-data
  decorator. Falls back to an in-process TTL dict when Redis is unreachable,
  so a cache outage degrades to "slower", never to "down".
* ``RedisProgressPublisher`` — the ``ProgressPublisherPort``. Publishes
  ``WsEnvelope`` frames to ``alphaforge:progress:<task_id>`` so every worker
  sees every frame; the WebSocket layer subscribes and fans out to its own
  local sockets.

The redis client is synchronous on purpose (see ports.py). All calls happen
inside worker threads or short async bridges, never on the request loop.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable

from app.config import Settings, get_settings
from app.domain.models import WsEnvelope

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# In-memory fallbacks (also the test doubles)
# ---------------------------------------------------------------------------


class InMemoryCache:
    """Bounded TTL dict. Good enough for a single worker and for tests."""

    def __init__(self, max_entries: int = 2048) -> None:
        self._entries: dict[str, tuple[str, float]] = {}
        self._max = max_entries
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._entries.get(key)
            if item is None:
                return None
            value, expires_at = item
            if expires_at <= time.monotonic():
                self._entries.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        with self._lock:
            if len(self._entries) >= self._max and key not in self._entries:
                oldest = min(self._entries, key=lambda k: self._entries[k][1])
                self._entries.pop(oldest, None)
            self._entries[key] = (value, time.monotonic() + max(ttl_seconds, 1))

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


# ---------------------------------------------------------------------------
# Redis cache adapter
# ---------------------------------------------------------------------------


class RedisCacheAdapter:
    name = "redis"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = self._connect()

    def _connect(self):
        try:
            import redis  # imported lazily: optional dependency

            client = redis.Redis.from_url(
                self._settings.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
                health_check_interval=30,
            )
            client.ping()
            log.info("redis cache connected")
            return client
        except Exception as exc:  # noqa: BLE001 — cache is best-effort
            log.warning("redis unavailable (%s); using in-memory cache", exc)
            return None

    def get(self, key: str) -> str | None:
        if self._client is None:
            return self._fallback.get(key)
        try:
            return self._client.get(key)
        except Exception as exc:  # noqa: BLE001
            log.debug("redis get failed: %s", exc)
            return self._fallback.get(key)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        if self._client is None:
            self._fallback.set(key, value, ttl_seconds)
            return
        try:
            self._client.setex(key, max(ttl_seconds, 1), value)
        except Exception as exc:  # noqa: BLE001
            log.debug("redis setex failed: %s", exc)
            self._fallback.set(key, value, ttl_seconds)

    @property
    def _fallback(self) -> InMemoryCache:
        if not hasattr(self, "_memory"):
            self._memory = InMemoryCache()
        return self._memory

    def health(self) -> bool:
        if self._client is None:
            return True  # degraded but serving
        try:
            return bool(self._client.ping())
        except Exception:  # noqa: BLE001
            return False


# ---------------------------------------------------------------------------
# Redis progress publisher
# ---------------------------------------------------------------------------


class RedisProgressPublisher:
    """Publishes WS envelopes to Redis; a local sink receives them too.

    ``on_local`` lets the WebSocket layer receive frames published by *this*
    process without a Redis round-trip, keeping latency low on the happy path
    while other workers still get the frame through pub/sub.
    """

    name = "redis"

    def __init__(
        self,
        settings: Settings | None = None,
        on_local: Callable[[str, str], None] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._on_local = on_local
        self._client = self._connect()

    def _connect(self):
        try:
            import redis

            client = redis.Redis.from_url(
                self._settings.redis_url, decode_responses=True, socket_timeout=2.0
            )
            client.ping()
            log.info("redis progress bus connected")
            return client
        except Exception as exc:  # noqa: BLE001 — bus is best-effort
            log.warning("redis pub/sub unavailable (%s); single-worker mode", exc)
            return None

    def _channel(self, task_id: str) -> str:
        return f"{self._settings.redis_channel_prefix}:{task_id}"

    def _publish(self, envelope: WsEnvelope) -> None:
        frame = envelope.model_dump_json(by_alias=True, exclude_none=True)
        task_id = envelope.task_id
        if self._on_local is not None:
            try:
                self._on_local(task_id, frame)
            except Exception as exc:  # noqa: BLE001 — a dead socket is not fatal
                log.debug("local progress sink failed: %s", exc)
        if self._client is None:
            return
        try:
            self._client.publish(self._channel(task_id), frame)
        except Exception as exc:  # noqa: BLE001
            log.debug("redis publish failed: %s", exc)

    def publish_progress(self, payload) -> None:  # type: ignore[no-untyped-def]
        self._publish(WsEnvelope(type="progress", task_id=payload.task_id, payload=payload))

    def publish_verdict(self, task_id: str, payload) -> None:  # type: ignore[no-untyped-def]
        self._publish(WsEnvelope(type="verdict", task_id=task_id, payload=payload))

    def publish_error(self, task_id: str, message: str) -> None:
        self._publish(
            WsEnvelope(type="error", task_id=task_id, payload={"message": message})
        )

    def subscribe(self, task_id: str, on_frame: Callable[[str], None]) -> Callable[[], None]:
        """Subscribe to a task channel; returns an unsubscribe callable.

        The listener runs on a daemon thread. When Redis is absent the
        returned callable is a no-op (single-worker mode needs no bus).
        """
        if self._client is None:
            return lambda: None

        pubsub = self._client.pubsub(ignore_subscribe_messages=True)
        channel = self._channel(task_id)

        def _listen() -> None:
            try:
                for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    on_frame(str(message.get("data", "")))
            except Exception as exc:  # noqa: BLE001 — listener death is logged only
                log.debug("progress listener for %s stopped: %s", task_id, exc)

        thread = threading.Thread(target=_listen, daemon=True, name=f"ws-bus-{task_id}")
        try:
            pubsub.subscribe(channel)
        except Exception as exc:  # noqa: BLE001
            log.debug("redis subscribe failed for %s: %s", task_id, exc)
            return lambda: None
        thread.start()

        def _unsubscribe() -> None:
            try:
                pubsub.unsubscribe(channel)
                pubsub.close()
            except Exception:  # noqa: BLE001
                pass

        return _unsubscribe

    def health(self) -> bool:
        if self._client is None:
            return True
        try:
            return bool(self._client.ping())
        except Exception:  # noqa: BLE001
            return False


def build_cache(settings: Settings | None = None) -> Any:
    """CachePort implementation chosen by settings (redis or in-memory)."""
    resolved = settings or get_settings()
    if resolved.cache_backend == "redis":
        return RedisCacheAdapter(resolved)
    return InMemoryCache()
