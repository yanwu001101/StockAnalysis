"""龙虎榜数据模块 (设计文档 §3.4)。

采集: 当日龙虎榜个股列表 + 买卖席位明细。
席位明细只拉净买额靠前的个股 (config.LHB_SEAT_DETAIL_TOP), 控制请求频率。
"""
from __future__ import annotations

import time

import akshare as ak

import config
from data.market import _num, _retry


def _s(v) -> str:
    text = str(v) if v is not None else ""
    return "" if text.lower() in ("nan", "none", "nat") else text


def fetch_lhb(date: str) -> list[dict]:
    """当日龙虎榜列表 (同一代码多个上榜原因时保留龙虎榜成交额最大的一条)。"""
    try:
        df = _retry(ak.stock_lhb_detail_em, start_date=date, end_date=date)
    except Exception:
        return []
    if df is None or df.empty:
        return []
    by_code: dict[str, dict] = {}
    for _, r in df.iterrows():
        row = {
            "code": _s(r.get("代码")).zfill(6),
            "name": _s(r.get("名称")),
            "pct": _num(r.get("涨跌幅")),
            "close": _num(r.get("收盘价")),
            "net_buy": _num(r.get("龙虎榜净买额")),      # 元
            "buy": _num(r.get("龙虎榜买入额")),
            "sell": _num(r.get("龙虎榜卖出额")),
            "lhb_amount": _num(r.get("龙虎榜成交额")),
            "total_amount": _num(r.get("市场总成交额")),
            "reason": _s(r.get("上榜原因")),
            "seats": None,
        }
        old = by_code.get(row["code"])
        if old is None or (row["lhb_amount"] or 0) > (old["lhb_amount"] or 0):
            by_code[row["code"]] = row
    rows = sorted(by_code.values(), key=lambda x: -(x["net_buy"] or 0))
    return rows


def fetch_seats(code: str, date: str) -> dict:
    """个股买卖席位明细: {buy: [{seat, buy, sell, net}], sell: [...]}。"""
    out: dict = {"buy": [], "sell": []}
    for flag, key in (("买入", "buy"), ("卖出", "sell")):
        try:
            df = _retry(ak.stock_lhb_stock_detail_em, symbol=code, date=date, flag=flag)
        except Exception:
            continue
        if df is None or df.empty:
            continue
        for _, r in df.iterrows():
            seat = _s(r.get("交易营业部名称"))
            if not seat:
                continue
            out[key].append(
                {
                    "seat": seat,
                    "buy": _num(r.get("买入金额"), 0) or 0,
                    "sell": _num(r.get("卖出金额"), 0) or 0,
                    "net": _num(r.get("净额"), 0) or 0,
                }
            )
    return out


def attach_seats(lhb: list[dict], date: str, top: int | None = None) -> None:
    """就地为净买额靠前的个股补充席位明细。"""
    top = top or config.LHB_SEAT_DETAIL_TOP
    for row in lhb[:top]:
        row["seats"] = fetch_seats(row["code"], date)
        time.sleep(0.3)  # 温和限速
