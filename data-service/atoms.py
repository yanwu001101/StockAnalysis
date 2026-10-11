# -*- coding: utf-8 -*-
"""原子因子库（Atomic Factor Library）。

因子挖掘的变量层：每个原子因子是一张「交易日 × 股票」的向量化矩阵，
只使用 <= t 的数据（全部向后窗口），由 :class:`alphalab` 的懒加载命名空间
按需计算并缓存——不引用的原子零开销，引用过的整个任务内只算一次。

数据可得性：每个原子声明 needs（kline/amount/moneyflow/index/industry），
GET /api/factormine/atoms 会探查数据库实际覆盖并返回
ok / limited / unsupported，绝不伪造缺失字段。
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sqlalchemy import text

import db
from backtest import engine
from indicators import calc_adx, calc_bollinger, calc_cci, calc_ema, calc_kdj, calc_rsi


@dataclass(frozen=True)
class AtomSpec:
    name: str            # 表达式里使用的变量名（大写）
    category: str        # 价格/收益/均线/成交量/波动/动量/趋势/相对强弱/资金
    desc: str
    needs: tuple = ("kline",)          # 数据能力依赖
    window: int = 1                    # 最大回看窗口（交易日），供预热/缺失率参考
    fn: object = None                  # fn(panel) -> DataFrame(dates × codes)


def _ret(close: pd.DataFrame, n: int) -> pd.DataFrame:
    return close.pct_change(n)


def _safe_ratio(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    out = a / b.replace(0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# 各原子实现（panel 为 build_extended_panel 的产物）
# ---------------------------------------------------------------------------

def _atom_vwap(p):
    # 真实成交均价 = 成交额 / 成交量（amount 元、volume 股）；缺失为 NaN，不用 (H+L+C)/3 伪造
    return _safe_ratio(p["amount"], p["volume"].where(p["volume"] > 0))


def _atom_amplitude(p):
    prev = p["close"].shift(1).replace(0, np.nan)
    return (p["high"] - p["low"]) / prev


def _atom_std(p, n):
    return p["returns"].rolling(n, min_periods=n).std()


def _atom_volume_ratio(p, n):
    return _safe_ratio(p["volume"], p["volume"].rolling(n, min_periods=n).mean())


def _atom_boll_width(p):
    upper, middle, lower = calc_bollinger(p["close"], 20, 2.0)
    return _safe_ratio(upper - lower, middle)


def _atom_macd(p):
    # MACD 柱按收盘价归一（×100），否则截面不可比
    _, _, hist = _macd_hist(p["close"])
    return hist / p["close"].replace(0, np.nan) * 100.0


def _macd_hist(close):
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=9, adjust=False).mean()
    return dif, dea, 2 * (dif - dea)


def _atom_rsi(p):
    return calc_rsi(p["close"], 14)


def _atom_kdj(p):
    k, d, j = calc_kdj(p["high"], p["low"], p["close"], 9)
    return j


def _atom_cci(p):
    return calc_cci(p["high"], p["low"], p["close"], 14)


def _atom_adx(p):
    adx, _, _ = calc_adx(p["high"], p["low"], p["close"], 14)
    return adx


def _atom_atr(p):
    from indicators import calc_atr_df
    return calc_atr_df(p["high"], p["low"], p["close"], 14) / p["close"].replace(0, np.nan) * 100.0


def _ma(close, n):
    return close.rolling(n, min_periods=n).mean()


def _atom_ma_slope(p):
    ma = _ma(p["close"], 20)
    return ma.pct_change(5)


def _atom_ema_slope(p):
    ema = calc_ema(p["close"], 20)
    return ema.pct_change(5)


def _atom_mrs(p):
    # 个股 20 日收益 − 沪深300 同期收益
    idx = p.get("index_close")
    ret20 = _ret(p["close"], 20)
    if idx is None or len(idx.dropna()) < 25:
        return ret20 * np.nan
    idx_ret = idx.pct_change(20)
    idx_ret.index = pd.to_datetime(idx_ret.index)
    idx_ret = idx_ret.reindex(ret20.index)
    return ret20.sub(idx_ret, axis=0)


def _atom_irs(p):
    # 个股 20 日收益 − 所属行业均值（行业分类为 stock_info 当前快照，存在轻微前视，展示层明示）
    from factorlab import _industry_map
    ret20 = _ret(p["close"], 20)
    imap = _industry_map()
    cols = [c for c in ret20.columns if c in imap]
    if not cols:
        return ret20 * np.nan
    sub = ret20[cols]
    ind = pd.Series([imap[c] for c in cols], index=cols)
    industry_mean = sub.T.groupby(ind).transform("mean").T
    return ret20[cols].sub(industry_mean)


def _mf_ratio(p, cols):
    panels = [p.get(c) for c in cols]
    if any(x is None for x in panels):
        return p["close"] * np.nan
    num = panels[0] + panels[1]
    denom = sum(x.abs() for x in panels)
    return num / denom.replace(0, np.nan)


def _atom_mf_change(p):
    net = _atom_net_mf(p)
    return net - net.shift(5)


def _atom_net_mf(p):
    main = p.get("mf_main")
    if main is None:
        return p["close"] * np.nan
    amount = p["amount"]
    if amount is None:
        return p["close"] * np.nan
    # main_net 单位万元，amount 单位元 → ×1e4 归一为净流入占比
    return main * 1e4 / amount.replace(0, np.nan)


def _mf_single(p, key):
    panel = p.get(key)
    amount = p.get("amount")
    if panel is None or amount is None:
        return p["close"] * np.nan
    return panel * 1e4 / amount.replace(0, np.nan)


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------

def _reg() -> dict[str, AtomSpec]:
    specs: list[AtomSpec] = []
    A = AtomSpec

    # —— 价格 ——
    for name, key in [("OPEN", "open"), ("HIGH", "high"), ("LOW", "low"), ("CLOSE", "close")]:
        specs.append(A(name, "价格", {"OPEN": "开盘价", "HIGH": "最高价",
                                      "LOW": "最低价", "CLOSE": "收盘价"}[name],
                       fn=lambda p, key=key: p[key]))
    specs.append(A("VWAP", "价格", "成交均价 = 成交额/成交量（真实 VWAP，非 (H+L+C)/3 代理）",
                   needs=("kline", "amount"), fn=_atom_vwap))

    # —— 收益 ——
    for n in (1, 3, 5, 10, 20, 60):
        specs.append(A(f"RETURN_{n}", "收益", f"近 {n} 日收益率 close/close[{n}日前] − 1",
                       window=n, fn=lambda p, n=n: _ret(p["close"], n)))

    # —— 均线 ——
    for n in (5, 10, 20, 60, 120, 250):
        specs.append(A(f"MA{n}", "均线", f"{n} 日简单均线",
                       window=n, fn=lambda p, n=n: _ma(p["close"], n)))
    for n in (5, 10, 20, 60):
        specs.append(A(f"EMA{n}", "均线", f"{n} 日指数均线",
                       window=n, fn=lambda p, n=n: calc_ema(p["close"], n)))

    # —— 成交量 ——
    specs += [
        A("VOLUME", "成交量", "成交量（股）", fn=lambda p: p["volume"]),
        A("AMOUNT", "成交量", "成交额（元）", needs=("kline", "amount"), fn=lambda p: p["amount"]),
        A("TURNOVER", "成交量", "换手率（%）", needs=("kline", "turnover"), fn=lambda p: p["turnover"]),
    ]
    for n in (5, 10, 20):
        specs.append(A(f"VOLUME_RATIO_{n}", "成交量", f"量比：今日成交量 / {n} 日均量",
                       window=n, fn=lambda p, n=n: _atom_volume_ratio(p, n)))

    # —— 波动 ——
    specs += [
        A("ATR14", "波动", "14 日 ATR / 收盘价 ×100（归一化真实波幅）", window=15, fn=_atom_atr),
        A("STD5", "波动", "5 日日收益率标准差", window=6, fn=lambda p: _atom_std(p, 5)),
        A("STD10", "波动", "10 日日收益率标准差", window=11, fn=lambda p: _atom_std(p, 10)),
        A("STD20", "波动", "20 日日收益率标准差", window=21, fn=lambda p: _atom_std(p, 20)),
        A("STD60", "波动", "60 日日收益率标准差", window=61, fn=lambda p: _atom_std(p, 60)),
        A("AMPLITUDE", "波动", "日振幅 (高−低)/昨收", window=2, fn=_atom_amplitude),
        A("BOLL_WIDTH", "波动", "布林带宽度 (上轨−下轨)/中轨（20, 2σ）", window=20, fn=_atom_boll_width),
    ]

    # —— 动量 ——
    specs += [
        A("ROC20", "动量", "20 日变动速率 close/close[20日前] − 1", window=21,
          fn=lambda p: _ret(p["close"], 20)),
        A("RSI14", "动量", "14 日 RSI（Wilder 平滑）", window=15, fn=_atom_rsi),
        A("MACD", "动量", "MACD 柱 / 收盘价 ×100（按价格归一，截面可比）", window=35, fn=_atom_macd),
        A("KDJ_K", "动量", "KDJ 指标 K 线（9,3,3）", window=9, fn=lambda p: calc_kdj(p["high"], p["low"], p["close"], 9)[0]),
        A("KDJ_D", "动量", "KDJ 指标 D 线（9,3,3）", window=9, fn=lambda p: calc_kdj(p["high"], p["low"], p["close"], 9)[1]),
        A("KDJ_J", "动量", "KDJ 指标 J 线（9,3,3）", window=9, fn=_atom_kdj),
        A("CCI14", "动量", "14 日 CCI 顺势指标（真实滚动 MAD）", window=14, fn=_atom_cci),
        A("ADX14", "动量", "14 日 ADX 趋势强度（Wilder）", window=42, fn=_atom_adx),
    ]

    # —— 趋势 ——
    specs += [
        A("MA_SLOPE20", "趋势", "MA20 的 5 日斜率（MA20.pct_change(5)）", window=25, fn=_atom_ma_slope),
        A("EMA_SLOPE20", "趋势", "EMA20 的 5 日斜率", window=25, fn=_atom_ema_slope),
        A("PRICE_MA_DISTANCE", "趋势", "收盘价偏离 MA20：close/MA20 − 1", window=20,
          fn=lambda p: _safe_ratio(p["close"], _ma(p["close"], 20)) - 1.0),
        A("MA5_MA20_DISTANCE", "趋势", "MA5/MA20 − 1（短期均线偏离）", window=20,
          fn=lambda p: _safe_ratio(_ma(p["close"], 5), _ma(p["close"], 20)) - 1.0),
        A("MA20_MA60_DISTANCE", "趋势", "MA20/MA60 − 1（中期均线偏离）", window=60,
          fn=lambda p: _safe_ratio(_ma(p["close"], 20), _ma(p["close"], 60)) - 1.0),
    ]

    # —— 相对强弱 ——
    specs += [
        A("MARKET_RELATIVE_STRENGTH", "相对强弱", "个股 20 日收益 − 沪深300 同期收益", window=21,
          needs=("kline", "index"), fn=_atom_mrs),
        A("INDUSTRY_RELATIVE_STRENGTH", "相对强弱",
          "个股 20 日收益 − 所属行业均值（行业为当前快照分类）", window=21,
          needs=("kline", "industry"), fn=_atom_irs),
    ]

    # —— 资金 ——
    specs += [
        A("NET_MONEY_FLOW", "资金", "主力净流入占比 = main_net×1e4/成交额", needs=("kline", "amount", "moneyflow"),
          fn=_atom_net_mf),
        A("LARGE_ORDER_FLOW", "资金", "大单净流入占比 = large_net×1e4/成交额", needs=("kline", "amount", "moneyflow"),
          fn=lambda p: _mf_single(p, "mf_large")),
        A("SUPER_LARGE_ORDER_FLOW", "资金", "超大单净流入占比 = super_large_net×1e4/成交额",
          needs=("kline", "amount", "moneyflow"), fn=lambda p: _mf_single(p, "mf_super")),
        A("MONEY_FLOW_RATIO", "资金",
          "大单强度 = (超大单+大单净额)/四类单净额绝对值之和 ∈ [-1,1]", needs=("kline", "moneyflow"),
          fn=lambda p: _mf_ratio(p, ("mf_super", "mf_large", "mf_medium", "mf_small"))),
        A("MONEY_FLOW_CHANGE", "资金", "主力净流入占比的 5 日变化", window=6,
          needs=("kline", "amount", "moneyflow"), fn=_atom_mf_change),
    ]
    return {s.name: s for s in specs}


ATOMS: dict[str, AtomSpec] = _reg()
ATOM_CATEGORIES = ["价格", "收益", "均线", "成交量", "波动", "动量", "趋势", "相对强弱", "资金"]


# ---------------------------------------------------------------------------
# 扩展面板：alphalab 基础面板 + amount/turnover/资金流/指数
# ---------------------------------------------------------------------------

def build_extended_panel(start: dt.date, end: dt.date) -> dict:
    """在 alphalab.build_panel（OHLCV/vwap/returns + PIT 财务）之上补充
    amount / turnover / 资金流 / 基准指数收盘。索引统一 DatetimeIndex。"""
    import alphalab
    p = alphalab.build_panel(start, end)
    if not p:
        return {}
    eng = db.get_engine()
    if eng is None:
        return p
    with eng.connect() as conn:
        try:
            kl = pd.read_sql(text(
                "SELECT trade_date, code, amount, turnover FROM stock_kline_daily "
                "WHERE trade_date BETWEEN :s AND :e"), conn, params={"s": start, "e": end})
        except Exception:
            kl = pd.DataFrame()
        try:
            mf = pd.read_sql(text(
                "SELECT trade_date, code, main_net, super_large_net, large_net, medium_net, small_net "
                "FROM stock_moneyflow WHERE trade_date BETWEEN :s AND :e"),
                conn, params={"s": start, "e": end})
        except Exception:
            mf = pd.DataFrame()
        try:
            idx = pd.read_sql(text(
                "SELECT trade_date, close FROM index_kline_daily WHERE code='000300' "
                "AND trade_date BETWEEN :s AND :e ORDER BY trade_date"),
                conn, params={"s": start, "e": end})
        except Exception:
            idx = pd.DataFrame()

    idx_dt = p["close"].index

    def _pivot(df: pd.DataFrame, col: str) -> pd.DataFrame | None:
        if df.empty or col not in df.columns:
            return None
        m = df.pivot_table(index="trade_date", columns="code", values=col, aggfunc="last")
        m.index = pd.DatetimeIndex(pd.to_datetime(m.index))
        return m.reindex(idx_dt).sort_index()

    if not kl.empty:
        for c in ("amount", "turnover"):
            kl[c] = pd.to_numeric(kl[c], errors="coerce")
        p["amount"] = _pivot(kl, "amount")
        p["turnover"] = _pivot(kl, "turnover")
    for col, key in [("main_net", "mf_main"), ("super_large_net", "mf_super"),
                     ("large_net", "mf_large"), ("medium_net", "mf_medium"),
                     ("small_net", "mf_small")]:
        mf_col = _pivot(mf, col)
        if mf_col is not None:
            p[key] = mf_col.astype(float)
    if not idx.empty:
        s = pd.Series(idx["close"].astype(float).values,
                      index=pd.DatetimeIndex(pd.to_datetime(idx["trade_date"])))
        p["index_close"] = s.reindex(idx_dt)
    return p


def restrict_panel(panel: dict, codes: list[str]) -> dict:
    """把面板矩阵裁剪到宇宙列（挖掘的性能关键：原子只算宇宙内的股票）。"""
    out = {}
    for k, v in panel.items():
        if isinstance(v, pd.DataFrame):
            cols = [c for c in codes if c in v.columns]
            out[k] = v[cols] if cols else v.iloc[:, :0]
        else:
            out[k] = v
    return out


def compute_atom(name: str, panel: dict) -> pd.DataFrame:
    spec = ATOMS.get(name)
    if spec is None or spec.fn is None:
        raise KeyError(f"unknown atom: {name}")
    out = spec.fn(panel)
    if not isinstance(out, pd.DataFrame):
        raise ValueError(f"atom {name} did not return a panel matrix")
    return out.replace([np.inf, -np.inf], np.nan)


# ---------------------------------------------------------------------------
# 数据可得性探查（GET /api/factormine/atoms 用）
# ---------------------------------------------------------------------------

def availability() -> dict:
    """探查各数据能力的实际覆盖，返回 {capability: {...}, atoms: {name: status}}。"""
    eng = db.get_engine()
    caps: dict[str, dict] = {}
    probe = {
        "kline": ("SELECT COUNT(*) AS n, MAX(trade_date) AS mx, MIN(trade_date) AS mn "
                  "FROM stock_kline_daily", "n", "mn", "mx"),
        "amount": ("SELECT COUNT(*) AS n, MAX(trade_date) AS mx, MIN(trade_date) AS mn "
                   "FROM stock_kline_daily WHERE amount IS NOT NULL AND amount > 0", "n", "mn", "mx"),
        "turnover": ("SELECT COUNT(*) AS n, MAX(trade_date) AS mx, MIN(trade_date) AS mn "
                     "FROM stock_kline_daily WHERE turnover IS NOT NULL AND turnover > 0", "n", "mn", "mx"),
        "moneyflow": ("SELECT COUNT(*) AS n, MAX(trade_date) AS mx, MIN(trade_date) AS mn "
                      "FROM stock_moneyflow", "n", "mn", "mx"),
        "index": ("SELECT COUNT(*) AS n, MAX(trade_date) AS mx, MIN(trade_date) AS mn "
                  "FROM index_kline_daily WHERE code='000300'", "n", "mn", "mx"),
        "industry": ("SELECT COUNT(*) AS n, NULL AS mn, NULL AS mx FROM stock_info "
                     "WHERE industry IS NOT NULL AND industry != ''", "n", "mn", "mx"),
    }
    if eng is not None:
        with eng.connect() as conn:
            for cap, (sql, n_c, mn_c, mx_c) in probe.items():
                try:
                    row = conn.execute(text(sql)).mappings().first()
                    caps[cap] = {
                        "rows": int(row[n_c] or 0),
                        "from": str(row[mn_c]) if row[mn_c] else None,
                        "to": str(row[mx_c]) if row[mx_c] else None,
                        "ok": bool(row[n_c]),
                    }
                except Exception:
                    caps[cap] = {"rows": 0, "from": None, "to": None, "ok": False}
    else:
        caps = {c: {"rows": 0, "from": None, "to": None, "ok": False} for c in probe}

    atom_status: dict[str, dict] = {}
    for name, spec in ATOMS.items():
        missing = [c for c in spec.needs if not caps.get(c, {}).get("ok")]
        if missing:
            status = "unsupported"
        elif any(caps[c]["rows"] < 100 for c in spec.needs):
            status = "limited"
        else:
            status = "ok"
        atom_status[name] = {"status": status, "missing": missing,
                             "coverage": {c: caps[c] for c in spec.needs}}
    return {"capabilities": caps, "atoms": atom_status}
