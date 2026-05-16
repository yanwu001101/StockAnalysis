# -*- coding: utf-8 -*-
"""Playwright browser pool.

Used only for sources behind JS-encrypted parameters (e.g. 同花顺 `hexin-v`).
For everything else, use core.http_client which is much faster.

Lazy init: the browser is only launched on first request. If playwright is
unavailable or ENABLE_PLAYWRIGHT=false, calls return None and source adapters
fall back to other paths.
"""
from __future__ import annotations
import asyncio
import threading
from typing import Optional

from config import settings
from core.trace import logger

_browser = None
_pw_ctx = None
_lock = threading.Lock()


def _enabled() -> bool:
    return settings.sources.enable_playwright


async def _ensure_browser():
    global _browser, _pw_ctx
    if _browser is not None:
        return _browser
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        logger.warning("playwright not installed: %s", e)
        return None
    _pw_ctx = await async_playwright().start()
    _browser = await _pw_ctx.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
    )
    logger.info("playwright browser ready")
    return _browser


async def fetch(url: str, wait_for: str | None = None, timeout_ms: int = 15000) -> Optional[str]:
    """Open `url`, optionally wait for a CSS selector, return rendered HTML.

    Returns None when playwright is disabled / unavailable.
    """
    if not _enabled():
        return None
    browser = await _ensure_browser()
    if browser is None:
        return None
    context = await browser.new_context(
        user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        viewport={"width": 1366, "height": 768},
    )
    page = await context.new_page()
    try:
        await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
        if wait_for:
            await page.wait_for_selector(wait_for, timeout=timeout_ms)
        return await page.content()
    finally:
        await context.close()


async def get_cookie(url: str, name: str, wait_ms: int = 1500) -> Optional[str]:
    """Visit `url`, wait briefly, then return cookie value `name` if present."""
    if not _enabled():
        return None
    browser = await _ensure_browser()
    if browser is None:
        return None
    context = await browser.new_context()
    page = await context.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=10000)
        await page.wait_for_timeout(wait_ms)
        cookies = await context.cookies()
        for c in cookies:
            if c.get("name") == name:
                return c.get("value")
        return None
    finally:
        await context.close()


async def shutdown() -> None:
    global _browser, _pw_ctx
    try:
        if _browser is not None:
            await _browser.close()
    finally:
        _browser = None
    try:
        if _pw_ctx is not None:
            await _pw_ctx.stop()
    finally:
        _pw_ctx = None
