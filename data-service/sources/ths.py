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
from sources.base import AbstractSource


CONCEPT_LIST_URL = "https://q.10jqka.com.cn/gn/"


class ThsSource(AbstractSource):
    name = "ths"

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
