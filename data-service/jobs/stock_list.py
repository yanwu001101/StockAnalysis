# -*- coding: utf-8 -*-
"""A股基础清单刷新——交易所官方口径（沪/深/北）。

背景：stock_info 自 2026-07-04 起冻结（原写入方是死代码），近月新上市个股在行业
映射、备用宇宙、F10 里全部不可见，且 335 只 industry 为空。

职责边界（重要）：
  * 只维护 code/name——官方清单是这两列的权威源；
  * 绝不覆盖 industry/market_cap/latest_price/财务列（那些来自行情与财务管线）；
  * 缺失行业单独用东财单股 f127 补齐（与既有申万口径同源）。深市清单里的
    「所属行业」是证监会分类，与现口径不同 taxonomy，混进去会让板块聚合裂开。
"""
from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
from sqlalchemy import text

import db
from repo.base import upsert

log = logging.getLogger(__name__)

# B 股前缀（沪 900xxx / 深 200xxx）不属于 A 股宇宙
_EXCLUDE_PREFIX = ("900", "200")


def fetch_official_lists() -> pd.DataFrame:
    """沪（主板A股+科创板）+ 深（A股列表）+ 北交所 → code/name/list_date/exchange。"""
    import akshare as ak

    specs = (
        ("SH_MAIN", ak.stock_info_sh_name_code, {"symbol": "主板A股"}, "证券代码", "证券简称", "上市日期"),
        ("SH_STAR", ak.stock_info_sh_name_code, {"symbol": "科创板"}, "证券代码", "证券简称", "上市日期"),
        ("SZ", ak.stock_info_sz_name_code, {"symbol": "A股列表"}, "A股代码", "A股简称", "A股上市日期"),
        ("BJ", ak.stock_info_bj_name_code, {}, "证券代码", "证券简称", "上市日期"),
    )
    frames = []
    for label, fn, kwargs, code_col, name_col, date_col in specs:
        try:
            raw = fn(**kwargs)
        except Exception as e:
            log.warning("[job:stock_list] %s failed: %s", label, e)
            continue
        if raw is None or raw.empty or code_col not in raw.columns:
            log.warning("[job:stock_list] %s returned no usable frame", label)
            continue
        codes = raw[code_col].astype(str).str.extract(r"(\d+)", expand=False)
        names = raw[name_col].astype(str).str.strip() if name_col in raw.columns else ""
        dates = (pd.to_datetime(raw[date_col], errors="coerce").dt.date
                 if date_col in raw.columns else [None] * len(raw))
        d = pd.DataFrame({
            "code": codes.str.zfill(6),
            "name": names,
            "list_date": list(dates),
            "exchange": label,
        })
        d = d[d["code"].notna() & (d["code"].str.len() == 6)]
        d = d[~d["code"].str.startswith(_EXCLUDE_PREFIX)]
        frames.append(d)
        log.info("[job:stock_list] %s -> %d rows", label, len(d))
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out = out[out["name"].str.len().between(1, 40)]
    return out.drop_duplicates(subset=["code"]).reset_index(drop=True)


def sync_stock_info(df: Optional[pd.DataFrame] = None) -> dict:
    """新股入库 + 现股改名。update_columns 只含 name——其余列一律不动。"""
    eng = db.get_engine()
    if eng is None:
        return {"ok": False, "reason": "mysql unavailable"}
    if df is None:
        df = fetch_official_lists()
    if df.empty:
        return {"ok": False, "reason": "official lists empty"}
    with eng.connect() as conn:
        have = pd.read_sql(text("SELECT code, name FROM stock_info"), conn)
    have["code"] = have["code"].astype(str).str.zfill(6)
    known = set(have["code"])
    new_df = df[~df["code"].isin(known)]

    merged = df.merge(have[["code", "name"]].rename(columns={"name": "name_old"}), on="code")
    changed = merged[merged["name"].astype(str) != merged["name_old"].astype(str)]
    rename_cnt = int(len(changed))

    inserted = 0
    if not new_df.empty:
        rows = [{"code": c, "name": n, "industry": ""}
                for c, n in zip(new_df["code"], new_df["name"])]
        inserted = upsert("stock_info", rows, ["code", "name", "industry"], update_columns=["name"])

    updated = 0
    if rename_cnt:
        # 只更 name:industry/market_cap/财务列由行情与财务管线负责
        rows = [{"code": c, "name": n, "industry": ""}
                for c, n in zip(changed["code"], changed["name"])]
        updated = upsert("stock_info", rows, ["code", "name", "industry"], update_columns=["name"])

    stats = {"ok": True, "listed": int(len(df)), "new": int(len(new_df)),
             "renamed": rename_cnt, "inserted_rows": inserted, "updated_rows": updated}
    log.info("[job:stock_list] %s", stats)
    return stats


def fill_missing_industry(limit: int = 30, sleep_s: float = 1.0) -> int:
    """给 industry 缺失的股票补申万口径行业（与既有值同源）。

    走 em_realtime.fetch_single_quote（curl_cffi 浏览器指纹）：httpx 直连 push2
    单股接口在批量下会立刻 Server disconnected——与全市场 clist 是同一堵墙。
    配额刻意保守（默认 30 只 / 1s 间隔）：2026-10-11 一次 380 只的突发把
    单股行情与 push2his 都打成了分钟级封锁，代价比收益大。
    优先 ''（新入库股票，真的在市）再补 '-'（历史遗留/停牌），已有行业一律不覆盖；
    停牌股单股行情返回 '-' 取不到行业，保持为空而不是造数。
    """
    import time

    import em_realtime

    eng = db.get_engine()
    if eng is None:
        return 0
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT code FROM stock_info "
            "WHERE industry IS NULL OR industry='' OR industry='-' "
            "ORDER BY CASE WHEN industry='' THEN 0 ELSE 1 END LIMIT :lim"
        ), {"lim": limit}).fetchall()
    codes = [str(r[0]).zfill(6) for r in rows]
    if not codes:
        return 0

    mapping: dict[str, str] = {}
    for c in codes:
        try:
            df = em_realtime.fetch_single_quote(c)
        except Exception as e:
            log.debug("[job:stock_list] single quote %s failed: %s", c, e)
            df = None
        if df is not None and not df.empty:
            ind = str(df.iloc[0].get("行业") or "").strip()
            if ind and ind != "-":
                mapping[c] = ind
        if sleep_s:
            time.sleep(sleep_s)

    if not mapping:
        log.warning("[job:stock_list] industry 补齐 0/%d（单股行情未返回行业）", len(codes))
        return 0
    with eng.begin() as conn:
        for c, ind in mapping.items():
            conn.execute(text(
                "UPDATE stock_info SET industry=:i "
                "WHERE code=:c AND (industry IS NULL OR industry='' OR industry=:dash)"
            ), {"i": ind, "c": c, "dash": "-"})
    log.info("[job:stock_list] industry 补齐 %d/%d", len(mapping), len(codes))
    return len(mapping)


def run(fill_limit: int = 30) -> dict:
    stats = sync_stock_info()
    if stats.get("ok"):
        stats["industry_filled"] = fill_missing_industry(limit=fill_limit)
    return stats


def fill_only(fill_limit: int = 30) -> int:
    """每日小配额补齐行业——新股入库后不必等整周。"""
    return fill_missing_industry(limit=fill_limit)
