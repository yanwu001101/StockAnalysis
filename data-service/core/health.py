# -*- coding: utf-8 -*-
"""Health check service for all data sources.

Periodically pings each source and records availability metrics.
Used by the aggregator to reorder sources dynamically.
"""
from __future__ import annotations
import asyncio
import time
from dataclasses import dataclass
from typing import Dict, Optional

from core.trace import logger


@dataclass
class SourceHealth:
    name: str
    available: bool = True
    success_count: int = 0
    failure_count: int = 0
    last_success: float = 0.0
    last_failure: float = 0.0
    avg_latency_ms: float = 0.0
    circuit_open: bool = False

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 1.0

    @property
    def health_score(self) -> float:
        """0-100 score combining success rate, recency, and latency."""
        if not self.available or self.circuit_open:
            return 0.0

        # Success rate: 0-60 points
        rate_score = self.success_rate * 60

        # Recency: 0-20 points (last success within 5min = full points)
        time_since_success = time.time() - self.last_success
        recency_score = max(0, 20 - (time_since_success / 300) * 20)

        # Latency: 0-20 points (< 1s = full points, > 5s = 0 points)
        latency_score = max(0, 20 - (self.avg_latency_ms / 5000) * 20)

        return rate_score + recency_score + latency_score


class HealthChecker:
    def __init__(self):
        self._health: Dict[str, SourceHealth] = {}
        self._lock = asyncio.Lock()

    def record_success(self, source: str, latency_ms: float) -> None:
        """Record successful fetch."""
        async def _record():
            async with self._lock:
                h = self._health.setdefault(source, SourceHealth(name=source))
                h.success_count += 1
                h.last_success = time.time()
                # Exponential moving average for latency
                alpha = 0.3
                h.avg_latency_ms = alpha * latency_ms + (1 - alpha) * h.avg_latency_ms
                h.available = True
                h.circuit_open = False

        asyncio.create_task(_record())

    def record_failure(self, source: str, circuit_open: bool = False) -> None:
        """Record failed fetch."""
        async def _record():
            async with self._lock:
                h = self._health.setdefault(source, SourceHealth(name=source))
                h.failure_count += 1
                h.last_failure = time.time()
                if circuit_open:
                    h.circuit_open = True
                # Mark unavailable if too many recent failures
                if h.success_rate < 0.2:
                    h.available = False

        asyncio.create_task(_record())

    async def get_health(self, source: str) -> Optional[SourceHealth]:
        """Get health status for a source."""
        async with self._lock:
            return self._health.get(source)

    async def get_all_health(self) -> Dict[str, SourceHealth]:
        """Get health status for all sources."""
        async with self._lock:
            return dict(self._health)

    async def get_sorted_sources(self, sources: list) -> list:
        """Sort sources by health score (best first)."""
        async with self._lock:
            scored = []
            for src in sources:
                h = self._health.get(src.name, SourceHealth(name=src.name))
                scored.append((src, h.health_score))
            scored.sort(key=lambda x: x[1], reverse=True)
            return [src for src, _ in scored]


_checker: Optional[HealthChecker] = None


def default() -> HealthChecker:
    global _checker
    if _checker is None:
        _checker = HealthChecker()
    return _checker
