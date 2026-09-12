# -*- coding: utf-8 -*-
"""Daily push job (17:45 after scoring): market close summary via webhook.

Content: 数据新鲜度 / 看多信号统计 / 高分股票 Top5 / 数据异常提醒。
周末跳过；非交易日数据不更新时在摘要中标注「数据未更新」。
"""
from __future__ import annotations
import datetime as dt

import pandas as pd
from sqlalchemy import text

import notifier
from core.trace import logger
from repo import base, index_kline_repo
from repo import strategy_score_repo

TOP_STRATEGY = "technical_resonance"   # 摘要用的代表策略（技术共振：多因子合成）


def _is_trading_day(today: dt.date) -> bool:
    df = base.fetch_df(
        "SELECT trade_date FROM index_kline_daily WHERE code=:c AND trade_date=:d",
        {"c": "000300", "d": today},
    )
    return not df.empty


def _latest_kline_date() -> str:
    df = base.fetch_df("SELECT MAX(trade_date) AS d FROM stock_kline_daily")
    if df.empty or df.iloc[0]["d"] is None:
        return "—"
    return str(pd.to_datetime(df.iloc[0]["d"]).date())


def _market_summary(today: dt.date) -> str:
    """沪深300 当日涨跌（有指数数据时）。"""
    df = base.fetch_df(
        "SELECT trade_date, close FROM index_kline_daily WHERE code=:c "
        "ORDER BY trade_date DESC LIMIT 2",
        {"c": "000300"},
    )
    if len(df) < 2:
        return ""
    closes = [float(x) for x in df["close"]]
    chg = (closes[0] / closes[1] - 1) * 100 if closes[1] else 0.0
    latest = pd.to_datetime(df.iloc[0]["trade_date"]).date()
    if latest != today:
        return f"\n**市场**：沪深300 {closes[0]:.2f}（{latest} 收盘，今日数据未更新）"
    arrow = "🔴" if chg >= 0 else "🟢"
    return f"\n**市场**：沪深300 {closes[0]:.2f} {arrow} {chg:+.2f}%"


def _signal_stats(today: dt.date) -> tuple[int, int]:
    """今日评分中看多 / 看空信号数（全部策略合计）。"""
    df = base.fetch_df(
        f"SELECT signal_type, COUNT(*) AS n FROM {strategy_score_repo.TABLE} "
        "WHERE DATE(computed_at) = :d AND score > 0 "
        "GROUP BY signal_type",
        {"d": today},
    )
    bull = bear = 0
    if not df.empty:
        for _, r in df.iterrows():
            sig = str(r["signal_type"] or "").lower()
            if sig == "bullish":
                bull = int(r["n"])
            elif sig == "bearish":
                bear = int(r["n"])
    return bull, bear


def _top_picks(top_n: int = 5) -> list[tuple[str, str, float]]:
    """代表策略今日评分 Top5（代码、名称、评分）。"""
    df = base.fetch_df(
        f"SELECT s.code, COALESCE(i.name, s.code) AS name, s.score "
        f"FROM {strategy_score_repo.TABLE} s "
        f"LEFT JOIN stock_info i ON i.code = s.code "
        f"WHERE s.strategy_id = :sid AND s.score > 0 "
        f"AND DATE(s.computed_at) = :d "
        f"ORDER BY s.score DESC LIMIT {top_n}",
        {"sid": TOP_STRATEGY, "d": dt.date.today()},
    )
    return [(str(r["code"]), str(r["name"]), float(r["score"])) for _, r in df.iterrows()]


def build_summary(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    lines: list[str] = [f"**📊 盘后摘要 · {today}**"]

    lines.append(_market_summary(today))
    lines.append(f"\n**数据**：K 线最新 {_latest_kline_date()}")

    bull, bear = _signal_stats(today)
    if bull or bear:
        lines.append(f"**信号**：看多 {bull} 条 · 看空 {bear} 条（29 策略合计，今日评分）")
    else:
        lines.append("**信号**：今日评分尚未生成或为空 — 检查 17:30 评分任务是否成功")

    picks = _top_picks()
    if picks:
        lines.append(f"\n**{TOP_STRATEGY} Top{len(picks)}**")
        for code, name, score in picks:
            lines.append(f"> {code} {name} — {score:.0f} 分")


    return "\n".join(lines)


def run(today: dt.date | None = None) -> bool:
    today = today or dt.date.today()
    if today.weekday() >= 5:
        logger.info("[daily_push] weekend — skip")
        return False
    if not _is_trading_day(today):
        # 节假日：指数日历里没有今天 → 无新数据，提示性跳过
        logger.info("[daily_push] %s not a trading day — skip", today)
        return False
    md = build_summary(today)
    ok = notifier.send_markdown(f"盘后摘要 {today}", md)
    logger.info("[daily_push] pushed=%s", ok)
    return ok
