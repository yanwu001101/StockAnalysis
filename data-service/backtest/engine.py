# -*- coding: utf-8 -*-
"""Lightweight matrix backtester (vectorbt-style, no extra dep).

Two modes:
  * `run()`        — cross-sectional TopN portfolio backtest
  * `run_single()` — single-stock signal timing (bullish=buy, bearish=sell)

Both return {equity_curve, trades, metrics, picks}.
"""
from __future__ import annotations
import datetime as dt

import numpy as np
import pandas as pd
from sqlalchemy import text

import db
from backtest.metrics import compute
from core.trace import logger
from strategies import REGISTRY, by_id
from strategies.base import StrategyContext


def _trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    eng = db.get_engine()
    if eng is None:
        # Approximation: weekdays
        days = []
        d = start
        while d <= end:
            if d.weekday() < 5:
                days.append(d)
            d += dt.timedelta(days=1)
        return days
    with eng.connect() as conn:
        rows = conn.execute(
            text("SELECT DISTINCT trade_date FROM stock_kline_daily "
                 "WHERE trade_date BETWEEN :s AND :e ORDER BY trade_date"),
            {"s": start, "e": end},
        ).fetchall()
    return [r[0] for r in rows]


def _universe_close_matrix(start: dt.date, end: dt.date) -> pd.DataFrame:
    """Return DataFrame indexed by trade_date, columns=code, values=close."""
    eng = db.get_engine()
    if eng is None:
        return pd.DataFrame()
    with eng.connect() as conn:
        df = pd.read_sql(
            text(
                "SELECT trade_date, code, close FROM stock_kline_daily "
                "WHERE trade_date BETWEEN :s AND :e"
            ),
            conn, params={"s": start, "e": end},
        )
    if df.empty:
        return df
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.pivot(index="trade_date", columns="code", values="close").sort_index()


def _score_universe(strategy_id: str, codes: list[str]) -> dict[str, float]:
    """Compute strategy score for each code using latest data in MySQL.

    Each context is built from the latest persisted data, so scores are static
    over the backtest window. Good enough for relative ranking validation.
    """
    strat = by_id(strategy_id)
    if strat is None:
        return {}

    eng = db.get_engine()
    if eng is None:
        return {}
    out: dict[str, float] = {}
    with eng.connect() as conn:
        for code in codes:
            try:
                dk = pd.read_sql(
                    text("SELECT trade_date, open, close, high, low, volume "
                         "FROM stock_kline_daily WHERE code=:c "
                         "ORDER BY trade_date DESC LIMIT 260"),
                    conn, params={"c": code},
                )
                if dk.empty:
                    continue
                dk = dk.sort_values("trade_date").rename(columns={
                    "trade_date": "日期", "open": "开盘", "close": "收盘",
                    "high": "最高", "low": "最低", "volume": "成交量",
                })
                ctx = StrategyContext(code=code, daily_df=dk)
                # Pull fundamental etc. only if strategy needs it
                if strategy_id in ("piotroski_f", "magic_formula", "quality_factor", "pead"):
                    f = pd.read_sql(
                        text("SELECT * FROM stock_fundamental WHERE code=:c "
                             "ORDER BY report_date DESC LIMIT 12"),
                        conn, params={"c": code},
                    )
                    if not f.empty:
                        ctx.fundamental_df = f
                if strategy_id in ("northbound_smart_money", "technical_resonance"):
                    n = pd.read_sql(
                        text("SELECT * FROM stock_northbound WHERE code=:c "
                             "ORDER BY trade_date DESC LIMIT 60"),
                        conn, params={"c": code},
                    )
                    if not n.empty:
                        ctx.northbound_df = n
                if strategy_id == "lhb_followup":
                    l = pd.read_sql(
                        text("SELECT * FROM stock_lhb WHERE code=:c "
                             "ORDER BY trade_date DESC LIMIT 60"),
                        conn, params={"c": code},
                    )
                    if not l.empty:
                        ctx.lhb_df = l
                res = strat.score(ctx)
                if res and res.score > 0:
                    out[code] = res.score
            except Exception as e:
                logger.debug("backtest score code=%s err=%s", code, e)
    return out


def _rebalance_dates(trading_days: list[dt.date], freq: str) -> list[dt.date]:
    if not trading_days:
        return []
    if freq == "daily":
        return trading_days
    by_period: dict = {}
    for d in trading_days:
        key = (d.year, d.isocalendar()[1]) if freq == "weekly" else (d.year, d.month)
        by_period[key] = d   # last day in period
    return sorted(by_period.values())


def run(strategy_id: str, start: dt.date, end: dt.date,
        initial_capital: float = 1_000_000,
        top_n: int = 10,
        rebalance: str = "weekly") -> dict:
    trading_days = _trading_days(start, end)
    if not trading_days:
        return {"error": "no trading days in range — has the backfill run?"}

    px = _universe_close_matrix(start, end)
    if px.empty:
        return {"error": "no price matrix; run postmarket job to populate stock_kline_daily"}

    codes = px.columns.tolist()
    scores = _score_universe(strategy_id, codes)
    if not scores:
        return {"error": "no positive scores; strategy data missing"}

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    picks = [c for c, _ in ranked[:top_n]]

    rebal = _rebalance_dates(trading_days, rebalance)
    equity_vals: list[float] = []
    equity_dates: list[dt.date] = []
    trades: list[dict] = []
    capital = initial_capital
    holdings: dict[str, float] = {}   # code -> shares

    def value_at(date: dt.date) -> float:
        total = 0.0
        if date not in px.index:
            return capital + sum(holdings.values()) * 0  # fallback
        row = px.loc[date]
        for code, sh in holdings.items():
            if code in row and pd.notna(row[code]):
                total += sh * float(row[code])
        return total

    cash = capital
    for d in trading_days:
        if d in rebal:
            mv = value_at(d) + cash
            if mv > 0:
                # equal-weight top_n
                target = {c: mv / len(picks) for c in picks if c in px.columns and d in px.index and pd.notna(px.at[d, c])}
                new_holdings: dict[str, float] = {}
                spent = 0.0
                for c, tgt in target.items():
                    px_c = float(px.at[d, c])
                    if px_c <= 0:
                        continue
                    sh = tgt / px_c
                    new_holdings[c] = sh
                    spent += sh * px_c
                # Record trades for entries that changed
                for c in set(holdings) | set(new_holdings):
                    diff_sh = new_holdings.get(c, 0) - holdings.get(c, 0)
                    if abs(diff_sh) > 1e-6:
                        trades.append({
                            "date": d.isoformat(),
                            "code": c,
                            "side": "buy" if diff_sh > 0 else "sell",
                            "shares": diff_sh,
                            "price": float(px.at[d, c]) if c in px.columns and pd.notna(px.at[d, c]) else None,
                            "pnl": None,
                        })
                holdings = new_holdings
                cash = mv - spent
        equity_vals.append(value_at(d) + cash)
        equity_dates.append(d)

    eq_series = pd.Series(equity_vals, index=pd.to_datetime(equity_dates))
    metrics = compute(eq_series, trades=trades)
    return {
        "strategy_id": strategy_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_capital": initial_capital,
        "top_n": top_n,
        "rebalance": rebalance,
        "metrics": metrics.as_dict(),
        "equity_curve": [
            {"date": d.isoformat(), "value": round(v, 2)}
            for d, v in zip(equity_dates, equity_vals)
        ],
        "trades": trades[:200],   # cap for response size
        "picks": picks,
    }


# ---------------------------------------------------------------------------
# Single-stock timing backtest
# ---------------------------------------------------------------------------

def _load_full_history(code: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Pull all available history rows for one code, sorted ascending by date."""
    eng = db.get_engine()
    empty = pd.DataFrame()
    if eng is None:
        return empty, empty, empty, empty
    with eng.connect() as conn:
        dk = pd.read_sql(
            text("SELECT trade_date, open, close, high, low, volume "
                 "FROM stock_kline_daily WHERE code=:c ORDER BY trade_date ASC"),
            conn, params={"c": code},
        )
        fund = pd.read_sql(
            text("SELECT * FROM stock_fundamental WHERE code=:c ORDER BY report_date ASC"),
            conn, params={"c": code},
        )
        nb = pd.read_sql(
            text("SELECT * FROM stock_northbound WHERE code=:c ORDER BY trade_date ASC"),
            conn, params={"c": code},
        )
        lhb = pd.read_sql(
            text("SELECT * FROM stock_lhb WHERE code=:c ORDER BY trade_date ASC"),
            conn, params={"c": code},
        )
    return dk, fund, nb, lhb


def run_single(strategy_id: str, code: str, start: dt.date, end: dt.date,
               initial_capital: float = 1_000_000) -> dict:
    """Run a long-only timing backtest for ONE stock.

    Rule: on each trading day the strategy outputs a `signal`
      - `bullish` and flat → buy the day's close with all available cash
      - `bearish` and holding → sell at the day's close
      - `neutral` → hold

    The strategy context is rebuilt each day with data sliced "as of t" (no
    look-ahead): daily K up to and including t; fundamentals dated <= t;
    northbound / LHB <= t.
    """
    from strategies import by_id
    from strategies.base import StrategyContext

    code = str(code).zfill(6)
    strat = by_id(strategy_id)
    if strat is None:
        return {"error": f"unknown strategy_id: {strategy_id}"}

    full_dk, full_fund, full_nb, full_lhb = _load_full_history(code)
    if full_dk.empty:
        return {"error": f"no kline data for {code}"}

    # Filter to backtest window (warmup needs prior bars too — keep full
    # history available; only iterate within the window).
    full_dk["trade_date"] = pd.to_datetime(full_dk["trade_date"]).dt.date
    if "report_date" in full_fund.columns:
        full_fund["report_date"] = pd.to_datetime(full_fund["report_date"]).dt.date
    if "trade_date" in full_nb.columns:
        full_nb["trade_date"] = pd.to_datetime(full_nb["trade_date"]).dt.date
    if "trade_date" in full_lhb.columns:
        full_lhb["trade_date"] = pd.to_datetime(full_lhb["trade_date"]).dt.date

    in_window = full_dk[(full_dk["trade_date"] >= start) & (full_dk["trade_date"] <= end)]
    if in_window.empty:
        return {"error": f"no bars in [{start}, {end}] for {code}"}

    cash = float(initial_capital)
    shares = 0.0
    last_buy_price: float | None = None
    equity_dates: list[dt.date] = []
    equity_vals: list[float] = []
    trades: list[dict] = []
    signal_log: list[dict] = []

    for _, row in in_window.iterrows():
        d = row["trade_date"]
        price = float(row["close"]) if pd.notna(row["close"]) else None
        if price is None or price <= 0:
            continue
        # As-of slice
        hist = full_dk[full_dk["trade_date"] <= d].tail(260)
        if len(hist) < 30:
            equity_vals.append(cash + shares * price)
            equity_dates.append(d)
            continue
        ctx_dk = hist.rename(columns={
            "trade_date": "日期", "open": "开盘", "close": "收盘",
            "high": "最高", "low": "最低", "volume": "成交量",
        })
        ctx = StrategyContext(code=code, daily_df=ctx_dk)
        if not full_fund.empty and "report_date" in full_fund.columns:
            ctx.fundamental_df = full_fund[full_fund["report_date"] <= d].tail(12)
        if not full_nb.empty and "trade_date" in full_nb.columns:
            ctx.northbound_df = full_nb[full_nb["trade_date"] <= d].tail(60)
        if not full_lhb.empty and "trade_date" in full_lhb.columns:
            ctx.lhb_df = full_lhb[full_lhb["trade_date"] <= d].tail(60)

        try:
            res = strat.score(ctx)
            sig = res.signal
        except Exception:
            sig = "neutral"

        signal_log.append({"date": d.isoformat(), "signal": sig,
                           "score": getattr(res, "score", 0) if "res" in dir() else 0})

        # Trade execution at today's close
        if sig == "bullish" and shares == 0 and cash > 0:
            sh = cash / price
            shares = sh
            last_buy_price = price
            trades.append({
                "date": d.isoformat(), "code": code, "side": "buy",
                "shares": round(sh, 2), "price": price, "pnl": None,
            })
            cash = 0.0
        elif sig == "bearish" and shares > 0:
            proceeds = shares * price
            pnl = (price - (last_buy_price or price)) * shares
            trades.append({
                "date": d.isoformat(), "code": code, "side": "sell",
                "shares": round(shares, 2), "price": price, "pnl": round(pnl, 2),
            })
            cash = proceeds
            shares = 0.0
            last_buy_price = None

        equity_vals.append(cash + shares * price)
        equity_dates.append(d)

    # Mark-to-market close at end if still holding
    if shares > 0 and equity_vals:
        last_price = float(in_window.iloc[-1]["close"])
        pnl = (last_price - (last_buy_price or last_price)) * shares
        trades.append({
            "date": in_window.iloc[-1]["trade_date"].isoformat(),
            "code": code, "side": "mark_to_market",
            "shares": round(shares, 2), "price": last_price, "pnl": round(pnl, 2),
        })

    eq_series = pd.Series(equity_vals, index=pd.to_datetime(equity_dates))
    metrics = compute(eq_series, trades=trades)
    return {
        "mode": "single",
        "strategy_id": strategy_id,
        "code": code,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_capital": initial_capital,
        "metrics": metrics.as_dict(),
        "equity_curve": [
            {"date": d.isoformat(), "value": round(v, 2)}
            for d, v in zip(equity_dates, equity_vals)
        ],
        "trades": trades,
        "signal_log": signal_log[-120:],   # last few months of daily signals
        "picks": [code],
    }
