# -*- coding: utf-8 -*-
"""Tencent finance source — primary K-line provider (most reliable free feed).

Daily/weekly/monthly: web.ifzq.gtimg.cn appstock kline
Minute (1/5/15/30/60min): web.ifzq.gtimg.cn appstock minute / m5+ history
Realtime quote (light): qt.gtimg.cn  (not used here)
"""
from __future__ import annotations
import json
import random
import re
from typing import Optional

import pandas as pd

from core import http_client, parser
from sources.base import AbstractSource


KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
MIN_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/mkline"

_PERIOD_MAP = {"daily": "day", "weekly": "week", "monthly": "month"}
_MIN_PERIODS = {"5min": "m5", "15min": "m15", "30min": "m30", "60min": "m60"}
_VAR_RE = re.compile(r"^[^=]*=")


def _tx_sym(code: str) -> str:
    c = parser.normalize_code(code)
    return f"sh{c}" if c[0] in ("6", "9") else f"sz{c}"


def _strip_var(text: str) -> Optional[dict]:
    if not text:
        return None
    body = _VAR_RE.sub("", text.strip().rstrip(";"))
    try:
        return json.loads(body)
    except Exception:
        return None


class TencentSource(AbstractSource):
    name = "tencent"

    async def fetch_kline(self, code: str, period: str = "daily", count: int = 250) -> pd.DataFrame:
        if period not in _PERIOD_MAP:
            return pd.DataFrame()
        sym = _tx_sym(code)
        period_key = f"{_PERIOD_MAP[period]}qfq"
        params = {
            "_var": f"kline_{period_key}",
            "param": f"{sym},{_PERIOD_MAP[period]},,,{count},qfq",
            "r": random.random(),
        }
        text = await http_client.get_text(KLINE_URL, params=params, source=self.name)
        obj = _strip_var(text)
        if not obj:
            return pd.DataFrame()
        data = (obj.get("data") or {}).get(sym) or {}
        klines = data.get(period_key) or data.get(_PERIOD_MAP[period]) or []
        if not klines:
            return pd.DataFrame()
        rows = []
        for k in klines:
            if len(k) < 6:
                continue
            rows.append({
                "code": parser.normalize_code(code),
                "trade_date": k[0],
                "open": float(k[1]) if k[1] else None,
                "close": float(k[2]) if k[2] else None,
                "high": float(k[3]) if k[3] else None,
                "low": float(k[4]) if k[4] else None,
                "volume": float(k[5]) * 100 if k[5] else None,   # 手 -> 股
                "amount": float(k[6]) if len(k) > 6 and k[6] else None,
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        return df

    async def fetch_minute_kline(
        self, code: str, period: str = "5min", count: int = 240
    ) -> pd.DataFrame:
        if period not in _MIN_PERIODS:
            return pd.DataFrame()
        sym = _tx_sym(code)
        params = {
            "param": f"{sym},{_MIN_PERIODS[period]},,,{count},qfq",
            "_var": f"m_{period}",
            "r": random.random(),
        }
        text = await http_client.get_text(MIN_KLINE_URL, params=params, source=self.name)
        obj = _strip_var(text)
        if not obj:
            return pd.DataFrame()
        data = (obj.get("data") or {}).get(sym) or {}
        klines = data.get(_MIN_PERIODS[period] + "qfq") or data.get(_MIN_PERIODS[period]) or []
        if not klines:
            return pd.DataFrame()
        rows = []
        for k in klines:
            if len(k) < 6:
                continue
            rows.append({
                "code": parser.normalize_code(code),
                "dt": k[0],
                "period": period,
                "open": float(k[1]) if k[1] else None,
                "close": float(k[2]) if k[2] else None,
                "high": float(k[3]) if k[3] else None,
                "low": float(k[4]) if k[4] else None,
                "volume": float(k[5]) * 100 if k[5] else None,
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["dt"] = pd.to_datetime(df["dt"], format="%Y%m%d%H%M", errors="coerce")
        return df


_default = TencentSource()


def default() -> TencentSource:
    return _default
