# -*- coding: utf-8 -*-
"""Eastmoney source — A-share's most-covered free data feed.

Endpoints used here are public web APIs of:
  https://quote.eastmoney.com/  (push2 / push2delay — spot)
  https://data.eastmoney.com/    (datacenter-web — fundamentals, lhb, northbound, dividends)
  https://emweb.securities.eastmoney.com/  (F10 detail)

We intentionally use the *delay* spot endpoint (push2delay) because the realtime
one (push2) blocks unauthenticated bursts. For K-line we delegate to Tencent /
Sina via the `tencent` / `sina` source modules — push2his is too aggressively
rate-limited.
"""
from __future__ import annotations
import asyncio
import datetime as dt
import os
import random
from typing import Iterable

import pandas as pd

from core import http_client, parser
from core.trace import logger
from sources.base import AbstractSource


SPOT_URL_REALTIME = "http://push2.eastmoney.com/api/qt/clist/get"
SPOT_URL_DELAYED = "http://push2delay.eastmoney.com/api/qt/clist/get"
DATACENTER_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
FFLOW_URL = "http://push2.eastmoney.com/api/qt/stock/fflow/daykline/get"

SPOT_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
SPOT_FIELDS = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21,f23,f100"


def _spot_urls() -> list[str]:
    mode = os.getenv("EM_SPOT_MODE", "auto").strip().lower()
    if mode in ("realtime", "real", "live", "push2"):
        return [SPOT_URL_REALTIME]
    if mode in ("delay", "delayed", "push2delay"):
        return [SPOT_URL_DELAYED]
    return [SPOT_URL_REALTIME, SPOT_URL_DELAYED]


def _secid(code: str) -> str:
    c = parser.normalize_code(code)
    return f"1.{c}" if c.startswith(("6", "9")) else f"0.{c}"


class EastmoneySource(AbstractSource):
    name = "eastmoney"

    # ---------- spot ----------
    async def fetch_spot(self) -> pd.DataFrame:
        rows: list = []
        for url in _spot_urls():
            rows.clear()
            page = 1
            empty = 0
            while page <= 60 and empty < 2:
                params = {
                    "pn": page, "pz": 200, "po": 1, "np": 1,
                    "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                    "fltt": 2, "invt": 2, "fid": "f3",
                    "fs": SPOT_FS, "fields": SPOT_FIELDS,
                    "_": str(int(random.random() * 1e13)),
                }
                obj = await http_client.get_json(url, params=params, source=self.name)
                diff = ((obj or {}).get("data") or {}).get("diff") or []
                if isinstance(diff, dict):
                    diff = list(diff.values())
                if not diff:
                    empty += 1
                else:
                    rows.extend(diff)
                    empty = 0
                page += 1
            if rows:
                break
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).rename(columns={
            "f12": "code", "f14": "name", "f2": "price", "f3": "pct_change",
            "f4": "change", "f5": "volume", "f6": "amount", "f7": "amplitude",
            "f8": "turnover", "f9": "pe", "f10": "vol_ratio",
            "f15": "high", "f16": "low", "f17": "open", "f18": "prev_close",
            "f20": "market_cap", "f21": "float_cap", "f23": "pb", "f100": "industry",
        })
        if "code" in df:
            df["code"] = df["code"].astype(str).str.zfill(6)
        df = parser.to_numeric_cols(df, [
            "price", "pct_change", "change", "volume", "amount", "turnover",
            "pe", "pb", "high", "low", "open", "prev_close",
            "market_cap", "float_cap", "vol_ratio", "amplitude",
        ])
        if "market_cap" in df:
            df["market_cap_yi"] = df["market_cap"] / 1e8
        return df

    # ---------- fundamental (业绩报表合并) ----------
    async def fetch_fundamental(self, code: str, periods: int = 8) -> pd.DataFrame:
        # Income + balance sheet aggregated from datacenter
        secid = _secid(code)
        params = {
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "pageSize": periods,
            "pageNumber": 1,
            "reportName": "RPT_LICO_FN_CPD",   # 业绩快报/利润表合并
            "columns": "ALL",
            "filter": f"(SECURITY_CODE=\"{parser.normalize_code(code)}\")",
            "source": "WEB",
            "client": "WEB",
        }
        obj = await http_client.get_json(DATACENTER_URL, params=params, source=self.name)
        rows = ((obj or {}).get("result") or {}).get("data") or []
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        rename = {
            "REPORT_DATE": "report_date",
            "TOTAL_OPERATE_INCOME": "revenue",
            "PARENT_NETPROFIT": "net_profit",
            "WEIGHTAVG_ROE": "roe",
            "DEBT_ASSET_RATIO": "debt_ratio",
            "YOY_NETPROFIT": "net_profit_yoy",
            "YOY_INCOME": "revenue_yoy",
            "OPERATE_CASHFLOW_PS": "op_cashflow_ps",
            "GROSS_PROFIT_MARGIN": "gross_margin",
            "BASIC_EPS": "eps",
            "BPS": "bvps",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        if "report_date" in df:
            df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce").dt.date
        df["code"] = parser.normalize_code(code)
        return df

    # ---------- moneyflow ----------
    async def fetch_moneyflow(self, code: str, days: int = 60) -> pd.DataFrame:
        params = {
            "lmt": days,
            "klt": 101,
            "secid": _secid(code),
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            "ut": "b2884a393a59ad64002292a3e90d46a5",
            "_": str(int(random.random() * 1e13)),
        }
        obj = await http_client.get_json(FFLOW_URL, params=params, source=self.name)
        klines = ((obj or {}).get("data") or {}).get("klines") or []
        if not klines:
            return pd.DataFrame()
        rows = []
        for line in klines:
            parts = line.split(",")
            if len(parts) < 14:
                continue
            rows.append({
                "code": parser.normalize_code(code),
                "trade_date": parts[0],
                "main_net": float(parts[1]) if parts[1] else None,
                "small_net": float(parts[2]) if parts[2] else None,
                "medium_net": float(parts[3]) if parts[3] else None,
                "large_net": float(parts[4]) if parts[4] else None,
                "super_large_net": float(parts[5]) if parts[5] else None,
            })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        return df

    # ---------- northbound holdings (HSGT mutual top) ----------
    async def fetch_northbound_holdings(self, code: str, days: int = 60) -> pd.DataFrame:
        params = {
            "sortColumns": "HOLD_DATE",
            "sortTypes": "-1",
            "pageSize": days,
            "pageNumber": 1,
            "reportName": "RPT_MUTUAL_STOCK_HOLDRANKS",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
            "filter": f"(SECURITY_CODE=\"{parser.normalize_code(code)}\")",
        }
        obj = await http_client.get_json(DATACENTER_URL, params=params, source=self.name)
        rows = ((obj or {}).get("result") or {}).get("data") or []
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).rename(columns={
            "HOLD_DATE": "trade_date",
            "SHARES_HOLD": "hold_shares",
            "HOLD_MARKET_CAP": "hold_market_cap",
            "HOLD_RATIO": "hold_ratio",
            "NET_BUY": "net_buy",
        })
        if "trade_date" in df:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        df["code"] = parser.normalize_code(code)
        return df

    # ---------- 龙虎榜 ----------
    async def fetch_lhb(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        """Fetch per-seat LHB details from eastmoney datacenter.

        Uses RPT_BILLBOARD_DAILYDETAILSBUY (席位买入明细) which includes
        OPERATEDEPT_NAME (席位名称) and both BUY/SELL amounts per seat.
        Falls back to RPT_DAILYBILLBOARD_DETAILS (stock-level only) if
        the seat-level report returns nothing.
        """
        all_rows: list = []
        for report in ("RPT_BILLBOARD_DAILYDETAILSBUY", "RPT_DAILYBILLBOARD_DETAILS"):
            all_rows.clear()
            for page in range(1, 21):   # safety cap: 21 pages = 10500 rows
                params = {
                    "sortColumns": "TRADE_DATE",
                    "sortTypes": "-1",
                    "pageSize": 500,
                    "pageNumber": page,
                    "reportName": report,
                    "columns": "ALL",
                    "source": "WEB",
                    "client": "WEB",
                    "filter": (
                        f"(TRADE_DATE>='{start.isoformat()}')"
                        f"(TRADE_DATE<='{end.isoformat()}')"
                    ),
                }
                obj = await http_client.get_json(DATACENTER_URL, params=params, source=self.name)
                rows = ((obj or {}).get("result") or {}).get("data") or []
                if not rows:
                    break
                all_rows.extend(rows)
                if len(rows) < 500:
                    break
            if all_rows:
                logger.debug("fetch_lhb: got %d rows from %s", len(all_rows), report)
                break
        if not all_rows:
            return pd.DataFrame()
        df = pd.DataFrame(all_rows).rename(columns={
            "SECURITY_CODE": "code",
            "TRADE_DATE": "trade_date",
            "EXPLANATION": "reason",
            "OPERATEDEPT_NAME": "seat_name",
            # RPT_BILLBOARD_DAILYDETAILSBUY columns
            "BUY": "buy_amount",
            "SELL": "sell_amount",
            "NET": "net_amount",
            # RPT_DAILYBILLBOARD_DETAILS columns (fallback)
            "BILLBOARD_BUY_AMT": "buy_amount",
            "BILLBOARD_SELL_AMT": "sell_amount",
            "BILLBOARD_NET_AMT": "net_amount",
        })
        if "code" in df:
            df["code"] = df["code"].astype(str).str.zfill(6)
        if "trade_date" in df:
            df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
        # Derive seat_type from seat_name: "机构专用" → 机构, others → 营业部
        if "seat_name" in df.columns:
            df["seat_type"] = df["seat_name"].apply(
                lambda x: "机构" if isinstance(x, str) and "机构" in x else "营业部"
            )
        else:
            df["seat_type"] = ""
        return df

    # ---------- 股东户数 ----------
    async def fetch_shareholder(self, code: str) -> pd.DataFrame:
        params = {
            "sortColumns": "END_DATE",
            "sortTypes": "-1",
            "pageSize": 12,
            "pageNumber": 1,
            "reportName": "RPT_HOLDERNUMLATEST",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
            "filter": f"(SECURITY_CODE=\"{parser.normalize_code(code)}\")",
        }
        obj = await http_client.get_json(DATACENTER_URL, params=params, source=self.name)
        rows = ((obj or {}).get("result") or {}).get("data") or []
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).rename(columns={
            "END_DATE": "report_date",
            "HOLDER_NUM": "holder_count",
            "HOLDER_NUM_RATIO": "holder_count_yoy",
        })
        if "report_date" in df:
            df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce").dt.date
        df["code"] = parser.normalize_code(code)
        return df

    # ---------- 分红送转 ----------
    async def fetch_dividend(self, code: str) -> pd.DataFrame:
        params = {
            "sortColumns": "REPORT_DATE",
            "sortTypes": "-1",
            "pageSize": 50,
            "pageNumber": 1,
            "reportName": "RPT_SHAREBONUS_DET",
            "columns": "ALL",
            "source": "WEB",
            "client": "WEB",
            "filter": f"(SECURITY_CODE=\"{parser.normalize_code(code)}\")",
        }
        obj = await http_client.get_json(DATACENTER_URL, params=params, source=self.name)
        rows = ((obj or {}).get("result") or {}).get("data") or []
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).rename(columns={
            "NOTICE_DATE": "ann_date",
            "EX_DIVIDEND_DATE": "ex_date",
            "PAY_CASH": "cash_per_10",
            "BONUS_RATIO": "share_per_10",
            "TRANSFER_RATIO": "transfer_per_10",
        })
        for c in ("ann_date", "ex_date"):
            if c in df:
                df[c] = pd.to_datetime(df[c], errors="coerce").dt.date
        df["code"] = parser.normalize_code(code)
        return df

    # ---------- 公告 ----------
    async def fetch_announcements(self, codes: Iterable[str], days: int = 7) -> pd.DataFrame:
        # Use cms-list which is what eastmoney's 公告 page calls.
        end = dt.date.today()
        start = end - dt.timedelta(days=days)
        codes = [parser.normalize_code(c) for c in codes]
        tasks = []
        for c in codes:
            params = {
                "sr": "-1",
                "page_size": 50,
                "page_index": 1,
                "ann_type": "A",
                "client_source": "web",
                "stock_list": c,
                "begin_time": start.isoformat(),
                "end_time": end.isoformat(),
                "f_node": "0",
                "s_node": "0",
            }
            tasks.append(http_client.get_json(
                "https://np-anotice-stock.eastmoney.com/api/security/ann",
                params=params, source=self.name,
            ))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        rows = []
        for code, r in zip(codes, results):
            if isinstance(r, Exception) or not r:
                continue
            for it in (r.get("data") or {}).get("list", []) or []:
                rows.append({
                    "code": code,
                    "ann_date": it.get("notice_date"),
                    "title": it.get("title", ""),
                    "type": (it.get("columns") or [{}])[0].get("column_name", ""),
                    "url": f"https://np-cnotice-stock.eastmoney.com/api/content/ann?art_code={it.get('art_code','')}",
                })
        df = pd.DataFrame(rows)
        if not df.empty:
            df["ann_date"] = pd.to_datetime(df["ann_date"], errors="coerce").dt.date
        return df


_default = EastmoneySource()


def default() -> EastmoneySource:
    return _default
