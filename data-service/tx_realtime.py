# -*- coding: utf-8 -*-
"""腾讯全市场实时行情(qt.gtimg.cn 批量行情)。

背景:东财 /api/qt/clist/get(全市场快照)对 curl_cffi chrome 指纹也开始
RemoteDisconnected(2026-09 起),em_realtime 全 host 拿 0 行。qt.gtimg.cn
批量行情接口无指纹墙,单请求可带 ~100 个代码,响应含总市值(字段 45,亿),
正好补上新浪兜底缺市值导致宇宙筛选为空的断链。

返回 DataFrame 使用中文列名,与 eastmoney.py / em_realtime.py::fetch_all_spot
一致(单位也对齐:成交量=手,成交额=元,总市值=元)。行业列由 stock_info
基础表补充(行情接口不含行业;缺行业填 '-',消费方既有惯例即过滤 '-'),
量比列缺失,消费方均按「列存在才用」访问,不构成兼容问题。

代码清单来自 stock_info(基础表,约 5900 只,含北交所)。近 3 个月新上市
个股在基础表刷新前会缺席——对按市值排序的宇宙选择反而符合「剔除新股」
的 A 股规则;代价是涨幅榜看不到 C 前缀次新股。
"""
from __future__ import annotations

import asyncio
import logging
import random
import time

import pandas as pd

log = logging.getLogger(__name__)

BATCH_SIZE = 80
BATCH_SLEEP_S = (0.15, 0.35)
MIN_OK_ROWS = 4000  # 与 em_realtime 同门槛:低于此视为抓取失败,让调用方换源


async def _fetch_all_spot_async() -> pd.DataFrame:
    from sources.tencent import _stock_info_codes, _tx_sym, fetch_quote_rows, stock_industry_map

    codes = await asyncio.to_thread(_stock_info_codes)
    if not codes:
        log.warning("tx_realtime: stock_info 代码表为空")
        return pd.DataFrame()
    rows: list[dict] = []
    t0 = time.time()
    for i in range(0, len(codes), BATCH_SIZE):
        chunk = await fetch_quote_rows([_tx_sym(c) for c in codes[i:i + BATCH_SIZE]])
        rows.extend(chunk)
        if i + BATCH_SIZE < len(codes):
            await asyncio.sleep(random.uniform(*BATCH_SLEEP_S))
    if not rows:
        return pd.DataFrame()
    if len(rows) < MIN_OK_ROWS:
        log.warning("tx_realtime: 仅 %d 行(<%d),视为失败", len(rows), MIN_OK_ROWS)
        return pd.DataFrame()
    df = pd.DataFrame(rows).drop_duplicates(subset=["code"])
    df = df.rename(columns={
        "code": "代码", "name": "名称", "price": "最新价", "pct_change": "涨跌幅",
        "change": "涨跌额", "volume": "成交量", "turnover": "换手率",
        "pe": "市盈率", "amplitude": "振幅", "high": "最高", "low": "最低",
        "open": "今开", "prev_close": "昨收", "pb": "市净率",
    })
    df["成交额"] = pd.to_numeric(df["amount_wan"], errors="coerce") * 1e4
    df["总市值"] = pd.to_numeric(df["total_cap_yi"], errors="coerce") * 1e8
    df["流通市值"] = pd.to_numeric(df["float_cap_yi"], errors="coerce") * 1e8
    df["总市值_亿"] = pd.to_numeric(df["total_cap_yi"], errors="coerce")
    ind = await asyncio.to_thread(stock_industry_map)
    if ind:
        df["行业"] = df["代码"].map(ind).fillna("-")
    df.attrs["source_host"] = "qt.gtimg.cn"
    log.info("tx_realtime: 全市场快照 %d 行,耗时 %.1fs", len(df), time.time() - t0)
    return df


def fetch_all_spot() -> pd.DataFrame:
    """全市场实时快照(中文列)。同步入口,事件循环占用时切线程。"""
    try:
        return asyncio.run(_fetch_all_spot_async())
    except RuntimeError:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(_fetch_all_spot_async())).result()


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    logging.basicConfig(level=logging.INFO)
    df = fetch_all_spot()
    print("全市场快照行数:", len(df), "来源:", df.attrs.get("source_host"))
    if not df.empty:
        print(df[["代码", "名称", "最新价", "涨跌幅", "总市值_亿"]]
              .sort_values("总市值_亿", ascending=False).head(8).to_string(index=False))
