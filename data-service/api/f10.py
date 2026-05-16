# -*- coding: utf-8 -*-
"""F10 (company profile + top holders + dividend + peer comparison)."""
from __future__ import annotations
from typing import Optional

import pandas as pd
from flask import Blueprint, jsonify
from sqlalchemy import text

import cache
import db


bp = Blueprint("f10_v2", __name__, url_prefix="/api/stock")


def _safe_ak(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


@bp.route("/<code>/f10")
def f10(code: str):
    code = str(code).zfill(6)
    out: dict = {"code": code}

    # 1. Company profile — try multiple sources because EM datacenter often
    # returns RemoteDisconnected on free tier. We layer:
    #   Layer 1: akshare stock_individual_info_em (EM push2 — most fields)
    #   Layer 2: 同花顺 stock_zyjs_ths (主营业务)
    #   Layer 3: cached spot snapshot (always available)
    #   Layer 4: stock_info DB table
    import akshare as ak
    info = _safe_ak(ak.stock_individual_info_em, symbol=code)
    profile: dict = {}
    if info is not None and not info.empty and "item" in info.columns and "value" in info.columns:
        for _, r in info.iterrows():
            profile[str(r["item"])] = str(r["value"])

    if "主营业务" not in profile and "主营介绍" not in profile:
        zyjs = _safe_ak(ak.stock_zyjs_ths, symbol=code)
        if zyjs is not None and not zyjs.empty:
            for col in ("主营业务", "主营介绍", "经营范围", "产品类型"):
                if col in zyjs.columns:
                    v = zyjs.iloc[0].get(col)
                    if v and str(v).strip():
                        profile[col] = str(v).strip()
                        break

    if len(profile) < 5:
        spot = cache.get("spot")
        if spot is not None and hasattr(spot, "columns") and "代码" in spot.columns:
            spot = spot.copy()
            spot["代码"] = spot["代码"].astype(str).str.zfill(6)
            r = spot[spot["代码"] == code]
            if not r.empty:
                row = r.iloc[0]
                pairs = {
                    "股票代码": code,
                    "股票简称": row.get("名称", ""),
                    "行业": row.get("行业", ""),
                    "最新价": row.get("最新价"),
                    "总市值(亿)": row.get("总市值_亿"),
                    "流通市值": row.get("流通市值"),
                    "市盈率": row.get("市盈率"),
                    "市净率": row.get("市净率"),
                    "换手率(%)": row.get("换手率"),
                }
                for k, v in pairs.items():
                    if k not in profile and v is not None and not (isinstance(v, float) and pd.isna(v)):
                        profile[k] = str(v)

    if len(profile) < 5:
        eng = db.get_engine()
        if eng is not None:
            with eng.connect() as conn:
                row = conn.execute(text(
                    "SELECT name, industry, latest_price, market_cap, roe, "
                    "debt_ratio, revenue_growth, profit_growth, gross_margin "
                    "FROM stock_info WHERE code=:c LIMIT 1"
                ), {"c": code}).fetchone()
                if row:
                    pairs = {
                        "股票简称": row[0], "行业": row[1], "最新价": row[2],
                        "总市值": row[3], "ROE(%)": row[4],
                        "资产负债率(%)": row[5], "营收增长(%)": row[6],
                        "净利润增长(%)": row[7], "毛利率(%)": row[8],
                    }
                    for k, v in pairs.items():
                        if k not in profile and v is not None:
                            profile[k] = str(v)
    out["profile"] = profile

    # 2. Top 10 floating shareholders (latest report period)
    top_holders: list = []
    try:
        df = _safe_ak(ak.stock_gdfx_top_10_free_em, symbol=code)
        if df is not None and not df.empty:
            df = df.head(10)
            for _, r in df.iterrows():
                top_holders.append({
                    "rank": int(r.get("名次", 0) or 0) if "名次" in df.columns else 0,
                    "name": str(r.get("股东名称", r.get("股东", ""))),
                    "shares": float(r.get("持股数量", 0) or 0),
                    "ratio": float(r.get("持股比例", 0) or 0),
                    "type": str(r.get("股东性质", "")),
                    "change": str(r.get("持股变动", r.get("增减", ""))),
                })
    except Exception:
        pass
    out["topHolders"] = top_holders

    # 3. Dividend history from local DB
    dividends: list = []
    eng = db.get_engine()
    if eng is not None:
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT ann_date, ex_date, cash_per_10, share_per_10, transfer_per_10 "
                "FROM stock_dividend WHERE code=:c "
                "ORDER BY ann_date DESC LIMIT 30"
            ), {"c": code}).fetchall()
            for r in rows:
                dividends.append({
                    "annDate": r[0].isoformat() if r[0] else None,
                    "exDate": r[1].isoformat() if r[1] else None,
                    "cashPer10": float(r[2]) if r[2] is not None else None,
                    "sharePer10": float(r[3]) if r[3] is not None else None,
                    "transferPer10": float(r[4]) if r[4] is not None else None,
                })
    out["dividends"] = dividends

    # 4. Peer comparison: same-industry codes ranked by PE / PB / ROE
    out["peers"] = _peer_compare(code)

    return jsonify(out)


def _peer_compare(code: str) -> dict:
    """Return same-industry stocks ranked alongside the target."""
    spot = cache.get("spot")
    if spot is None or not hasattr(spot, "columns"):
        return {}
    code = code.zfill(6)
    if "代码" not in spot.columns or "行业" not in spot.columns:
        return {}
    spot = spot.copy()
    spot["代码"] = spot["代码"].astype(str).str.zfill(6)
    target_row = spot[spot["代码"] == code]
    if target_row.empty:
        return {}
    industry = str(target_row.iloc[0].get("行业", "") or "").strip()
    if not industry or industry == "-":
        return {}
    peers = spot[spot["行业"].astype(str) == industry].copy()
    # Convert numeric columns
    for col in ("最新价", "涨跌幅", "市盈率", "市净率", "总市值_亿"):
        if col in peers.columns:
            peers[col] = pd.to_numeric(peers[col], errors="coerce")

    # Pull ROE / debt_ratio for this industry from stock_fundamental (latest)
    eng = db.get_engine()
    roe_map: dict[str, float] = {}
    debt_map: dict[str, float] = {}
    if eng is not None:
        with eng.connect() as conn:
            codes_csv = ",".join(f"'{c}'" for c in peers["代码"].tolist())
            if codes_csv:
                rows = conn.execute(text(
                    f"SELECT f.code, f.roe, f.debt_ratio "
                    f"FROM stock_fundamental f "
                    f"INNER JOIN ("
                    f"  SELECT code, MAX(report_date) AS rd FROM stock_fundamental "
                    f"  WHERE code IN ({codes_csv}) GROUP BY code"
                    f") m ON f.code=m.code AND f.report_date=m.rd"
                )).fetchall()
                for r in rows:
                    if r[1] is not None:
                        roe_map[r[0]] = float(r[1])
                    if r[2] is not None:
                        debt_map[r[0]] = float(r[2])

    peer_rows: list = []
    def _num(v, default=0.0):
        """NaN-safe numeric coercion — fastjson2 rejects NaN, so we always
        emit finite floats."""
        try:
            f = float(v)
            if f != f or f in (float("inf"), float("-inf")):  # NaN / Inf check
                return default
            return f
        except (TypeError, ValueError):
            return default

    for _, r in peers.iterrows():
        c = r["代码"]
        peer_rows.append({
            "code": c,
            "name": str(r.get("名称", "")),
            "price": _num(r.get("最新价")),
            "changePercent": round(_num(r.get("涨跌幅")), 2),
            "pe": _num(r.get("市盈率")),
            "pb": _num(r.get("市净率")),
            "marketCap": round(_num(r.get("总市值_亿")), 0),
            "roe": _num(roe_map.get(c)),
            "debtRatio": _num(debt_map.get(c)),
            "isTarget": c == code,
        })

    # Compute the target's rank by each metric
    def rank_in(metric: str, ascending: bool = False) -> int | None:
        vs = [p[metric] for p in peer_rows if p[metric] > 0]
        target_v = next((p[metric] for p in peer_rows if p["isTarget"]), None)
        if target_v is None or target_v <= 0 or not vs:
            return None
        sorted_vs = sorted(vs, reverse=not ascending)
        try:
            return sorted_vs.index(target_v) + 1
        except ValueError:
            return None

    target = next((p for p in peer_rows if p["isTarget"]), None)
    ranks = {}
    if target:
        ranks = {
            "industry": industry,
            "industrySize": len(peer_rows),
            "peByRank": rank_in("pe", ascending=True),         # 低 PE 排名靠前
            "pbByRank": rank_in("pb", ascending=True),
            "roeRank": rank_in("roe", ascending=False),        # 高 ROE 排名靠前
            "marketCapRank": rank_in("marketCap", ascending=False),
        }

    # Sort peers by market cap and cap to 20
    peer_rows.sort(key=lambda x: x.get("marketCap", 0), reverse=True)
    return {
        "industry": industry,
        "totalPeers": len(peer_rows),
        "ranks": ranks,
        "peers": peer_rows[:20],
    }
