# -*- coding: utf-8 -*-
"""东方财富实时行情客户端(curl_cffi 指纹破甲版)。

背景 / 逆向结论
--------------
push2.eastmoney.com 的 /api/qt/clist/get(全市场快照)对未认证客户端的拦截
发生在 **TLS/HTTP 连接指纹层**:Python 的 urllib/requests/aiohttp 会被直接
RemoteDisconnected;真实浏览器 / curl 的指纹放行。本模块用 curl_cffi 的
impersonate="chrome" 伪造 Chrome 的 JA3/JA4(TLS)+ HTTP/2 指纹骗过它。

分层策略(实测得出)
------------------
* 全市场快照:走 **push2delay**。它对沪深 A 股(secid 前缀 0/1)本就是实时的
  (dlmkts 标记的延迟市场是港股/美股/期货),且**翻页无频次限流**,能翻满 60
  页拿全 ~5900 只。curl_cffi 指纹进一步增强抗反爬。
* 单股 / 榜单 Top N:走 **push2**(纯 push2 实时源)。push2 破甲后能连、能实时,
  但连续翻页 ~16 页(1600 只)后会被频次墙断连,故只适合单股与榜单,不适合全市场。

其它坑
------
* 单页上限固定 100 行(pz 设更大无效),拿全市场必须翻页。
* fs 里的 "+"(如 m:0+t:6)是 AND 连接符,必须靠 params 字典 urlencode 成 %2B,
  手拼进 URL 会被当空格 → 筛选失效 → 返回空。
* clist 的 f86 与单股 stock/get 的 f86 语义不同:单股 f86 是标准 Unix 秒;
  clist 的 f86 不是可靠的 tick 时间戳,判断实时性以价格变动为准。

返回 DataFrame 使用中文列名,与 data-service/eastmoney.py::fetch_all_spot 一致。
"""
from __future__ import annotations

import logging
import os
import random
import time

import pandas as pd
from curl_cffi import requests as creq

log = logging.getLogger(__name__)

# 全市场:push2delay 优先(实时+完整+无翻页限流);push2 兜底
SPOT_HOSTS = ["push2delay", "push2"]
# 单股/榜单:push2 优先(纯实时破甲源);push2delay 兜底
QUOTE_HOSTS = ["push2", "push2delay"]

IMPERSONATE = os.getenv("EM_RT_IMPERSONATE", "chrome")
TIMEOUT_S = int(os.getenv("EM_RT_TIMEOUT", "12"))
PAGE_SIZE = 100  # push2/push2delay 单页硬上限就是 100

# 沪深京 A 股:m:0深 m:1沪;t:6/t:80深主板/创业板,t:2/t:23沪主板/科创,t:81+s:2048北交所
SPOT_FS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
SPOT_FIELDS = ("f12,f14,f2,f3,f4,f5,f6,f7,f8,f9,f10,"
               "f15,f16,f17,f18,f20,f21,f23,f100")
RENAME = {
    "f12": "代码", "f14": "名称", "f2": "最新价", "f3": "涨跌幅",
    "f4": "涨跌额", "f5": "成交量", "f6": "成交额", "f7": "振幅",
    "f8": "换手率", "f9": "市盈率", "f10": "量比",
    "f15": "最高", "f16": "最低", "f17": "今开", "f18": "昨收",
    "f20": "总市值", "f21": "流通市值", "f23": "市净率", "f100": "行业",
}
_NUM_COLS = ("最新价", "涨跌幅", "涨跌额", "成交量", "成交额", "换手率", "市盈率",
             "市净率", "最高", "最低", "今开", "昨收", "总市值", "流通市值", "量比", "振幅")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA, "Accept": "*/*", "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://quote.eastmoney.com/",
}


def _spot_hosts() -> list[str]:
    env = os.getenv("EM_RT_SPOT_HOSTS", "").strip()
    return [h.strip() for h in env.split(",") if h.strip()] or SPOT_HOSTS


def secid(code: str) -> str:
    c = str(code).zfill(6)
    return f"1.{c}" if c[0] in ("6", "9") else f"0.{c}"


def _new_session() -> creq.Session:
    """带 Chrome 指纹的 Session,复用连接。"""
    return creq.Session(impersonate=IMPERSONATE, headers=HEADERS, timeout=TIMEOUT_S)


def _clist_page(session, host, page, fid="f3") -> list:
    url = f"https://{host}.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": page, "pz": PAGE_SIZE, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": fid,
        "fs": SPOT_FS, "fields": SPOT_FIELDS,
        "_": str(int(time.time() * 1000)),
    }
    r = session.get(url, params=params)
    diff = (r.json().get("data") or {}).get("diff") or []
    return list(diff.values()) if isinstance(diff, dict) else list(diff)


def _finalize(rows: list) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).rename(columns=RENAME)
    if "代码" in df:
        df["代码"] = df["代码"].astype(str).str.zfill(6)
    for col in _NUM_COLS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "总市值" in df:
        df["总市值_亿"] = df["总市值"] / 1e8
    return df


def fetch_all_spot(max_pages: int = 60, min_ok_rows: int = 4000) -> pd.DataFrame:
    """全市场实时快照(中文列)。push2delay 优先(实时+完整),不足则换下一个 host。

    min_ok_rows: 一个 host 至少要拿到这么多行才算成功;不足则尝试下一个 host
    (push2 会在 ~1600 行处被频次墙断连,达不到全市场 → 自动落到 push2delay)。
    """
    session = _new_session()
    best = pd.DataFrame()
    for host in _spot_hosts():
        rows: list = []
        empty = 0
        page = 1
        while page <= max_pages and empty < 2:
            try:
                chunk = _clist_page(session, host, page)
            except Exception as e:
                log.debug("em_realtime: host=%s page=%s 失败: %s", host, page, e)
                chunk = []
                empty += 1
                page += 1
                continue
            if not chunk:
                empty += 1
            else:
                rows.extend(chunk)
                empty = 0
            page += 1
            time.sleep(random.uniform(0.03, 0.10))  # 轻微 jitter
        if len(rows) > len(best):
            best = _finalize(rows)
            best.attrs["source_host"] = host
        if len(rows) >= min_ok_rows:
            log.info("em_realtime: 全市场快照来自 %s,共 %d 行", host, len(rows))
            return best
        log.warning("em_realtime: host=%s 仅 %d 行(<%d),尝试下一个源", host, len(rows), min_ok_rows)
    if not best.empty:
        log.warning("em_realtime: 全市场快照不完整,返回最优 %d 行(来源 %s)",
                    len(best), best.attrs.get("source_host"))
    return best


def fetch_top_realtime(n: int = 100, fid: str = "f3") -> pd.DataFrame:
    """push2 破甲拉实时榜单前 n 只(n<=1600)。fid: f3=涨幅榜 f6=成交额榜 f8=换手榜。

    这是 push2 破甲的独特能力:纯 push2 实时源,适合盘中榜单。
    """
    session = _new_session()
    rows: list = []
    for host in ("push2", "push2delay"):
        rows = []
        try:
            page = 1
            while len(rows) < n and page <= (n // PAGE_SIZE + 1):
                chunk = _clist_page(session, host, page, fid=fid)
                if not chunk:
                    break
                rows.extend(chunk)
                page += 1
                time.sleep(random.uniform(0.03, 0.10))
        except Exception as e:
            log.debug("em_realtime top: host=%s 失败: %s", host, e)
        if rows:
            df = _finalize(rows[:n])
            df.attrs["source_host"] = host
            return df
    return pd.DataFrame()


def fetch_single_quote(code: str) -> pd.DataFrame:
    """单股实时行情(中文列一行)。push2 单股接口稳定实时,push2delay 兜底。

    行情时间 列为单股 f86(标准 Unix 秒),可用于实时性监控。
    """
    session = _new_session()
    fields = "f43,f57,f58,f86,f169,f170,f116,f127"
    for host in QUOTE_HOSTS:
        url = f"https://{host}.eastmoney.com/api/qt/stock/get"
        params = {"secid": secid(code), "ut": "fa5fd1943c7b386f172d6893dbfba10b",
                  "invt": 2, "fltt": 2, "fields": fields,
                  "_": str(int(time.time() * 1000))}
        try:
            d = (session.get(url, params=params).json().get("data") or {})
        except Exception as e:
            log.debug("em_realtime single %s host=%s 失败: %s", code, host, e)
            continue
        price = d.get("f43")
        if price in (None, "-", ""):
            continue
        mc = d.get("f116")
        return pd.DataFrame([{
            "代码": str(d.get("f57") or code).zfill(6),
            "名称": str(d.get("f58") or ""),
            "行业": str(d.get("f127") or ""),
            "最新价": pd.to_numeric(price, errors="coerce"),
            "涨跌幅": pd.to_numeric(d.get("f170"), errors="coerce"),
            "行情时间": d.get("f86"),
            "总市值_亿": (mc / 1e8) if isinstance(mc, (int, float)) else None,
        }])
    return pd.DataFrame()


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO)
    df = fetch_all_spot(max_pages=60)
    print("全市场快照行数:", len(df), "来源:", df.attrs.get("source_host"))
    if not df.empty:
        print(df[["代码", "名称", "最新价", "涨跌幅", "成交额"]]
              .sort_values("涨跌幅", ascending=False).head(8).to_string(index=False))
