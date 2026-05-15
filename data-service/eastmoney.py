# -*- coding: utf-8 -*-
# Multi-source A-share data client (async).
#
# Endpoints chosen to work under restricted networks where push2/push2his is blocked:
#   - Spot (full market): http://push2delay.eastmoney.com/api/qt/clist/get
#   - K-line history:     https://web.ifzq.gtimg.cn/appstock/app/fqkline/get (Tencent)
#   - Fallback K-line:    http://money.finance.sina.com.cn (Sina)
#
# DataFrames use CHINESE column names (日期/开盘/收盘/最高/最低/成交量) because
# strategies.py hard-depends on them.
from __future__ import annotations
import asyncio
import json
import logging
import os
import random
import re

import aiohttp
import pandas as pd

log = logging.getLogger(__name__)

CONCURRENCY = int(os.getenv("EM_CONCURRENCY", "8"))
JITTER_MIN_MS = int(os.getenv("EM_JITTER_MIN_MS", "50"))
JITTER_MAX_MS = int(os.getenv("EM_JITTER_MAX_MS", "200"))
TIMEOUT_S = 10

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS_EM = {"User-Agent": UA, "Accept": "*/*", "Referer": "https://quote.eastmoney.com/"}
HEADERS_TX = {"User-Agent": UA, "Accept": "*/*", "Referer": "https://gu.qq.com/"}
HEADERS_SINA = {"User-Agent": UA, "Accept": "*/*", "Referer": "https://finance.sina.com.cn/"}

SPOT_URL = "http://push2delay.eastmoney.com/api/qt/clist/get"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
SINA_KLINE_URL = "http://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

SPOT_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
SPOT_FIELDS = "f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,f15,f16,f17,f18,f20,f21,f23,f100"

KLT_MAP = {101: "day", 102: "week", 103: "month"}


def secid(code: str) -> str:
    # 6/9 prefix -> SSE (1), else SZSE (0)
    c = str(code).zfill(6)
    return f"1.{c}" if c[0] in ("6", "9") else f"0.{c}"


def tx_symbol(code: str) -> str:
    # Tencent style: sh600519 / sz000001
    c = str(code).zfill(6)
    return f"sh{c}" if c[0] in ("6", "9") else f"sz{c}"


def _jitter_sleep() -> float:
    return random.uniform(JITTER_MIN_MS, JITTER_MAX_MS) / 1000.0


# ---------------------------------------------------------------------------
# Spot snapshot via push2delay
# ---------------------------------------------------------------------------

async def _fetch_spot_page(session, page: int, page_size: int) -> list:
    params = {
        "pn": page, "pz": page_size, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": SPOT_FS, "fields": SPOT_FIELDS,
        "_": str(int(random.random() * 1e13)),
    }
    async with session.get(SPOT_URL, params=params, headers=HEADERS_EM,
                           timeout=aiohttp.ClientTimeout(total=TIMEOUT_S)) as r:
        text = await r.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []
        diff = (data.get("data") or {}).get("diff") or []
        return list(diff) if isinstance(diff, list) else list(diff.values())


async def _fetch_all_spot_async() -> pd.DataFrame:
    page_size = 200
    rows = []
    async with aiohttp.ClientSession() as s:
        first = await _fetch_spot_page(s, 1, page_size)
        rows.extend(first)
        if not first:
            return pd.DataFrame()
        page = 2
        empty_streak = 0
        while page <= 60 and empty_streak < 2:
            await asyncio.sleep(_jitter_sleep())
            chunk = await _fetch_spot_page(s, page, page_size)
            if not chunk:
                empty_streak += 1
            else:
                rows.extend(chunk)
                empty_streak = 0
            page += 1
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    rename = {
        "f12": "代码", "f14": "名称", "f2": "最新价", "f3": "涨跌幅",
        "f4": "涨跌额", "f5": "成交量", "f6": "成交额", "f7": "振幅",
        "f8": "换手率", "f9": "市盈率", "f10": "量比",
        "f15": "最高", "f16": "最低", "f17": "今开", "f18": "昨收",
        "f20": "总市值", "f21": "流通市值", "f23": "市净率", "f100": "行业",
    }
    df = df.rename(columns=rename)
    if "代码" in df:
        df["代码"] = df["代码"].astype(str).str.zfill(6)
    if "总市值" in df:
        df["总市值_亿"] = pd.to_numeric(df["总市值"], errors="coerce") / 100_000_000
    for col in ("最新价", "涨跌幅", "最高", "最低", "今开", "昨收", "市盈率", "市净率"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_all_spot() -> pd.DataFrame:
    try:
        return asyncio.run(_fetch_all_spot_async())
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(_fetch_all_spot_async())).result()


# ---------------------------------------------------------------------------
# K-line: Tencent primary, Sina fallback
# ---------------------------------------------------------------------------

_TX_VAR_RE = re.compile(r"^[^=]*=")


def _parse_tencent_kline(text: str, symbol: str, period_key: str) -> pd.DataFrame:
    body = _TX_VAR_RE.sub("", text.strip().rstrip(";"))
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        return pd.DataFrame()
    data = (obj.get("data") or {}).get(symbol) or {}
    klines = data.get(period_key) or data.get(period_key.replace("qfq", "")) or []
    if not klines:
        return pd.DataFrame()
    rows = []
    for k in klines:
        if len(k) < 6:
            continue
        rows.append({
            "日期": k[0],
            "开盘": float(k[1]) if k[1] else None,
            "收盘": float(k[2]) if k[2] else None,
            "最高": float(k[3]) if k[3] else None,
            "最低": float(k[4]) if k[4] else None,
            "成交量": float(k[5]) * 100 if k[5] else None,  # Tencent: hand -> shares
        })
    return pd.DataFrame(rows)


async def _fetch_kline_tencent(session, sem, code: str, klt: int, count: int):
    period = KLT_MAP.get(klt, "day")
    period_key = f"{period}qfq"
    sym = tx_symbol(code)
    params = {
        "_var": f"kline_{period_key}",
        "param": f"{sym},{period},,,{count},qfq",
        "r": random.random(),
    }
    async with sem:
        await asyncio.sleep(_jitter_sleep())
        try:
            async with session.get(TENCENT_KLINE_URL, params=params, headers=HEADERS_TX,
                                   timeout=aiohttp.ClientTimeout(total=TIMEOUT_S)) as r:
                text = await r.text()
        except Exception as e:
            log.debug("tencent kline %s failed: %s", code, e)
            return None
    df = _parse_tencent_kline(text, sym, period_key)
    return df if not df.empty else None


async def _fetch_kline_sina(session, sem, code: str, klt: int, count: int):
    scale = 240 if klt == 101 else 1680 if klt == 102 else 240
    sym = tx_symbol(code)
    params = {"symbol": sym, "scale": scale, "ma": 5, "datalen": count}
    async with sem:
        await asyncio.sleep(_jitter_sleep())
        try:
            async with session.get(SINA_KLINE_URL, params=params, headers=HEADERS_SINA,
                                   timeout=aiohttp.ClientTimeout(total=TIMEOUT_S)) as r:
                text = await r.text()
        except Exception as e:
            log.debug("sina kline %s failed: %s", code, e)
            return None
    try:
        arr = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not arr or not isinstance(arr, list):
        return None
    rows = []
    for row in arr:
        rows.append({
            "日期": row.get("day"),
            "开盘": float(row["open"]) if row.get("open") else None,
            "收盘": float(row["close"]) if row.get("close") else None,
            "最高": float(row["high"]) if row.get("high") else None,
            "最低": float(row["low"]) if row.get("low") else None,
            "成交量": float(row["volume"]) if row.get("volume") else None,
        })
    df = pd.DataFrame(rows)
    return df if not df.empty else None


async def _fetch_kline_one(session, sem, code: str, klt: int, count: int):
    df = await _fetch_kline_tencent(session, sem, code, klt, count)
    if df is not None and not df.empty:
        return df
    return await _fetch_kline_sina(session, sem, code, klt, count)


async def _batch_klines_async(codes: list, klt: int, count: int) -> dict:
    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [_fetch_kline_one(session, sem, c, klt, count) for c in codes]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    out = {}
    for code, res in zip(codes, results):
        if isinstance(res, pd.DataFrame) and not res.empty:
            out[code] = res
    return out


def batch_klines(codes: list, klt: int = 101, count: int = 250) -> dict:
    # klt: 101=daily, 102=weekly, 103=monthly
    if not codes:
        return {}
    try:
        return asyncio.run(_batch_klines_async(codes, klt, count))
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(_batch_klines_async(codes, klt, count))).result()


def fetch_kline(code: str, klt: int = 101, count: int = 250) -> pd.DataFrame:
    out = batch_klines([code], klt=klt, count=count)
    return out.get(code, pd.DataFrame())
