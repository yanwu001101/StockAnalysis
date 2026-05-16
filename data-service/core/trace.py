# -*- coding: utf-8 -*-
"""Structured logging + Prometheus metrics.

Call `setup_logging()` once at app start. Modules use
    from core.trace import logger
    logger.info("event", code="600519", source="eastmoney")
"""
from __future__ import annotations
import logging
import os
import time
from contextlib import contextmanager
from typing import Iterator

try:
    import structlog
    _HAS_STRUCTLOG = True
except Exception:
    _HAS_STRUCTLOG = False

try:
    from prometheus_client import Counter, Histogram, Gauge
    _HAS_PROM = True
except Exception:
    _HAS_PROM = False


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

def setup_logging(level: str | None = None) -> None:
    lvl = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if _HAS_STRUCTLOG:
        structlog.configure(
            processors=[
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.dev.ConsoleRenderer()
                if os.getenv("APP_ENV", "dev") == "dev"
                else structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, lvl)),
            cache_logger_on_first_use=True,
        )


def get_logger(name: str = "data-service"):
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return logging.getLogger(name)


logger = get_logger()


# ---------------------------------------------------------------------------
# Metrics (no-op when prometheus_client is missing)
# ---------------------------------------------------------------------------

class _NoopMetric:
    def labels(self, **_kw): return self
    def inc(self, *_a, **_kw): pass
    def observe(self, *_a, **_kw): pass
    def set(self, *_a, **_kw): pass


if _HAS_PROM:
    REQUEST_TOTAL = Counter(
        "ds_request_total", "External HTTP requests by source/result",
        ["source", "result"],
    )
    REQUEST_LATENCY = Histogram(
        "ds_request_latency_seconds", "Request latency by source",
        ["source"], buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
    )
    CIRCUIT_STATE = Gauge(
        "ds_circuit_state", "Circuit breaker state (0=closed,1=half,2=open)",
        ["source"],
    )
    PIPELINE_ROWS = Counter(
        "ds_pipeline_rows_total", "Rows upserted by pipeline",
        ["pipeline"],
    )
else:
    REQUEST_TOTAL = _NoopMetric()       # type: ignore[assignment]
    REQUEST_LATENCY = _NoopMetric()     # type: ignore[assignment]
    CIRCUIT_STATE = _NoopMetric()       # type: ignore[assignment]
    PIPELINE_ROWS = _NoopMetric()       # type: ignore[assignment]


@contextmanager
def timed(source: str) -> Iterator[None]:
    """Use as `with timed("eastmoney"):` around an external call."""
    t0 = time.monotonic()
    try:
        yield
        REQUEST_LATENCY.labels(source=source).observe(time.monotonic() - t0)
    except Exception:
        REQUEST_LATENCY.labels(source=source).observe(time.monotonic() - t0)
        raise


def record_request(source: str, ok: bool) -> None:
    REQUEST_TOTAL.labels(source=source, result="ok" if ok else "err").inc()
