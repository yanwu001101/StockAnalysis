"""Two-tier cache: Redis (shared with backend) with in-memory fallback.

Key namespace: `ds:*` to avoid colliding with backend's `stock:*` keys.
"""
from __future__ import annotations
import os
import time
import json
import pickle
import base64
import logging
from typing import Any, Callable

import pandas as pd

log = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD") or None
KEY_PREFIX = "ds:"

_redis = None
_mem: dict[str, tuple[Any, float, int]] = {}


def _client():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis
        _redis = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD,
            socket_connect_timeout=1.5, socket_timeout=2.0,
            decode_responses=False,
            health_check_interval=30,
        )
        _redis.ping()
        log.info("Redis connected: %s:%s", REDIS_HOST, REDIS_PORT)
    except Exception as e:
        log.warning("Redis unavailable, fallback to memory cache: %s", e)
        _redis = False
    return _redis


def _encode(val: Any) -> bytes:
    if isinstance(val, pd.DataFrame):
        return b"DF:" + pickle.dumps(val, protocol=4)
    try:
        return b"JS:" + json.dumps(val, ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError):
        return b"PK:" + pickle.dumps(val, protocol=4)


def _decode(raw: bytes) -> Any:
    if raw.startswith(b"DF:"):
        return pickle.loads(raw[3:])
    if raw.startswith(b"JS:"):
        return json.loads(raw[3:].decode("utf-8"))
    if raw.startswith(b"PK:"):
        return pickle.loads(raw[3:])
    return raw


def get(key: str) -> Any:
    full = KEY_PREFIX + key
    cli = _client()
    if cli:
        try:
            raw = cli.get(full)
            if raw is not None:
                return _decode(raw)
        except Exception as e:
            log.debug("redis get failed: %s", e)
    # mem fallback
    entry = _mem.get(full)
    if entry:
        val, ts, ttl = entry
        if time.time() - ts < ttl:
            return val
        _mem.pop(full, None)
    return None


def set(key: str, val: Any, ttl: int) -> None:
    full = KEY_PREFIX + key
    cli = _client()
    if cli:
        try:
            cli.setex(full, ttl, _encode(val))
            return
        except Exception as e:
            log.debug("redis set failed: %s", e)
    _mem[full] = (val, time.time(), ttl)


def get_or_fetch(key: str, ttl: int, fetcher: Callable[[], Any]) -> Any:
    cached = get(key)
    if cached is not None:
        return cached
    val = fetcher()
    if val is not None:
        try:
            set(key, val, ttl)
        except Exception as e:
            log.debug("cache write failed: %s", e)
    return val


def delete(key: str) -> None:
    full = KEY_PREFIX + key
    cli = _client()
    if cli:
        try:
            cli.delete(full)
        except Exception:
            pass
    _mem.pop(full, None)
