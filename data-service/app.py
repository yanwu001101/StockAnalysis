"""Flask data service - Eastmoney push2 + asyncio + Redis-cached."""
from __future__ import annotations
import datetime as dt
import math
import re
import time
import traceback

import akshare as ak
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

import cache
import eastmoney
import kline_repo
import scheduler
from strategies import (
    score_macd_ma, score_multi_factor, score_momentum_breakout,
    score_rsi_rebound, score_bollinger_squeeze, score_chip_concentration,
    score_dividend_stability, score_northbound_flow, score_sector_rotation,
    score_kdj_rsi_resonance,
)

app = Flask(__name__)
CORS(app)

# Start background scheduler (warmup + periodic refresh). 1-worker gunicorn keeps it singleton.
try:
    scheduler.start()
except Exception as _e:
    print(f'[data-service] scheduler.start failed: {_e}')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def retry_call(func, *args, retries=3, wait=2.0, **kwargs):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(wait * attempt)
    raise last_err or RuntimeError("API call failed")


def normalize_code(code) -> str:
    text = str(code).strip()
    digits = re.sub(r"\D", "", text)
    return digits.zfill(6)[-6:]


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce",
    )


def first_existing(columns, candidates):
    available = set(columns)
    for c in candidates:
        if c in available:
            return c
    return None


# ---------------------------------------------------------------------------
# Data fetching (Redis-backed, see cache.py)
# ---------------------------------------------------------------------------


def cached(key: str, ttl: int, fetcher):
    return cache.get_or_fetch(key, ttl, fetcher)


SPOT_MIN_ROWS = 4000

def fetch_spot() -> pd.DataFrame:
    def _fetch():
        print("[data-service] Fetching market spot (eastmoney push2)...")
        try:
            df = eastmoney.fetch_all_spot()
            n = 0 if df is None else len(df)
            if df is not None and "代码" in df.columns and n >= SPOT_MIN_ROWS:
                df["代码"] = df["代码"].map(normalize_code)
                if "涨跌幅" in df.columns:
                    df["涨跌幅"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
                return df
            print(f"[data-service] eastmoney spot incomplete ({n} rows); falling back to akshare")
        except Exception as e:
            print(f"[data-service] eastmoney spot failed, fallback to akshare: {e}")
        try:
            df = retry_call(ak.stock_zh_a_spot_em, retries=2, wait=2)
        except Exception:
            df = retry_call(ak.stock_zh_a_spot, retries=2, wait=2)
        df = df.copy()
        code_col = first_existing(df.columns, ["代码", "证券代码"])
        name_col = first_existing(df.columns, ["名称", "证券简称"])
        industry_col = first_existing(df.columns, ["行业", "所属行业", "板块名称"])
        price_col = first_existing(df.columns, ["最新价", "收盘"])
        cap_col = first_existing(df.columns, ["总市值"])
        change_col = first_existing(df.columns, ["涨跌幅"])
        keep = [code_col, name_col]
        rename = {code_col: "代码", name_col: "名称"}
        if industry_col: keep.append(industry_col); rename[industry_col] = "行业"
        if price_col: keep.append(price_col); rename[price_col] = "最新价"
        if cap_col: keep.append(cap_col); rename[cap_col] = "总市值"
        if change_col: keep.append(change_col); rename[change_col] = "涨跌幅"
        out = df[keep].copy().rename(columns=rename)
        out["代码"] = out["代码"].map(normalize_code)
        if "总市值" in out:
            out["总市值_亿"] = to_number(out["总市值"]) / 100_000_000
        if "涨跌幅" in out:
            out["涨跌幅"] = to_number(out["涨跌幅"])
        return out
    return cached("spot", 300, _fetch)


def report_dates(quarters=10) -> list:
    today = dt.date.today()
    dates = []
    for year in range(today.year, today.year - 4, -1):
        for suffix in ("1231", "0930", "0630", "0331"):
            text = f"{year}{suffix}"
            report_day = dt.datetime.strptime(text, "%Y%m%d").date()
            if report_day <= today:
                dates.append(text)
    return dates[:quarters]


def fetch_financial() -> pd.DataFrame:
    def _fetch():
        print("[data-service] Fetching financial data...")
        dates = report_dates()

        yjbb, yjbb_date = None, None
        for date in dates:
            try:
                df = retry_call(ak.stock_yjbb_em, date=date, retries=2, wait=1)
                if df is not None and len(df) >= 1000:
                    yjbb, yjbb_date = df.copy(), date
                    break
            except Exception:
                continue

        zcfz, zcfz_date = None, None
        for date in dates:
            try:
                df = retry_call(ak.stock_zcfz_em, date=date, retries=2, wait=1)
                if df is not None and len(df) >= 1000:
                    zcfz, zcfz_date = df.copy(), date
                    break
            except Exception:
                continue

        if yjbb is None or zcfz is None:
            return pd.DataFrame()

        for df in (yjbb, zcfz):
            code_col = first_existing(df.columns, ["股票代码", "代码"])
            if code_col:
                df["代码"] = df[code_col].map(normalize_code)

        result = yjbb[["代码"]].copy()

        # ROE annualization
        report_month = int(yjbb_date[4:6])
        factor = 12.0 / report_month if report_month in [3, 6, 9, 12] else 1.0
        raw_roe = to_number(yjbb["净资产收益率"])
        result["净资产收益率_原始"] = raw_roe
        result["净资产收益率"] = raw_roe * factor

        growth_map = {
            "营收同比增长率": ["营业总收入-同比增长", "营业总收入同比增长率"],
            "净利润同比增长率": ["净利润-同比增长", "净利润同比增长率"],
            "销售毛利率": ["销售毛利率"],
        }
        for target, candidates in growth_map.items():
            src = first_existing(yjbb.columns, candidates)
            result[target] = to_number(yjbb[src]) if src else math.nan

        cash_col = first_existing(yjbb.columns, ["每股经营现金流量", "每股经营现金流"])
        result["经营现金流"] = to_number(yjbb[cash_col]) if cash_col else math.nan

        zcfz_result = zcfz[["代码"]].copy()
        zcfz_result["资产负债率"] = to_number(zcfz["资产负债率"])

        merged = result.drop_duplicates("代码").merge(
            zcfz_result.drop_duplicates("代码"), on="代码", how="left")
        return merged

    return cached("financial", 600, _fetch)


def fetch_stock_daily(code: str, days: int = 250, adjust: str = "qfq") -> pd.DataFrame:
    # Persisted kline_repo only holds front-adjusted data; for hfq / none we
    # always go straight to the source with a separate cache key.
    if adjust == "qfq":
        key = f"daily:{code}:{days}"
        def _fetch():
            try:
                df = kline_repo.get_daily(code, days)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                print(f"[data-service] kline_repo daily {code} failed: {e}")
            try:
                end = dt.date.today()
                start = end - dt.timedelta(days=int(days * 1.5))
                df = ak.stock_zh_a_hist(
                    symbol=code, period="daily",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="qfq")
                return df.tail(days) if df is not None and not df.empty else pd.DataFrame()
            except Exception:
                return pd.DataFrame()
        return cached(key, 120, _fetch)

    ak_adjust = "" if adjust == "none" else adjust  # "" = un-adjusted in akshare
    key = f"daily:{code}:{days}:{adjust}"
    def _fetch():
        try:
            end = dt.date.today()
            start = end - dt.timedelta(days=int(days * 1.5))
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust=ak_adjust)
            return df.tail(days) if df is not None and not df.empty else pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    return cached(key, 300, _fetch)


def fetch_stock_weekly(code: str, days: int = 900, adjust: str = "qfq") -> pd.DataFrame:
    if adjust == "qfq":
        key = f"weekly:{code}:{days}"
        def _fetch():
            weeks = max(int(days / 7) + 4, 60)
            try:
                df = kline_repo.get_weekly(code, weeks)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                print(f"[data-service] kline_repo weekly {code} failed: {e}")
            try:
                end = dt.date.today()
                start = end - dt.timedelta(days=days)
                df = ak.stock_zh_a_hist(
                    symbol=code, period="weekly",
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                    adjust="qfq")
                return df if df is not None else pd.DataFrame()
            except Exception:
                return pd.DataFrame()
        return cached(key, 300, _fetch)

    ak_adjust = "" if adjust == "none" else adjust
    key = f"weekly:{code}:{days}:{adjust}"
    def _fetch():
        try:
            end = dt.date.today()
            start = end - dt.timedelta(days=days)
            df = ak.stock_zh_a_hist(
                symbol=code, period="weekly",
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
                adjust=ak_adjust)
            return df if df is not None else pd.DataFrame()
        except Exception:
            return pd.DataFrame()
    return cached(key, 600, _fetch)


def fetch_weekly_trend(code: str) -> dict:
    df = fetch_stock_weekly(code)
    if df is None or df.empty or "收盘" not in df:
        return {"周线收盘": None, "周线MA60": None, "MA60之上": False}
    close = to_number(df["收盘"])
    if len(close) < 60:
        return {"周线收盘": float(close.iloc[-1]), "周线MA60": None, "MA60之上": False}
    ma60 = close.rolling(60).mean()
    latest_close = float(close.iloc[-1])
    latest_ma60 = float(ma60.iloc[-1])
    return {
        "周线收盘": round(latest_close, 3),
        "周线MA60": round(latest_ma60, 3),
        "MA60之上": bool(pd.notna(latest_close) and pd.notna(latest_ma60) and latest_close >= latest_ma60),
    }


def compute_weekly_trend(df: pd.DataFrame) -> dict:
    # MA60 trend from pre-fetched weekly DataFrame.
    if df is None or df.empty or "收盘" not in df:
        return {"周线收盘": None, "周线MA60": None, "MA60之上": False}
    close = to_number(df["收盘"])
    if len(close) < 60:
        last = float(close.iloc[-1]) if len(close) else None
        return {"周线收盘": last, "周线MA60": None, "MA60之上": False}
    ma60 = close.rolling(60).mean()
    latest_close = float(close.iloc[-1])
    latest_ma60 = float(ma60.iloc[-1])
    return {
        "周线收盘": round(latest_close, 3),
        "周线MA60": round(latest_ma60, 3),
        "MA60之上": bool(pd.notna(latest_close) and pd.notna(latest_ma60) and latest_close >= latest_ma60),
    }


# ---------------------------------------------------------------------------
# Policy keywords (from existing stock_screener.py)
# ---------------------------------------------------------------------------

POLICY_KEYWORDS = {
    "新质生产力": ("半导体", "芯片", "人工智能", "AI", "算力", "机器人", "工业互联网",
                "高端装备", "航空", "军工", "新能源", "电池", "光伏", "储能", "软件", "通信"),
    "央国企改革": ("银行", "证券", "保险", "电力", "石油", "煤炭", "建筑",
                "交运", "铁路", "港口", "公用事业", "运营商", "中字头"),
    "内需消费升级": ("白酒", "食品", "饮料", "家电", "医药", "医疗",
                  "旅游", "酒店", "免税", "零售", "消费", "汽车"),
}


def policy_bucket(name: str, industry: str) -> tuple:
    text = f"{name} {industry}"
    buckets = []
    for bucket, keywords in POLICY_KEYWORDS.items():
        if any(kw.lower() in text.lower() for kw in keywords):
            buckets.append(bucket)
    return ("、".join(buckets) if buckets else "未命中", min(len(buckets), 2) * 6)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/market/summary")
def market_summary():
    try:
        spot = fetch_spot()
        financial = fetch_financial()
        merged = spot.merge(financial, on="代码", how="left")

        change_col = "涨跌幅" if "涨跌幅" in merged.columns else None
        if change_col:
            chg = pd.to_numeric(merged[change_col], errors="coerce")
            up = int((chg > 0).sum())
            down = int((chg < 0).sum())
            flat = int((chg == 0).sum())
            avg_change = round(float(chg.mean()), 2)
            # A-share daily limit: 主板 ±10% (历史允许 9.95+ 即涨停), 创业/科创 ±20%
            code_series = merged["代码"].astype(str)
            is_chinext = code_series.str.startswith(("30", "68"))
            up_limit = int(((chg >= 19.5) & is_chinext).sum() + ((chg >= 9.7) & ~is_chinext).sum())
            down_limit = int(((chg <= -19.5) & is_chinext).sum() + ((chg <= -9.7) & ~is_chinext).sum())
        else:
            up = down = flat = up_limit = down_limit = 0
            avg_change = 0

        # Top gainers
        if change_col:
            top = merged.nlargest(10, change_col)
            top_list = []
            for _, r in top.iterrows():
                top_list.append({
                    "code": str(r.get("代码", "")),
                    "name": str(r.get("名称", "")),
                    "industry": str(r.get("行业", "")),
                    "price": float(r.get("最新价", 0) or 0),
                    "changePercent": round(float(r.get(change_col, 0) or 0), 2),
                    "marketCap": round(float(r.get("总市值_亿", 0) or 0), 0),
                })
        else:
            top_list = []

        # Hot sectors
        hot_sectors = []
        if "行业" in merged.columns and change_col:
            df_sec = merged[merged["行业"].astype(str).str.strip().replace("-", pd.NA).notna()]
            df_sec = df_sec[pd.to_numeric(df_sec[change_col], errors="coerce").notna()]
            sector_avg = df_sec.groupby("行业")[change_col].mean().sort_values(ascending=False).dropna()
            for name, chg_v in sector_avg.head(5).items():
                hot_sectors.append({"name": str(name), "change": round(float(chg_v), 2), "flow": 0, "momentum": 0, "rank": 0})

        return jsonify({
            "totalStocks": len(spot),
            "upCount": up,
            "downCount": down,
            "flatCount": flat,
            "upLimit": up_limit,
            "downLimit": down_limit,
            "avgChange": avg_change,
            "northboundFlow": 0,
            "topGainers": top_list,
            "topLosers": [],
            "hotSectors": hot_sectors,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/market/top-stocks")
def top_stocks():
    try:
        limit = int(request.args.get("limit", 20))
        spot = fetch_spot()
        financial = fetch_financial()
        merged = spot.merge(financial, on="代码", how="left")

        # Pre-score everyone (sync)
        prelim = []
        for _, row in merged.iterrows():
            if pd.isna(row.get("净资产收益率")):
                continue
            mf = score_multi_factor(row=row)
            _, policy_score = policy_bucket(str(row.get("名称", "")), str(row.get("行业", "")))
            prelim.append((row, mf["score"] + policy_score))

        # Batch-fetch weekly via MySQL-first repo (hits cache for warmed-up codes)
        codes_need_trend = [str(r["代码"]) for r, b in prelim if b >= 50]
        weekly_map: dict = {}
        if codes_need_trend:
            try:
                weekly_map = kline_repo.batch_get_weekly(codes_need_trend, weeks=200)
            except Exception as e:
                print(f"[data-service] batch_get_weekly failed: {e}")

        results = []
        for row, total in prelim:
            code = str(row.get("代码", ""))
            wk_df = weekly_map.get(code)
            if wk_df is not None:
                trend = compute_weekly_trend(wk_df)
                if trend.get("MA60之上"):
                    total += 12
                elif trend.get("周线MA60") is not None:
                    total -= 5

            results.append({
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "industry": str(row.get("行业", "")),
                "price": round(float(row.get("最新价", 0) or 0), 2),
                "changePercent": round(float(row.get("涨跌幅", 0) or 0), 2),
                "marketCap": round(float(row.get("总市值_亿", 0) or 0), 0),
                "compositeScore": min(total, 100),
                "signal": "bullish" if total >= 70 else "bearish" if total <= 30 else "neutral",
                "roe": round(float(row.get("净资产收益率", 0) or 0), 2),
                "debtRatio": round(float(row.get("资产负债率", 0) or 0), 2),
            })

        results.sort(key=lambda x: x["compositeScore"], reverse=True)
        return jsonify(results[:limit])
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/stock/<code>")
def stock_detail(code):
    try:
        code = normalize_code(code)
        spot = fetch_spot()
        financial = fetch_financial()
        row = spot[spot["代码"] == code]
        fin = financial[financial["代码"] == code]

        if row.empty:
            try:
                single = eastmoney.fetch_single_quote(code)
                if single is not None and not single.empty:
                    row = single
            except Exception as _e:
                print(f"[data-service] single quote {code} failed: {_e}")

        if row.empty:
            return jsonify({"error": "Stock not found"}), 404

        r = row.iloc[0]

        # Some fundamental fields (e.g. 销售毛利率 for bank stocks) come back
        # as NaN, which Python passes through round() unchanged and `or 0`
        # cannot guard against (bool(NaN) is True). JSON spec forbids NaN,
        # so the downstream Java parser then 500s on what looks like fine data.
        def safe_round(v, digits=2):
            try:
                x = float(v) if v is not None else None
            except (TypeError, ValueError):
                return None
            if x is None or x != x:  # NaN check
                return None
            return round(x, digits)

        result = {
            "code": code,
            "name": str(r.get("名称", "")),
            "industry": str(r.get("行业", "")),
            "price": safe_round(r.get("最新价"), 2) or 0,
            "changePercent": safe_round(r.get("涨跌幅"), 2) or 0,
            "marketCap": safe_round(r.get("总市值_亿"), 0) or 0,
        }

        if not fin.empty:
            f = fin.iloc[0]
            result.update({
                "roe": safe_round(f.get("净资产收益率"), 2),
                "rawRoe": safe_round(f.get("净资产收益率_原始"), 2),
                "debtRatio": safe_round(f.get("资产负债率"), 2),
                "cashFlowPerShare": safe_round(f.get("经营现金流"), 4),
                "revenueGrowth": safe_round(f.get("营收同比增长率"), 2),
                "profitGrowth": safe_round(f.get("净利润同比增长率"), 2),
                "grossMargin": safe_round(f.get("销售毛利率"), 2),
            })

        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/stock/<code>/kline")
def stock_kline(code):
    try:
        code = normalize_code(code)
        period = request.args.get("period", "daily")
        days = int(request.args.get("days", 250))
        adjust = request.args.get("adjust", "qfq")
        if adjust not in ("qfq", "hfq", "none"):
            adjust = "qfq"

        df = fetch_stock_daily(code, days, adjust) if period == "daily" \
            else fetch_stock_weekly(code, days, adjust)
        if df is None or df.empty:
            return jsonify([])

        result = []
        for _, row in df.iterrows():
            result.append({
                "date": str(row.get("日期", row.name)),
                "open": float(row.get("开盘", 0) or 0),
                "close": float(row.get("收盘", 0) or 0),
                "high": float(row.get("最高", 0) or 0),
                "low": float(row.get("最低", 0) or 0),
                "volume": float(row.get("成交量", 0) or 0),
            })
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/stock/<code>/strategies")
def stock_strategies(code):
    try:
        code = normalize_code(code)
        spot = fetch_spot()
        financial = fetch_financial()
        daily = fetch_stock_daily(code, 250)

        row = spot[spot["代码"] == code]
        fin = financial[financial["代码"] == code]
        merged_row = None
        if not row.empty and not fin.empty:
            merged_row = pd.concat([row.iloc[0], fin.iloc[0]])
        elif not fin.empty:
            merged_row = fin.iloc[0]

        kwargs = {"daily_df": daily, "code": code}

        strategies = {
            "macd_ma": score_macd_ma(daily_df=daily),
            "multi_factor": score_multi_factor(row=merged_row) if merged_row is not None else {"score": 0, "signal": "neutral", "details": {}},
            "momentum_breakout": score_momentum_breakout(daily_df=daily),
            "rsi_rebound": score_rsi_rebound(daily_df=daily),
            "bollinger_squeeze": score_bollinger_squeeze(daily_df=daily),
            "chip_concentration": score_chip_concentration(daily_df=daily),
            "dividend_stability": score_dividend_stability(daily_df=daily, price=float(row.iloc[0].get("最新价", 0) or 0) if not row.empty else 0),
            "northbound_flow": score_northbound_flow(code=code),
            "sector_rotation": score_sector_rotation(industry=str(row.iloc[0].get("行业", "")) if not row.empty else ""),
            "kdj_rsi_resonance": score_kdj_rsi_resonance(daily_df=daily),
        }

        # Add weekly trend bonus
        try:
            trend = fetch_weekly_trend(code)
            if trend.get("MA60之上"):
                strategies["macd_ma"]["score"] = min(strategies["macd_ma"]["score"] + 12, 100)
        except Exception:
            pass

        # Add policy bonus
        if not row.empty:
            _, policy_score = policy_bucket(str(row.iloc[0].get("名称", "")), str(row.iloc[0].get("行业", "")))
            strategies["multi_factor"]["score"] = min(strategies["multi_factor"]["score"] + policy_score, 100)

        # Composite score
        weights = {
            "multi_factor": 0.25, "macd_ma": 0.12, "momentum_breakout": 0.10,
            "rsi_rebound": 0.08, "bollinger_squeeze": 0.08, "chip_concentration": 0.10,
            "dividend_stability": 0.08, "northbound_flow": 0.07, "sector_rotation": 0.07,
            "kdj_rsi_resonance": 0.05,
        }
        total = sum(strategies[k]["score"] * weights.get(k, 0) for k in strategies)
        total = round(min(total, 100))

        signal = "bullish" if total >= 70 else "bearish" if total <= 30 else "neutral"

        return jsonify({"total": total, "signal": signal, "strategies": strategies})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/screen", methods=["POST"])
def screen():
    try:
        body = request.get_json(force=True)
        strategies_cfg = body.get("strategies", {})
        filters = body.get("filters", {})
        limit = body.get("limit", 80)

        min_score = filters.get("minScore", 50)
        min_cap = filters.get("minMarketCap", 100)
        max_debt = filters.get("maxDebtRatio", 60)
        min_roe = filters.get("minRoe", 10)

        spot = fetch_spot()
        financial = fetch_financial()
        merged = spot.merge(financial, on="代码", how="left")

        # Hard filters
        mask = pd.Series(True, index=merged.index)
        if "净资产收益率" in merged.columns:
            mask &= merged["净资产收益率"].notna() & (merged["净资产收益率"] >= min_roe)
        if "资产负债率" in merged.columns:
            mask &= merged["资产负债率"].notna() & (merged["资产负债率"] <= max_debt)
        if "总市值_亿" in merged.columns:
            cap_mask = merged["总市值_亿"].notna() & (merged["总市值_亿"] >= min_cap)
            cap_mask |= merged["总市值_亿"].isna()
            mask &= cap_mask

        filtered = merged[mask].copy()
        sort_cols = [c for c in ["总市值_亿", "净资产收益率"] if c in filtered.columns]
        if sort_cols:
            filtered = filtered.sort_values(sort_cols, ascending=False)
        candidates = filtered.head(max(limit * 2, 50)).copy()

        # Score candidates
        results = []
        for _, row in candidates.iterrows():
            mf = score_multi_factor(row=row)
            policy, policy_score = policy_bucket(str(row.get("名称", "")), str(row.get("行业", "")))
            total = mf["score"] + policy_score

            if total < min_score:
                continue

            results.append({
                "code": str(row.get("代码", "")),
                "name": str(row.get("名称", "")),
                "industry": str(row.get("行业", "")),
                "price": round(float(row.get("最新价", 0) or 0), 2),
                "changePercent": round(float(row.get("涨跌幅", 0) or 0), 2),
                "marketCap": round(float(row.get("总市值_亿", 0) or 0), 0),
                "compositeScore": min(total, 100),
                "signal": "bullish" if total >= 70 else "bearish" if total <= 30 else "neutral",
                "roe": round(float(row.get("净资产收益率", 0) or 0), 2),
                "debtRatio": round(float(row.get("资产负债率", 0) or 0), 2),
            })

        results.sort(key=lambda x: x["compositeScore"], reverse=True)
        return jsonify(results[:limit])
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/market/sector-rotation")
def sector_rotation():
    try:
        spot = fetch_spot()
        if "行业" not in spot.columns or "涨跌幅" not in spot.columns:
            return jsonify([])

        df = spot[spot["行业"].astype(str).str.strip().replace("-", pd.NA).notna()]
        df = df[pd.to_numeric(df["涨跌幅"], errors="coerce").notna()]

        sector_avg = df.groupby("行业").agg(
            avg_change=("涨跌幅", "mean"),
            count=("代码", "count"),
        ).sort_values("avg_change", ascending=False)
        sector_avg = sector_avg[sector_avg["avg_change"].notna()]

        result = []
        for i, (name, row) in enumerate(sector_avg.iterrows()):
            result.append({
                "name": str(name),
                "change": round(float(row["avg_change"]), 2),
                "flow": 0,
                "momentum": 0,
                "rank": i + 1,
            })
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/market/northbound-flow")
def northbound_flow():
    try:
        days = int(request.args.get("days", 30))
        # Placeholder - northbound flow data
        return jsonify([])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# New market endpoints (Phase B): indices, gainers, losers, most-active
# ---------------------------------------------------------------------------

_INDEX_LABELS = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000300": "沪深300",
    "000688": "科创50",
    "000016": "上证50",
    "000905": "中证500",
}


@app.route("/api/market/indices")
def market_indices():
    """Realtime quotes for major A-share indices."""
    try:
        import akshare as ak
        # Sina is more stable than EM for this query right now. Hit it first
        # without going through retry_call to avoid kwarg shadowing.
        df = None
        try:
            df = ak.stock_zh_index_spot_sina()
        except Exception:
            df = None
        if df is None or df.empty:
            try:
                df = ak.stock_zh_index_spot_em(symbol="上证系列指数")
            except Exception:
                df = None
        if df is None or df.empty:
            return jsonify([])

        # Normalise column names — akshare keeps changing them
        rename = {
            "代码": "code", "名称": "name", "最新价": "price",
            "涨跌幅": "changePercent", "涨跌额": "change",
            "成交额": "amount", "成交量": "volume",
            "最高": "high", "最低": "low", "今开": "open", "昨收": "prevClose",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        if "code" not in df.columns:
            return jsonify([])
        df["code"] = df["code"].astype(str).str.replace("sh", "", regex=False).str.replace("sz", "", regex=False).str.zfill(6)
        df = df[df["code"].isin(_INDEX_LABELS.keys())]
        for col in ("price", "changePercent", "change", "open", "high", "low", "prevClose", "amount", "volume"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        result = []
        for _, r in df.iterrows():
            result.append({
                "code": r["code"],
                "name": _INDEX_LABELS.get(r["code"], str(r.get("name", ""))),
                "price": round(float(r.get("price") or 0), 2),
                "changePercent": round(float(r.get("changePercent") or 0), 2),
                "change": round(float(r.get("change") or 0), 2),
                "open": round(float(r.get("open") or 0), 2),
                "high": round(float(r.get("high") or 0), 2),
                "low": round(float(r.get("low") or 0), 2),
                "prevClose": round(float(r.get("prevClose") or 0), 2),
            })
        order = ["000001", "399001", "399006", "000300", "000688", "000016", "000905"]
        result.sort(key=lambda x: order.index(x["code"]) if x["code"] in order else 99)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def _spot_sorted_list(ascending: bool, limit: int, key_col: str = "涨跌幅") -> list:
    spot = fetch_spot()
    if spot is None or spot.empty or key_col not in spot.columns:
        return []
    df = spot.copy()
    df[key_col] = pd.to_numeric(df[key_col], errors="coerce")
    df = df.dropna(subset=[key_col])
    df = df.sort_values(key_col, ascending=ascending).head(limit)
    out = []
    for _, r in df.iterrows():
        out.append({
            "code": str(r.get("代码", "")),
            "name": str(r.get("名称", "")),
            "industry": str(r.get("行业", "")),
            "price": round(float(r.get("最新价", 0) or 0), 2),
            "changePercent": round(float(r.get("涨跌幅", 0) or 0), 2),
            "volume": int(r.get("成交量", 0) or 0),
            "amount": round(float(r.get("成交额", 0) or 0) / 1e8, 2),  # 亿元
            "turnover": round(float(r.get("换手率", 0) or 0), 2),
            "marketCap": round(float(r.get("总市值_亿", 0) or 0), 0),
        })
    return out


@app.route("/api/market/gainers")
def market_gainers():
    try:
        limit = int(request.args.get("limit", 20))
        return jsonify(_spot_sorted_list(ascending=False, limit=limit, key_col="涨跌幅"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/market/losers")
def market_losers():
    try:
        limit = int(request.args.get("limit", 20))
        return jsonify(_spot_sorted_list(ascending=True, limit=limit, key_col="涨跌幅"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/market/most-active")
def market_most_active():
    try:
        limit = int(request.args.get("limit", 20))
        key_col = "成交额" if "成交额" in fetch_spot().columns else "成交量"
        return jsonify(_spot_sorted_list(ascending=False, limit=limit, key_col=key_col))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stock/search")
def search_stock():
    try:
        keyword = request.args.get("keyword", "").strip()
        if not keyword:
            return jsonify([])

        spot = fetch_spot()
        mask = (
            spot["代码"].str.contains(keyword, na=False) |
            spot["名称"].str.contains(keyword, na=False)
        )
        results = spot[mask].head(10)
        return jsonify([{
            "code": str(r["代码"]),
            "name": str(r["名称"]),
            "industry": str(r.get("行业", "")),
        } for _, r in results.iterrows()])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health")
def health():
    return jsonify({"status": "ok", "timestamp": dt.datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# Blueprints (P5+): backtest, /metrics, /circuits
# ---------------------------------------------------------------------------
try:
    from api.backtest import bp as backtest_bp
    from api.metrics import bp as ops_bp
    from api.strategies_v2 import bp as v2_bp
    from api.lhb import bp as lhb_bp
    from api.moneyflow import bp as mf_bp
    from api.f10 import bp as f10_bp
    from api.conditions import bp as cond_bp
    from api.expression import bp as expr_bp
    from api.admin import bp as admin_bp
    app.register_blueprint(backtest_bp)
    app.register_blueprint(ops_bp)
    app.register_blueprint(v2_bp)
    app.register_blueprint(lhb_bp)
    app.register_blueprint(mf_bp)
    app.register_blueprint(f10_bp)
    app.register_blueprint(cond_bp)
    app.register_blueprint(expr_bp)
    app.register_blueprint(admin_bp)
except Exception as _bp_err:
    print(f'[data-service] blueprint registration failed: {_bp_err}')


if __name__ == "__main__":
    print("Starting stock data service on port 5000...")
    app.run(host="0.0.0.0", port=5001, debug=False)
