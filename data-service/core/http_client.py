# -*- coding: utf-8 -*-
"""Unified HTTP client for source adapters.

Wraps httpx.AsyncClient with:
  * Per-domain rate limiting (token bucket + adaptive)
  * Tenacity-based retry on transient errors
  * Per-source circuit breaker
  * Rotating User-Agent / domain Referer / per-host cookie jar
  * Optional proxy pool
  * Prometheus latency + success metrics

Source adapters call:
    from core.http_client import get_text, get_json, get_jsonp
    text = await get_text(url, source="eastmoney")
"""
from __future__ import annotations
import asyncio
import threading
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from config import settings
from core import circuit, headers, parser, proxy, ratelimit, trace
from core.retry import retry, FatalError


# ---------------------------------------------------------------------------
# Async clients — 每个事件循环各持一份。
#
# httpx.AsyncClient 的连接池与 anyio 内部锁绑定在首次驱动它的事件循环上。
# 本服务大量同步入口(tx_realtime / pipelines / 调度器 / 各 job)习惯用
# asyncio.run() 临时新建循环来跑同一段异步代码,若共享同一个 client,
# 第二个循环再去拿这把属于已关闭循环的锁就会永久阻塞——实测并发全市场
# 抓取会把 gunicorn 的 worker 全部挂死,连 /health 都不返回(CPU 0%)。
# 故按循环持有客户端,并回收已关闭循环的残留。
# ---------------------------------------------------------------------------

_clients: dict[asyncio.AbstractEventLoop, httpx.AsyncClient] = {}
_clients_guard = threading.Lock()


def _new_client() -> httpx.AsyncClient:
    limits = httpx.Limits(
        max_connections=settings.http.max_connections,
        max_keepalive_connections=settings.http.max_keepalive,
    )
    timeout = httpx.Timeout(
        settings.http.timeout_s,
        connect=settings.http.connect_timeout_s,
    )
    return httpx.AsyncClient(
        http2=settings.http.http2,
        limits=limits,
        timeout=timeout,
        verify=settings.http.verify_ssl,
        follow_redirects=True,
    )


async def _get_client() -> httpx.AsyncClient:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is not None and not client.is_closed:
        return client
    # 循环已关闭 → 连接池作废,只能丢引用(asyncio.run 退出时该循环已清理)
    for dead in [k for k in _clients if k is not loop and k.is_closed()]:
        _clients.pop(dead, None)
    with _clients_guard:
        client = _clients.get(loop)
        if client is None or client.is_closed:
            client = _new_client()
            _clients[loop] = client
    return client


async def shutdown() -> None:
    for client in list(_clients.values()):
        try:
            await client.aclose()
        except Exception:
            pass
    _clients.clear()


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------

class HttpStatusError(Exception):
    def __init__(self, status_code: int, url: str, body: str = ""):
        super().__init__(f"HTTP {status_code} for {url}")
        self.status_code = status_code
        self.url = url
        self.body = body


@retry()
async def _do_get(
    url: str,
    params: dict | None,
    extra_headers: dict | None,
    source: str,
    proxy_url: Optional[str],
) -> str:
    cb = circuit.get(source)
    if not cb.allow():
        raise FatalError(f"circuit open for source={source}")

    await ratelimit.default().acquire_async(url)
    host = urlparse(url).hostname or ""
    hdr = headers.build(url, extra_headers)
    cookies = headers.get_cookies(host) or None

    client = await _get_client()
    req_kw: dict[str, Any] = {
        "params": params,
        "headers": hdr,
        "cookies": cookies,
    }
    if proxy_url:
        # httpx supports per-request proxy via mounts only; for one-shot use a temp client
        async with httpx.AsyncClient(
            proxies=proxy_url,
            http2=settings.http.http2,
            timeout=client.timeout,
            verify=settings.http.verify_ssl,
            follow_redirects=True,
        ) as tmp:
            r = await tmp.get(url, **req_kw)
    else:
        r = await client.get(url, **req_kw)

    # Capture any new cookies the server set for this host
    if r.cookies:
        new = {c: r.cookies.get(c) for c in r.cookies.keys()}
        headers.seed(host, new)

    ratelimit.default().report(url, status_code=r.status_code, ok=r.is_success)
    cb.record(r.is_success or r.status_code in (404,))
    trace.record_request(source, ok=r.is_success)

    if r.status_code >= 400:
        # Status >= 500 / 408 / 429 will be retried by tenacity; others fatal.
        if r.status_code >= 500 or r.status_code in (408, 429):
            r.raise_for_status()
        raise FatalError(f"HTTP {r.status_code} {url}")
    return r.text


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def get_text(
    url: str,
    *,
    params: dict | None = None,
    extra_headers: dict | None = None,
    source: str = "default",
) -> Optional[str]:
    """Return body text or None on failure (after retries / circuit-open)."""
    pool = proxy.default()
    pr = pool.pick() if pool.enabled() else None
    try:
        with trace.timed(source):
            text = await _do_get(url, params, extra_headers, source, pr)
        if pr:
            pool.report(pr, True)
        return text
    except FatalError as e:
        trace.logger.debug("fetch fatal: %s", e)
    except Exception as e:
        if pr:
            pool.report(pr, False)
        trace.logger.debug("fetch failed url=%s err=%s", url, e)
    return None


async def get_json(
    url: str, *, params: dict | None = None, source: str = "default",
    extra_headers: dict | None = None,
) -> Any:
    text = await get_text(url, params=params, extra_headers=extra_headers, source=source)
    return parser.parse_json(text) if text else None


async def get_jsonp(
    url: str, *, params: dict | None = None, source: str = "default",
    extra_headers: dict | None = None,
) -> Any:
    text = await get_text(url, params=params, extra_headers=extra_headers, source=source)
    return parser.parse_jsonp(text) if text else None


# ---------------------------------------------------------------------------
# Sync helpers (for use inside Flask request handlers)
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine from sync code, creating a new loop when needed."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(coro)).result()


def get_text_sync(url: str, **kw) -> Optional[str]:
    return run(get_text(url, **kw))


def get_json_sync(url: str, **kw) -> Any:
    return run(get_json(url, **kw))


def get_jsonp_sync(url: str, **kw) -> Any:
    return run(get_jsonp(url, **kw))
