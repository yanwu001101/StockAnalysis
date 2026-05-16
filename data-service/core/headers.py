# -*- coding: utf-8 -*-
"""HTTP header pools: User-Agent / Referer / Cookie rotation.

Goals:
  * Look like real browsers (Chrome/Edge/Firefox latest), not "python-requests".
  * Domain-aware Referer so each call carries a plausible origin.
  * Cookie jar that survives across calls within the same domain.
"""
from __future__ import annotations
import random
import threading
from typing import Dict, Optional
from urllib.parse import urlparse

# Curated UA pool (refreshed periodically). Falls back to fake-useragent if installed.
_FALLBACK_UAS = [
    # Chrome on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    # Edge on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) "
    "Gecko/20100101 Firefox/125.0",
    # Safari on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

try:
    from fake_useragent import UserAgent
    _UA = UserAgent(browsers=["chrome", "edge", "firefox", "safari"])
    def _random_ua() -> str:
        try:
            return _UA.random
        except Exception:
            return random.choice(_FALLBACK_UAS)
except Exception:
    def _random_ua() -> str:
        return random.choice(_FALLBACK_UAS)


# Per-domain Referer that looks like a real browse path
_REFERER_MAP: Dict[str, str] = {
    "push2delay.eastmoney.com": "https://quote.eastmoney.com/",
    "push2.eastmoney.com": "https://quote.eastmoney.com/",
    "push2his.eastmoney.com": "https://quote.eastmoney.com/",
    "datacenter.eastmoney.com": "https://data.eastmoney.com/",
    "datacenter-web.eastmoney.com": "https://data.eastmoney.com/",
    "data.eastmoney.com": "https://data.eastmoney.com/",
    "f10.eastmoney.com": "https://emweb.securities.eastmoney.com/",
    "emweb.securities.eastmoney.com": "https://emweb.securities.eastmoney.com/",
    "web.ifzq.gtimg.cn": "https://gu.qq.com/",
    "qt.gtimg.cn": "https://gu.qq.com/",
    "money.finance.sina.com.cn": "https://finance.sina.com.cn/",
    "stock.finance.sina.com.cn": "https://finance.sina.com.cn/",
    "vip.stock.finance.sina.com.cn": "https://finance.sina.com.cn/",
    "stock.xueqiu.com": "https://xueqiu.com/",
    "xueqiu.com": "https://xueqiu.com/",
    "d.10jqka.com.cn": "https://stockpage.10jqka.com.cn/",
    "basic.10jqka.com.cn": "https://stockpage.10jqka.com.cn/",
}


def referer_for(url: str) -> Optional[str]:
    host = urlparse(url).hostname or ""
    return _REFERER_MAP.get(host)


def build(url: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Build a per-request header dict with rotated UA + domain Referer."""
    h = {
        "User-Agent": _random_ua(),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
    }
    ref = referer_for(url)
    if ref:
        h["Referer"] = ref
    if extra:
        h.update(extra)
    return h


# ---------------------------------------------------------------------------
# Cookie jar: per-domain, in-memory, thread-safe. Sources that need warm-up
# (e.g. Xueqiu xq_a_token) call `seed(host, cookies)` after their first call.
# ---------------------------------------------------------------------------

_JAR: Dict[str, Dict[str, str]] = {}
_JAR_LOCK = threading.Lock()


def get_cookies(host: str) -> Dict[str, str]:
    with _JAR_LOCK:
        return dict(_JAR.get(host, {}))


def seed(host: str, cookies: Dict[str, str]) -> None:
    if not cookies:
        return
    with _JAR_LOCK:
        bag = _JAR.setdefault(host, {})
        bag.update(cookies)


def clear(host: Optional[str] = None) -> None:
    with _JAR_LOCK:
        if host is None:
            _JAR.clear()
        else:
            _JAR.pop(host, None)
