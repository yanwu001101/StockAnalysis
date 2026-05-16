# -*- coding: utf-8 -*-
"""Condition-based screener (Phase 2).

A small DSL for stock filtering:

    {
      "logic": "AND",                 # or "OR"
      "conditions": [
        {"field": "pe", "op": ">=", "value": 10},
        {"field": "pe", "op": "<=", "value": 30},
        {"field": "roe", "op": ">=", "value": 15},
        {"field": "industry", "op": "in", "value": ["半导体", "白酒Ⅱ"]},
        {"field": "above_ma20", "op": "==", "value": true},
        {"field": "main_net_5d_positive", "op": "==", "value": true}
      ],
      "limit": 50
    }

Fields are resolved against:
  * `spot` snapshot (price/pe/pb/turnover/industry/...)
  * `stock_fundamental` (latest row per code)
  * `stock_kline_daily` (last 60 bars per code for technical flags)
  * `stock_moneyflow` (last N days net sum)
  * `stock_northbound` (last N days share delta)
"""
from __future__ import annotations

import pandas as pd
from flask import Blueprint, jsonify, request
from sqlalchemy import text

import cache
import db


bp = Blueprint("conditions_v2", __name__, url_prefix="/api/v2")


# ---------------------------------------------------------------------------
# Field catalogue (returned to the front-end builder)
# ---------------------------------------------------------------------------

FIELDS: list[dict] = [
    # Quote (spot)
    {"id": "price", "label": "最新价", "type": "number", "unit": "元",
     "ops": [">=", "<=", ">", "<", "between"]},
    {"id": "pct_change", "label": "今日涨跌幅", "type": "number", "unit": "%",
     "ops": [">=", "<=", ">", "<", "between"]},
    {"id": "pe", "label": "市盈率 (PE)", "type": "number",
     "ops": [">=", "<=", "between"]},
    {"id": "pb", "label": "市净率 (PB)", "type": "number",
     "ops": [">=", "<=", "between"]},
    {"id": "turnover", "label": "换手率", "type": "number", "unit": "%",
     "ops": [">=", "<=", "between"]},
    {"id": "market_cap_yi", "label": "总市值", "type": "number", "unit": "亿",
     "ops": [">=", "<=", "between"]},
    {"id": "amount_yi", "label": "成交额", "type": "number", "unit": "亿",
     "ops": [">=", "<=", "between"]},
    {"id": "industry", "label": "行业", "type": "industry",
     "ops": ["in", "not_in"]},

    # Fundamentals
    {"id": "roe", "label": "ROE", "type": "number", "unit": "%", "source": "fund",
     "ops": [">=", "<=", "between"]},
    {"id": "debt_ratio", "label": "资产负债率", "type": "number", "unit": "%", "source": "fund",
     "ops": [">=", "<=", "between"]},
    {"id": "gross_margin", "label": "毛利率", "type": "number", "unit": "%", "source": "fund",
     "ops": [">=", "<=", "between"]},
    {"id": "revenue_yoy", "label": "营收同比", "type": "number", "unit": "%", "source": "fund",
     "ops": [">=", "<=", "between"]},
    {"id": "net_profit_yoy", "label": "净利同比", "type": "number", "unit": "%", "source": "fund",
     "ops": [">=", "<=", "between"]},

    # Technical (derived)
    {"id": "above_ma20", "label": "股价站上 MA20", "type": "bool", "source": "kline",
     "ops": ["=="]},
    {"id": "above_ma60", "label": "股价站上 MA60", "type": "bool", "source": "kline",
     "ops": ["=="]},
    {"id": "macd_golden_5d", "label": "5 日内 MACD 金叉", "type": "bool", "source": "kline",
     "ops": ["=="]},
    {"id": "rsi_oversold", "label": "RSI < 30 (超卖)", "type": "bool", "source": "kline",
     "ops": ["=="]},
    {"id": "rsi_overbought", "label": "RSI > 70 (超买)", "type": "bool", "source": "kline",
     "ops": ["=="]},
    {"id": "volume_surge_2x", "label": "成交量放大 2 倍以上", "type": "bool", "source": "kline",
     "ops": ["=="]},
    {"id": "break_high_20d", "label": "突破 20 日新高", "type": "bool", "source": "kline",
     "ops": ["=="]},

    # Flow
    {"id": "main_net_5d_positive", "label": "5 日主力净流入", "type": "bool", "source": "flow",
     "ops": ["=="]},
    {"id": "main_net_5d_strong", "label": "5 日主力净流入 > 5000万", "type": "bool", "source": "flow",
     "ops": ["=="]},
    {"id": "northbound_accumulating", "label": "5 日北向加仓", "type": "bool", "source": "flow",
     "ops": ["=="]},
]


@bp.route("/condition-fields")
def condition_fields():
    return jsonify(FIELDS)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

def _eval_one(row: dict, cond: dict) -> bool:
    f = cond.get("field")
    op = cond.get("op", "==")
    v = cond.get("value")
    cur = row.get(f)
    if cur is None:
        return False
    try:
        if op == ">=": return float(cur) >= float(v)
        if op == "<=": return float(cur) <= float(v)
        if op == ">":  return float(cur) >  float(v)
        if op == "<":  return float(cur) <  float(v)
        if op == "between" and isinstance(v, list) and len(v) == 2:
            return float(v[0]) <= float(cur) <= float(v[1])
        if op == "==": return bool(cur) == bool(v)
        if op == "in" and isinstance(v, list):
            return str(cur) in [str(x) for x in v]
        if op == "not_in" and isinstance(v, list):
            return str(cur) not in [str(x) for x in v]
    except Exception:
        return False
    return False


def _apply(row: dict, logic: str, conditions: list[dict]) -> bool:
    if not conditions:
        return True
    results = [_eval_one(row, c) for c in conditions]
    return all(results) if logic.upper() == "AND" else any(results)


# ---------------------------------------------------------------------------
# Universe builder — assemble all fields for top-N candidate stocks
# ---------------------------------------------------------------------------

def _build_universe(top_n: int = 500) -> pd.DataFrame:
    """Return a DataFrame keyed by code containing every queryable field."""
    spot = cache.get("spot")
    if spot is None or not hasattr(spot, "columns"):
        return pd.DataFrame()
    df = spot.copy()
    if "代码" not in df.columns:
        return pd.DataFrame()
    df["code"] = df["代码"].astype(str).str.zfill(6)
    # Numeric coercion
    rename = {
        "最新价": "price", "涨跌幅": "pct_change", "市盈率": "pe", "市净率": "pb",
        "换手率": "turnover", "总市值_亿": "market_cap_yi", "成交额": "_amount",
        "行业": "industry", "名称": "name",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    for col in ("price", "pct_change", "pe", "pb", "turnover", "market_cap_yi", "_amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["amount_yi"] = (df["_amount"] / 1e8) if "_amount" in df.columns else None
    # Top-N by market cap
    if "market_cap_yi" in df.columns:
        df = df.sort_values("market_cap_yi", ascending=False, na_position="last").head(top_n)

    codes = df["code"].tolist()
    eng = db.get_engine()
    if eng is not None and codes:
        codes_csv = ",".join(f"'{c}'" for c in codes)
        # Fundamentals (latest per code)
        with eng.connect() as conn:
            fund = pd.read_sql(text(
                f"SELECT f.code, f.roe, f.debt_ratio, f.gross_margin, "
                f"  f.revenue_yoy, f.net_profit_yoy "
                f"FROM stock_fundamental f "
                f"INNER JOIN (SELECT code, MAX(report_date) AS rd "
                f"  FROM stock_fundamental WHERE code IN ({codes_csv}) GROUP BY code) m "
                f"ON f.code=m.code AND f.report_date=m.rd"
            ), conn)
            mf = pd.read_sql(text(
                f"SELECT code, SUM(main_net) AS main_net_5d "
                f"FROM stock_moneyflow "
                f"WHERE code IN ({codes_csv}) "
                f"AND trade_date >= (CURDATE() - INTERVAL 5 DAY) "
                f"GROUP BY code"
            ), conn)
            nb = pd.read_sql(text(
                f"SELECT t.code, t.shares_diff FROM ("
                f"  SELECT code,"
                f"    MAX(CASE WHEN trade_date=m.maxd THEN hold_shares END) -"
                f"    MAX(CASE WHEN trade_date=m.mind THEN hold_shares END) AS shares_diff"
                f"  FROM stock_northbound n,"
                f"    (SELECT MIN(trade_date) AS mind, MAX(trade_date) AS maxd"
                f"     FROM stock_northbound"
                f"     WHERE trade_date >= (CURDATE() - INTERVAL 5 DAY)) m"
                f"  WHERE trade_date IN (m.mind, m.maxd) AND code IN ({codes_csv})"
                f"  GROUP BY code"
                f") t WHERE t.shares_diff IS NOT NULL"
            ), conn)
        if not fund.empty:
            df = df.merge(fund, on="code", how="left")
        if not mf.empty:
            df = df.merge(mf, on="code", how="left")
        if not nb.empty:
            df = df.merge(nb, on="code", how="left")

    # Derived technical flags — compute on demand only when needed
    if "main_net_5d" in df.columns:
        df["main_net_5d_positive"] = df["main_net_5d"].fillna(0) > 0
        df["main_net_5d_strong"] = df["main_net_5d"].fillna(0) > 50_000_000
    else:
        df["main_net_5d_positive"] = False
        df["main_net_5d_strong"] = False
    if "shares_diff" in df.columns:
        df["northbound_accumulating"] = df["shares_diff"].fillna(0) > 0
    else:
        df["northbound_accumulating"] = False
    return df


def _attach_technicals(df: pd.DataFrame, need_keys: set[str]) -> pd.DataFrame:
    """Compute MA / MACD / RSI / volume flags for each code, lazily."""
    eng = db.get_engine()
    if eng is None or df.empty:
        return df
    flag_cols = ("above_ma20", "above_ma60", "macd_golden_5d", "rsi_oversold",
                 "rsi_overbought", "volume_surge_2x", "break_high_20d")
    if not (need_keys & set(flag_cols)):
        return df

    for col in flag_cols:
        df[col] = False

    from indicators import calc_macd, calc_rsi
    codes = df["code"].tolist()
    with eng.connect() as conn:
        for code in codes:
            try:
                dk = pd.read_sql(text(
                    "SELECT trade_date, close, high, low, volume "
                    "FROM stock_kline_daily WHERE code=:c "
                    "ORDER BY trade_date DESC LIMIT 80"
                ), conn, params={"c": code})
                if dk.empty or len(dk) < 30:
                    continue
                dk = dk.sort_values("trade_date").reset_index(drop=True)
                close = pd.to_numeric(dk["close"], errors="coerce")
                volume = pd.to_numeric(dk["volume"], errors="coerce")
                high = pd.to_numeric(dk["high"], errors="coerce")
                ma20 = close.rolling(20).mean().iloc[-1]
                ma60 = close.rolling(60).mean().iloc[-1] if len(close) >= 60 else None
                last_close = close.iloc[-1]
                flags = {
                    "above_ma20": bool(pd.notna(ma20) and last_close > ma20),
                    "above_ma60": bool(ma60 is not None and pd.notna(ma60) and last_close > ma60),
                }
                # MACD golden cross within last 5 days
                dif, dea, _ = calc_macd(close)
                gc = False
                for i in range(-5, 0):
                    if i - 1 < -len(dif): continue
                    if dif.iloc[i] > dea.iloc[i] and dif.iloc[i - 1] <= dea.iloc[i - 1]:
                        gc = True
                        break
                flags["macd_golden_5d"] = gc
                # RSI
                rsi = calc_rsi(close)
                if pd.notna(rsi.iloc[-1]):
                    flags["rsi_oversold"] = float(rsi.iloc[-1]) < 30
                    flags["rsi_overbought"] = float(rsi.iloc[-1]) > 70
                # Volume surge
                if len(volume) >= 20:
                    avg = volume.tail(20).mean()
                    flags["volume_surge_2x"] = bool(volume.iloc[-1] > 2 * avg)
                # 20-day high breakout
                if len(high) >= 21:
                    h20 = high.iloc[-21:-1].max()
                    flags["break_high_20d"] = bool(last_close > h20)

                idx = df.index[df["code"] == code]
                if len(idx):
                    for k, v in flags.items():
                        df.at[idx[0], k] = v
            except Exception:
                continue
    return df


@bp.route("/screen/conditions", methods=["POST"])
def screen_conditions():
    body = request.get_json(silent=True) or {}
    logic = body.get("logic", "AND")
    conditions = body.get("conditions", [])
    limit = int(body.get("limit") or 50)
    top_universe = int(body.get("topUniverse") or 500)

    df = _build_universe(top_universe)
    if df.empty:
        return jsonify([])

    # Lazy-compute technical flags only if any condition needs them
    need_keys = {c.get("field") for c in conditions}
    df = _attach_technicals(df, need_keys)

    out: list[dict] = []
    for _, r in df.iterrows():
        row = r.to_dict()
        if _apply(row, logic, conditions):
            out.append({
                "code": row.get("code"),
                "name": row.get("name", ""),
                "industry": row.get("industry", ""),
                "price": round(float(row.get("price") or 0), 2),
                "changePercent": round(float(row.get("pct_change") or 0), 2),
                "pe": round(float(row.get("pe") or 0), 2),
                "pb": round(float(row.get("pb") or 0), 2),
                "marketCap": round(float(row.get("market_cap_yi") or 0), 0),
                "roe": round(float(row.get("roe") or 0), 2),
                "debtRatio": round(float(row.get("debt_ratio") or 0), 2),
                "turnover": round(float(row.get("turnover") or 0), 2),
            })
        if len(out) >= limit:
            break
    out.sort(key=lambda x: x.get("marketCap", 0), reverse=True)
    return jsonify(out)
