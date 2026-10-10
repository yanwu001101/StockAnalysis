# -*- coding: utf-8 -*-
"""Sina finance source — K-line fallback when Tencent fails."""
from __future__ import annotations
from typing import Any

import pandas as pd

from core import http_client, parser
from sources.base import AbstractSource


KLINE_URL = (
    "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "CN_MarketData.getKLineData"
)

# 个股资金流历史（每日一行:r0~r3 净额,单位元）。
# 东财 fflow daykline 2026-09 起被墙,此接口是主力资金管线的可用主源。
MONEYFLOW_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "MoneyFlow.ssl_qsfx_lscjfb"
)

_SCALE_MAP = {"daily": 240, "weekly": 1680, "monthly": 7200}


def _sina_sym(code: str) -> str:
    c = parser.normalize_code(code)
    return f"sh{c}" if c[0] in ("6", "9") else f"sz{c}"


def _mf_sym(code: str) -> str:
    c = parser.normalize_code(code)
    if c[0] in ("6", "9"):
        return f"sh{c}"
    if c[:2] in ("43", "83", "87", "92"):
        return f"bj{c}"
    return f"sz{c}"


def _f(v: Any) -> float | None:
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


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

    async def fetch_index_kline(self, secid: str, count: int = 900) -> pd.DataFrame:
        """指数日线（新浪 symbol 形如 'sh000300' / 'sz399001'）。

        东财 push2his 被限时的第二腿：这些 bar 同时充当回测器的交易日历，
        停更会让最近窗口的会话表被静默截断。
        """
        sym = str(secid or "").strip()
        if "." in sym:  # 东财 secid 形态 '1.000300' → 新浪 'sh000300'
            mkt, code = sym.split(".", 1)
            sym = ("sh" if mkt in ("1", "sh") else "sz") + code
        params = {"symbol": sym, "scale": 240, "ma": 5, "datalen": count}
        obj = await http_client.get_json(KLINE_URL, params=params, source=self.name)
        if not isinstance(obj, list) or not obj:
            return pd.DataFrame()
        rows = []
        for row in obj:
            rows.append({
                "code": sym[-6:],
                "trade_date": row.get("day"),
                "open": float(row["open"]) if row.get("open") else None,
                "close": float(row["close"]) if row.get("close") else None,
                "high": float(row["high"]) if row.get("high") else None,
                "low": float(row["low"]) if row.get("low") else None,
                "volume": float(row.get("volume")) if row.get("volume") else None,
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        return df

    async def fetch_moneyflow(self, code: str, days: int = 60) -> pd.DataFrame:
        params = {
            "page1": 1,
            "num": min(max(days, 1), 60),
            "sort": "opendate",
            "asc": 0,
            "daima": _mf_sym(code),
        }
        obj = await http_client.get_json(MONEYFLOW_URL, params=params, source=self.name)
        if not isinstance(obj, list) or not obj:
            return pd.DataFrame()
        rows = []
        for row in obj:
            r0 = _f(row.get("r0_net"))
            r1 = _f(row.get("r1_net"))
            rows.append({
                "code": parser.normalize_code(code),
                "trade_date": row.get("opendate"),
                "super_large_net": r0,
                "large_net": r1,
                "medium_net": _f(row.get("r2_net")),
                "small_net": _f(row.get("r3_net")),
                # 主力=超大+大(与东财口径一致);r1 缺失时置 None,不拿 netamount 冒充
                "main_net": (r0 + r1) if (r0 is not None and r1 is not None) else None,
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        return df


_default = SinaSource()


def default() -> SinaSource:
    return _default
