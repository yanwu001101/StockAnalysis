# -*- coding: utf-8 -*-
"""Retry decorator built on tenacity.

Distinguishes:
  * Transient errors (network, 5xx, timeout) -> retry with exp backoff + jitter
  * Non-retryable (4xx auth, parse error) -> raise immediately
"""
from __future__ import annotations
import asyncio
import functools
import logging
from typing import Callable, Type

import httpx
from tenacity import (
    AsyncRetrying,
    Retrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from config import settings

log = logging.getLogger(__name__)


class TransientError(Exception):
    """Raise this to force a retry from non-network code paths."""


class FatalError(Exception):
    """Raise this to break out of retry early."""


_RETRYABLE_EXCEPTIONS: tuple[Type[BaseException], ...] = (
    httpx.TransportError,
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    TransientError,
    ConnectionError,
    TimeoutError,
)


def _should_retry_http(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        sc = exc.response.status_code
        # 5xx + 408 + 429 are retryable; 4xx auth/permission are not
        return sc >= 500 or sc in (408, 429)
    return isinstance(exc, _RETRYABLE_EXCEPTIONS)


def retry(
    attempts: int | None = None,
    min_wait: float | None = None,
    max_wait: float | None = None,
):
    """Sync/async aware retry decorator.

    Usage:
        @retry()
        async def fetch(): ...
    """
    a = attempts or settings.retry.max_attempts
    mn = min_wait or settings.retry.base_wait_s
    mx = max_wait or settings.retry.max_wait_s

    def decorator(fn: Callable):
        if asyncio.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def aw(*args, **kwargs):
                try:
                    async for attempt in AsyncRetrying(
                        stop=stop_after_attempt(a),
                        wait=wait_random_exponential(multiplier=mn, max=mx),
                        retry=retry_if_exception_type(BaseException),
                        reraise=True,
                    ):
                        with attempt:
                            try:
                                return await fn(*args, **kwargs)
                            except FatalError:
                                raise
                            except Exception as e:
                                if _should_retry_http(e):
                                    raise
                                raise FatalError(str(e)) from e
                except RetryError as e:
                    raise e.last_attempt.exception() or e
            return aw
        else:
            @functools.wraps(fn)
            def sw(*args, **kwargs):
                try:
                    for attempt in Retrying(
                        stop=stop_after_attempt(a),
                        wait=wait_random_exponential(multiplier=mn, max=mx),
                        retry=retry_if_exception_type(BaseException),
                        reraise=True,
                    ):
                        with attempt:
                            try:
                                return fn(*args, **kwargs)
                            except FatalError:
                                raise
                            except Exception as e:
                                if _should_retry_http(e):
                                    raise
                                raise FatalError(str(e)) from e
                except RetryError as e:
                    raise e.last_attempt.exception() or e
            return sw
    return decorator
