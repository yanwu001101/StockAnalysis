# -*- coding: utf-8 -*-
"""10jqka (同花顺) source — concept board members via playwright.

The concept-board page builds its DOM client-side from an XHR that requires the
`hexin-v` cookie (JS-derived). Easiest path is to render the page in headless
Chromium and read the table — slower but stable and rare (once per day).

If ENABLE_PLAYWRIGHT=false this source returns empty DataFrames so pipelines
fall through to akshare's `stock_board_concept_*` helpers.
"""
from __future__ import annotations
import re
from typing import Optional

import pandas as pd

from core import browser
from core import http_client, parser
from sources.base import AbstractSource


CONCEPT_LIST_URL = "https://q.10jqka.com.cn/gn/"
KLINE_URL = "https://d.10jqka.com.cn/v6/line/hs_{code}/{period}/last.js"
_PERIOD_MAP = {"daily": "01", "weekly": "11", "monthly": "21"}


class ThsSource(AbstractSource):
    name = "ths"

    async def fetch_kline(self, code: str, period: str = "daily", count: int = 250) -> pd.DataFrame:
        period_code = _PERIOD_MAP.get(period)
        if period_code is None:
            return pd.DataFrame()
        normalized = parser.normalize_code(code)
        text = await http_client.get_text(
            KLINE_URL.format(code=normalized, period=period_code),
            source=self.name,
            extra_headers={"Referer": "https://stockpage.10jqka.com.cn/"},
        )
        if not text:
            return pd.DataFrame()
        try:
            import json
            payload = json.loads(text[text.index("(") + 1:text.rindex(")")])
        except (ValueError, json.JSONDecodeError):
            return pd.DataFrame()
        rows = []
        for item in str(payload.get("data") or "").split(";"):
            fields = item.split(",")
            if len(fields) < 7:
                continue
            rows.append({
                "code": normalized, "trade_date": fields[0],
                "open": fields[1], "high": fields[2], "low": fields[3],
                "close": fields[4], "volume": fields[5], "amount": fields[6],
            })
        df = pd.DataFrame(rows).tail(count)
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
            df = parser.to_numeric_cols(df, ["open", "close", "high", "low", "volume", "amount"])
        return df

    async def fetch_concept_index(self) -> pd.DataFrame:
        html = await browser.fetch(CONCEPT_LIST_URL, wait_for="table.m-table", timeout_ms=15000)
        if not html:
            return pd.DataFrame()
        try:
            tables = pd.read_html(html)
        except Exception:
            return pd.DataFrame()
        if not tables:
            return pd.DataFrame()
        df = tables[0]
        # Normalize column names
        df = df.rename(columns={"代码": "concept_code", "概念名称": "concept_name", "涨跌幅": "pct_change"})
        if "concept_code" in df:
            df["concept_code"] = df["concept_code"].astype(str)
        return df

    async def fetch_concept_members(self, concept_code: Optional[str] = None) -> pd.DataFrame:
        """Stub — full implementation requires per-concept page; deferred to akshare."""
        return pd.DataFrame()


_default = ThsSource()


def default() -> ThsSource:
    return _default
