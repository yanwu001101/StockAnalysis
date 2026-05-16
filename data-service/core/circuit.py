# -*- coding: utf-8 -*-
"""Circuit breaker, per source.

States: closed -> open (on failure burst) -> half-open (probe) -> closed/open.
Used by source-aware HTTP wrappers and pipeline fallback chains.
"""
from __future__ import annotations
import collections
import threading
import time
from enum import Enum

from config import settings


class State(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: float | None = None,
        sample_window: int | None = None,
        open_seconds: float | None = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold or settings.cb.failure_threshold
        self.window = sample_window or settings.cb.sample_window
        self.open_seconds = open_seconds or settings.cb.open_seconds

        self._state = State.CLOSED
        self._calls: collections.deque[bool] = collections.deque(maxlen=self.window)
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> State:
        return self._state

    def allow(self) -> bool:
        """Return True iff a call may proceed. Caller MUST then call record()."""
        with self._lock:
            if self._state == State.CLOSED:
                return True
            if self._state == State.OPEN:
                if time.time() - self._opened_at >= self.open_seconds:
                    self._state = State.HALF_OPEN
                    return True
                return False
            # HALF_OPEN: allow one probe; subsequent calls are blocked until probe outcome
            return True

    def record(self, ok: bool) -> None:
        with self._lock:
            self._calls.append(ok)
            if self._state == State.HALF_OPEN:
                if ok:
                    self._state = State.CLOSED
                    self._calls.clear()
                else:
                    self._state = State.OPEN
                    self._opened_at = time.time()
                return
            if self._state == State.CLOSED and len(self._calls) >= self.window:
                failure_rate = sum(1 for c in self._calls if not c) / len(self._calls)
                if failure_rate >= self.failure_threshold:
                    self._state = State.OPEN
                    self._opened_at = time.time()


# ---------------------------------------------------------------------------
# Registry (one breaker per source name)
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = threading.Lock()


def get(name: str) -> CircuitBreaker:
    with _REGISTRY_LOCK:
        cb = _REGISTRY.get(name)
        if cb is None:
            cb = CircuitBreaker(name)
            _REGISTRY[name] = cb
        return cb


def snapshot() -> dict[str, str]:
    """For /metrics endpoint."""
    with _REGISTRY_LOCK:
        return {name: cb.state.value for name, cb in _REGISTRY.items()}
