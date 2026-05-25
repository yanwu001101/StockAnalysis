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


def _load_panel(codes: list[str], end: dt.date) -> dict[str, dict[str, pd.DataFrame]]:
    """Bulk-load every code's full history up to `end` in a single round-trip
    per table. Returns {code -> {"dk", "fund", "nb", "lhb"}} so the rebalance
    loop can slice an as-of view without hitting MySQL again.

    Without this, a 200-stock x 52-week back-test would issue 40 000 queries.
    """
    eng = db.get_engine()
    if eng is None:
        return {}
    if not codes:
        return {}
    in_list = ",".join(f"'{c}'" for c in codes)

    def _bulk(sql: str) -> pd.DataFrame:
        with eng.connect() as conn:
            return pd.read_sql(text(sql), conn)

    dk = _bulk(
        f"SELECT code, trade_date, open, close, high, low, volume "
        f"FROM stock_kline_daily "
        f"WHERE code IN ({in_list}) AND trade_date <= '{end.isoformat()}'"
    )
    fund = _bulk(
        f"SELECT * FROM stock_fundamental "
        f"WHERE code IN ({in_list}) AND report_date <= '{end.isoformat()}'"
    )
    nb = _bulk(
        f"SELECT * FROM stock_northbound "
        f"WHERE code IN ({in_list}) AND trade_date <= '{end.isoformat()}'"
    )
    lhb = _bulk(
        f"SELECT * FROM stock_lhb "
        f"WHERE code IN ({in_list}) AND trade_date <= '{end.isoformat()}'"
    )

    if not dk.empty:
        dk["trade_date"] = pd.to_datetime(dk["trade_date"]).dt.date
    if not fund.empty and "report_date" in fund.columns:
        fund["report_date"] = pd.to_datetime(fund["report_date"]).dt.date
    if not nb.empty and "trade_date" in nb.columns:
        nb["trade_date"] = pd.to_datetime(nb["trade_date"]).dt.date
    if not lhb.empty and "trade_date" in lhb.columns:
        lhb["trade_date"] = pd.to_datetime(lhb["trade_date"]).dt.date

    panel: dict[str, dict[str, pd.DataFrame]] = {}
    for code in codes:
        panel[code] = {
            "dk": dk[dk["code"] == code].sort_values("trade_date") if not dk.empty else pd.DataFrame(),
            "fund": fund[fund["code"] == code].sort_values("report_date") if not fund.empty and "report_date" in fund.columns else pd.DataFrame(),
            "nb": nb[nb["code"] == code].sort_values("trade_date") if not nb.empty and "trade_date" in nb.columns else pd.DataFrame(),
            "lhb": lhb[lhb["code"] == code].sort_values("trade_date") if not lhb.empty and "trade_date" in lhb.columns else pd.DataFrame(),
        }
    return panel


def _score_at(strat, panel_one: dict[str, pd.DataFrame], code: str, as_of: dt.date) -> float:
    """Re-score one code using ONLY data <= as_of. Returns 0 on hard failure;
    we let the strategy itself decide whether it has enough fields — basic
    quality / piotroski strategies only need fundamentals, not 30 K-line bars.
    """
    dk_full = panel_one.get("dk")
    dk_asof = pd.DataFrame()
    if dk_full is not None and not dk_full.empty:
        dk_asof = dk_full[dk_full["trade_date"] <= as_of].tail(260)

    daily_df = None
    if not dk_asof.empty:
        daily_df = dk_asof.rename(columns={
            "trade_date": "日期", "open": "开盘", "close": "收盘",
            "high": "最高", "low": "最低", "volume": "成交量",
        })
    ctx = StrategyContext(code=code, daily_df=daily_df)
    fund_full = panel_one.get("fund")
    if fund_full is not None and not fund_full.empty:
        ctx.fundamental_df = fund_full[fund_full["report_date"] <= as_of].tail(12)
    nb_full = panel_one.get("nb")
    if nb_full is not None and not nb_full.empty:
        ctx.northbound_df = nb_full[nb_full["trade_date"] <= as_of].tail(60)
    lhb_full = panel_one.get("lhb")
    if lhb_full is not None and not lhb_full.empty:
        ctx.lhb_df = lhb_full[lhb_full["trade_date"] <= as_of].tail(60)
    try:
        res = strat.score(ctx)
        return float(res.score) if res and res.score > 0 else 0.0
    except Exception:
        return 0.0


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

    strat = by_id(strategy_id)
    if strat is None:
        return {"error": f"unknown strategy_id: {strategy_id}"}

    # Pre-load full panel once so the rebalance loop never re-queries MySQL.
    # This is the only price we pay to kill the look-ahead: every rebalance
    # date now re-scores using ONLY data available on that date.
    panel = _load_panel(codes, end)
    if not panel:
        return {"error": "panel load failed"}

    rebal = _rebalance_dates(trading_days, rebalance)
    rebal_set = set(rebal)

    # Note: we used to sanity-probe the first rebalance date and bail with
    # "no positive scores" if it returned nothing — that was too strict for
    # momentum / breakout strategies whose lookback window may not be filled
    # at the very first rebalance. We now silently hold cash until the
    # strategy has enough data to produce picks.

    last_picks: list[str] = []
    equity_vals: list[float] = []
    equity_dates: list[dt.date] = []
    trades: list[dict] = []
    holdings: dict[str, float] = {}      # code -> shares
    # cost basis per code so we can attribute realised PnL per partial sell
    cost_basis: dict[str, float] = {}    # code -> avg cost / share
    capital = initial_capital
    cash = capital

    def value_at(date: dt.date) -> float:
        total = 0.0
        if date not in px.index:
            return 0.0
        row = px.loc[date]
        for code, sh in holdings.items():
            if code in row and pd.notna(row[code]):
                total += sh * float(row[code])
        return total

    for d in trading_days:
        if d in rebal_set:
            mv = value_at(d) + cash
            if mv > 0:
                # Re-score with AS-OF data — picks now reflect what was known
                # on date `d`, not what happens later.
                scores_today: dict[str, float] = {}
                for c in codes:
                    s = _score_at(strat, panel[c], c, d)
                    if s > 0:
                        scores_today[c] = s
                if scores_today:
                    ranked = sorted(scores_today.items(), key=lambda kv: kv[1], reverse=True)
                    picks = [c for c, _ in ranked[:top_n]]
                    last_picks = picks
                else:
                    picks = last_picks  # nothing scoreable today; hold previous basket

                if picks:
                    target = {c: mv / len(picks) for c in picks
                              if c in px.columns and d in px.index and pd.notna(px.at[d, c])}
                    new_holdings: dict[str, float] = {}
                    new_basis: dict[str, float] = {}
                    spent = 0.0
                    for c, tgt in target.items():
                        px_c = float(px.at[d, c])
                        if px_c <= 0:
                            continue
                        sh = tgt / px_c
                        new_holdings[c] = sh
                        new_basis[c] = px_c
                        spent += sh * px_c
                    # Emit trade rows + attribute PnL for closed/reduced positions
                    for c in set(holdings) | set(new_holdings):
                        old_sh = holdings.get(c, 0.0)
                        new_sh = new_holdings.get(c, 0.0)
                        diff_sh = new_sh - old_sh
                        if abs(diff_sh) < 1e-6:
                            continue
                        px_c = float(px.at[d, c]) if c in px.columns and d in px.index and pd.notna(px.at[d, c]) else None
                        side = "buy" if diff_sh > 0 else "sell"
                        pnl = None
                        if diff_sh < 0 and px_c is not None and c in cost_basis:
                            # partial / full sell — realised pnl on the sold shares
                            pnl = round((px_c - cost_basis[c]) * (-diff_sh), 2)
                        trades.append({
                            "date": d.isoformat(),
                            "code": c,
                            "side": side,
                            "shares": round(diff_sh, 4),
                            "price": px_c,
                            "pnl": pnl,
                        })
                    # Update basis: keep old basis for surviving shares, take new px for adds
                    for c, sh in new_holdings.items():
                        old_sh = holdings.get(c, 0.0)
                        old_basis = cost_basis.get(c, new_basis[c])
                        if sh > old_sh and old_sh > 0:
                            cost_basis[c] = (old_basis * old_sh + new_basis[c] * (sh - old_sh)) / sh
                        elif old_sh == 0:
                            cost_basis[c] = new_basis[c]
                    for c in list(cost_basis):
                        if c not in new_holdings:
                            cost_basis.pop(c, None)
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
        "picks": last_picks,
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

    # Adaptive signal threshold — strategies were calibrated for the
    # cross-sectional top-10% (score >= 60), which a single stock's time series
    # almost never hits. We replace the fixed threshold with rolling
    # quantiles over THIS stock's own recent score history, so any strategy
    # whose score moves meaningfully will produce trades.
    WARMUP = 30           # bars before we trust the quantile window
    LOOKBACK = 60         # rolling window for quantile estimation
    Q_BULL = 0.70         # current score >= 70th percentile → bullish
    Q_BEAR = 0.30         # current score <= 30th percentile → bearish
    recent_scores: list[float] = []

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
            raw_score = float(getattr(res, "score", 0) or 0)
        except Exception:
            res = None
            raw_score = 0.0

        # Override the strategy's own bullish/bearish call with one derived
        # from THIS stock's recent score distribution.
        recent_scores.append(raw_score)
        if len(recent_scores) > LOOKBACK:
            recent_scores.pop(0)
        if len(recent_scores) >= WARMUP:
            window = sorted(recent_scores)
            n = len(window)
            bull_cut = window[min(int(Q_BULL * n), n - 1)]
            bear_cut = window[max(int(Q_BEAR * n) - 1, 0)]
            # Require some dispersion — if score is flat (e.g. fundamental
            # strategy on a single stock) treat everything as neutral.
            if bull_cut - bear_cut < 1e-6:
                sig = "neutral"
            elif raw_score >= bull_cut and raw_score > bear_cut:
                sig = "bullish"
            elif raw_score <= bear_cut and raw_score < bull_cut:
                sig = "bearish"
            else:
                sig = "neutral"
        else:
            # Warming up — defer to the strategy's own absolute call so we
            # don't trade blindly before we have a distribution.
            sig = getattr(res, "signal", "neutral") if res is not None else "neutral"

        signal_log.append({"date": d.isoformat(), "signal": sig, "score": raw_score})

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

    # End-of-window: force-close any remaining position at the last close so
    # the trade ledger shows a proper buy↔sell pairing for the user. Without
    # this the UI rendered a stray `mark_to_market` row that looked like the
    # strategy "forgot" to sell.
    if shares > 0 and equity_vals:
        last_price = float(in_window.iloc[-1]["close"])
        pnl = (last_price - (last_buy_price or last_price)) * shares
        trades.append({
            "date": in_window.iloc[-1]["trade_date"].isoformat(),
            "code": code, "side": "sell",
            "shares": round(shares, 2), "price": last_price,
            "pnl": round(pnl, 2),
            "reason": "end_of_window",
        })
        cash += shares * last_price
        shares = 0.0

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
