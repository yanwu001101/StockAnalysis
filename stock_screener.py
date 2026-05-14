from __future__ import annotations

import argparse
import datetime as dt
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed # 新增并发提速

import pandas as pd


POLICY_KEYWORDS = {
    "新质生产力": (
        "半导体", "芯片", "人工智能", "AI", "算力", "机器人", "工业互联网",
        "高端装备", "航空", "军工", "新能源", "电池", "光伏", "储能", "软件", "通信",
    ),
    "央国企改革": (
        "银行", "证券", "保险", "电力", "石油", "煤炭", "建筑",
        "交运", "铁路", "港口", "公用事业", "运营商", "中字头",
    ),
    "内需消费升级": (
        "白酒", "食品", "饮料", "家电", "医药", "医疗",
        "旅游", "酒店", "免税", "零售", "消费", "汽车",
    ),
}


@dataclass(frozen=True)
class Thresholds:
    roe_min: float = 15.0
    raw_roe_min: float = 3.0
    debt_ratio_max: float = 50.0
    market_cap_min_yi: float = 200.0
    min_score: int = 60
    max_results: int = 80
    include_st: bool = False


def import_akshare():
    try:
        import akshare as ak  # type: ignore
    except ModuleNotFoundError as exc:
        raise SystemExit("缺少 akshare。请先运行: pip install akshare pandas openpyxl") from exc
    return ak


def normalize_code(code: object) -> str:
    text = str(code).strip()
    digits = re.sub(r"\D", "", text)
    return digits.zfill(6)[-6:]


def to_number(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.replace("%", "", regex=False).str.replace(",", "", regex=False),
        errors="coerce",
    )


def first_existing(columns: Iterable[str], candidates: Iterable[str]) -> str | None:
    available = set(columns)
    for candidate in candidates:
        if candidate in available:
            return candidate
    return None


def retry_call(func, *args, retries: int = 3, wait: float = 2.0, **kwargs):
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(wait * attempt)
    raise last_error or RuntimeError("数据接口请求失败。")


def fetch_spot(ak) -> pd.DataFrame:
    print("正在获取全市场实时行情...")
    try:
        df = retry_call(ak.stock_zh_a_spot_em, retries=4, wait=2)
    except Exception:
        df = retry_call(ak.stock_zh_a_spot, retries=3, wait=2)
    df = df.copy()
    code_col = first_existing(df.columns, ["代码", "证券代码"])
    name_col = first_existing(df.columns, ["名称", "证券简称"])
    industry_col = first_existing(df.columns, ["行业", "所属行业", "板块名称"])
    price_col = first_existing(df.columns, ["最新价", "收盘"])
    cap_col = first_existing(df.columns, ["总市值"])
    
    if not code_col or not name_col:
        raise RuntimeError("行情数据缺少股票代码或名称列。")

    keep = [code_col, name_col]
    rename = {code_col: "代码", name_col: "名称"}
    
    if industry_col: keep.append(industry_col); rename[industry_col] = "行业"
    if price_col: keep.append(price_col); rename[price_col] = "最新价"
    if cap_col: keep.append(cap_col); rename[cap_col] = "总市值"
        
    out = df[keep].copy()
    out = out.rename(columns=rename)
    out["代码"] = out["代码"].map(normalize_code)
    
    if "总市值" in out:
        out["总市值_亿"] = to_number(out["总市值"]) / 100_000_000
    else:
        out["总市值_亿"] = math.nan
    return out


def report_dates(quarters: int = 10) -> list[str]:
    today = dt.date.today()
    years = range(today.year, today.year - 4, -1)
    dates: list[str] = []
    for year in years:
        for suffix in ("1231", "0930", "0630", "0331"):
            text = f"{year}{suffix}"
            report_day = dt.datetime.strptime(text, "%Y%m%d").date()
            if report_day <= today:
                dates.append(text)
    return dates[:quarters]


def latest_report(ak_func, dates: list[str], min_rows: int = 1000) -> tuple[pd.DataFrame, str]:
    last_error: Exception | None = None
    for date in dates:
        try:
            df = retry_call(ak_func, date=date, retries=2, wait=1)
            if df is not None and len(df) >= min_rows:
                return df.copy(), date
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("没有拿到可用的全市场财务报表。")


def fetch_financial(ak) -> pd.DataFrame:
    print("正在获取最新财报数据 (这可能需要十几秒)...")
    dates = report_dates()
    yjbb, yjbb_date = latest_report(ak.stock_yjbb_em, dates)
    zcfz, zcfz_date = latest_report(ak.stock_zcfz_em, dates)

    for df in (yjbb, zcfz):
        code_col = first_existing(df.columns, ["股票代码", "代码"])
        if not code_col:
            raise RuntimeError("财务报表缺少股票代码列。")
        df["代码"] = df[code_col].map(normalize_code)

    yjbb_result = yjbb[["代码"]].copy()
    
    # 【核心优化】ROE年化处理，解决一季报/中报被错杀的问题
    report_month = int(yjbb_date[4:6]) # 提取报表月份，如 "03", "06"
    annualize_factor = 12.0 / report_month if report_month in [3, 6, 9, 12] else 1.0
    
    raw_roe = to_number(yjbb["净资产收益率"])
    yjbb_result["净资产收益率_原始"] = raw_roe
    yjbb_result["净资产收益率"] = raw_roe * annualize_factor # 转换为年化

    growth_columns = {
        "营收同比增长率": ["营业总收入-同比增长", "营业总收入同比增长率"],
        "净利润同比增长率": ["净利润-同比增长", "净利润同比增长率"],
        "销售毛利率": ["销售毛利率"],
    }
    for target, candidates in growth_columns.items():
        source = first_existing(yjbb.columns, candidates)
        yjbb_result[target] = to_number(yjbb[source]) if source else math.nan
    
    cash_col = first_existing(yjbb.columns, ["每股经营现金流量", "每股经营现金流"])
    if cash_col:
        yjbb_result["经营现金流"] = to_number(yjbb[cash_col])
    else:
        yjbb_result["经营现金流"] = math.nan
        
    yjbb_result["财报期_ROE现金流"] = yjbb_date

    zcfz_result = zcfz[["代码"]].copy()
    zcfz_result["资产负债率"] = to_number(zcfz["资产负债率"])
    zcfz_result["财报期_负债率"] = zcfz_date

    result = yjbb_result.drop_duplicates("代码").merge(
        zcfz_result.drop_duplicates("代码"), on="代码", how="left"
    )
    return result


def fetch_weekly_trend(ak, code: str, lookback_days: int = 900) -> dict[str, float | bool | None]:
    end = dt.date.today()
    start = end - dt.timedelta(days=lookback_days)
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="weekly", start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"), adjust="qfq",
        )
    except Exception:
        return {"周线收盘": None, "周线MA60": None, "MA60之上": False}
        
    if df is None or df.empty or "收盘" not in df:
        return {"周线收盘": None, "周线MA60": None, "MA60之上": False}
        
    close = to_number(df["收盘"])
    if len(close) < 60:
        return {"周线收盘": float(close.iloc[-1]), "周线MA60": None, "MA60之上": False}
        
    ma60 = close.rolling(60).mean()
    latest_close = float(close.iloc[-1])
    latest_ma60 = float(ma60.iloc[-1])
    above = bool(pd.notna(latest_close) and pd.notna(latest_ma60) and latest_close >= latest_ma60)
    
    return {
        "周线收盘": round(latest_close, 3),
        "周线MA60": round(latest_ma60, 3),
        "MA60之上": above,
    }


def policy_bucket(name: str, industry: str) -> tuple[str, int]:
    text = f"{name} {industry}"
    buckets: list[str] = []
    for bucket, keywords in POLICY_KEYWORDS.items():
        if any(keyword.lower() in text.lower() for keyword in keywords):
            buckets.append(bucket)
    return ("、".join(buckets) if buckets else "未命中", min(len(buckets), 2) * 6)


# 【核心优化】质量优先评分：财务质量打底，成长和趋势确认，政策只做辅助加分
def score_row(row: pd.Series) -> int:
    score = 0
    roe = row.get("净资产收益率", 0)
    raw_roe = row.get("净资产收益率_原始", 0)
    debt = row.get("资产负债率", 100)
    cash = row.get("经营现金流", 0)
    cap = row.get("总市值_亿", 0)
    revenue_growth = row.get("营收同比增长率", math.nan)
    profit_growth = row.get("净利润同比增长率", math.nan)
    gross_margin = row.get("销售毛利率", math.nan)

    # 1. 盈利能力：年化 ROE 和原始 ROE 同看，避免一季报年化过度美化
    if pd.notna(roe):
        if roe >= 30: score += 25
        elif roe >= 22: score += 20
        elif roe >= 15: score += 14
    if pd.notna(raw_roe):
        if raw_roe >= 8: score += 8
        elif raw_roe >= 5: score += 5
        elif raw_roe >= 3: score += 3

    # 2. 现金流：优先选择利润能变成真现金的公司
    if pd.notna(cash):
        if cash >= 2.0: score += 15
        elif cash >= 1.0: score += 12
        elif cash > 0: score += 8

    # 3. 资产负债率：越轻越好，适度负债可接受
    if pd.notna(debt):
        if debt <= 30: score += 15
        elif debt <= 45: score += 11
        elif debt <= 60: score += 6

    # 4. 成长质量：利润增长、营收增长、毛利率组合确认
    if pd.notna(profit_growth):
        if profit_growth >= 30: score += 10
        elif profit_growth >= 10: score += 7
        elif profit_growth >= 0: score += 4
        elif profit_growth < -20: score -= 6
    if pd.notna(revenue_growth):
        if revenue_growth >= 20: score += 8
        elif revenue_growth >= 8: score += 5
        elif revenue_growth >= 0: score += 2
    if pd.notna(gross_margin):
        if gross_margin >= 50: score += 8
        elif gross_margin >= 35: score += 6
        elif gross_margin >= 20: score += 3

    # 5. 市值：白马稳定性加分，但数据源缺失时不惩罚
    if pd.notna(cap):
        if cap >= 1000: score += 15  # 千亿白马更稳定
        elif cap >= 500: score += 10
        elif cap >= 200: score += 5

    # 6. 技术面趋势：只做确认，不替代基本面
    if bool(row.get("MA60之上")):
        score += 12
    elif pd.notna(row.get("周线MA60")):
        score -= 5

    # 7. 政策加分：顺风加速，但不让题材盖过财务
    score += int(row.get("政策分", 0))

    return max(0, min(score, 100))


def screen(thresholds: Thresholds, with_trend: bool) -> pd.DataFrame:
    ak = import_akshare()
    spot = fetch_spot(ak)
    financial = fetch_financial(ak)

    data = spot.merge(financial, on="代码", how="left")
    if not thresholds.include_st:
        data = data[~data["名称"].astype(str).str.contains("ST", case=False, na=False)].copy()

    for col in ["净资产收益率", "资产负债率", "经营现金流", "总市值_亿"]:
        if col not in data:
            data[col] = math.nan

    policy = data.apply(lambda r: policy_bucket(str(r.get("名称", "")), str(r.get("行业", ""))), axis=1)
    data["政策方向"] = [item[0] for item in policy]
    data["政策分"] = [item[1] for item in policy]

    # 硬性过滤环节：只保留基本面安全底线，其余交给综合评分排序
    mask = (
        (data["净资产收益率"] >= thresholds.roe_min)
        & (data["净资产收益率_原始"] >= thresholds.raw_roe_min)
        & (data["资产负债率"] <= thresholds.debt_ratio_max)
        & (data["经营现金流"] > 0)
    )
    if data["总市值_亿"].notna().any():
        mask = mask & (data["总市值_亿"] >= thresholds.market_cap_min_yi)

    filtered = data[mask].copy()
    
    # 先选出最头部的，防止后面多线程请求数量过多
    filtered = filtered.sort_values(["总市值_亿", "净资产收益率"], ascending=False)
    filtered = filtered.head(max(thresholds.max_results, 1)).copy()

    # 【核心优化】多线程并发获取技术面数据，速度极大幅提升
    if with_trend and not filtered.empty:
        print(f"正在并发获取 {len(filtered)} 只股票的周线技术面数据，请稍候...")
        trend_results = {}
        with ThreadPoolExecutor(max_workers=15) as executor:
            future_to_code = {executor.submit(fetch_weekly_trend, ak, code): code for code in filtered["代码"]}
            for future in as_completed(future_to_code):
                code = future_to_code[future]
                trend_results[code] = future.result()
                
        # 按照原 filtered 的顺序提取结果
        trend_rows = [trend_results[code] for code in filtered["代码"]]
        trend_df = pd.DataFrame(trend_rows)
        trend_df.index = filtered.index
        filtered = pd.concat([filtered, trend_df], axis=1)
    else:
        filtered["周线收盘"] = None
        filtered["周线MA60"] = None
        filtered["MA60之上"] = False

    if filtered.empty:
        print("未筛选出符合条件的股票。可能是条件过于严苛。")
        return pd.DataFrame()

    filtered["综合分"] = [score_row(row) for _, row in filtered.iterrows()]
    filtered = filtered[filtered["综合分"] >= thresholds.min_score].copy()
    if filtered.empty:
        print(f"通过基本面底线的股票综合分均低于 {thresholds.min_score}。可尝试降低 --min-score。")
        return pd.DataFrame()
    
    # 控制显示列及顺序
    columns = [
        "综合分", "代码", "名称", "行业", "政策方向", "最新价", "总市值_亿",
        "净资产收益率", "净资产收益率_原始", "资产负债率", "经营现金流",
        "营收同比增长率", "净利润同比增长率", "销售毛利率",
        "财报期_ROE现金流", "财报期_负债率", "周线收盘", "周线MA60", "MA60之上",
    ]
    existing = [col for col in columns if col in filtered.columns]
    
    # 按照综合打分做最终排序，同分看ROE和市值
    return filtered[existing].sort_values(["综合分", "净资产收益率", "总市值_亿"], ascending=False)


def write_excel(df: pd.DataFrame, output: Path) -> None:
    if df.empty: return
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="优质股票筛选")
        ws = writer.book["优质股票筛选"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        widths = {
            "A": 8, "B": 10, "C": 12, "D": 12, "E": 20, "F": 10,
            "G": 12, "H": 14, "I": 16, "J": 12, "K": 12, "L": 18, 
            "M": 14, "N": 10, "O": 10, "P": 12
        }
        for col_letter, width in widths.items():
            if col_letter in ws.column_dimensions:
                ws.column_dimensions[col_letter].width = width


def main() -> None:
    parser = argparse.ArgumentParser(description="A股优质股票指标筛选器 (高性能优化版)")
    parser.add_argument("--roe", type=float, default=15.0, help="最低年化ROE，默认 15")
    parser.add_argument("--raw-roe", type=float, default=3.0, help="最低单期原始ROE，默认 3，防止年化ROE虚高")
    parser.add_argument("--debt", type=float, default=50.0, help="最高资产负债率，默认 50。若需筛金融/基建建议设为 90")
    parser.add_argument("--cap", type=float, default=200.0, help="最低总市值(亿元)，默认 200")
    parser.add_argument("--min-score", type=int, default=60, help="最低综合分，默认 60")
    parser.add_argument("--limit", type=int, default=80, help="最多输出数量，默认 80")
    parser.add_argument("--include-st", action="store_true", help="包含 ST 股票")
    parser.add_argument("--no-trend", action="store_true", help="跳过周线验证")
    parser.add_argument("--output", default="优质股票筛选结果.xlsx", help="输出文件名")
    args = parser.parse_args()

    print(
        f"筛选条件 => 年化ROE: >{args.roe}% | 原始ROE: >{args.raw_roe}% | "
        f"负债率: <{args.debt}% | 市值: >{args.cap}亿 | 综合分: >={args.min_score}"
    )
    thresholds = Thresholds(
        roe_min=args.roe,
        raw_roe_min=args.raw_roe,
        debt_ratio_max=args.debt,
        market_cap_min_yi=args.cap,
        min_score=args.min_score,
        max_results=args.limit,
        include_st=args.include_st,
    )
    
    start_time = time.time()
    result = screen(thresholds=thresholds, with_trend=not args.no_trend)
    
    if not result.empty:
        output = Path(args.output).resolve()
        write_excel(result, output)
        print(f"\n筛选完成! 耗时: {time.time() - start_time:.1f} 秒")
        print(f"命中数量: {len(result)} 只，结果已保存至: {output}")
        # 在终端展示前10名，保留两位小数方便查看
        display_df = result.head(10).copy()
        for col in ["最新价", "总市值_亿", "净资产收益率", "净资产收益率_原始", "资产负债率", "经营现金流", "营收同比增长率", "净利润同比增长率"]:
            if col in display_df.columns:
                display_df[col] = display_df[col].apply(lambda x: round(x, 2) if pd.notna(x) else x)
        print("\n=== 前10名高分榜单 ===")
        display_columns = [
            col for col in ["综合分", "名称", "行业", "总市值_亿", "净资产收益率", "净资产收益率_原始", "净利润同比增长率", "资产负债率", "政策方向", "MA60之上"]
            if col in display_df.columns
        ]
        print(display_df[display_columns].to_string(index=False))
    else:
        print(f"\n筛选完成! 耗时: {time.time() - start_time:.1f} 秒。未找到符合条件的股票。")


if __name__ == "__main__":
    main()
