# -*- coding: utf-8 -*-
"""Abstract data source contract.

Every adapter (eastmoney/tencent/sina/...) implements a subset of these methods.
Pipelines query `available()` to decide which sources to chain for fallback.

All return values are pandas DataFrames with English column names matching the
fields on `models.py`. Empty DataFrame on miss; raise only on programming errors.
"""
from __future__ import annotations
import abc
import datetime as dt
from typing import Iterable

import pandas as pd


class AbstractSource(abc.ABC):
    name: str = "abstract"

    def available(self, capability: str) -> bool:
        return hasattr(self, capability) and callable(getattr(self, capability))

    # ---- capability stubs (override what you implement) ----

    async def fetch_spot(self) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_kline(
        self, code: str, period: str = "daily", count: int = 250
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_minute_kline(
        self, code: str, period: str = "5min", count: int = 240
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_fundamental(
        self, code: str, periods: int = 8
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_moneyflow(
        self, code: str, days: int = 60
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_northbound_holdings(
        self, code: str, days: int = 60
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_lhb(
        self, start: dt.date, end: dt.date
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_shareholder(
        self, code: str
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_dividend(
        self, code: str
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_concept_members(self) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()

    async def fetch_announcements(
        self, codes: Iterable[str], days: int = 7
    ) -> pd.DataFrame:  # noqa: B027
        return pd.DataFrame()
