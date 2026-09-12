# -*- coding: utf-8 -*-
"""Prediction calibration: turn the sigmoid "probability" into a historically
calibrated one.

Skill 规范第 4/5 条：评分 ≠ 概率。predictor.py 的 probability_up 只是
composite 的 sigmoid 变换，从未与真实胜率对照。本模块在历史 K 线上回放
composite 信号，按分桶统计 T+1/3/5/10 的真实上涨概率与平均收益，
让「看多 68%」变成「历史上 312 个相似信号中 61.3% 在 T+5 上涨」。

缓存：按 (date, buckets) 缓存校准表（当日全市场共享一张表，盘后失效）。
"""
from __future__ import annotations
import datetime as dt
import time

import numpy as np
import pandas as pd
from sqlalchemy import text

import db
from core.trace import logger

HORIZONS = (1, 3, 5, 10)
N_BUCKETS = 10
MIN_SAMPLES_PER_BUCKET = 30
SAMPLE_UNIVERSE = 120   # 校准样本股票数（按成交额取头部，控制回放耗时）
LOOKBACK_DAYS = 500     # 回放窗口

_CAL_CACHE: dict = {}
_CAL_TS = 0.0
_CAL_TTL = 3600.0


def _sample_codes(lookback_end: dt.date) -> list[str]:
    eng = db.get_engine()
    if eng is None:
        return []
    with eng.connect() as conn:
        # legacy upsert 未写 amount 列 — 用 volume×close 近似成交额
        rows = conn.execute(text(
            "SELECT code, AVG(volume * close) AS amt FROM stock_kline_daily "
            "WHERE trade_date >= :s AND trade_date <= :e "
            "AND volume IS NOT NULL AND close IS NOT NULL "
            "GROUP BY code ORDER BY amt DESC LIMIT :n"
        ), {"s": lookback_end - dt.timedelta(days=90), "e": lookback_end,
            "n": SAMPLE_UNIVERSE}).fetchall()
    return [r[0] for r in rows]


def _load_panel(codes: list[str], start: dt.date, end: dt.date) -> dict[str, pd.DataFrame]:
    eng = db.get_engine()
    if eng is None or not codes:
        return {}
    in_list = ",".join(f"'{c}'" for c in codes)
    with eng.connect() as conn:
        df = pd.read_sql(text(
            f"SELECT code, trade_date, open, close, high, low, volume "
            f"FROM stock_kline_daily WHERE code IN ({in_list}) "
            f"AND trade_date BETWEEN :s AND :e ORDER BY code, trade_date"
        ), conn, params={"s": start, "e": end})
    if df.empty:
        return {}
    out = {}
    for code, g in df.groupby("code"):
        g = g.sort_values("trade_date").rename(columns={
            "trade_date": "日期", "open": "开盘", "close": "收盘",
            "high": "最高", "low": "最低", "volume": "成交量"})
        out[str(code)] = g.reset_index(drop=True)
    return out


def _replay_composite(panel: dict[str, pd.DataFrame], horizons) -> pd.DataFrame:
    """逐股逐日回放 composite（复用 predictor 维度但只用价量，跳过资金/北向维度）。"""
    from predictor import (_calc_multi_horizon_momentum, _calc_technical_momentum,
                           _calc_trend_structure, _calc_volume_price,
                           _calc_mean_reversion, _calc_volatility_regime,
                           _calc_pattern_signal)
    REWEIGHT_SUM = 0.20 + 0.15 + 0.18 + 0.12 + 0.08 + 0.09 + 0.05   # 7 个价量维度
    rows = []
    for code, df in panel.items():
        n = len(df)
        closes = df["收盘"].astype(float).to_numpy()
        # 每 3 个交易日采样一次回放点（加速；样本足够）
        for i in range(60, n - max(horizons) - 1, 3):
            sub = df.iloc[:i + 1]
            try:
                dims = [
                    _calc_multi_horizon_momentum(sub),
                    _calc_technical_momentum(sub),
                    _calc_trend_structure(sub),
                    _calc_volume_price(sub),
                    _calc_mean_reversion(sub),
                    _calc_volatility_regime(sub),
                    _calc_pattern_signal(sub),
                ]
                w = {"multi_momentum": .20, "technical_momentum": .15,
                     "trend_structure": .18, "volume_price": .12,
                     "mean_reversion": .08, "volatility_regime": .09,
                     "pattern": .05}
                comp = sum(d.score * w.get(d.name_en, 0) for d in dims) / REWEIGHT_SUM
            except Exception:
                continue
            base = closes[i]
            if not base or base <= 0:
                continue
            row = {"composite": comp}
            for h in horizons:
                fwd = closes[i + h] / base - 1 if i + h < n else np.nan
                row[f"fwd_{h}"] = fwd
            rows.append(row)
    return pd.DataFrame(rows)


def _calibration_table(df: pd.DataFrame, horizons) -> list[dict]:
    if df.empty or len(df) < 100:
        return []
    df = df.copy()
    df["bucket"] = pd.qcut(df["composite"], q=N_BUCKETS, labels=False, duplicates="drop")
    out = []
    for b, g in df.groupby("bucket"):
        entry = {
            "bucket": int(b),
            "lo": round(float(g["composite"].min()), 3),
            "hi": round(float(g["composite"].max()), 3),
            "n": int(len(g)),
        }
        for h in horizons:
            fwd = g[f"fwd_{h}"].dropna()
            entry[f"win_{h}"] = round(float((fwd > 0).mean()), 4) if len(fwd) else None
            entry[f"avg_{h}"] = round(float(fwd.mean()), 4) if len(fwd) else None
        out.append(entry)
    return out


def get_calibration(today: dt.date | None = None) -> dict:
    """当日全市场共享的校准表（带缓存）。"""
    global _CAL_CACHE, _CAL_TS
    today = today or dt.date.today()
    now = time.time()
    if _CAL_CACHE and now - _CAL_TS < _CAL_TTL:
        return _CAL_CACHE
    try:
        codes = _sample_codes(today)
        if not codes:
            return {}
        panel = _load_panel(codes, today - dt.timedelta(days=LOOKBACK_DAYS), today)
        if not panel:
            return {}
        df = _replay_composite(panel, HORIZONS)
        table = _calibration_table(df, HORIZONS)
        if not table:
            return {}
        result = {
            "date": today.isoformat(),
            "universe": len(codes),
            "replay_rows": int(len(df)),
            "buckets": table,
        }
        _CAL_CACHE, _CAL_TS = result, now
        return result
    except Exception as e:
        logger.warning("[calibration] failed: %s", e)
        return {}


def calibrate(composite: float, horizon: int = 5) -> dict | None:
    """把 composite 映射到历史同桶的真实表现。样本不足时返回 None（调用方回退）。"""
    cal = get_calibration()
    if not cal:
        return None
    for b in cal["buckets"]:
        if b["lo"] <= composite <= b["hi"]:
            n = b.get("n", 0)
            win = b.get(f"win_{horizon}")
            avg = b.get(f"avg_{horizon}")
            if win is None or n < MIN_SAMPLES_PER_BUCKET:
                return {"insufficient": True, "n": n,
                        "bucket": [b["lo"], b["hi"]],
                        "cal_date": cal["date"]}
            return {
                "insufficient": False,
                "win_rate": win,
                "avg_return": avg,
                "n": n,
                "bucket": [b["lo"], b["hi"]],
                "cal_date": cal["date"],
                "universe": cal["universe"],
            }
    return None
