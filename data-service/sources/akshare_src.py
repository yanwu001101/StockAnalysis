# -*- coding: utf-8 -*-
"""Akshare source — broad coverage fallback.

akshare wraps a huge number of public endpoints. We use it as a last-resort
fallback when source-specific adapters fail, and as the primary feed for
concept boards / sector flow where other sources are messy.

All akshare functions are synchronous, so we wrap them in `asyncio.to_thread`.
"""
from __future__ import annotations
import asyncio
import datetime as dt

import pandas as pd

from core import parser
from sources.base import AbstractSource


def _safe(fn, *args, **kwargs) -> pd.DataFrame:
    try:
        return fn(*args, **kwargs)
    except Exception:
        return pd.DataFrame()


class AkshareSource(AbstractSource):
    name = "akshare"

    async def fetch_spot(self) -> pd.DataFrame:
        import akshare as ak
        df = await asyncio.to_thread(_safe, ak.stock_zh_a_spot_em)
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "代码": "code", "名称": "name", "最新价": "price", "涨跌幅": "pct_change",
            "涨跌额": "change", "成交量": "volume", "成交额": "amount",
            "振幅": "amplitude", "换手率": "turnover",
            "市盈率-动态": "pe", "市净率": "pb",
            "总市值": "market_cap", "流通市值": "float_cap",
            "最高": "high", "最低": "low", "今开": "open", "昨收": "prev_close",
        })
        if "code" in df:
            df["code"] = df["code"].astype(str).str.zfill(6)
        df = parser.to_numeric_cols(df, [
            "price", "pct_change", "change", "volume", "amount",
            "pe", "pb", "high", "low", "open", "prev_close",
            "market_cap", "float_cap", "turnover", "amplitude",
        ])
        if "market_cap" in df:
            df["market_cap_yi"] = df["market_cap"] / 1e8
        return df

    async def fetch_kline(self, code: str, period: str = "daily", count: int = 250) -> pd.DataFrame:
        import akshare as ak
        end = dt.date.today()
        start = end - dt.timedelta(days=max(count * 2, 365))
        period_map = {"daily": "daily", "weekly": "weekly", "monthly": "monthly"}
        df = await asyncio.to_thread(
            _safe, ak.stock_zh_a_hist,
            symbol=parser.normalize_code(code),
            period=period_map.get(period, "daily"),
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        )
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.rename(columns={
            "日期": "trade_date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "涨跌幅": "pct_change", "换手率": "turnover",
        })
        df["code"] = parser.normalize_code(code)
        if "trade_date" in df:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df = df.tail(count)
        return df

    async def fetch_fundamental(self, code: str, periods: int = 8) -> pd.DataFrame:
        import akshare as ak
        import calendar
        c = parser.normalize_code(code)
        today = dt.date.today()

        # Walk back through quarter ends; take the first one that has data.
        candidates: list[dt.date] = []
        y, m = today.year, today.month
        for _ in range(periods + 2):
            # Find the most recent quarter end <= today
            qe_month = ((m - 1) // 3) * 3
            if qe_month == 0:
                qe_year, qe_month = y - 1, 12
            else:
                qe_year = y
            last_day = calendar.monthrange(qe_year, qe_month)[1]
            qe = dt.date(qe_year, qe_month, last_day)
            if qe < today and qe not in candidates:
                candidates.append(qe)
            # step back one quarter
            m -= 3
            if m <= 0:
                m += 12
                y -= 1

        rows: list[dict] = []
        for qe in candidates:
            date_str = qe.strftime("%Y%m%d")
            df_yj = await asyncio.to_thread(_safe, ak.stock_yjbb_em, date=date_str)
            if df_yj is None or df_yj.empty:
                continue
            df_yj["股票代码"] = df_yj["股票代码"].astype(str).str.zfill(6)
            row = df_yj[df_yj["股票代码"] == c]
            if row.empty:
                continue
            r = row.iloc[0]
            entry = {
                "code": c,
                "report_date": qe,
                "period_type": "Q",
                "revenue": r.get("营业总收入-营业总收入"),
                "net_profit": r.get("净利润-净利润"),
                "eps": r.get("每股收益"),
                "revenue_yoy": r.get("营业总收入-同比增长"),
                "net_profit_yoy": r.get("净利润-同比增长"),
                "roe": r.get("净资产收益率"),
                "gross_margin": r.get("销售毛利率"),
                "op_cashflow": r.get("每股经营性现金流"),
                "bvps": r.get("每股净资产"),
            }
            # Try to enrich with debt ratio from stock_zcfz_em
            df_zcfz = await asyncio.to_thread(_safe, ak.stock_zcfz_em, date=date_str)
            if df_zcfz is not None and not df_zcfz.empty and "股票代码" in df_zcfz.columns:
                df_zcfz["股票代码"] = df_zcfz["股票代码"].astype(str).str.zfill(6)
                zr = df_zcfz[df_zcfz["股票代码"] == c]
                if not zr.empty:
                    entry["debt_ratio"] = zr.iloc[0].get("资产负债率")
            rows.append(entry)
            if len(rows) >= periods:
                break
        return pd.DataFrame(rows)

    async def fetch_northbound_holdings(self, code: str, days: int = 60) -> pd.DataFrame:
        """Per-stock northbound (沪深股通) holding history via akshare."""
        import akshare as ak
        c = parser.normalize_code(code)
        df = await asyncio.to_thread(_safe, ak.stock_hsgt_individual_em, symbol=c)
        if df is None or df.empty:
            return pd.DataFrame()
        rename = {
            "持股日期": "trade_date", "持股股数": "hold_shares", "持股数量": "hold_shares",
            "持股市值": "hold_market_cap", "持股比例": "hold_ratio",
            "持股占流通股比": "hold_ratio", "持股占总股本比": "hold_ratio",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        if "trade_date" not in df.columns:
            return pd.DataFrame()
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df = df.dropna(subset=["trade_date"])
        df["code"] = c
        cols_keep = [c for c in ["code", "trade_date", "hold_shares", "hold_market_cap", "hold_ratio"] if c in df.columns]
        return df[cols_keep].sort_values("trade_date", ascending=False).head(days)

    async def fetch_moneyflow(self, code: str, days: int = 60) -> pd.DataFrame:
        """Per-stock daily money flow series via akshare.

        Fallback for the unstable EM push2/fflow endpoint. Returns 主力/超大/大/
        中/小单 net amounts ordered by trade_date desc, capped to `days`.
        """
        import akshare as ak
        c = parser.normalize_code(code)
        market = "sh" if c.startswith(("6", "9")) else "sz"
        df = await asyncio.to_thread(_safe, ak.stock_individual_fund_flow,
                                      stock=c, market=market)
        if df is None or df.empty:
            return pd.DataFrame()
        rename = {
            "日期": "trade_date",
            "主力净流入-净额": "main_net",
            "超大单净流入-净额": "super_large_net",
            "大单净流入-净额": "large_net",
            "中单净流入-净额": "medium_net",
            "小单净流入-净额": "small_net",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df["code"] = c
        cols_keep = ["code", "trade_date", "main_net", "super_large_net",
                     "large_net", "medium_net", "small_net"]
        cols_keep = [c for c in cols_keep if c in df.columns]
        return df[cols_keep].sort_values("trade_date", ascending=False).head(days)


_default = AkshareSource()


def default() -> AkshareSource:
    return _default
