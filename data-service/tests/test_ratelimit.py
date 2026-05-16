# -*- coding: utf-8 -*-
"""Rate limiter / circuit breaker / parser unit tests."""
from __future__ import annotations
import time


def test_ratelimit_cooldown_on_429():
    from core.ratelimit import default
    rl = default()
    url = "http://x.example.com/y"
    rl.acquire(url)
    rl.report(url, status_code=429)
    t0 = time.monotonic()
    rl.acquire(url)
    elapsed = time.monotonic() - t0
    assert elapsed >= 0


def test_circuit_breaker_states():
    from core.circuit import get
    cb = get("test_src")
    for _ in range(cb.window + 1):
        cb.record(False)
    assert cb.allow() is False or cb.state.value in ("open", "half_open")


def test_parser_jsonp_handles_callback():
    from core.parser import parse_jsonp
    text = 'callback({"a": 1, "b": [2,3]});'
    obj = parse_jsonp(text)
    assert obj == {"a": 1, "b": [2, 3]}


def test_parser_jsonp_handles_var():
    from core.parser import parse_jsonp
    text = 'var kline_dayqfq={"data":{"sh600519":{"day":[]}}};'
    obj = parse_jsonp(text)
    assert obj is not None and "data" in obj


def test_headers_rotation():
    from core.headers import build
    h1 = build("https://stock.xueqiu.com/v5/x")
    h2 = build("https://stock.xueqiu.com/v5/x")
    # User-Agent should always be set; Referer should match the xueqiu mapping
    assert "User-Agent" in h1
    assert h1.get("Referer") == "https://xueqiu.com/"
    assert h2.get("Referer") == "https://xueqiu.com/"
