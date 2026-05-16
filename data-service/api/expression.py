# -*- coding: utf-8 -*-
"""Expression-based screener (Phase 3).

Users write a Python-like boolean expression and we evaluate it against every
candidate stock. Example:

    ROE > 15 and DEBT < 60 and CLOSE > MA(CLOSE, 60) and MACD_GC(5)

Security: we use ast.parse + node-class whitelist + function whitelist. NO
`__builtins__`, NO attribute access, NO imports, NO comprehensions.
"""
from __future__ import annotations
import ast
import math

import numpy as np
import pandas as pd
from flask import Blueprint, jsonify, request
from sqlalchemy import text

import cache
import db


bp = Blueprint("expression_v2", __name__, url_prefix="/api/v2")


# ---------------------------------------------------------------------------
# AST whitelist
# ---------------------------------------------------------------------------

_SAFE_NODES = {
    ast.Expression, ast.BinOp, ast.BoolOp, ast.Compare, ast.UnaryOp,
    ast.Name, ast.Load, ast.Constant, ast.Call,
    ast.And, ast.Or, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv, ast.Pow,
    ast.USub, ast.UAdd,
    ast.IfExp,                      # ternary x if cond else y
    ast.Tuple, ast.List,
}

_ALLOWED_FUNCS = {
    "MA", "EMA", "STD", "MAX", "MIN", "ABS", "SUM", "MEAN", "RANK",
    "MACD", "MACD_GC", "MACD_DC", "RSI", "KDJ_K", "KDJ_D",
    "REF", "DELTA", "CROSS_UP", "CROSS_DOWN",
    "HHV", "LLV", "PCT_CHG",
}


class ExprError(Exception):
    pass


def parse_safe(expr: str) -> ast.AST:
    if not expr or not expr.strip():
        raise ExprError("空表达式")
    if len(expr) > 2000:
        raise ExprError("表达式过长（限制 2000 字符）")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ExprError(f"语法错误: {e.msg}")
    for node in ast.walk(tree):
        if type(node) not in _SAFE_NODES:
            raise ExprError(f"不允许的语法: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise ExprError("只允许直接函数调用，不允许 obj.method()")
            if node.func.id not in _ALLOWED_FUNCS:
                raise ExprError(f"未知函数: {node.func.id}()")
        if isinstance(node, ast.Name):
            # Name nodes refer to predefined variables/functions only.
            pass
    return tree


# ---------------------------------------------------------------------------
# Function library
# ---------------------------------------------------------------------------

def _last_scalar(series: pd.Series | float) -> float:
    if isinstance(series, (int, float, np.integer, np.floating)):
        return float(series)
    if hasattr(series, "iloc") and len(series):
        v = series.iloc[-1]
        try:
            return float(v) if pd.notna(v) else 0.0
        except Exception:
            return 0.0
    return 0.0


def _as_series(x) -> pd.Series:
    if isinstance(x, pd.Series):
        return x
    return pd.Series([x] if x is not None else [])


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _calc_macd(close: pd.Series, fast=12, slow=26, sig=9):
    if len(close) < slow:
        return pd.Series([0] * len(close)), pd.Series([0] * len(close)), pd.Series([0] * len(close))
    ema_fast = _ema(close, fast)
    ema_slow = _ema(close, slow)
    dif = ema_fast - ema_slow
    dea = _ema(dif, sig)
    hist = (dif - dea) * 2
    return dif, dea, hist


def _calc_rsi(close: pd.Series, n: int = 14) -> pd.Series:
    if len(close) < n + 1:
        return pd.Series([50.0] * len(close))
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(n).mean()
    loss = (-delta.clip(upper=0)).rolling(n).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(50)


def _build_namespace(daily_df: pd.DataFrame, scalars: dict) -> dict:
    """Construct the per-stock evaluation namespace."""
    if daily_df is None or daily_df.empty:
        empty = pd.Series([], dtype=float)
        close = open_ = high = low = vol = amount = empty
    else:
        close = pd.to_numeric(daily_df["收盘"], errors="coerce").reset_index(drop=True)
        open_ = pd.to_numeric(daily_df["开盘"], errors="coerce").reset_index(drop=True)
        high = pd.to_numeric(daily_df["最高"], errors="coerce").reset_index(drop=True)
        low = pd.to_numeric(daily_df["最低"], errors="coerce").reset_index(drop=True)
        vol = pd.to_numeric(daily_df["成交量"], errors="coerce").reset_index(drop=True)
        amount = pd.Series([], dtype=float)  # not always available

    ns: dict = {
        # Time-series fields
        "CLOSE": close, "C": close,
        "OPEN": open_, "O": open_,
        "HIGH": high, "H": high,
        "LOW": low, "L": low,
        "VOL": vol, "V": vol, "VOLUME": vol,
        "AMOUNT": amount,
        # ---- Library: time-series-aware, returns scalar at last bar ----
        "MA": lambda s, n: _last_scalar(_as_series(s).rolling(int(n)).mean()),
        "EMA": lambda s, n: _last_scalar(_ema(_as_series(s), int(n))),
        "STD": lambda s, n: _last_scalar(_as_series(s).rolling(int(n)).std()),
        "MAX": lambda s, n: _last_scalar(_as_series(s).rolling(int(n)).max()),
        "MIN": lambda s, n: _last_scalar(_as_series(s).rolling(int(n)).min()),
        "HHV": lambda s, n: _last_scalar(_as_series(s).rolling(int(n)).max()),
        "LLV": lambda s, n: _last_scalar(_as_series(s).rolling(int(n)).min()),
        "SUM": lambda s, n=None: _last_scalar(
            _as_series(s).rolling(int(n)).sum() if n else _as_series(s).sum()),
        "MEAN": lambda s, n=None: _last_scalar(
            _as_series(s).rolling(int(n)).mean() if n else _as_series(s).mean()),
        "ABS": lambda x: abs(_last_scalar(x)),
        "REF": lambda s, n: _last_scalar(_as_series(s).shift(int(n))),
        "DELTA": lambda s, n=1: _last_scalar(_as_series(s) - _as_series(s).shift(int(n))),
        "PCT_CHG": lambda s, n=1: _last_scalar(_as_series(s).pct_change(int(n)) * 100),
        "CROSS_UP": _cross_up,
        "CROSS_DOWN": _cross_down,
        # Indicator shortcuts (return scalar at last bar)
        "MACD": lambda c=None: _last_scalar(_calc_macd(_as_series(c) if c is not None else close)[2]),
        "MACD_GC": lambda window=5: _macd_gc(close, int(window)),
        "MACD_DC": lambda window=5: _macd_dc(close, int(window)),
        "RSI": lambda n=14: _last_scalar(_calc_rsi(close, int(n))),
        "KDJ_K": lambda n=9: _kdj_k(close, high, low, int(n)),
        "KDJ_D": lambda n=9: _kdj_d(close, high, low, int(n)),
        "RANK": lambda x: 0,  # placeholder; cross-sectional rank handled outside
    }
    ns.update(scalars)
    return ns


def _cross_up(a, b) -> bool:
    sa, sb = _as_series(a), _as_series(b)
    if len(sa) < 2 or len(sb) < 2:
        return False
    return bool(sa.iloc[-2] <= sb.iloc[-2] and sa.iloc[-1] > sb.iloc[-1])


def _cross_down(a, b) -> bool:
    sa, sb = _as_series(a), _as_series(b)
    if len(sa) < 2 or len(sb) < 2:
        return False
    return bool(sa.iloc[-2] >= sb.iloc[-2] and sa.iloc[-1] < sb.iloc[-1])


def _macd_gc(close: pd.Series, window: int) -> bool:
    dif, dea, _ = _calc_macd(close)
    n = min(window, len(dif) - 1)
    for i in range(-n, 0):
        if i - 1 < -len(dif): continue
        if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
            return True
    return False


def _macd_dc(close: pd.Series, window: int) -> bool:
    dif, dea, _ = _calc_macd(close)
    n = min(window, len(dif) - 1)
    for i in range(-n, 0):
        if i - 1 < -len(dif): continue
        if dif.iloc[i] < dea.iloc[i] and dif.iloc[i - 1] >= dea.iloc[i - 1]:
            return True
    return False


def _kdj_k(close, high, low, n=9):
    if len(close) < n:
        return 50.0
    llv = low.rolling(n).min()
    hhv = high.rolling(n).max()
    rsv = (close - llv) / (hhv - llv).replace(0, np.nan) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    return _last_scalar(k)


def _kdj_d(close, high, low, n=9):
    if len(close) < n:
        return 50.0
    llv = low.rolling(n).min()
    hhv = high.rolling(n).max()
    rsv = (close - llv) / (hhv - llv).replace(0, np.nan) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    return _last_scalar(d)


# ---------------------------------------------------------------------------
# Field catalogue for the UI helper panel
# ---------------------------------------------------------------------------

EXPR_FIELDS = [
    {"category": "时序", "items": [
        {"name": "CLOSE / C", "desc": "收盘价序列"},
        {"name": "OPEN / O", "desc": "开盘价序列"},
        {"name": "HIGH / H", "desc": "最高价序列"},
        {"name": "LOW / L", "desc": "最低价序列"},
        {"name": "VOL / V", "desc": "成交量序列"},
    ]},
    {"category": "标量(行情)", "items": [
        {"name": "PRICE", "desc": "最新价"},
        {"name": "PE", "desc": "市盈率"},
        {"name": "PB", "desc": "市净率"},
        {"name": "TURNOVER", "desc": "今日换手率(%)"},
        {"name": "MKT_CAP", "desc": "总市值(亿)"},
        {"name": "PCT_CHANGE", "desc": "今日涨跌幅(%)"},
    ]},
    {"category": "标量(财务)", "items": [
        {"name": "ROE", "desc": "净资产收益率(%)"},
        {"name": "DEBT", "desc": "资产负债率(%)"},
        {"name": "GROSS_MARGIN", "desc": "毛利率(%)"},
        {"name": "REV_YOY", "desc": "营收同比(%)"},
        {"name": "NP_YOY", "desc": "净利同比(%)"},
    ]},
    {"category": "函数", "items": [
        {"name": "MA(S, n)", "desc": "n 日简单均线最后值"},
        {"name": "EMA(S, n)", "desc": "n 日指数均线最后值"},
        {"name": "STD(S, n)", "desc": "n 日标准差"},
        {"name": "HHV(S, n)", "desc": "n 日最高"},
        {"name": "LLV(S, n)", "desc": "n 日最低"},
        {"name": "REF(S, n)", "desc": "n 天前的值"},
        {"name": "DELTA(S, n)", "desc": "n 天前到当前的差"},
        {"name": "PCT_CHG(S, n)", "desc": "n 天累计涨跌幅(%)"},
        {"name": "MACD_GC(window=5)", "desc": "最近 window 日内是否出现 MACD 金叉"},
        {"name": "MACD_DC(window=5)", "desc": "死叉版本"},
        {"name": "RSI(n=14)", "desc": "RSI 当前值"},
        {"name": "KDJ_K(n=9)", "desc": "KDJ K 线当前值"},
        {"name": "CROSS_UP(A, B)", "desc": "A 上穿 B（最近 1 日）"},
    ]},
]

EXAMPLES = [
    {"name": "价值股", "expr": "PE > 0 and PE <= 25 and PB <= 3 and ROE >= 15 and DEBT <= 60"},
    {"name": "动量突破", "expr": "CLOSE > MA(CLOSE, 60) and MACD_GC(5) and V > MA(V, 20) * 2"},
    {"name": "RSI 超卖反弹", "expr": "RSI(6) < 30 and CLOSE > REF(CLOSE, 1) and V > MA(V, 10) * 1.5"},
    {"name": "20 日新高 + 量能", "expr": "CLOSE > HHV(HIGH, 20) and V > MA(V, 5) * 1.5 and PCT_CHANGE > 2"},
    {"name": "成长股", "expr": "REV_YOY >= 20 and NP_YOY >= 30 and GROSS_MARGIN >= 30 and ROE >= 12"},
]


@bp.route("/expression/help")
def expression_help():
    return jsonify({"fields": EXPR_FIELDS, "examples": EXAMPLES, "functions": sorted(_ALLOWED_FUNCS)})


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def _load_universe(top_n: int) -> tuple[pd.DataFrame, dict]:
    spot = cache.get("spot")
    if spot is None or not hasattr(spot, "columns"):
        return pd.DataFrame(), {}
    df = spot.copy()
    if "代码" not in df.columns:
        return pd.DataFrame(), {}
    df["code"] = df["代码"].astype(str).str.zfill(6)
    rename = {"最新价": "price", "涨跌幅": "pct_change", "市盈率": "pe",
              "市净率": "pb", "换手率": "turnover", "总市值_亿": "market_cap_yi",
              "行业": "industry", "名称": "name"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    for c in ("price", "pct_change", "pe", "pb", "turnover", "market_cap_yi"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "market_cap_yi" in df.columns:
        df = df.sort_values("market_cap_yi", ascending=False, na_position="last").head(top_n)
    codes = df["code"].tolist()

    fund_map: dict[str, dict] = {}
    eng = db.get_engine()
    if eng is not None and codes:
        codes_csv = ",".join(f"'{c}'" for c in codes)
        with eng.connect() as conn:
            rows = conn.execute(text(
                f"SELECT f.code, f.roe, f.debt_ratio, f.gross_margin, "
                f"  f.revenue_yoy, f.net_profit_yoy "
                f"FROM stock_fundamental f INNER JOIN ("
                f"  SELECT code, MAX(report_date) AS rd "
                f"  FROM stock_fundamental WHERE code IN ({codes_csv}) GROUP BY code"
                f") m ON f.code=m.code AND f.report_date=m.rd"
            )).fetchall()
            for r in rows:
                fund_map[r[0]] = {
                    "ROE": float(r[1] or 0), "DEBT": float(r[2] or 0),
                    "GROSS_MARGIN": float(r[3] or 0),
                    "REV_YOY": float(r[4] or 0), "NP_YOY": float(r[5] or 0),
                }
    return df, fund_map


@bp.route("/screen/expression", methods=["POST"])
def screen_expression():
    body = request.get_json(silent=True) or {}
    expr = body.get("expression", "").strip()
    limit = int(body.get("limit") or 50)
    top_universe = int(body.get("topUniverse") or 300)
    need_kline = body.get("needKline", True)

    try:
        tree = parse_safe(expr)
        code_obj = compile(tree, "<expr>", "eval")
    except ExprError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"解析失败: {e}"}), 400

    df, fund_map = _load_universe(top_universe)
    if df.empty:
        return jsonify([])

    # Optional kline preload
    daily_by_code: dict[str, pd.DataFrame] = {}
    if need_kline:
        eng = db.get_engine()
        if eng is not None:
            codes_csv = ",".join(f"'{c}'" for c in df["code"].tolist())
            with eng.connect() as conn:
                allk = pd.read_sql(text(
                    f"SELECT code, trade_date, open, close, high, low, volume "
                    f"FROM stock_kline_daily WHERE code IN ({codes_csv}) "
                    f"ORDER BY code, trade_date"
                ), conn)
            for code, g in allk.groupby("code"):
                g = g.rename(columns={
                    "trade_date": "日期", "open": "开盘", "close": "收盘",
                    "high": "最高", "low": "最低", "volume": "成交量",
                })
                daily_by_code[code] = g

    out: list[dict] = []
    skipped = 0
    for _, r in df.iterrows():
        code = r["code"]
        scalars = {
            "PRICE": float(r.get("price") or 0),
            "PE": float(r.get("pe") or 0),
            "PB": float(r.get("pb") or 0),
            "TURNOVER": float(r.get("turnover") or 0),
            "MKT_CAP": float(r.get("market_cap_yi") or 0),
            "PCT_CHANGE": float(r.get("pct_change") or 0),
        }
        scalars.update({"ROE": 0.0, "DEBT": 0.0, "GROSS_MARGIN": 0.0,
                        "REV_YOY": 0.0, "NP_YOY": 0.0})
        scalars.update(fund_map.get(code, {}))
        dk = daily_by_code.get(code) if need_kline else None
        try:
            ns = _build_namespace(dk, scalars)
            res = eval(code_obj, {"__builtins__": {}}, ns)
            ok = bool(res)
        except Exception:
            skipped += 1
            continue
        if ok:
            out.append({
                "code": code,
                "name": str(r.get("name") or ""),
                "industry": str(r.get("industry") or ""),
                "price": round(scalars["PRICE"], 2),
                "changePercent": round(scalars["PCT_CHANGE"], 2),
                "pe": round(scalars["PE"], 2),
                "pb": round(scalars["PB"], 2),
                "marketCap": round(scalars["MKT_CAP"], 0),
                "roe": round(scalars["ROE"], 2),
                "debtRatio": round(scalars["DEBT"], 2),
            })
        if len(out) >= limit:
            break

    out.sort(key=lambda x: x.get("marketCap", 0), reverse=True)
    return jsonify(out)


@bp.route("/screen/expression/validate", methods=["POST"])
def validate_expression():
    body = request.get_json(silent=True) or {}
    expr = body.get("expression", "").strip()
    try:
        parse_safe(expr)
        return jsonify({"ok": True})
    except ExprError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
