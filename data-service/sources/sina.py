# -*- coding: utf-8 -*-
"""Sina finance source — K-line fallback when Tencent fails."""
from __future__ import annotations
from typing import Any
import math

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
    if c.startswith(("4", "8", "92")):
        return f"bj{c}"
    return f"sh{c}" if c[0] in ("6", "9") else f"sz{c}"


def _mf_sym(code: str) -> str:
    c = parser.normalize_code(code)
    if c.startswith(("4", "8", "92")):
        return f"bj{c}"
    if c[0] in ("6", "9"):
        return f"sh{c}"
    return f"sz{c}"


def _f(v: Any) -> float | None:
    try:
        f = float(v)
        return f if math.isfinite(f) else None
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
        """个股每日资金流（新浪口径:r0=超大单 r1=大单 r2=中单 r3=小单,元）。

        主力净额 = 超大单 + 大单,与东财口径一致。大单缺失时主力净额
        置 None(不能拿 netamount 冒充主力口径,也不能写 0)。

        深度靠 `num` 一次拿满：实测 num=2000 不截断(单请求即 8 年历史),
        而 `page1=2` 返回与 page1=1 **完全相同**的行——分页参数被忽略。
        之前按 page 循环 + num=60 的写法看起来能加深,实际永远只有 60 天
        (库里 avg=60.4 天/只 就是这么来的),不要再写分页循环。
        """
        limit = min(max(int(days), 1), 2000)
        params = {"page1": 1, "num": limit, "sort": "opendate",
                  "asc": 0, "daima": _mf_sym(code)}
        obj = await http_client.get_json(MONEYFLOW_URL, params=params, source=self.name)
        if not isinstance(obj, list) or not obj:
            return pd.DataFrame()
        rows = []
        for row in obj:
            day = row.get("opendate")
            if not day:
                continue
            r0, r1 = _f(row.get("r0_net")), _f(row.get("r1_net"))
            rows.append({"code": parser.normalize_code(code), "trade_date": day,
                         "super_large_net": r0, "large_net": r1,
                         "medium_net": _f(row.get("r2_net")), "small_net": _f(row.get("r3_net")),
                         "main_net": r0 + r1 if r0 is not None and r1 is not None else None})
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        return (df.dropna(subset=["trade_date"])
                  .sort_values("trade_date").tail(limit).reset_index(drop=True))


_default = SinaSource()


def default() -> SinaSource:
    return _default
