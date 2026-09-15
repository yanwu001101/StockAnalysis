# -*- coding: utf-8 -*-
"""AkShare source adapter — last-resort fallback for spot/kline/fundamental.

AkShare is a synchronous library, so we wrap each call in asyncio.to_thread
to avoid blocking the event loop.
"""
from __future__ import annotations
import asyncio
import datetime as dt

import pandas as pd

from core import parser
from core.trace import logger
from sources.base import AbstractSource


class AkShareSource(AbstractSource):
    name = "akshare"

    async def fetch_spot(self) -> pd.DataFrame:
        """Fetch A-share spot via akshare.stock_zh_a_spot_em."""
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_zh_a_spot_em)
        except Exception as e:
            logger.debug("akshare spot_em failed: %s, trying spot_sina", e)
            try:
                import akshare as ak
                df = await asyncio.to_thread(ak.stock_zh_a_spot)
            except Exception as e2:
                logger.warning("akshare spot sources failed: %s", e2)
                return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # Normalize column names
        rename_map = {
            "代码": "code",
            "证券代码": "code",
            "名称": "name",
            "证券简称": "name",
            "最新价": "price",
            "收盘": "price",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "成交量": "volume",
            "成交额": "amount",
            "振幅": "amplitude",
            "换手率": "turnover",
            "市盈率": "pe",
            "量比": "vol_ratio",
            "最高": "high",
            "最低": "low",
            "今开": "open",
            "昨收": "prev_close",
            "总市值": "market_cap",
            "流通市值": "float_cap",
            "市净率": "pb",
            "行业": "industry",
            "所属行业": "industry",
            "板块名称": "industry",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        if "code" not in df.columns:
            return pd.DataFrame()

        df["code"] = df["code"].astype(str).str.zfill(6)
        df = parser.to_numeric_cols(df, [
            "price", "pct_change", "change", "volume", "amount",
            "turnover", "pe", "pb", "high", "low", "open", "prev_close",
            "market_cap", "float_cap", "vol_ratio", "amplitude",
        ])
        if "market_cap" in df.columns:
            df["market_cap_yi"] = df["market_cap"] / 1e8
        return df

    async def fetch_kline(self, code: str, period: str = "daily", count: int = 250) -> pd.DataFrame:
        """Fetch K-line via akshare.stock_zh_a_hist."""
        if period not in ("daily", "weekly", "monthly"):
            return pd.DataFrame()

        code = parser.normalize_code(code)
        end = dt.date.today()
        # Fetch more days to ensure we get enough trading days
        days_mult = {"daily": 1.5, "weekly": 10, "monthly": 40}
        start = end - dt.timedelta(days=int(count * days_mult.get(period, 2)))

        try:
            import akshare as ak
            df = await asyncio.to_thread(
                ak.stock_zh_a_hist,
                symbol=code,
                period=period,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust="qfq",
            )
        except Exception as e:
            logger.warning("akshare kline %s/%s failed: %s", code, period, e)
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        # Normalize columns
        rename_map = {
            "日期": "trade_date",
            "开盘": "open",
            "收盘": "close",
            "最高": "high",
            "最低": "low",
            "成交量": "volume",
            "成交额": "amount",
            "涨跌幅": "pct_change",
            "涨跌额": "change",
            "振幅": "amplitude",
            "换手率": "turnover",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df["code"] = code
        df = parser.to_numeric_cols(df, ["open", "close", "high", "low", "volume", "amount"])
        # akshare stock_zh_a_hist 的成交量单位是"手";库内统一为"股"(与 eastmoney / tencent 源一致),
        # 否则同一只股票在不同来源接缝处会出现 100 倍的量能跳变。
        if "volume" in df.columns:
            df["volume"] = df["volume"] * 100
        return df.tail(count)

    async def fetch_fundamental(self, code: str, periods: int = 8) -> pd.DataFrame:
        """Not implemented — akshare fundamental APIs are unstable."""
        return pd.DataFrame()


_default = AkShareSource()


def default() -> AkShareSource:
    return _default
