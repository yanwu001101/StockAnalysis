# -*- coding: utf-8 -*-
"""Daily paper trading job (17:50, after strategy scoring).

流程（每个交易日）：
  1. mark-to-market：按最新收盘更新净值曲线（含沪深300基准对比）
  2. 调仓检查：weekly = 本周最后一个交易日；首次运行当日直接建仓
  3. 调仓执行：最新综合评分 TopN 等权，收盘价成交，
     带成本（佣金/印花税/滑点）与约束（涨停不买/跌停不卖/停牌跳过/整手）

综合评分口径：stock_strategy_score 最新快照，各策略按注册默认权重加权
（score>0 才计入该策略）。用户自定义权重目前存在前端 localStorage，
服务端暂用注册表默认权重 — 待权重云同步后自动对齐。
"""
from __future__ import annotations
import datetime as dt

import numpy as np
import pandas as pd
from sqlalchemy import text

import db
from core.trace import logger
from strategies import REGISTRY
from repo import paper_repo

LOT = 100
COMMISSION_RATE = 0.00025
COMMISSION_MIN = 5.0
STAMP_TAX = 0.0005
SLIPPAGE = 0.001


def _commission(amount: float) -> float:
    return max(amount * COMMISSION_RATE, COMMISSION_MIN)


def _limit_price(prev_close: float, code: str, down: bool) -> float:
    c = str(code).zfill(6)
    if c.startswith(("300", "301", "688", "689")):
        ratio = 0.20
    elif c.startswith(("8", "4", "92")):
        ratio = 0.30
    else:
        ratio = 0.10
    x = prev_close * (1 - ratio if down else 1 + ratio)
    return np.floor(x * 100 + 0.5) / 100 if not down else np.ceil(x * 100 - 0.5) / 100


def _strategy_weights() -> dict[str, float]:
    return {cls.id: float(cls.default_weight) for cls in REGISTRY}


def _composite_scores(today: dt.date) -> dict[str, float]:
    """最新评分快照的加权综合分。score<=0 的策略不参与该股加权。"""
    eng = db.get_engine()
    if eng is None:
        return {}
    weights = _strategy_weights()
    try:
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT code, strategy_id, score FROM stock_strategy_score "
                "WHERE score > 0 AND DATE(computed_at) = :d"
            ), {"d": today}).fetchall()
    except Exception as e:
        logger.warning("[paper] score query failed: %s", e)
        return {}
    num: dict[str, float] = {}
    den: dict[str, float] = {}
    for code, sid, score in rows:
        w = weights.get(str(sid))
        if w is None or w <= 0:
            continue
        c = str(code).zfill(6)
        num[c] = num.get(c, 0.0) + w * float(score)
        den[c] = den.get(c, 0.0) + w
    return {c: num[c] / den[c] for c in num if den[c] > 0}


def _bench_close(today: dt.date) -> float | None:
    eng = db.get_engine()
    if eng is None:
        return None
    try:
        with eng.connect() as conn:
            row = conn.execute(text(
                "SELECT close FROM index_kline_daily WHERE code='000300' AND trade_date<=:d "
                "ORDER BY trade_date DESC LIMIT 1"), {"d": today}).fetchone()
        return float(row[0]) if row else None
    except Exception:
        return None


def _trading_days_until(today: dt.date, n: int = 30) -> list[dt.date]:
    eng = db.get_engine()
    if eng is None:
        return []
    start = today - dt.timedelta(days=n * 2)
    try:
        with eng.connect() as conn:
            rows = conn.execute(text(
                "SELECT trade_date FROM index_kline_daily "
                "WHERE code='000300' AND trade_date BETWEEN :s AND :e ORDER BY trade_date"),
                {"s": start, "e": today}).fetchall()
        return [r[0] for r in rows]
    except Exception:
        return []


def _is_rebalance_day(today: dt.date, trading_days: list[dt.date], freq: str,
                      never_traded: bool) -> bool:
    if never_traded:
        return True   # 首次运行当日建仓
    if freq == "daily":
        return True
    later = [d for d in trading_days if d > today]
    if freq == "weekly":
        week = today.isocalendar()[:2]
        return not any(d.isocalendar()[:2] == week for d in later)
    return not any(d.month == today.month for d in later)


def _has_trades() -> bool:
    eng = db.get_engine()
    if eng is None:
        return False
    try:
        with eng.connect() as conn:
            row = conn.execute(text(
                "SELECT COUNT(*) FROM paper_trades WHERE account_id = :i"),
                {"i": paper_repo.ACCOUNT_ID}).fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def run(today: dt.date | None = None) -> dict:
    today = today or dt.date.today()
    if today.weekday() >= 5:
        logger.info("[paper] weekend — skip")
        return {"skipped": "weekend"}

    acc = paper_repo.ensure_account()
    account_id = paper_repo.ACCOUNT_ID
    cash = float(acc["cash"])

    eng = db.get_engine()
    if eng is None:
        return {"error": "no db"}

    # 当日全市场收盘/量
    with eng.connect() as conn:
        df = pd.read_sql(text(
            "SELECT code, close, volume FROM stock_kline_daily WHERE trade_date = :d"
        ), conn, params={"d": today})
    if df.empty:
        logger.info("[paper] %s has no kline rows yet — skip", today)
        return {"skipped": "no bars today"}
    close_today = {str(r["code"]).zfill(6): float(r["close"])
                   for _, r in df.iterrows() if pd.notna(r["close"])}
    vol_today = {str(r["code"]).zfill(6): (float(r["volume"]) if pd.notna(r["volume"]) else 0.0)
                 for _, r in df.iterrows()}

    # 昨收（涨跌停基准）
    with eng.connect() as conn:
        prev_df = pd.read_sql(text(
            "SELECT code, close FROM stock_kline_daily "
            "WHERE trade_date = (SELECT MAX(trade_date) FROM stock_kline_daily "
            "WHERE trade_date < :d)"
        ), conn, params={"d": today})
    prev_close = {str(r["code"]).zfill(6): float(r["close"])
                  for _, r in prev_df.iterrows() if pd.notna(r["close"])}

    def suspended(c: str) -> bool:
        return close_today.get(c, 0) <= 0 or vol_today.get(c, 0) <= 0

    def sealed_up(c: str) -> bool:
        px, pc = close_today.get(c), prev_close.get(c)
        return px is not None and pc is not None and px >= _limit_price(pc, c, down=False)

    def sealed_down(c: str) -> bool:
        px, pc = close_today.get(c), prev_close.get(c)
        return px is not None and pc is not None and px <= _limit_price(pc, c, down=True)

    # ---- 1) mark-to-market ----
    positions = {p["code"]: {"shares": float(p["shares"]), "avg_cost": float(p["avg_cost"]),
                             "buy_date": p["buy_date"]}
                 for p in paper_repo.get_positions()}
    pos_value = 0.0
    with eng.connect() as conn:
        for c, h in positions.items():
            row = conn.execute(text(
                "SELECT close FROM stock_kline_daily WHERE code=:c AND trade_date<=:d "
                "AND close IS NOT NULL ORDER BY trade_date DESC LIMIT 1"),
                {"c": c, "d": today}).fetchone()
            price = float(row[0]) if row else h["avg_cost"]
            pos_value += h["shares"] * price
    equity = cash + pos_value
    bench = _bench_close(today)
    paper_repo.upsert_equity(account_id, today, cash, pos_value, equity, bench)

    # ---- 2) 调仓检查 ----
    trading_days = _trading_days_until(today)
    never_traded = not _has_trades()
    if not _is_rebalance_day(today, trading_days, str(acc.get("rebalance") or "weekly"),
                             never_traded):
        logger.info("[paper] %s not a rebalance day — marked only", today)
        return {"status": "marked", "equity": round(equity, 2)}

    # ---- 3) 调仓 ----
    scores = _composite_scores(today)
    if not scores:
        logger.warning("[paper] no composite scores for %s — skip rebalance", today)
        return {"status": "no-scores"}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    picks = [c for c, _ in ranked[:int(acc["top_n"])]]
    pick_set = set(picks)
    total_cost = 0.0

    # 卖出：调出组合且可卖（未跌停/未停牌）
    for c in list(positions.keys()):
        if c in pick_set:
            continue
        if suspended(c) or sealed_down(c):
            logger.info("[paper] %s 跌停/停牌无法卖出，继续持有", c)
            continue
        h = positions[c]
        exec_px = close_today[c] * (1 - SLIPPAGE)
        gross = h["shares"] * exec_px
        fee = _commission(gross)
        tax = gross * STAMP_TAX
        cash += gross - fee - tax
        total_cost += fee + tax
        paper_repo.add_trade(account_id, today, c, "sell", -h["shares"],
                             round(exec_px, 3), round(gross, 2), round(fee + tax, 2))
        del positions[c]
        paper_repo.delete_position(account_id, c)

    # 买入：等权整手
    held_value = sum(h["shares"] * close_today.get(c, h["avg_cost"])
                     for c, h in positions.items() if c in pick_set)
    n_target = max(len(picks), 1)
    tgt_value = (cash + held_value) / n_target
    for c in picks:
        if suspended(c) or sealed_up(c):
            logger.info("[paper] %s 涨停/停牌无法买入，跳过", c)
            continue
        px_exec = close_today[c] * (1 + SLIPPAGE)
        cur_sh = positions.get(c, {}).get("shares", 0.0)
        tgt_sh = int((tgt_value / px_exec) / LOT) * LOT
        diff_sh = tgt_sh - cur_sh
        if diff_sh <= 0:
            continue
        amount = diff_sh * px_exec
        fee = _commission(amount)
        if amount + fee > cash:
            afford_lots = int((cash / px_exec) / LOT)
            diff_sh = afford_lots * LOT - cur_sh
            if diff_sh <= 0:
                continue
            amount = diff_sh * px_exec
            fee = _commission(amount)
        cash -= amount + fee
        total_cost += fee
        h = positions.get(c, {"shares": 0.0, "avg_cost": px_exec, "buy_date": today})
        new_sh = cur_sh + diff_sh
        old_basis = h["avg_cost"] if cur_sh > 0 else px_exec
        new_basis = (old_basis * cur_sh + px_exec * diff_sh) / new_sh if new_sh > 0 else px_exec
        positions[c] = {"shares": new_sh, "avg_cost": new_basis, "buy_date": today}
        paper_repo.upsert_position(account_id, c, new_sh, new_basis, today)
        paper_repo.add_trade(account_id, today, c, "buy", diff_sh,
                             round(exec_px, 3), round(amount, 2), round(fee, 2))

    # 更新现金与收盘净值
    with eng.begin() as conn:
        conn.execute(text("UPDATE paper_account SET cash = :c WHERE id = :i"),
                     {"c": cash, "i": account_id})
    pos_value = 0.0
    with eng.connect() as conn:
        for c, h in positions.items():
            if c in close_today:
                price = close_today[c]
            else:
                row = conn.execute(text(
                    "SELECT close FROM stock_kline_daily WHERE code=:c AND trade_date<=:d "
                    "AND close IS NOT NULL ORDER BY trade_date DESC LIMIT 1"),
                    {"c": c, "d": today}).fetchone()
                price = float(row[0]) if row else h["avg_cost"]
            pos_value += h["shares"] * price
    equity = cash + pos_value
    paper_repo.upsert_equity(account_id, today, cash, pos_value, equity, bench)
    logger.info("[paper] %s rebalanced: %d holdings, equity %.0f, cost %.0f",
                today, len(positions), equity, total_cost)
    return {"status": "rebalanced", "equity": round(equity, 2),
            "cost": round(total_cost, 2), "holdings": len(positions)}
