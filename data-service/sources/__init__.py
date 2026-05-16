# -*- coding: utf-8 -*-
"""Source registry.

`pipelines/` import from here to walk a fallback chain:
    for src in chain("spot"):
        df = await src.fetch_spot()
        if not df.empty:
            return df
"""
from __future__ import annotations
from typing import Iterator

from sources.akshare_src import default as ak_default
from sources.base import AbstractSource
from sources.eastmoney import default as em_default
from sources.sina import default as sina_default
from sources.tencent import default as tx_default
from sources.ths import default as ths_default
from sources.tushare_src import default as ts_default
from sources.xueqiu import default as xq_default


_CHAINS: dict[str, list[AbstractSource]] = {
    "spot": [em_default(), ak_default()],
    "kline": [tx_default(), sina_default(), ak_default()],
    "minute_kline": [tx_default()],
    "fundamental": [ts_default(), em_default(), ak_default()],
    "moneyflow": [em_default(), ak_default()],
    "northbound_holdings": [ts_default(), em_default(), ak_default()],
    "lhb": [em_default()],
    "shareholder": [em_default()],
    "dividend": [em_default()],
    "concept_members": [ths_default(), ak_default()],
    "announcements": [em_default()],
    "quote": [xq_default(), em_default()],
}


def chain(capability: str) -> Iterator[AbstractSource]:
    for src in _CHAINS.get(capability, []):
        if isinstance(src, AbstractSource) and src.available(f"fetch_{capability}"):
            # Tushare guard: skip when token missing
            if src.name == "tushare":
                from sources.tushare_src import TushareSource
                assert isinstance(src, TushareSource)
                if not src.enabled():
                    continue
            yield src


def all_sources() -> list[AbstractSource]:
    return [em_default(), tx_default(), sina_default(),
            xq_default(), ths_default(), ak_default(), ts_default()]
