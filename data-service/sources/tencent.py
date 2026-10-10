# -*- coding: utf-8 -*-
"""Tencent finance source — primary K-line provider (most reliable free feed).

Daily/weekly/monthly: web.ifzq.gtimg.cn appstock kline
Minute (1/5/15/30/60min): web.ifzq.gtimg.cn appstock minute / m5+ history
Realtime quote (light): qt.gtimg.cn  (not used here)
"""
from __future__ import annotations
import asyncio
import json
import random
import re
import time
from typing import Optional

import pandas as pd

from core import http_client, parser
from sources.base import AbstractSource


KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
MIN_KLINE_URL = "https://ifzq.gtimg.cn/appstock/app/kline/mkline"
QUOTE_URL = "https://qt.gtimg.cn/q="

_PERIOD_MAP = {"daily": "day", "weekly": "week", "monthly": "month"}
_MIN_PERIODS = {"5min": "m5", "15min": "m15", "30min": "m30", "60min": "m60"}
_VAR_RE = re.compile(r"^[^=]*=")


def _tx_sym(code: str) -> str:
    c = parser.normalize_code(code)
    # 92/8/4 开头的北交所必须先于「9→沪」判断,否则 920xxx 会错映射成 sh
    if c[0] in ("4", "8") or c.startswith("92"):
        return f"bj{c}"
    if c[0] == "6" or c[0] == "9":
        return f"sh{c}"
    return f"sz{c}"


def _strip_var(text: str) -> Optional[dict]:
    if not text:
        return None
    body = _VAR_RE.sub("", text.strip().rstrip(";"))
    try:
        return json.loads(body)
    except Exception:
        return None


# qt.gtimg.cn 批量行情字段位(实测 2026-10;北交所字段数 87 vs 沪深 88,前 46 位一致)
_QT_NAME, _QT_CODE, _QT_PRICE = 1, 2, 3
_QT_PREV_CLOSE, _QT_OPEN = 4, 5
_QT_TIME, _QT_CHANGE, _QT_PCT = 30, 31, 32
_QT_HIGH, _QT_LOW, _QT_VOLUME, _QT_AMOUNT = 33, 34, 36, 37   # 量=手, 额=万元
_QT_TURNOVER, _QT_PE, _QT_AMPLITUDE = 38, 39, 43
_QT_FLOAT_CAP, _QT_TOTAL_CAP, _QT_PB = 44, 45, 46           # 市值单位=亿


def _parse_quote_line(line: str) -> Optional[dict]:
    """v_sh600000="1~浦发银行~600000~..." -> 单行行情 dict(单位见常量注释)。"""
    if "=" not in line:
        return None
    payload = line.split("=", 1)[1].strip().strip('"').strip(";").strip('"')
    f = payload.split("~")
    if len(f) <= _QT_PB:
        return None
    def _num(i: int) -> Optional[float]:
        v = f[i]
        if v in ("", "-"):
            return None
        try:
            return float(v)
        except ValueError:
            return None
    price = _num(_QT_PRICE)
    if price is None or price <= 0:
        return None
    return {
        "symbol": f"{_QT_CODE}",
        "code": str(f[_QT_CODE]).zfill(6),
        "name": f[_QT_NAME],
        "price": price,
        "pct_change": _num(_QT_PCT),
        "change": _num(_QT_CHANGE),
        "volume": _num(_QT_VOLUME),
        "amount_wan": _num(_QT_AMOUNT),
        "turnover": _num(_QT_TURNOVER),
        "pe": _num(_QT_PE),
        "amplitude": _num(_QT_AMPLITUDE),
        "high": _num(_QT_HIGH),
        "low": _num(_QT_LOW),
        "open": _num(_QT_OPEN),
        "prev_close": _num(_QT_PREV_CLOSE),
        "float_cap_yi": _num(_QT_FLOAT_CAP),
        "total_cap_yi": _num(_QT_TOTAL_CAP),
        "pb": _num(_QT_PB),
        "quote_time": f[_QT_TIME],
    }


async def fetch_quote_rows(symbols: list[str]) -> list[dict]:
    """一批 qt.gtimg.cn 行情(≤100 个 sh/sz/bj 前缀代码)。失败返回空列表。"""
    if not symbols:
        return []
    url = QUOTE_URL + ",".join(symbols)
    text = await http_client.get_text(url, source="tencent")
    if not text:
        return []
    rows = []
    for line in text.split(";"):
        row = _parse_quote_line(line.strip())
        if row:
            rows.append(row)
    return rows


def _stock_info_codes() -> list[str]:
    """stock_info 全代码表(约 5900 只,含北交所)。DB 不可用返回空。

    前缀白名单剔除 81 开头的定向可转债(带行情价但非股票)与 B 股。
    """
    try:
        from repo.base import fetch_df
        df = fetch_df(
            "SELECT code FROM stock_info WHERE code REGEXP '^(00|30|60|68|43|83|87|92)'",
            {},
        )
        if df is None or df.empty:
            return []
        return df["code"].astype(str).str.zfill(6).tolist()
    except Exception:
        return []


_INDUSTRY_CACHE: tuple[float, dict[str, str]] | None = None
_INDUSTRY_TTL = 3600.0


def stock_industry_map() -> dict[str, str]:
    """code → 行业(stock_info 基础表,东财行业口径)。

    qt.gtimg.cn 行情不含行业,板块涨跌/领涨板块/板块强度全靠本映射补列。
    行业为慢变参考属性,模块级缓存 1 小时;DB 不可用返回空 dict(调用方跳过补列)。
    """
    global _INDUSTRY_CACHE
    now = time.time()
    if _INDUSTRY_CACHE is not None and now - _INDUSTRY_CACHE[0] < _INDUSTRY_TTL:
        return _INDUSTRY_CACHE[1]
    m: dict[str, str] = {}
    try:
        from repo.base import fetch_df
        df = fetch_df("SELECT code, industry FROM stock_info", {})
        if df is not None and not df.empty:
            for code, ind in zip(df["code"].astype(str).str.zfill(6),
                                 df["industry"].astype(str).str.strip()):
                if ind and ind not in ("-", "None", "nan"):
                    m[code] = ind
    except Exception:
        pass
    if m:
        _INDUSTRY_CACHE = (now, m)
    return m


class TencentSource(AbstractSource):
    name = "tencent"

    async def fetch_spot(self, codes: Optional[list[str]] = None) -> pd.DataFrame:
        """全市场实时快照(英文列,单位与 eastmoney v2 对齐:量=手,额=元,市值=元)。

        codes 缺省时从 stock_info 取全代码表(约 5900 只;近 3 月新上市个股
        因基础表未刷新会缺席,对按市值排序的宇宙选择无影响)。
        行业列由 stock_industry_map 从 stock_info 补(行情接口本身不含行业);
        缺行业填 "-",与消费方既有过滤惯例一致。
        """
        if codes is None:
            codes = await asyncio.to_thread(_stock_info_codes)
        codes = [str(c).zfill(6) for c in codes]
        rows: list[dict] = []
        batch = 80
        for i in range(0, len(codes), batch):
            chunk = await fetch_quote_rows([_tx_sym(c) for c in codes[i:i + batch]])
            rows.extend(chunk)
            if i + batch < len(codes):
                await asyncio.sleep(random.uniform(0.15, 0.35))
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).drop_duplicates(subset=["code"])
        for col in ("price", "pct_change", "change", "volume", "turnover", "pe",
                    "amplitude", "high", "low", "open", "prev_close", "pb"):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["amount"] = pd.to_numeric(df["amount_wan"], errors="coerce") * 1e4
        df["market_cap"] = pd.to_numeric(df["total_cap_yi"], errors="coerce") * 1e8
        df["float_cap"] = pd.to_numeric(df["float_cap_yi"], errors="coerce") * 1e8
        df["market_cap_yi"] = pd.to_numeric(df["total_cap_yi"], errors="coerce")
        ind = await asyncio.to_thread(stock_industry_map)
        if ind:
            df["industry"] = df["code"].map(ind).fillna("-")
        return df.drop(columns=["amount_wan", "total_cap_yi", "float_cap_yi"])

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
        # mkline uses the compact `symbol,period,,count` form. The fqkline
        # endpoint accepts daily bars but silently returns no minute payload.
        params = {
            "param": f"{sym},{_MIN_PERIODS[period]},,{count}",
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
        if df.empty:
            return df
        for col in ("open", "close", "high", "low"):
            df = df[pd.to_numeric(df[col], errors="coerce") > 0]
        return df.reset_index(drop=True)


_default = TencentSource()


def default() -> TencentSource:
    return _default
