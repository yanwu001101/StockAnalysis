# -*- coding: utf-8 -*-
"""Sina finance source — K-line fallback when Tencent fails."""
from __future__ import annotations

import pandas as pd

from core import http_client, parser
from sources.base import AbstractSource


KLINE_URL = (
    "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData"
)

_SCALE_MAP = {"daily": 240, "weekly": 1680, "monthly": 7200}


def _sina_sym(code: str) -> str:
    c = parser.normalize_code(code)
    return f"sh{c}" if c[0] in ("6", "9") else f"sz{c}"


class SinaSource(AbstractSource):
    name = "sina"

    async def fetch_kline(self, code: str, period: str = "daily", count: int = 250) -> pd.DataFrame:
        scale = _SCALE_MAP.get(period, 240)
        params = {
            "symbol": _sina_sym(code),
            "scale": scale,
            "ma": 5,
            "datalen": count,
        }
        obj = await http_client.get_json(KLINE_URL, params=params, source=self.name)
        if not isinstance(obj, list) or not obj:
            return pd.DataFrame()
        rows = []
        for row in obj:
            rows.append({
                "code": parser.normalize_code(code),
                "trade_date": row.get("day"),
                "open": float(row.get("open")) if row.get("open") else None,
                "close": float(row.get("close")) if row.get("close") else None,
                "high": float(row.get("high")) if row.get("high") else None,
                "low": float(row.get("low")) if row.get("low") else None,
                "volume": float(row.get("volume")) if row.get("volume") else None,
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        return df


_default = SinaSource()


def default() -> SinaSource:
    return _default
