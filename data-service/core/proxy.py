# -*- coding: utf-8 -*-
"""Proxy pool interface.

We don't ship a built-in proxy provider — many free pools are unreliable. Instead
this module reads `PROXY_POOL_URL` (a simple HTTP endpoint that returns
`http://host:port` plain text or JSON `{"proxy": "..."}`) and rotates fetched
proxies. When the env var is unset, callers go direct (the common case in dev).

Health-tracking: callers report success/failure; we down-weight bad proxies and
auto-evict ones that fail consecutively.
"""
from __future__ import annotations
import json
import random
import threading
import time
from typing import Optional

import httpx

from config import settings


class ProxyPool:
    def __init__(self, url: Optional[str] = None, refresh_s: float = 60.0):
        self._url = url or settings.sources.proxy_pool_url
        self._refresh_s = refresh_s
        self._proxies: list[str] = []
        self._fail: dict[str, int] = {}
        self._last_refresh = 0.0
        self._lock = threading.Lock()

    def enabled(self) -> bool:
        return bool(self._url)

    def _maybe_refresh(self) -> None:
        if not self._url:
            return
        now = time.time()
        if now - self._last_refresh < self._refresh_s and self._proxies:
            return
        with self._lock:
            if now - self._last_refresh < self._refresh_s and self._proxies:
                return
            try:
                with httpx.Client(timeout=5.0) as c:
                    r = c.get(self._url)
                    r.raise_for_status()
                    text = r.text.strip()
                # Accept either JSON {"proxy": "..."} / list, or newline-delimited
                proxies: list[str] = []
                try:
                    obj = json.loads(text)
                    if isinstance(obj, dict) and "proxy" in obj:
                        proxies = [str(obj["proxy"])]
                    elif isinstance(obj, list):
                        proxies = [str(x) for x in obj]
                except Exception:
                    proxies = [ln.strip() for ln in text.splitlines() if ln.strip()]
                # Normalize to scheme://host:port
                norm: list[str] = []
                for p in proxies:
                    if "://" not in p:
                        p = "http://" + p
                    norm.append(p)
                self._proxies = norm
                self._last_refresh = now
            except Exception:
                # Keep stale pool; report failure but don't crash.
                pass

    def pick(self) -> Optional[str]:
        self._maybe_refresh()
        if not self._proxies:
            return None
        # Weighted random: lower fail count gets higher weight
        items = self._proxies
        weights = [1.0 / (1 + self._fail.get(p, 0)) for p in items]
        return random.choices(items, weights=weights, k=1)[0]

    def report(self, proxy: str, ok: bool) -> None:
        with self._lock:
            if ok:
                self._fail.pop(proxy, None)
            else:
                self._fail[proxy] = self._fail.get(proxy, 0) + 1
                if self._fail[proxy] >= 5:
                    try:
                        self._proxies.remove(proxy)
                    except ValueError:
                        pass
                    self._fail.pop(proxy, None)


_default: Optional[ProxyPool] = None


def default() -> ProxyPool:
    global _default
    if _default is None:
        _default = ProxyPool()
    return _default
