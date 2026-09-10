# -*- coding: utf-8 -*-
"""Browser-based scraper using Playwright — ultimate fallback when APIs fail.

Only enabled when ENABLE_PLAYWRIGHT=true. Uses headless Chromium to fetch data
from web pages that block headless requests.

Usage:
    from sources.browser import default as browser_src
    if browser_src().enabled():
        spot = await browser_src().fetch_spot()
"""
from __future__ import annotations
import asyncio
import json
import re
from typing import Optional

import pandas as pd

from config import settings
from core import parser
from core.trace import logger
from sources.base import AbstractSource


class BrowserSource(AbstractSource):
    name = "browser"

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._enabled = settings.sources.enable_playwright
        self._lock = asyncio.Lock()

    def enabled(self) -> bool:
        return self._enabled

    async def _ensure_browser(self):
        """Lazy init playwright browser."""
        if not self._enabled:
            raise RuntimeError("Playwright not enabled (set ENABLE_PLAYWRIGHT=true)")

        if self._browser is not None:
            return

        async with self._lock:
            if self._browser is not None:
                return

            try:
                from playwright.async_api import async_playwright
            except ImportError:
                logger.warning("playwright not installed; browser source disabled")
                self._enabled = False
                raise RuntimeError("playwright package not installed")

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = await self._browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            # Anti-detection
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            logger.info("playwright browser initialized")

    async def shutdown(self):
        """Cleanup browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._context = None
        self._browser = None
        self._playwright = None

    async def fetch_spot(self) -> pd.DataFrame:
        """Scrape eastmoney web page for spot data."""
        await self._ensure_browser()
        page = await self._context.new_page()
        try:
            # Eastmoney quote center
            url = "https://quote.eastmoney.com/center/gridlist.html#hs_a_board"
            await page.goto(url, wait_until="networkidle", timeout=30000)
            await page.wait_for_timeout(2000)

            # Extract data from the page's internal API call
            # The page uses push2 or push2delay endpoint; we intercept the response
            rows = []
            async with page.expect_response(
                lambda r: "api/qt/clist/get" in r.url,
                timeout=10000,
            ) as response_info:
                await page.reload()
                response = await response_info.value
                text = await response.text()
                try:
                    data = json.loads(text)
                    diff = ((data.get("data") or {}).get("diff") or [])
                    if isinstance(diff, dict):
                        diff = list(diff.values())
                    rows.extend(diff)
                except Exception as e:
                    logger.warning("browser spot: failed to parse response: %s", e)

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows).rename(columns={
                "f12": "code", "f14": "name", "f2": "price", "f3": "pct_change",
                "f5": "volume", "f6": "amount", "f8": "turnover", "f100": "industry",
                "f20": "market_cap", "f15": "high", "f16": "low", "f17": "open",
            })
            if "code" in df:
                df["code"] = df["code"].astype(str).str.zfill(6)
            df = parser.to_numeric_cols(df, [
                "price", "pct_change", "volume", "amount", "turnover",
                "market_cap", "high", "low", "open",
            ])
            if "market_cap" in df:
                df["market_cap_yi"] = df["market_cap"] / 1e8
            return df
        finally:
            await page.close()

    async def fetch_kline(self, code: str, period: str = "daily", count: int = 250) -> pd.DataFrame:
        """Scrape kline from eastmoney stock page."""
        await self._ensure_browser()
        code = parser.normalize_code(code)
        page = await self._context.new_page()
        try:
            # Navigate to stock detail page
            url = f"https://quote.eastmoney.com/{code}.html"
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Wait for K-line chart to load
            await page.wait_for_selector("#chart-container", timeout=10000)
            await page.wait_for_timeout(2000)

            # Extract K-line data from window object or API intercept
            kline_data = await page.evaluate("""
                () => {
                    // Try to extract from global chart data
                    if (window.chartData && window.chartData.klines) {
                        return window.chartData.klines;
                    }
                    return [];
                }
            """)

            if not kline_data:
                logger.warning("browser kline: no data found for %s", code)
                return pd.DataFrame()

            rows = []
            for item in kline_data:
                if isinstance(item, str):
                    parts = item.split(",")
                    if len(parts) >= 7:
                        rows.append({
                            "code": code,
                            "trade_date": parts[0],
                            "open": parts[1],
                            "close": parts[2],
                            "high": parts[3],
                            "low": parts[4],
                            "volume": parts[5],
                            "amount": parts[6],
                        })

            if not rows:
                return pd.DataFrame()

            df = pd.DataFrame(rows)
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
            df = parser.to_numeric_cols(df, ["open", "close", "high", "low", "volume", "amount"])
            return df.tail(count)
        finally:
            await page.close()


_default: Optional[BrowserSource] = None


def default() -> BrowserSource:
    global _default
    if _default is None:
        _default = BrowserSource()
    return _default
