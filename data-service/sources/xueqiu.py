# -*- coding: utf-8 -*-
"""Xueqiu source — F10 / valuation history / institutional ratings.

Xueqiu requires a `xq_a_token` cookie which is set by the homepage. We seed it
in `warm_up()`; calls reuse the cookie via headers.get_cookies().
"""
from __future__ import annotations

import pandas as pd

from config import settings
from core import headers, http_client, parser
from sources.base import AbstractSource


QUOTE_URL = "https://stock.xueqiu.com/v5/stock/quote.json"
HOMEPAGE = "https://xueqiu.com/"


class XueqiuSource(AbstractSource):
    name = "xueqiu"

    async def warm_up(self) -> None:
        """Visit homepage so the server sets xq_a_token cookie in our jar."""
        await http_client.get_text(HOMEPAGE, source=self.name)
        if settings.sources.xueqiu_cookie:
            kv = {}
            for part in settings.sources.xueqiu_cookie.split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    kv[k] = v
            if kv:
                headers.seed("xueqiu.com", kv)
                headers.seed("stock.xueqiu.com", kv)

    async def fetch_quote(self, code: str) -> pd.DataFrame:
        c = parser.normalize_code(code)
        sym = f"SH{c}" if c[0] in ("6", "9") else f"SZ{c}"
        params = {"symbol": sym, "extend": "detail"}
        obj = await http_client.get_json(QUOTE_URL, params=params, source=self.name)
        q = ((obj or {}).get("data") or {}).get("quote") or {}
        if not q:
            return pd.DataFrame()
        return pd.DataFrame([{
            "code": c,
            "name": q.get("name", ""),
            "price": q.get("current"),
            "pct_change": q.get("percent"),
            "pe": q.get("pe_ttm"),
            "pb": q.get("pb"),
            "market_cap": q.get("market_capital"),
            "float_cap": q.get("float_market_capital"),
            "dividend_yield": q.get("dividend_yield"),
        }])


_default = XueqiuSource()


def default() -> XueqiuSource:
    return _default
