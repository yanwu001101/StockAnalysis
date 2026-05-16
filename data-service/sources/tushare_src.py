# -*- coding: utf-8 -*-
"""Tushare Pro source — optional, only active when TUSHARE_TOKEN is set.

Tushare gives clean financial statements, northbound holdings, and lhb data
with one API per dataset. Best feed when the user has an account.
"""
from __future__ import annotations
import asyncio
import datetime as dt
from typing import Optional

import pandas as pd

from config import settings
from core import parser
from sources.base import AbstractSource


_pro = None


def _client():
    global _pro
    if _pro is not None or not settings.sources.tushare_token:
        return _pro
    try:
        import tushare as ts
        ts.set_token(settings.sources.tushare_token)
        _pro = ts.pro_api()
    except Exception:
        _pro = None
    return _pro


def _ts_code(code: str) -> str:
    c = parser.normalize_code(code)
    return f"{c}.SH" if c[0] in ("6", "9") else f"{c}.SZ"


def _safe(fn, **kw) -> pd.DataFrame:
    try:
        return fn(**kw)
    except Exception:
        return pd.DataFrame()


class TushareSource(AbstractSource):
    name = "tushare"

    def enabled(self) -> bool:
        return _client() is not None

    async def fetch_fundamental(self, code: str, periods: int = 8) -> pd.DataFrame:
        pro = _client()
        if pro is None:
            return pd.DataFrame()
        df = await asyncio.to_thread(_safe, pro.fina_indicator, ts_code=_ts_code(code))
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.head(periods).rename(columns={
            "end_date": "report_date",
            "roe": "roe",
            "debt_to_assets": "debt_ratio",
            "grossprofit_margin": "gross_margin",
            "or_yoy": "revenue_yoy",
            "netprofit_yoy": "net_profit_yoy",
            "ocfps": "op_cashflow_ps",
            "eps": "eps",
            "bps": "bvps",
        })
        if "report_date" in df:
            df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce").dt.date
        df["code"] = parser.normalize_code(code)
        return df

    async def fetch_northbound_holdings(self, code: str, days: int = 60) -> pd.DataFrame:
        pro = _client()
        if pro is None:
            return pd.DataFrame()
        end = dt.date.today()
        start = end - dt.timedelta(days=days)
        df = await asyncio.to_thread(
            _safe, pro.hk_hold,
            code=_ts_code(code),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "trade_date": "trade_date",
            "vol": "hold_shares",
            "ratio": "hold_ratio",
        })
        if "trade_date" in df:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df["code"] = parser.normalize_code(code)
        return df


_default = TushareSource()


def default() -> TushareSource:
    return _default
