"""SQLite 持久层 (设计文档 §5)。

表结构:
  stock         股票基础信息
  limit_up      每日涨停记录 (供板块持续性 / 情绪趋势回溯)
  longhu        龙虎榜记录
  trader        游资席位库
  market_daily  每日市场快照 (温度 / 涨停数 / 高度等, 供情绪周期趋势判断)
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Iterable

import config

_DDL = [
    """CREATE TABLE IF NOT EXISTS stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        name TEXT,
        industry TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS limit_up (
        date TEXT,
        code TEXT,
        name TEXT,
        height INTEGER,
        theme TEXT,
        amount REAL,
        seal_amount REAL,
        first_time TEXT,
        last_time TEXT,
        break_count INTEGER,
        zt_stat TEXT,
        PRIMARY KEY (date, code)
    )""",
    """CREATE TABLE IF NOT EXISTS longhu (
        date TEXT,
        code TEXT,
        name TEXT,
        buyer TEXT,
        seller TEXT,
        money REAL,
        net_buy REAL,
        reason TEXT,
        PRIMARY KEY (date, code)
    )""",
    """CREATE TABLE IF NOT EXISTS trader (
        name TEXT PRIMARY KEY,
        seat TEXT,
        style TEXT,
        history TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS market_daily (
        date TEXT PRIMARY KEY,
        payload TEXT
    )""",
]


@contextmanager
def conn():
    c = sqlite3.connect(str(config.DB_PATH))
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db() -> None:
    config.REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with conn() as c:
        for ddl in _DDL:
            c.execute(ddl)


# ---------------------------------------------------------------------------
# 涨停
# ---------------------------------------------------------------------------

def save_limit_up(date: str, rows: Iterable[dict]) -> None:
    rows = list(rows)
    with conn() as c:
        c.execute("DELETE FROM limit_up WHERE date=?", (date,))
        c.executemany(
            """INSERT OR REPLACE INTO limit_up
               (date, code, name, height, theme, amount, seal_amount,
                first_time, last_time, break_count, zt_stat)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (date, r.get("code"), r.get("name"), r.get("height"),
                 r.get("industry"), r.get("amount"), r.get("seal_amount"),
                 r.get("first_time"), r.get("last_time"),
                 r.get("break_count"), r.get("zt_stat"))
                for r in rows
            ],
        )
        c.executemany(
            "INSERT OR IGNORE INTO stock (code, name, industry) VALUES (?,?,?)",
            [(r.get("code"), r.get("name"), r.get("industry")) for r in rows],
        )


def theme_daily_counts(end_date: str, days: int = 10) -> dict[str, dict[str, int]]:
    """近 N 个有记录交易日, 每个板块每日涨停家数: {date: {theme: count}}。"""
    with conn() as c:
        dates = [
            r["date"] for r in c.execute(
                "SELECT DISTINCT date FROM limit_up WHERE date<=? ORDER BY date DESC LIMIT ?",
                (end_date, days),
            )
        ]
        if not dates:
            return {}
        marks = ",".join("?" * len(dates))
        out: dict[str, dict[str, int]] = {d: {} for d in dates}
        for r in c.execute(
            f"SELECT date, theme, COUNT(*) AS n FROM limit_up "
            f"WHERE date IN ({marks}) GROUP BY date, theme",
            dates,
        ):
            if r["theme"]:
                out[r["date"]][r["theme"]] = r["n"]
        return out


# ---------------------------------------------------------------------------
# 龙虎榜
# ---------------------------------------------------------------------------

def save_longhu(date: str, rows: Iterable[dict]) -> None:
    with conn() as c:
        c.execute("DELETE FROM longhu WHERE date=?", (date,))
        c.executemany(
            """INSERT OR REPLACE INTO longhu
               (date, code, name, buyer, seller, money, net_buy, reason)
               VALUES (?,?,?,?,?,?,?,?)""",
            [
                (date, r.get("code"), r.get("name"),
                 "; ".join(s.get("seat", "") for s in (r.get("seats") or {}).get("buy", [])[:5]),
                 "; ".join(s.get("seat", "") for s in (r.get("seats") or {}).get("sell", [])[:5]),
                 r.get("lhb_amount"), r.get("net_buy"), r.get("reason"))
                for r in rows
            ],
        )


# ---------------------------------------------------------------------------
# 游资席位库
# ---------------------------------------------------------------------------

def seed_traders(items: Iterable[dict]) -> None:
    with conn() as c:
        c.executemany(
            "INSERT OR IGNORE INTO trader (name, seat, style, history) VALUES (?,?,?,?)",
            [(t["name"], t["seat"], t["style"], t.get("history", "")) for t in items],
        )


def all_traders() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM trader")]


# ---------------------------------------------------------------------------
# 每日市场快照
# ---------------------------------------------------------------------------

def save_market_daily(date: str, payload: dict) -> None:
    with conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO market_daily (date, payload) VALUES (?,?)",
            (date, json.dumps(payload, ensure_ascii=False)),
        )


def load_market_daily(date: str) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT payload FROM market_daily WHERE date=?", (date,)).fetchone()
        return json.loads(row["payload"]) if row else None


def recent_market(end_date: str, days: int = 10) -> list[dict]:
    """<= end_date 的最近 N 天快照, 按日期升序。"""
    with conn() as c:
        rows = c.execute(
            "SELECT date, payload FROM market_daily WHERE date<=? ORDER BY date DESC LIMIT ?",
            (end_date, days),
        ).fetchall()
    out = []
    for r in reversed(rows):
        d = json.loads(r["payload"])
        d["date"] = r["date"]
        out.append(d)
    return out
