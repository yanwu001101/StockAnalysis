# -*- coding: utf-8 -*-
"""Paper trading repo: daily auto-rebalanced model portfolio.

每个交易日盘后（策略评分落地后）：
  1. 用最新综合评分选 TopN（各策略按注册权重加权，score>0 才计入）
  2. 等权目标调仓，成交价=当日收盘，带成本与涨跌停/停牌约束
  3. 逐日 mark-to-market 记录净值，与沪深300对比
"""
from __future__ import annotations
import datetime as dt

import pandas as pd
from sqlalchemy import text

import db
from core.trace import logger
from repo import base

ACCOUNT_ID = "default"
TABLE = "paper_account"


def get_account() -> dict | None:
    df = base.fetch_df(f"SELECT * FROM {TABLE} WHERE id = :i", {"i": ACCOUNT_ID})
    return df.to_dict("records")[0] if df else None


def ensure_account(initial_capital: float = 1_000_000, top_n: int = 10) -> dict:
    acc = get_account()
    if acc:
        return acc
    base.upsert(TABLE, [{"id": ACCOUNT_ID, "initial_capital": initial_capital,
                         "top_n": top_n, "rebalance": "weekly",
                         "cash": initial_capital}],
                ["id", "initial_capital", "top_n", "rebalance", "cash"])
    return get_account()


def reset_account(initial_capital: float, top_n: int) -> None:
    eng = base.engine()
    if eng is None:
        return
    with eng.begin() as conn:
        for t in ("paper_positions", "paper_trades", "paper_equity"):
            conn.execute(text(f"DELETE FROM {t} WHERE account_id = :i"), {"i": ACCOUNT_ID})
        conn.execute(text(
            f"REPLACE INTO {TABLE} (id, initial_capital, top_n, rebalance, cash) "
            f"VALUES (:i, :cap, :n, 'weekly', :cap)"),
            {"i": ACCOUNT_ID, "cap": initial_capital, "n": top_n},
    )


def get_positions() -> list[dict]:
    return base.fetch_df(
        "SELECT code, shares, avg_cost, buy_date FROM paper_positions "
        "WHERE account_id = :i ORDER BY code",
        {"i": ACCOUNT_ID},
    ).to_dict("records")


def upsert_position(account_id: str, code: str, shares: float, avg_cost: float, buy_date) -> None:
    base.upsert("paper_positions",
                [{"account_id": account_id, "code": code, "shares": shares,
                  "avg_cost": avg_cost, "buy_date": buy_date}],
                ["account_id", "code", "shares", "avg_cost", "buy_date"])


def delete_position(account_id: str, code: str) -> None:
    eng = base.engine()
    if eng is None:
        return
    with eng.begin() as conn:
        conn.execute(text("DELETE FROM paper_positions WHERE account_id=:i AND code=:c"),
                     {"i": account_id, "c": code})


def add_trade(account_id: str, d: dt.date, code: str, side: str,
              shares: float, price: float, amount: float, cost: float,
              reason: str = "") -> None:
    base.upsert("paper_trades", [{
        "account_id": account_id, "trade_date": d, "code": code, "side": side,
        "shares": shares, "price": price, "amount": amount, "cost": cost,
        "reason": reason,
    }], ["account_id", "trade_date", "code", "side", "shares", "price",
         "amount", "cost", "reason"])


def get_trades(limit: int = 100) -> list[dict]:
    return base.fetch_df(
        "SELECT trade_date, code, side, shares, price, amount, cost, reason "
        "FROM paper_trades WHERE account_id = :i "
        "ORDER BY trade_date DESC, id DESC LIMIT :n",
        {"i": ACCOUNT_ID, "n": limit},
    ).to_dict("records")


def get_equity_curve() -> list[dict]:
    return base.fetch_df(
        "SELECT trade_date, cash, positions_value, equity, benchmark_close "
        "FROM paper_equity WHERE account_id = :i ORDER BY trade_date",
        {"i": ACCOUNT_ID},
    ).to_dict("records")


def upsert_equity(account_id: str, d: dt.date, cash: float,
                  positions_value: float, equity: float, benchmark_close: float | None) -> None:
    base.upsert("paper_equity",
                [{"account_id": account_id, "trade_date": d, "cash": cash,
                  "positions_value": positions_value, "equity": equity,
                  "benchmark_close": benchmark_close}],
                ["account_id", "trade_date", "cash", "positions_value",
                 "equity", "benchmark_close"])


def latest_equity_date() -> dt.date | None:
    df = base.fetch_df(
        "SELECT MAX(trade_date) AS d FROM paper_equity WHERE account_id = :i",
        {"i": ACCOUNT_ID},
    )
    if df.empty or df.iloc[0]["d"] is None:
        return None
    return pd.to_datetime(df.iloc[0]["d"]).date()
