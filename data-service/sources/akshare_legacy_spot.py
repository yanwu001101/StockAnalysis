# -*- coding: utf-8 -*-
"""Stable broad A-share spot fallback via AkShare's legacy endpoint."""
from __future__ import annotations

import asyncio

import pandas as pd

from core import parser
from sources.base import AbstractSource


def _safe_spot() -> pd.DataFrame:
    try:
        import akshare as ak
        return ak.stock_zh_a_spot()
    except Exception:
        return pd.DataFrame()


class AkshareLegacySpotSource(AbstractSource):
    name = "akshare_legacy_spot"

    async def fetch_spot(self) -> pd.DataFrame:
        df = await asyncio.to_thread(_safe_spot)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "代码": "code",
            "名称": "name",
            "最新价": "price",
            "涨跌额": "change",
            "涨跌幅": "pct_change",
            "成交量": "volume",
            "成交额": "amount",
            "今开": "open",
            "最高": "high",
            "最低": "low",
            "昨收": "prev_close",
        })
        if "code" not in df:
            return pd.DataFrame()
        df["code"] = (
            df["code"].astype(str)
            .str.extract(r"(\d{6})", expand=False)
            .fillna("")
            .map(parser.normalize_code)
        )
        df = df[df["code"].astype(bool)]
        numeric_cols = [
            "price", "change", "pct_change", "volume", "amount",
            "open", "high", "low", "prev_close",
        ]
        df = parser.to_numeric_cols(df, numeric_cols)
        if "industry" not in df:
            df["industry"] = ""
        return df


_default = AkshareLegacySpotSource()


def default() -> AkshareLegacySpotSource:
    return _default
