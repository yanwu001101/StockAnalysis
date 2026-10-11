# -*- coding: utf-8 -*-
"""股东户数 pipeline."""
from __future__ import annotations
from typing import Iterable

import pandas as pd

from core.trace import PIPELINE_ROWS, logger
from pipelines._helpers import fetch_first_nonempty, gather_codes
from repo import shareholder_repo


async def run_market() -> dict:
    """全市场最新股东户数，按页拉取，避免只覆盖 warmup 的 top300。"""
    from core import http_client
    from sources.eastmoney import DATACENTER_URL
    from repo.base import fetch_df
    universe = fetch_df("SELECT code FROM stock_info")
    if universe.empty:
        raise RuntimeError("股票清单为空，停止股东户数回补")
    allowed = set(universe["code"].astype(str).str.zfill(6))
    total, codes, seen_pages = 0, set(), set()
    for page in range(1, 41):
        obj = await http_client.get_json(DATACENTER_URL, source="eastmoney", params={
            "reportName": "RPT_HOLDERNUMLATEST", "columns": "ALL", "pageSize": 500,
            "pageNumber": page, "sortColumns": "SECURITY_CODE", "sortTypes": "1",
            "source": "WEB", "client": "WEB"})
        result = (obj or {}).get("result") or {}
        rows = result.get("data") or []
        if not rows:
            if page == 1:
                raise RuntimeError("股东户数源返回空数据，未写入任何伪零值")
            break
        signature = tuple(str(r.get("SECURITY_CODE")) for r in rows)
        if signature in seen_pages:
            raise RuntimeError("股东源重复分页，停止避免重复计数")
        seen_pages.add(signature)
        df = pd.DataFrame(rows).rename(columns={"SECURITY_CODE": "code", "END_DATE": "report_date", "HOLDER_NUM": "holder_count"})
        df["code"] = df["code"].astype(str).str.zfill(6)
        df["report_date"] = pd.to_datetime(df["report_date"], errors="coerce").dt.date
        df["holder_count"] = pd.to_numeric(df["holder_count"], errors="coerce")
        df = df[df["code"].isin(allowed) & df["holder_count"].gt(0)].dropna(subset=["report_date"])
        written = shareholder_repo.upsert_shareholder(df)
        if len(df) and written != len(df):
            raise RuntimeError(f"股东户数第{page}页落库失败")
        total += written; codes.update(df["code"])
        if page >= int(result.get("pages") or page):
            break
    return {"rows": total, "codes": len(codes), "pages": len(seen_pages),
            "scope": "latest snapshot, not historical point-in-time data"}


async def fetch(code: str) -> pd.DataFrame:
    return await fetch_first_nonempty("shareholder", code)


async def run_batch(codes: Iterable[str]) -> int:
    res = await gather_codes(list(codes), fetch, concurrency=4)
    total = 0
    for _, df in res.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            total += shareholder_repo.upsert_shareholder(df)
    PIPELINE_ROWS.labels(pipeline="shareholder").inc(total)
    logger.info("[pipeline:shareholder] %d rows", total)
    return total
