# -*- coding: utf-8 -*-
"""Matrix backtester with realistic A-share execution model.

Two modes:
  * `run()`        — cross-sectional TopN portfolio backtest
  * `run_single()` — single-stock signal timing (bullish=buy, bearish=sell)

Execution realism (P0):
  * trading costs: commission (rate + per-trade minimum), stamp tax on sells,
    configurable slippage applied to the fill price
  * price-limit constraints: a stock sealed at limit-up cannot be bought,
    sealed at limit-down cannot be sold (board-aware: 10% main board,
    20% ChiNext/STAR, 30% BSE)
  * suspensions: volume == 0 or missing bar → untradeable; positions are
    carried at the last available close for valuation
  * board lot: buys round down to 100-share lots
  * no look-ahead: signals are computed at the t close from as-of data and
    EXECUTED at the t+1 OPEN (国际惯例 t 收盘出信号、t+1 开盘成交)；开盘
    一字涨停买不进、开盘跌停卖不出。T+1 由「成交在调仓日开盘」结构保证。
  * point-in-time fundamentals: quarterly rows are only visible from their
    announcement date (ann_date), falling back to the statutory disclosure
    deadline when ann_date is missing
  * benchmark: CSI 300 curve from index_kline_daily for excess-return comparison
"""
from __future__ import annotations
import datetime as dt
import time

import numpy as np
import pandas as pd
from sqlalchemy import text

import db
from backtest.metrics import compute
from core.trace import logger
from strategies import REGISTRY, by_id
from strategies.base import StrategyContext

BENCHMARK_CODE = "000300"   # 沪深300

DEFAULT_COSTS: dict[str, float] = {
    "commission_rate": 0.00025,   # 万 2.5，双边
    "commission_min": 5.0,        # 单笔最低佣金
    "stamp_tax": 0.0005,          # 印花税，卖出单边（2023-08 之后税率）
    "slippage": 0.001,            # 单边滑点 0.1%
}

LOT_SIZE = 100                 # A 股一手 100 股


def _normalize_costs(costs: dict | None) -> dict:
    out = dict(DEFAULT_COSTS)
    if costs:
        for k in out:
            try:
                v = float(costs.get(k, out[k]))
                if v >= 0:
                    out[k] = v
            except (TypeError, ValueError):
                pass
    return out


def _limit_ratio(code: str) -> float:
    """涨跌停幅度：创业板/科创板 20%，北交所 30%，其余主板 10%。
    ST 股 5% 未识别（无稳定的 ST 标记数据），主板口径偏保守。"""
    c = str(code).zfill(6)
    if c.startswith(("300", "301", "688", "689")):
        return 0.20
    if c.startswith(("8", "4", "92")):
        return 0.30
    return 0.10


def _commission(amount: float, costs: dict) -> float:
    return max(amount * costs["commission_rate"], costs["commission_min"])


def _round_price(x: float) -> float:
    """交易所价格按 0.01 四舍五入。"""
    return np.floor(x * 100.0 + 0.5) / 100.0


def _statutory_deadline(report_date: dt.date) -> dt.date:
    """季报法定披露截止日（ann_date 缺失时的保守可知时间）：
    一季报 04-30、半年报 08-31、三季报 10-31、年报次年 04-30。"""
    y, m = report_date.year, report_date.month
    if m == 3:
        return dt.date(y, 4, 30)
    if m == 6:
        return dt.date(y, 8, 31)
    if m == 9:
        return dt.date(y, 10, 31)
    if m == 12:
        return dt.date(y + 1, 4, 30)
    return report_date


def _fund_visible_from(row) -> dt.date:
    """这条财务数据从哪一天起对策略可见：优先公告日期，缺失按法定截止日兜底。"""
    ann = row.get("ann_date") if hasattr(row, "get") else None
    # 注意：pd.NaT 也是 datetime.date 的实例，必须用 pd.isna 统一判空
    if ann is not None and not pd.isna(ann):
        try:
            d = ann if isinstance(ann, dt.date) else pd.to_datetime(ann).date()
            if d:
                return d
        except Exception:
            pass
    rd = row.get("report_date")
    if rd is None:
        return dt.date(1970, 1, 1)
    return _statutory_deadline(rd if isinstance(rd, dt.date) else pd.to_datetime(rd).date())


def _trading_days(start: dt.date, end: dt.date) -> list[dt.date]:
    """交易日序列：优先指数日线（权威日历），退化到个股日线，再退化到工作日。"""
    eng = db.get_engine()
    if eng is None:
        days = []
        d = start
        while d <= end:
            if d.weekday() < 5:
                days.append(d)
            d += dt.timedelta(days=1)
        return days
    with eng.connect() as conn:
        try:
            rows = conn.execute(
                text("SELECT trade_date FROM index_kline_daily "
                     "WHERE code=:c AND trade_date BETWEEN :s AND :e ORDER BY trade_date"),
                {"c": BENCHMARK_CODE, "s": start, "e": end},
            ).fetchall()
            if rows:
                return [r[0] for r in rows]
        except Exception:
            pass   # 表可能尚未建立 — 退化到个股日线
        rows = conn.execute(
            text("SELECT DISTINCT trade_date FROM stock_kline_daily "
                 "WHERE trade_date BETWEEN :s AND :e ORDER BY trade_date"),
            {"s": start, "e": end},
        ).fetchall()
    return [r[0] for r in rows]


def _universe_ohlcv(start: dt.date, end: dt.date) -> dict[str, pd.DataFrame]:
    """Pivot the whole universe once: {open,close,high,low,volume} matrices
    indexed by trade_date, columns=code."""
    eng = db.get_engine()
    if eng is None:
        return {}
    with eng.connect() as conn:
        df = pd.read_sql(
            text(
                "SELECT trade_date, code, open, close, high, low, volume "
                "FROM stock_kline_daily WHERE trade_date BETWEEN :s AND :e"
            ),
            conn, params={"s": start, "e": end},
        )
    if df.empty:
        return {}
    for col in ("open", "close", "high", "low", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    out = {}
    for col in ("open", "close", "high", "low", "volume"):
        out[col] = df.pivot(index="trade_date", columns="code", values=col).sort_index()
    return out


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


def _load_panel(codes: list[str], end: dt.date,
                start: dt.date | None = None) -> dict[str, dict[str, pd.DataFrame]]:
    """Bulk-load every code's full history up to `end` in a single round-trip
    per table. Returns {code -> {"dk", "fund", "nb", "lhb"}} so the rebalance
    loop can slice an as-of view without hitting MySQL again.

    Without this, a 200-stock x 52-week back-test would issue 40 000 queries.

    `start` 给定时，K线/北向/龙虎榜按 `start - 400 天` 下界预过滤（约 270 个
    交易日，覆盖 260 根 K 线 + 60 日北向/龙虎榜的预热窗口），省一半以上的
    加载与内存；财务仍全量加载（真正的 point-in-time 过滤在切片时做）。
    """
    eng = db.get_engine()
    if eng is None:
        return {}
    if not codes:
        return {}
    in_list = ",".join(f"'{c}'" for c in codes)
    lower = f" AND trade_date >= '{(start - dt.timedelta(days=400)).isoformat()}'" if start else ""

    def _bulk(sql: str) -> pd.DataFrame:
        with eng.connect() as conn:
            return pd.read_sql(text(sql), conn)

    dk = _bulk(
        f"SELECT code, trade_date, open, close, high, low, volume "
        f"FROM stock_kline_daily "
        f"WHERE code IN ({in_list}) AND trade_date <= '{end.isoformat()}'{lower}"
    )
    # 财务按 report_date 预过滤足够宽；真正的 point-in-time 过滤在切片时按
    # ann_date / 法定披露截止日进行（effective_date 列在下方计算）。
    fund = _bulk(
        f"SELECT * FROM stock_fundamental "
        f"WHERE code IN ({in_list}) AND report_date <= '{end.isoformat()}'"
    )
    nb = _bulk(
        f"SELECT * FROM stock_northbound "
        f"WHERE code IN ({in_list}) AND trade_date <= '{end.isoformat()}'{lower}"
    )
    lhb = _bulk(
        f"SELECT * FROM stock_lhb "
        f"WHERE code IN ({in_list}) AND trade_date <= '{end.isoformat()}'{lower}"
    )

    if not dk.empty:
        dk["trade_date"] = pd.to_datetime(dk["trade_date"]).dt.date
    if not fund.empty and "report_date" in fund.columns:
        fund["report_date"] = pd.to_datetime(fund["report_date"]).dt.date
        if "ann_date" in fund.columns:
            fund["ann_date"] = pd.to_datetime(fund["ann_date"], errors="coerce").dt.date
        fund["effective_date"] = fund.apply(_fund_visible_from, axis=1)
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


def _fund_asof(fund_full: pd.DataFrame, as_of: dt.date, n: int = 12) -> pd.DataFrame | None:
    """point-in-time 财务切片：只保留 effective_date（公告日/法定截止日）<= as_of 的行。"""
    if fund_full is None or fund_full.empty:
        return None
    key = "effective_date" if "effective_date" in fund_full.columns else "report_date"
    key_series = fund_full[key]
    if not pd.api.types.is_datetime64_any_dtype(key_series):
        key_series = pd.to_datetime(key_series)
    sliced = fund_full[key_series <= pd.Timestamp(as_of)].tail(n)
    return sliced if not sliced.empty else None


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
    fund_asof = _fund_asof(fund_full, as_of)
    if fund_asof is not None:
        ctx.fundamental_df = fund_asof
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


# As-of 评分缓存：研究链路（factorlab/回测）反复重跑时，同一
# (strategy_id, code, as_of) 直接复用。TTL 10 分钟——盘后任务更新 K 线后
# 自动失效。评分只依赖 <= as_of 的数据，与加载窗口无关，跨请求缓存安全。
_SCORE_CACHE: dict[tuple, tuple[float, float]] = {}
_SCORE_TTL_S = 600.0
_SCORE_CACHE_MAX = 300_000


def _score_at_cached(strat, panel_one: dict[str, pd.DataFrame], code: str,
                     as_of: dt.date) -> float:
    key = (strat.id, code, as_of)
    now = time.time()
    hit = _SCORE_CACHE.get(key)
    if hit is not None and now - hit[0] < _SCORE_TTL_S:
        return hit[1]
    v = _score_at(strat, panel_one, code, as_of)
    if len(_SCORE_CACHE) > _SCORE_CACHE_MAX:
        _SCORE_CACHE.clear()
    _SCORE_CACHE[key] = (now, v)
    return v


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


def _benchmark_close(start: dt.date, end: dt.date) -> pd.Series | None:
    from repo import index_kline_repo
    try:
        s = index_kline_repo.get_index_close(BENCHMARK_CODE, start, end)
        return s if s is not None and len(s) >= 2 else None
    except Exception:
        return None


def run(strategy_id: str, start: dt.date, end: dt.date,
        initial_capital: float = 1_000_000,
        top_n: int = 10,
        rebalance: str = "weekly",
        costs: dict | None = None) -> dict:
    cost = _normalize_costs(costs)
    trading_days = _trading_days(start, end)
    if not trading_days:
        return {"error": "no trading days in range — has the backfill run?"}

    ohlcv = _universe_ohlcv(start, end)
    if not ohlcv:
        return {"error": "no price matrix; run postmarket job to populate stock_kline_daily"}

    close = ohlcv["close"]
    volume = ohlcv["volume"]
    codes = close.columns.tolist()

    strat = by_id(strategy_id)
    if strat is None:
        return {"error": f"unknown strategy_id: {strategy_id}"}

    # 估值价格：停牌日（bar 缺失）沿用最后收盘价，避免持仓被按 0 估值。
    val_close = close.ffill()
    prev_close = val_close.shift(1)
    # 涨跌停参考价：以前收盘为基准按板块幅度计算（停牌期间 prev 不动），
    # 交易所规则四舍五入到 0.01（floor(x+0.5) / ceil(x-0.5)，避免银行家舍入）。
    ratio = pd.Series({_c: _limit_ratio(_c) for _c in codes})
    limit_up = np.floor((prev_close * (1 + ratio)).mul(100) + 0.5) / 100.0
    limit_down = np.ceil((prev_close * (1 - ratio)).mul(100) - 0.5) / 100.0
    tradable = close.notna() & (volume.fillna(0) > 0)
    # 开盘可交易性（t+1 开盘成交用）：开盘价存在且未封板
    open_px = ohlcv.get("open")
    if open_px is None:
        open_px = close   # 数据缺失时退化为收盘成交（不应发生）
    buyable_open = tradable & open_px.notna() & (open_px < limit_up)
    sellable_open = tradable & open_px.notna() & (open_px > limit_down)

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
    cost_basis: dict[str, float] = {}    # code -> avg cost / share (含滑点的成交价)
    cash = float(initial_capital)
    total_traded = 0.0                   # 成交额（买+卖），用于换手率
    total_cost_paid = 0.0                # 佣金 + 印花税累计
    # t 日收盘产生的待执行信号：下一交易日开盘成交
    pending: tuple[dt.date, list[str], float] | None = None

    def value_at(date: dt.date) -> float:
        if date not in val_close.index or not holdings:
            return 0.0
        row = val_close.loc[date]
        total = 0.0
        for c, sh in holdings.items():
            if c in row.index and pd.notna(row[c]):
                total += sh * float(row[c])
        return total

    for i, d in enumerate(trading_days):
        # ---- 1) 执行上一信号日的待执行单：今日开盘成交 ----
        if pending is not None:
            sig_date, picks, mv_sig = pending
            pending = None
            if d in open_px.index:
                pick_set = set(picks)
                row_open = open_px.loc[d]
                row_buyable = buyable_open.loc[d]
                row_sellable = sellable_open.loc[d]

                def _on(col, c) -> bool:
                    return c in col.index and bool(col[c])

                # ---- 1a) 卖出：不在新组合里、且开盘未跌停/未停牌 ----
                for c in list(holdings):
                    if c in pick_set:
                        continue
                    if not _on(row_sellable, c):
                        continue
                    raw_px = float(row_open[c])
                    exec_px = raw_px * (1 - cost["slippage"])
                    sh = holdings[c]
                    gross = sh * exec_px
                    fee = _commission(gross, cost)
                    tax = gross * cost["stamp_tax"]
                    cash += gross - fee - tax
                    total_traded += gross
                    total_cost_paid += fee + tax
                    basis = cost_basis.get(c, raw_px)
                    trades.append({
                        "date": d.isoformat(), "code": c, "side": "sell",
                        "shares": round(-sh, 4), "price": round(exec_px, 3),
                        "pnl": round((exec_px - basis) * sh, 2),
                    })
                    del holdings[c]
                    cost_basis.pop(c, None)

                # ---- 1b) 买入/调平到等权目标；开盘涨停/停牌跳过 ----
                if picks and mv_sig > 0:
                    n_target = max(len(picks), 1)
                    tgt_value = mv_sig / n_target
                    for c in picks:
                        if not _on(row_buyable, c):
                            continue
                        raw_px = float(row_open[c])
                        if raw_px <= 0:
                            continue
                        exec_px = raw_px * (1 + cost["slippage"])
                        cur_sh = holdings.get(c, 0.0)
                        tgt_sh = tgt_value / exec_px
                        diff_lots = int((tgt_sh - cur_sh) // LOT_SIZE)
                        if diff_lots > 0:
                            add_sh = diff_lots * LOT_SIZE
                            amount = add_sh * exec_px
                            fee = _commission(amount, cost)
                            if amount + fee > cash:
                                afford_lots = int((cash / exec_px) // LOT_SIZE)
                                if afford_lots <= 0:
                                    continue
                                add_sh = afford_lots * LOT_SIZE
                                amount = add_sh * exec_px
                                fee = _commission(amount, cost)
                            cash -= amount + fee
                            total_traded += amount
                            total_cost_paid += fee
                            old_sh = cur_sh
                            old_basis = cost_basis.get(c, exec_px)
                            new_sh = old_sh + add_sh
                            cost_basis[c] = (old_basis * old_sh + exec_px * add_sh) / new_sh if new_sh > 0 else exec_px
                            holdings[c] = new_sh
                            trades.append({
                                "date": d.isoformat(), "code": c, "side": "buy",
                                "shares": round(add_sh, 4), "price": round(exec_px, 3),
                                "pnl": None,
                            })
                        elif diff_lots < 0:
                            sell_sh = min(-diff_lots * LOT_SIZE, cur_sh)
                            if not _on(row_sellable, c):
                                continue   # 想减仓但开盘跌停/停牌，保留
                            exec_px_s = raw_px * (1 - cost["slippage"])
                            gross = sell_sh * exec_px_s
                            fee = _commission(gross, cost)
                            tax = gross * cost["stamp_tax"]
                            cash += gross - fee - tax
                            total_traded += gross
                            total_cost_paid += fee + tax
                            basis = cost_basis.get(c, raw_px)
                            trades.append({
                                "date": d.isoformat(), "code": c, "side": "sell",
                                "shares": round(-sell_sh, 4), "price": round(exec_px_s, 3),
                                "pnl": round((exec_px_s - basis) * sell_sh, 2),
                            })
                            remaining = cur_sh - sell_sh
                            if remaining <= 1e-6:
                                holdings.pop(c, None)
                                cost_basis.pop(c, None)
                            else:
                                holdings[c] = remaining

        # ---- 2) 调仓日收盘：按 as-of 数据重评分，信号压入 pending ----
        if d in rebal_set:
            mv = value_at(d) + cash
            if mv > 0:
                # Re-score with AS-OF data — picks now reflect what was known
                # on date `d`, not what happens later.
                scores_today: dict[str, float] = {}
                for c in codes:
                    s = _score_at_cached(strat, panel[c], c, d)
                    if s > 0:
                        scores_today[c] = s
                if scores_today:
                    ranked = sorted(scores_today.items(), key=lambda kv: kv[1], reverse=True)
                    picks = [c for c, _ in ranked[:top_n]]
                    last_picks = picks
                else:
                    picks = last_picks  # nothing scoreable today; hold previous basket

                if picks and i + 1 < len(trading_days):
                    pending = (d, picks, mv)

        equity_vals.append(value_at(d) + cash)
        equity_dates.append(d)

    eq_series = pd.Series(equity_vals, index=pd.to_datetime(equity_dates))
    bench = _benchmark_close(start, end)
    years = max(len(trading_days) / 252.0, 1e-6)
    mean_equity = float(eq_series.mean()) if len(eq_series) else 0.0
    turnover_annual = (total_traded / mean_equity / years) if mean_equity > 0 else None

    metrics = compute(eq_series, trades=trades, benchmark=bench,
                      turnover_rate=turnover_annual, total_costs=total_cost_paid)

    out = {
        "strategy_id": strategy_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_capital": initial_capital,
        "top_n": top_n,
        "rebalance": rebalance,
        "costs": cost,
        "metrics": metrics.as_dict(),
        "equity_curve": [
            {"date": d.isoformat(), "value": round(v, 2)}
            for d, v in zip(equity_dates, equity_vals)
        ],
        "trades": trades[:200],   # cap for response size
        "picks": last_picks,
    }
    if bench is not None and len(bench) >= 2:
        bench = bench.reindex(pd.to_datetime(equity_dates)).ffill()
        base = float(bench.iloc[0]) if pd.notna(bench.iloc[0]) else None
        if base:
            out["benchmark_curve"] = [
                {"date": d.isoformat(), "value": round(float(v) / base * initial_capital, 2)}
                for d, v in bench.items() if pd.notna(v)
            ]
    return out


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
               initial_capital: float = 1_000_000, costs: dict | None = None) -> dict:
    """Run a long-only timing backtest for ONE stock.

    Rule: on each trading day the strategy outputs a `signal`
      - `bullish` and flat → buy the day's close (if not sealed limit-up)
      - `bearish` and holding → sell at the day's close (if not sealed limit-down)
      - `neutral` → hold

    Fills carry slippage and trading costs (commission + stamp tax). The
    strategy context is rebuilt each day with data sliced "as of t" (no
    look-ahead): daily K up to and including t; fundamentals visible from
    their announcement date (ann_date, statutory deadline as fallback);
    northbound / LHB <= t.
    """
    from strategies import by_id
    from strategies.base import StrategyContext

    code = str(code).zfill(6)
    cost = _normalize_costs(costs)
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
        if "ann_date" in full_fund.columns:
            full_fund["ann_date"] = pd.to_datetime(full_fund["ann_date"], errors="coerce").dt.date
        full_fund["effective_date"] = full_fund.apply(_fund_visible_from, axis=1)
    if "trade_date" in full_nb.columns:
        full_nb["trade_date"] = pd.to_datetime(full_nb["trade_date"]).dt.date
    if "trade_date" in full_lhb.columns:
        full_lhb["trade_date"] = pd.to_datetime(full_lhb["trade_date"]).dt.date

    in_window = full_dk[(full_dk["trade_date"] >= start) & (full_dk["trade_date"] <= end)]
    if in_window.empty:
        return {"error": f"no bars in [{start}, {end}] for {code}"}

    limit_ratio = _limit_ratio(code)
    cash = float(initial_capital)
    shares = 0.0
    last_buy_price: float | None = None
    equity_dates: list[dt.date] = []
    equity_vals: list[float] = []
    trades: list[dict] = []
    signal_log: list[dict] = []
    total_cost_paid = 0.0

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

    prev_close: float | None = None
    for _, row in in_window.iterrows():
        d = row["trade_date"]
        price = float(row["close"]) if pd.notna(row["close"]) else None
        vol = float(row["volume"]) if pd.notna(row["volume"]) else 0.0
        if price is None or price <= 0 or vol <= 0:
            # 停牌：不可交易，持仓按最后收盘估值
            if shares > 0 and prev_close:
                equity_vals.append(cash + shares * prev_close)
                equity_dates.append(d)
            prev_close = price if price else prev_close
            continue

        # 涨跌停（以前收盘为基准）
        if prev_close:
            limit_up = _round_price(prev_close * (1 + limit_ratio))
            limit_down = _round_price(prev_close * (1 - limit_ratio))
            sealed_up = price >= limit_up
            sealed_down = price <= limit_down
        else:
            sealed_up = sealed_down = False

        # As-of slice
        hist = full_dk[full_dk["trade_date"] <= d].tail(260)
        if len(hist) < 30:
            equity_vals.append(cash + shares * price)
            equity_dates.append(d)
            prev_close = price
            continue
        ctx_dk = hist.rename(columns={
            "trade_date": "日期", "open": "开盘", "close": "收盘",
            "high": "最高", "low": "最低", "volume": "成交量",
        })
        ctx = StrategyContext(code=code, daily_df=ctx_dk)
        fund_asof = _fund_asof(full_fund, d)
        if fund_asof is not None:
            ctx.fundamental_df = fund_asof
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

        # Trade execution at today's close (+ slippage / costs / price limits)
        if sig == "bullish" and shares == 0 and cash > 0 and not sealed_up:
            exec_px = price * (1 + cost["slippage"])
            lots = int((cash * 0.999) / exec_px / LOT_SIZE)   # 预留现金付佣金
            if lots <= 0:
                lots = 1 if cash > exec_px * LOT_SIZE else 0
            if lots > 0:
                sh = lots * LOT_SIZE
                amount = sh * exec_px
                fee = _commission(amount, cost)
                if amount + fee <= cash:
                    shares = sh
                    last_buy_price = exec_px
                    trades.append({
                        "date": d.isoformat(), "code": code, "side": "buy",
                        "shares": round(sh, 2), "price": round(exec_px, 3), "pnl": None,
                    })
                    cash -= amount + fee
                    total_cost_paid += fee
        elif sig == "bearish" and shares > 0 and not sealed_down:
            exec_px = price * (1 - cost["slippage"])
            gross = shares * exec_px
            fee = _commission(gross, cost)
            tax = gross * cost["stamp_tax"]
            pnl = (exec_px - (last_buy_price or exec_px)) * shares
            trades.append({
                "date": d.isoformat(), "code": code, "side": "sell",
                "shares": round(shares, 2), "price": round(exec_px, 3), "pnl": round(pnl, 2),
            })
            cash += gross - fee - tax
            total_cost_paid += fee + tax
            shares = 0.0
            last_buy_price = None

        equity_vals.append(cash + shares * price)
        equity_dates.append(d)
        prev_close = price

    # End-of-window: force-close any remaining position at the last close so
    # the trade ledger shows a proper buy↔sell pairing for the user. Without
    # this the UI rendered a stray `mark_to_market` row that looked like the
    # strategy "forgot" to sell.
    if shares > 0 and equity_vals:
        last_price = float(in_window.iloc[-1]["close"])
        exec_px = last_price * (1 - cost["slippage"])
        gross = shares * exec_px
        fee = _commission(gross, cost)
        tax = gross * cost["stamp_tax"]
        pnl = (exec_px - (last_buy_price or exec_px)) * shares
        trades.append({
            "date": in_window.iloc[-1]["trade_date"].isoformat(),
            "code": code, "side": "sell",
            "shares": round(shares, 2), "price": round(exec_px, 3),
            "pnl": round(pnl, 2),
            "reason": "end_of_window",
        })
        cash += gross - fee - tax
        total_cost_paid += fee + tax
        shares = 0.0

    eq_series = pd.Series(equity_vals, index=pd.to_datetime(equity_dates))
    bench = _benchmark_close(start, end)
    metrics = compute(eq_series, trades=trades, benchmark=bench, total_costs=total_cost_paid)
    return {
        "mode": "single",
        "strategy_id": strategy_id,
        "code": code,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_capital": initial_capital,
        "costs": cost,
        "metrics": metrics.as_dict(),
        "equity_curve": [
            {"date": d.isoformat(), "value": round(v, 2)}
            for d, v in zip(equity_dates, equity_vals)
        ],
        "trades": trades,
        "signal_log": signal_log[-120:],   # last few months of daily signals
        "picks": [code],
    }
