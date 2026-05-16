# -*- coding: utf-8 -*-
"""Adaptive per-domain rate limiter.

Token bucket per hostname. Each call:
  1. Awaits a token (rate = `_rates[host]` calls/sec).
  2. Adds [jitter_min, jitter_max] ms human-like delay.

After a call, callers report 2xx / 4xx-429 / 5xx; we automatically:
  * Halve the rate + insert cooldown on 429 / 418 / 403.
  * Slowly speed up after `speedup_after` consecutive successes.
"""
from __future__ import annotations
import asyncio
import random
import threading
import time
from typing import Dict
from urllib.parse import urlparse

from config import settings


class _Bucket:
    __slots__ = ("rate", "capacity", "tokens", "ts", "ok_streak", "cooldown_until")

    def __init__(self, rate: float, capacity: float):
        self.rate = rate                 # tokens per second
        self.capacity = capacity
        self.tokens = capacity
        self.ts = time.monotonic()
        self.ok_streak = 0
        self.cooldown_until = 0.0


class RateLimiter:
    def __init__(self):
        self._buckets: Dict[str, _Bucket] = {}
        self._lock = threading.Lock()
        self._alocks: Dict[str, asyncio.Lock] = {}

    def _bucket(self, host: str) -> _Bucket:
        b = self._buckets.get(host)
        if b is None:
            with self._lock:
                b = self._buckets.get(host)
                if b is None:
                    rate = float(settings.http.concurrency_default)
                    b = _Bucket(rate=rate, capacity=rate * 2)
                    self._buckets[host] = b
        return b

    def _alock(self, host: str) -> asyncio.Lock:
        lk = self._alocks.get(host)
        if lk is None:
            lk = asyncio.Lock()
            self._alocks[host] = lk
        return lk

    @staticmethod
    def _host(url: str) -> str:
        return urlparse(url).hostname or "_default"

    def _jitter(self) -> float:
        lo, hi = settings.rl.jitter_min_ms, settings.rl.jitter_max_ms
        return random.uniform(lo, hi) / 1000.0

    def _refill(self, b: _Bucket) -> None:
        now = time.monotonic()
        elapsed = now - b.ts
        b.tokens = min(b.capacity, b.tokens + elapsed * b.rate)
        b.ts = now

    def _wait_seconds(self, b: _Bucket) -> float:
        now = time.monotonic()
        if now < b.cooldown_until:
            return b.cooldown_until - now
        self._refill(b)
        if b.tokens >= 1.0:
            b.tokens -= 1.0
            return 0.0
        # Need 1 - tokens more; time = (1-tokens)/rate
        return max(0.0, (1.0 - b.tokens) / max(b.rate, 0.01))

    # -------- sync API --------
    def acquire(self, url: str) -> None:
        host = self._host(url)
        b = self._bucket(host)
        while True:
            with self._lock:
                wait = self._wait_seconds(b)
                if wait == 0.0:
                    break
            time.sleep(wait)
        time.sleep(self._jitter())

    # -------- async API --------
    async def acquire_async(self, url: str) -> None:
        host = self._host(url)
        b = self._bucket(host)
        lk = self._alock(host)
        async with lk:
            wait = self._wait_seconds(b)
        if wait > 0:
            await asyncio.sleep(wait)
        await asyncio.sleep(self._jitter())

    # -------- feedback --------
    def report(self, url: str, status_code: int | None = None, ok: bool | None = None) -> None:
        host = self._host(url)
        b = self._bucket(host)
        with self._lock:
            penalize = False
            if status_code is not None and status_code in (403, 418, 429):
                penalize = True
            elif ok is False:
                penalize = False  # network errors handled by retry, don't punish bucket
            if penalize:
                b.rate = max(0.5, b.rate * 0.5)
                b.cooldown_until = time.monotonic() + settings.rl.cooldown_s
                b.ok_streak = 0
            elif ok or (status_code and 200 <= status_code < 300):
                b.ok_streak += 1
                if b.ok_streak >= settings.rl.speedup_after:
                    b.ok_streak = 0
                    b.rate = min(b.capacity, b.rate * 1.25)


_default: RateLimiter | None = None


def default() -> RateLimiter:
    global _default
    if _default is None:
        _default = RateLimiter()
    return _default
