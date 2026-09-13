# -*- coding: utf-8 -*-
"""Alpha lab: user-defined cross-sectional factors, WorldQuant-BRAIN style.

用户写一个因子表达式（作用于「交易日 × 股票」的面板矩阵），引擎整面板向量化
求值后，接入与内置策略完全相同的检验管线（IC/分层/衰减/牛熊/行业中性/评级，
由 factorlab 提供）与组合回测（T+1 开盘成交、涨跌停/停牌约束、佣金+印花税+
滑点、整手买入）。

时间语义（无未来函数，与 SKILL §22 一致）：
  * 时序算子（TS_MEAN/DELAY/TS_CORR...）是向后窗口，只用 <= t 的数据；
  * 截面因子值 = t 日收盘后可知的信息；
  * 检验管线用 t → t+1 期前向收益（factorlab 既有口径）；
  * 组合回测在 t+1 日**开盘价**成交（引擎 run() 的同日收盘成交口径已修正为
    t+1 开盘，本模块与之一致），涨跌停/停牌约束按成交日开盘价判定。

安全：ast.parse + 节点白名单 + 名字白名单，无内建、无属性访问、无导入。
字段与算子目录见 help()（GET /api/alphalab/help）。
"""
from __future__ import annotations
import ast
import datetime as dt

import numpy as np
import pandas as pd
from sqlalchemy import text

import db
from backtest import engine
from core.trace import logger

# ---------------------------------------------------------------------------
# 字段目录（面板矩阵，dates × codes）
# ---------------------------------------------------------------------------

# 时序行情字段在 _build_panel 里生成；这里只登记目录与说明
PRICE_FIELDS = {
    "open": "开盘价",
    "high": "最高价",
    "low": "最低价",
    "close": "收盘价",
    "volume": "成交量",
    "vwap": "成交均价代理 (H+L+C)/3",
    "returns": "日收益率 close.pct_change()",
}
# 财务字段：point-in-time（按 ann_date/法定披露截止日进入，见 engine._fund_visible_from）
FUND_FIELDS = {
    "roe": "净资产收益率(%)",
    "debt": "资产负债率(%)",
    "gross_margin": "毛利率(%)",
    "rev_yoy": "营收同比(%)",
    "np_yoy": "净利润同比(%)",
}

OPERATORS = {
    # —— 时序（向后窗口）——
    "ts_mean(x,n)": "n 日均值",
    "ts_std(x,n)": "n 日标准差",
    "ts_sum(x,n)": "n 日求和",
    "ts_max(x,n)": "n 日最大",
    "ts_min(x,n)": "n 日最小",
    "ts_rank(x,n)": "当前值在最近 n 日中的分位（0~1）",
    "delay(x,n)": "n 天前的值",
    "delta(x,n)": "x - delay(x,n)",
    "pct_chg(x,n)": "n 日累计涨跌幅",
    "ts_corr(x,y,n)": "逐股 n 日滚动相关",
    # —— 截面（每个交易日横跨全部股票）——
    "rank(x)": "截面百分位秩（0~1）",
    "zscore(x)": "截面 z 分数",
    "sign(x)": "符号",
    "log(x)": "自然对数（自动防负）",
    "abs(x)": "绝对值",
}

EXAMPLES = [
    {"name": "20日反转", "expr": "-pct_chg(close, 20)",
     "desc": "跌得多的反弹——经典短期反转"},
    {"name": "量价背离", "expr": "-ts_corr(rank(close), rank(volume), 10)",
     "desc": "价量同步性低的股票占优（BRAIN 经典 Alpha#101 族）"},
    {"name": "低波动", "expr": "-ts_std(returns, 20)",
     "desc": "波动率异象：低波动跑赢高波动"},
    {"name": "60日突破强度", "expr": "close / ts_max(close, 60)",
     "desc": "接近阶段新高的动量"},
    {"name": "质量减杠杆", "expr": "rank(roe) - rank(debt)",
     "desc": "高 ROE、低负债（截面，point-in-time 财务）"},
    {"name": "缩量企稳", "expr": "-volume / ts_mean(volume, 60)",
     "desc": "当前量相对 60 日均量的萎缩度"},
]


class AlphaExprError(Exception):
    pass


# ---------------------------------------------------------------------------
# 安全解析
# ---------------------------------------------------------------------------

_SAFE_NODES = {
    ast.Expression, ast.BinOp, ast.BoolOp, ast.Compare, ast.UnaryOp,
    ast.Name, ast.Load, ast.Constant, ast.Call,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.Pow,
    ast.USub, ast.UAdd, ast.IfExp,
}


def parse_alpha(expr: str, namespace: dict):
    """解析并静态校验：节点白名单 + 所有名字必须在 namespace 里。

    返回编译好的 code 对象；语法/未知名字抛 AlphaExprError。
    """
    if not expr or not expr.strip():
        raise AlphaExprError("空表达式")
    if len(expr) > 2000:
        raise AlphaExprError("表达式过长（限制 2000 字符）")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise AlphaExprError(f"语法错误: {e.msg}")
    for node in ast.walk(tree):
        if type(node) not in _SAFE_NODES:
            raise AlphaExprError(f"不允许的语法: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in namespace:
                raise AlphaExprError("只允许直接调用白名单算子")
        if isinstance(node, ast.Name) and node.id not in namespace:
            raise AlphaExprError(f"未知字段或算子: {node.id}（见 /api/alphalab/help）")
    return compile(tree, "<alpha>", "eval")


# ---------------------------------------------------------------------------
# 面板构建
# ---------------------------------------------------------------------------

def _fund_matrices(trading_days: list[dt.date], end: dt.date) -> dict[str, pd.DataFrame]:
    """point-in-time 财务面板：每字段一张 dates × codes 矩阵。

    每条财务行从 effective_date（公告日，缺失用法定披露截止日）起可见；
    对全交易日序列 reindex+ffill 即得任意交易日的 as-of 值，缺失为 NaN。
    """
    eng = db.get_engine()
    out = {f: pd.DataFrame() for f in FUND_FIELDS}
    if eng is None:
        return out
    with eng.connect() as conn:
        fund = pd.read_sql(
            text("SELECT code, report_date, ann_date, roe, debt_ratio, gross_margin, "
                 "revenue_yoy, net_profit_yoy FROM stock_fundamental "
                 "WHERE report_date <= :e"),
            conn, params={"e": end},
        )
    if fund.empty:
        return out
    fund["report_date"] = pd.to_datetime(fund["report_date"]).dt.date
    fund["ann_date"] = pd.to_datetime(fund["ann_date"], errors="coerce").dt.date
    fund["effective_date"] = fund.apply(engine._fund_visible_from, axis=1)
    idx = pd.DatetimeIndex(pd.to_datetime(sorted(set(trading_days))))
    field_map = {"roe": "roe", "debt": "debt_ratio", "gross_margin": "gross_margin",
                 "rev_yoy": "revenue_yoy", "np_yoy": "net_profit_yoy"}
    for name, col in field_map.items():
        if col not in fund.columns:
            continue
        m = fund.dropna(subset=[col]).pivot_table(
            index="effective_date", columns="code", values=col, aggfunc="last")
        m.index = pd.DatetimeIndex(pd.to_datetime(m.index))
        out[name] = m.sort_index().reindex(idx).ffill()
    return out


def build_panel(start: dt.date, end: dt.date) -> dict[str, pd.DataFrame]:
    """整段窗口的行情 + 财务面板（dates × codes）。算子与表达式都吃这个。

    索引统一为 DatetimeIndex：K 线来自 MySQL 是 date 对象、财务面板是
    Timestamp——不归一的话混合表达式（如 rank(roe)+rank(close)）按索引
    对齐会得到全 NaN。
    """
    ohlcv = engine._universe_ohlcv(start, end)
    if not ohlcv:
        return {}
    trading_days = engine._trading_days(start, end)
    p: dict[str, pd.DataFrame] = {}
    for k, v in ohlcv.items():
        v = v.copy()
        v.index = pd.DatetimeIndex(pd.to_datetime(v.index))
        p[k] = v
    close = p["close"]
    p["vwap"] = (p["high"] + p["low"] + close) / 3.0
    p["returns"] = close.pct_change()
    fund = _fund_matrices(trading_days, end)
    p.update(fund)
    return p


def _make_namespace(panel: dict[str, pd.DataFrame]) -> dict:
    """字段 + 算子的求值命名空间；算子同时注册 WorldQuant 小写与大写别名。"""

    def _num(x) -> pd.DataFrame:
        if isinstance(x, pd.DataFrame):
            return x.astype(float)
        if isinstance(x, pd.Series):
            # 广播成与 close 同形的矩阵（常量列向量）
            return pd.DataFrame(
                np.tile(x.to_numpy(float)[:, None], (1, len(panel["close"].columns))),
                index=panel["close"].index, columns=panel["close"].columns)
        return panel["close"] * float(x)

    # —— 时序算子 ——
    def ts_mean(x, n): return _num(x).rolling(int(n), min_periods=int(n)).mean()
    def ts_std(x, n): return _num(x).rolling(int(n), min_periods=int(n)).std()
    def ts_sum(x, n): return _num(x).rolling(int(n), min_periods=int(n)).sum()
    def ts_max(x, n): return _num(x).rolling(int(n), min_periods=int(n)).max()
    def ts_min(x, n): return _num(x).rolling(int(n), min_periods=int(n)).min()

    def ts_rank(x, n):
        # 向量化：当前值在最近 n 日窗口内的分位 = (严格小于当前值的前 n-1 个值计数)/(n-1)。
        # 全窗口非 NaN 才有效（与 rolling 语义一致）。n-1 次向量化比较，避免逐窗口 apply。
        m = _num(x)
        n = int(n)
        cnt = None
        for j in range(1, n):
            cmp = (m > m.shift(j)).astype(float)
            cnt = cmp if cnt is None else cnt + cmp
        full = m.notna() & (m.rolling(n).count() == n)
        return (cnt / max(n - 1, 1)).where(full)

    def delay(x, n): return _num(x).shift(int(n))
    def delta(x, n): return _num(x) - _num(x).shift(int(n))
    def pct_chg(x, n): return _num(x).pct_change(int(n))

    def ts_corr(x, y, n):
        return _num(x).rolling(int(n), min_periods=int(n)).corr(_num(y))

    # —— 截面算子 ——
    def rank(x):
        m = _num(x)
        return m.rank(axis=1, pct=True)

    def zscore(x):
        m = _num(x)
        mu = m.mean(axis=1)
        sd = m.std(axis=1, ddof=0)
        return m.sub(mu, axis=0).div(sd.replace(0, np.nan), axis=0)

    def sign(x):
        return np.sign(_num(x))

    def log(x):
        m = _num(x)
        return np.log(m.where(m > 0))

    def abs_(x):
        return _num(x).abs()

    ts_ops = {"ts_mean": ts_mean, "ts_std": ts_std, "ts_sum": ts_sum,
              "ts_max": ts_max, "ts_min": ts_min, "ts_rank": ts_rank,
              "delay": delay, "delta": delta, "pct_chg": pct_chg,
              "ts_corr": ts_corr}
    cross_ops = {"rank": rank, "zscore": zscore, "sign": sign, "log": log, "abs": abs_}
    ns: dict = {}
    for d in (*PRICE_FIELDS, *FUND_FIELDS):
        ns[d] = panel[d]
    ns.update(ts_ops)
    ns.update(cross_ops)
    for base in (*ts_ops, *cross_ops):
        ns[base.upper()] = ns[base]
    ns["LOG"] = ns["log"]
    ns["ABS"] = ns["abs"]
    ns["SIGN"] = ns["sign"]
    return ns


# ---------------------------------------------------------------------------
# 因子求值
# ---------------------------------------------------------------------------

def eval_expression(expr: str, panel: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """整面板求值，返回 dates × codes 的因子矩阵。"""
    ns = _make_namespace(panel)
    code_obj = parse_alpha(expr, ns)
    try:
        res = eval(code_obj, {"__builtins__": {}}, ns)   # 白名单已静态校验
    except AlphaExprError:
        raise
    except Exception as e:
        raise AlphaExprError(f"求值失败: {e}")
    if not isinstance(res, pd.DataFrame):
        if isinstance(res, pd.Series):
            res = res.to_frame()
        else:
            raise AlphaExprError("表达式结果不是面板矩阵（检查字段名）")
    res = res.astype(float)
    if not res.index.is_monotonic_increasing:
        res = res.sort_index()
    return res


# ---------------------------------------------------------------------------
# 自定义因子检验（复用 factorlab 统计管线）
# ---------------------------------------------------------------------------

def _liquidity_universe(close: pd.DataFrame, volume: pd.DataFrame,
                        max_codes: int) -> list[str]:
    """流动性宇宙：日均成交额（close×volume）降序前 max_codes。"""
    liq = (close * volume).mean()
    return liq.sort_values(ascending=False).head(max_codes).index.tolist()


def analyze_expr(expr: str, start: dt.date, end: dt.date,
                 rebalance: str = "weekly", layers: int = 5,
                 max_codes: int = 400, neutralize: bool = True) -> dict:
    from factorlab import analyze_scores
    panel = build_panel(start, end)
    if not panel:
        return {"error": "no price matrix; run postmarket job first"}
    trading_days = engine._trading_days(start, end)
    if len(trading_days) < 30:
        return {"error": "not enough trading days in range"}
    try:
        factor = eval_expression(expr, panel)
    except AlphaExprError as e:
        return {"error": str(e), "error_kind": "expression"}

    close = panel["close"]
    # 流动性宇宙：与 analyze_scores 共用同一份（否则两个前 N 交集坍缩、覆盖失效）
    codes = [c for c in _liquidity_universe(close, panel["volume"], max_codes)
             if c in factor.columns]
    factor = factor[codes]

    # 预热不足的早期行是 NaN——检验循环的覆盖门槛会自动跳过这些期
    def provider(d: dt.date, codes_list: list[str]) -> pd.Series:
        d_ts = pd.Timestamp(d)
        if d_ts not in factor.index:
            return pd.Series(dtype=float)
        return factor.loc[d_ts].reindex(codes_list).dropna()

    result = analyze_scores(provider, start=start, end=end, rebalance=rebalance,
                            layers=layers, codes=codes, neutralize=neutralize,
                            factor_name="自定义因子")
    if "error" not in result:
        result["expression"] = expr
    return result


# ---------------------------------------------------------------------------
# 自定义因子组合回测：t 收盘出信号 → t+1 开盘成交
# ---------------------------------------------------------------------------

def backtest_expr(expr: str, start: dt.date, end: dt.date,
                  initial_capital: float = 1_000_000,
                  top_n: int = 10, rebalance: str = "weekly",
                  costs: dict | None = None,
                  max_codes: int = 500) -> dict:
    cost = engine._normalize_costs(costs)
    trading_days = engine._trading_days(start, end)
    if len(trading_days) < 30:
        return {"error": "not enough trading days in range"}
    panel = build_panel(start, end)
    if not panel:
        return {"error": "no price matrix; run postmarket job first"}
    try:
        factor = eval_expression(expr, panel)
    except AlphaExprError as e:
        return {"error": str(e), "error_kind": "expression"}

    close, volume = panel["close"], panel["volume"]
    open_ = panel["open"]
    codes = close.columns.tolist()
    factor = factor.reindex(columns=codes)

    liq = (close * volume).mean().sort_values(ascending=False)
    universe = [c for c in liq.head(max_codes).index]
    factor_u = factor[universe]

    # 估值与涨跌停参考（口径与 engine.run 相同：停牌 ffill 估值、交易所舍入）
    val_close = close.ffill()
    prev_close = val_close.shift(1)
    ratio = pd.Series({c: engine._limit_ratio(c) for c in codes})
    limit_up = np.floor((prev_close.mul(1 + ratio)).mul(100) + 0.5) / 100.0
    limit_down = np.ceil((prev_close.mul(1 - ratio)).mul(100) - 0.5) / 100.0
    tradable = close.notna() & (volume.fillna(0) > 0)
    # 开盘可交易性：开盘价未封板（一字板/开盘涨停买不进、开盘跌停卖不出）
    buyable_open = tradable & open_.notna() & (open_ < limit_up)
    sellable_open = tradable & open_.notna() & (open_ > limit_down)

    day_pos = {d: i for i, d in enumerate(trading_days)}
    rebal = engine._rebalance_dates(trading_days, rebalance)
    rebal_set = set(rebal)

    holdings: dict[str, float] = {}
    cost_basis: dict[str, float] = {}
    cash = float(initial_capital)
    total_traded = 0.0
    total_cost_paid = 0.0
    trades: list[dict] = []
    equity_vals: list[float] = []
    equity_dates: list[dt.date] = []
    rebal_log: list[dict] = []
    last_picks: list[str] = []

    pending = None   # (signal_date, picks) 等待下一个交易日开盘执行

    def value_at(date: dt.date) -> float:
        ts = pd.Timestamp(date)
        if ts not in val_close.index or not holdings:
            return 0.0
        row = val_close.loc[ts]
        total = 0.0
        for c, sh in holdings.items():
            if c in row.index and pd.notna(row[c]):
                total += sh * float(row[c])
        return total

    for d in trading_days:
        d_ts = pd.Timestamp(d)
        # ---- 1) 执行昨日信号：今日开盘成交 ----
        if pending is not None:
            sig_date, picks = pending
            pending = None
            if d_ts in open_.index:
                pick_set = set(picks)
                row_open = open_.loc[d_ts]
                row_buyable = buyable_open.loc[d_ts]
                row_sellable = sellable_open.loc[d_ts]
                mv = value_at(sig_date) + cash

                def _on(col, c) -> bool:
                    return c in col.index and bool(col[c])

                for c in list(holdings):
                    if c in pick_set or not _on(row_sellable, c):
                        continue
                    raw_px = float(row_open[c])
                    exec_px = raw_px * (1 - cost["slippage"])
                    sh = holdings[c]
                    gross = sh * exec_px
                    fee = engine._commission(gross, cost)
                    tax = gross * cost["stamp_tax"]
                    cash += gross - fee - tax
                    total_traded += gross
                    total_cost_paid += fee + tax
                    basis = cost_basis.get(c, raw_px)
                    trades.append({"date": d.isoformat(), "code": c, "side": "sell",
                                   "shares": round(-sh, 4), "price": round(exec_px, 3),
                                   "pnl": round((exec_px - basis) * sh, 2)})
                    del holdings[c]
                    cost_basis.pop(c, None)

                if picks and mv > 0:
                    n_target = max(len(picks), 1)
                    tgt_value = mv / n_target
                    for c in picks:
                        if not _on(row_buyable, c):
                            continue
                        raw_px = float(row_open[c])
                        if raw_px <= 0:
                            continue
                        exec_px = raw_px * (1 + cost["slippage"])
                        cur_sh = holdings.get(c, 0.0)
                        tgt_sh = tgt_value / exec_px
                        diff_lots = int((tgt_sh - cur_sh) // engine.LOT_SIZE)
                        if diff_lots > 0:
                            add_sh = diff_lots * engine.LOT_SIZE
                            amount = add_sh * exec_px
                            fee = engine._commission(amount, cost)
                            if amount + fee > cash:
                                afford_lots = int((cash / exec_px) // engine.LOT_SIZE)
                                if afford_lots <= 0:
                                    continue
                                add_sh = afford_lots * engine.LOT_SIZE
                                amount = add_sh * exec_px
                                fee = engine._commission(amount, cost)
                            cash -= amount + fee
                            total_traded += amount
                            total_cost_paid += fee
                            old_sh = cur_sh
                            old_basis = cost_basis.get(c, exec_px)
                            new_sh = old_sh + add_sh
                            cost_basis[c] = (old_basis * old_sh + exec_px * add_sh) / new_sh if new_sh > 0 else exec_px
                            holdings[c] = new_sh
                            trades.append({"date": d.isoformat(), "code": c, "side": "buy",
                                           "shares": round(add_sh, 4), "price": round(exec_px, 3),
                                           "pnl": None})
                        elif diff_lots < 0:
                            sell_sh = min(-diff_lots * engine.LOT_SIZE, cur_sh)
                            if not _on(row_sellable, c):
                                continue
                            exec_px_s = raw_px * (1 - cost["slippage"])
                            gross = sell_sh * exec_px_s
                            fee = engine._commission(gross, cost)
                            tax = gross * cost["stamp_tax"]
                            cash += gross - fee - tax
                            total_traded += gross
                            total_cost_paid += fee + tax
                            basis = cost_basis.get(c, raw_px)
                            trades.append({"date": d.isoformat(), "code": c, "side": "sell",
                                           "shares": round(-sell_sh, 4), "price": round(exec_px_s, 3),
                                           "pnl": round((exec_px_s - basis) * sell_sh, 2)})
                            remaining = cur_sh - sell_sh
                            if remaining <= 1e-6:
                                holdings.pop(c, None)
                                cost_basis.pop(c, None)
                            else:
                                holdings[c] = remaining

        # ---- 2) 收盘出信号，压入 pending（t+1 开盘执行）----
        if d in rebal_set and d_ts in factor_u.index:
            sig = factor_u.loc[d_ts].dropna()
            sig = sig[sig.index.isin(universe)]
            min_coverage = max(top_n * 3, 20)
            if len(sig) >= min_coverage:
                ranked = sig.sort_values(ascending=False)
                picks = [c for c, _ in ranked.head(top_n).items()]
                last_picks = picks
                rebal_log.append({"date": d.isoformat(), "picks": picks})
                if day_pos.get(d, len(trading_days) - 1) + 1 < len(trading_days):
                    pending = (d, picks)
            else:
                logger.info("[alphalab] %s factor coverage %d < %d — hold", d, len(sig), min_coverage)

        equity_vals.append(value_at(d) + cash)
        equity_dates.append(d)

    eq_series = pd.Series(equity_vals, index=pd.to_datetime(equity_dates))
    bench = engine._benchmark_close(start, end)
    years = max(len(trading_days) / 252.0, 1e-6)
    mean_equity = float(eq_series.mean()) if len(eq_series) else 0.0
    turnover_annual = (total_traded / mean_equity / years) if mean_equity > 0 else None
    metrics = engine.compute(eq_series, trades=trades, benchmark=bench,
                             turnover_rate=turnover_annual, total_costs=total_cost_paid)

    out = {
        "mode": "factor",
        "expression": expr,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "initial_capital": initial_capital,
        "top_n": top_n,
        "rebalance": rebalance,
        "costs": cost,
        "metrics": metrics.as_dict(),
        "equity_curve": [
            {"date": dd.isoformat(), "value": round(v, 2)}
            for dd, v in zip(equity_dates, equity_vals)
        ],
        "trades": trades[:200],
        "picks": last_picks,
        "rebalances": rebal_log[-12:],
        "universe_size": len(universe),
    }
    if bench is not None and len(bench) >= 2:
        bench = bench.reindex(pd.to_datetime(equity_dates)).ffill()
        base = float(bench.iloc[0]) if pd.notna(bench.iloc[0]) else None
        if base:
            out["benchmark_curve"] = [
                {"date": dd.isoformat(), "value": round(float(v) / base * initial_capital, 2)}
                for dd, v in bench.items() if pd.notna(v)
            ]
    return out


def help_payload() -> dict:
    return {
        "fields": [
            {"category": "行情（时序面板）", "items": [
                {"name": k, "desc": v} for k, v in PRICE_FIELDS.items()]},
            {"category": "财务（截面面板，point-in-time）", "items": [
                {"name": k, "desc": v} for k, v in FUND_FIELDS.items()]},
            {"category": "算子", "items": [
                {"name": k, "desc": v} for k, v in OPERATORS.items()]},
        ],
        "examples": EXAMPLES,
        "notes": [
            "时序算子是向后窗口，只用 <= t 的数据；截面因子值 t 日收盘后可知。",
            "组合回测按 t+1 日开盘价成交，开盘一字涨停买不进、开盘跌停卖不出。",
            "财务字段按公告日（缺失用法定披露截止日）进入，无未来数据。",
            "无历史市值数据，故不提供市值字段（避免用当前市值回填历史）。",
        ],
    }
