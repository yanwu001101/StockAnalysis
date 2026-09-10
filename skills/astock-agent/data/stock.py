"""涨停板数据模块 (设计文档 §3.2)。

采集: 涨停股池 / 跌停股池 / 炸板股池 / 昨日涨停股今日表现。
数据源: 东方财富 (via akshare), 支持历史日期。
"""
from __future__ import annotations

import akshare as ak

from data.market import _num, _retry


def _s(v) -> str:
    text = str(v) if v is not None else ""
    return "" if text.lower() in ("nan", "none", "nat") else text


def _keep(name) -> bool:
    """过滤 ST / *ST / 退市整理股, 避免污染情绪与梯队统计。"""
    n = _s(name).upper()
    return bool(n) and "ST" not in n and "退" not in n


def fetch_zt_pool(date: str) -> list[dict]:
    """当日涨停股池, 已归一化字段。"""
    try:
        df = _retry(ak.stock_zt_pool_em, date=date)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    rows = []
    for _, r in df.iterrows():
        if not _keep(r.get("名称")):
            continue
        rows.append(
            {
                "code": _s(r.get("代码")).zfill(6),
                "name": _s(r.get("名称")),
                "pct": _num(r.get("涨跌幅")),
                "price": _num(r.get("最新价")),
                "amount": _num(r.get("成交额")),          # 元
                "float_mv": _num(r.get("流通市值")),       # 元
                "turnover": _num(r.get("换手率")),
                "seal_amount": _num(r.get("封板资金")),    # 元
                "first_time": _s(r.get("首次封板时间")),
                "last_time": _s(r.get("最后封板时间")),
                "break_count": int(_num(r.get("炸板次数"), 0) or 0),
                "zt_stat": _s(r.get("涨停统计")),          # 如 "3/2" = 3天2板
                "height": int(_num(r.get("连板数"), 1) or 1),
                "industry": _s(r.get("所属行业")),
            }
        )
    rows.sort(key=lambda x: (-x["height"], -(x["amount"] or 0)))
    return rows


def fetch_dt_pool(date: str) -> list[dict]:
    """当日跌停股池。"""
    try:
        df = _retry(ak.stock_zt_pool_dtgc_em, date=date)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    return [
        {
            "code": _s(r.get("代码")).zfill(6),
            "name": _s(r.get("名称")),
            "pct": _num(r.get("涨跌幅")),
            "amount": _num(r.get("成交额")),
            "seal_amount": _num(r.get("封单资金")),
            "days": int(_num(r.get("连续跌停"), 1) or 1),
            "industry": _s(r.get("所属行业")),
        }
        for _, r in df.iterrows()
        if _keep(r.get("名称"))
    ]


def fetch_zb_pool(date: str) -> list[dict]:
    """当日炸板股池 (曾涨停后打开未回封)。"""
    try:
        df = _retry(ak.stock_zt_pool_zbgc_em, date=date)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    return [
        {
            "code": _s(r.get("代码")).zfill(6),
            "name": _s(r.get("名称")),
            "pct": _num(r.get("涨跌幅")),
            "amount": _num(r.get("成交额")),
            "break_count": int(_num(r.get("炸板次数"), 0) or 0),
            "zt_stat": _s(r.get("涨停统计")),
            "industry": _s(r.get("所属行业")),
        }
        for _, r in df.iterrows()
        if _keep(r.get("名称"))
    ]


def fetch_prev_zt_perf(date: str) -> dict:
    """昨日涨停股在 date 当日的表现 -> 接力赚钱效应。

    返回 {count, avg_pct, up_ratio, codes}。接口失败返回空 dict。
    """
    try:
        df = _retry(ak.stock_zt_pool_previous_em, date=date)
    except Exception:
        return {}
    if df is None or df.empty:
        return {}
    kept = [r for _, r in df.iterrows() if _keep(r.get("名称"))]
    pcts = [p for p in (_num(r.get("涨跌幅")) for r in kept) if p is not None]
    codes = [_s(r.get("代码")).zfill(6) for r in kept]
    if not pcts:
        return {}
    return {
        "count": len(codes),
        "avg_pct": round(sum(pcts) / len(pcts), 2),
        "up_ratio": round(sum(1 for p in pcts if p > 0) / len(pcts), 3),
        "codes": codes,
    }
