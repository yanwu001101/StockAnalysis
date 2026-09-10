"""AStock-Agent 主入口 (A股游资分析助手)。

用法:
  python main.py                    最近交易日全市场复盘 (生成 Markdown 报告)
  python main.py --date 20260715   指定交易日复盘
  python main.py --stock 002104    个股资金分析
  python main.py --no-ai           跳过 LLM, 纯规则报告
  python main.py --json            额外输出结构化 JSON (供 Agent / 程序消费)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config  # noqa: E402
from ai import gpt, prompt  # noqa: E402
from analysis import capital, dragon, emotion, theme  # noqa: E402
from data import longhu, market, stock  # noqa: E402
from database import sqlite as db  # noqa: E402
from report import generator  # noqa: E402


def log(msg: str) -> None:
    print(f"[AStock] {msg}", file=sys.stderr, flush=True)  # 日志走 stderr, stdout 留给 --json


def collect_daily(date: str) -> dict:
    """采集 + 分析, 返回完整 payload (设计文档 §2 数据流)。"""
    prev_date = market.prev_trade_date(date)
    note = None

    log(f"采集涨停/跌停/炸板股池 ({date}) ...")
    zt = stock.fetch_zt_pool(date)
    if not zt:
        fallback = prev_date
        log(f"{date} 无涨停池数据(非交易日或数据未生成), 回退 {fallback}")
        note = f"{date} 无数据, 已回退至最近有数据的交易日 {fallback}"
        date, prev_date = fallback, market.prev_trade_date(fallback)
        zt = stock.fetch_zt_pool(date)
    dt_pool = stock.fetch_dt_pool(date)
    zb = stock.fetch_zb_pool(date)
    prev_perf = stock.fetch_prev_zt_perf(date)
    prev_zt = stock.fetch_zt_pool(prev_date)

    log("采集指数与市场概况 ...")
    idx = market.index_snapshot(date)
    act = market.market_activity() if market.is_today(date) else None
    flows = market.sector_flows() if market.is_today(date) else {}

    log("采集龙虎榜与席位明细 ...")
    lhb = longhu.fetch_lhb(date)
    longhu.attach_seats(lhb, date)

    db.save_limit_up(date, zt)
    db.save_longhu(date, lhb)

    log("分析: 情绪周期 / 板块轮动 / 龙头评分 / 游资行为 ...")
    history = db.recent_market(prev_date)
    emo = emotion.analyze(zt, dt_pool, zb, act, idx, prev_zt, prev_perf, history)
    them = theme.analyze(zt, flows, db.theme_daily_counts(date), prev_zt)
    cap = capital.analyze(lhb)
    drg = dragon.score_dragons(
        zt,
        theme.theme_score_map(them),
        {r["code"]: r for r in lhb},
        capital.famous_by_code(cap),
    )
    ladder = dragon.build_ladder(zt)

    db.save_market_daily(
        date,
        {
            "temperature": emo["temperature"],
            "state": emo["state"],
            "phase": emo["phase"],
            "zt_count": emo["zt_count"],
            "dt_count": emo["dt_count"],
            "max_height": emo["max_height"],
            "amount": emo.get("amount"),
            "mainline": (them.get("mainline") or {}).get("name"),
        },
    )

    return {
        "date": date,
        "prev_date": prev_date,
        "note": note,
        "index": idx,
        "emotion": emo,
        "ladder": ladder,
        "theme": them,
        "dragons": drg,
        "capital": cap,
        "zt": zt,
        "dt": dt_pool,
        "zb": zb,
    }


def run_daily(date: str | None, use_ai: bool, as_json: bool) -> None:
    db.init_db()
    capital.seed_database()
    date = market.resolve_trade_date(date)
    payload = collect_daily(date)

    ai_text = None
    if use_ai and gpt.available():
        log(f"调用 AI 复盘引擎 ({config.LLM_MODEL}) ...")
        ai_text = gpt.chat(*prompt.build_review_prompt(payload))
    elif use_ai:
        log("未配置 ASTOCK_LLM_API_KEY, 跳过 AI 复盘 (纯规则报告)")

    md = generator.render_daily(payload, ai_text)
    out = config.REPORT_DIR / f"daily_{payload['date']}.md"
    out.write_text(md, encoding="utf-8")

    emo, ml = payload["emotion"], payload["theme"].get("mainline")
    log("=" * 56)
    log(f"复盘完成 {payload['date']}: 温度 {emo['temperature']}/100 · {emo['state']} · {emo['phase']}")
    log(f"涨停 {emo['zt_count']} / 跌停 {emo['dt_count']} / 高度 {emo['max_height']}板"
        f" / 晋级率 {round((emo.get('promote_rate') or 0) * 100)}%")
    if ml:
        log(f"主线: {ml['name']} ({ml['status']}) · 核心 {ml['leader']['name']}({ml['leader']['height']}板)")
    for d in payload["dragons"][:3]:
        log(f"龙头: {d['name']} {d['score']}分 [{d['role']}] {d['height']}板 · {d['theme']}")
    log(f"报告已生成: {out}")
    if as_json:
        slim = prompt.build_review_payload(payload)
        print(json.dumps(slim, ensure_ascii=False, indent=1))


def run_stock(code: str, date: str | None, use_ai: bool, as_json: bool) -> None:
    db.init_db()
    capital.seed_database()
    date = market.resolve_trade_date(date)
    code = str(code).strip().zfill(6)
    prev_date = market.prev_trade_date(date)

    log(f"采集 {code} 相关数据 ({date}) ...")
    zt = stock.fetch_zt_pool(date)
    zt_row = next((s for s in zt if s["code"] == code), None)
    lhb = longhu.fetch_lhb(date)
    lhb_row = next((r for r in lhb if r["code"] == code), None)
    seats = longhu.fetch_seats(code, date) if lhb_row else None
    if lhb_row and seats:
        lhb_row["seats"] = seats

    name = (zt_row or lhb_row or {}).get("name") or code
    info: dict = {"date": date, "code": code, "name": name, "zt": zt_row, "seats": seats}

    if zt:
        flows = market.sector_flows() if market.is_today(date) else {}
        them = theme.analyze(zt, flows, db.theme_daily_counts(date), stock.fetch_zt_pool(prev_date))
        if zt_row:
            info["theme"] = next(
                (t for t in them["themes"] if t["name"] == zt_row["industry"]), None
            )
            cap_all = capital.analyze([lhb_row] if lhb_row else [])
            drg = dragon.score_dragons(
                zt, theme.theme_score_map(them),
                {code: lhb_row} if lhb_row else {},
                capital.famous_by_code(cap_all),
            )
            info["dragon"] = next((d for d in drg if d["code"] == code), None)
    if lhb_row:
        info["capital"] = capital._analyze_stock(lhb_row)  # noqa: SLF001

    if not zt_row and not lhb_row:
        log(f"{name} 当日既未涨停也未上龙虎榜, 仅输出有限信息")

    ai_text = None
    if use_ai and gpt.available():
        log("调用 AI 个股分析 ...")
        ai_info = {k: v for k, v in info.items() if k != "seats"}
        ai_info["seats_top"] = {
            k: [{"seat": s["seat"], "net": s["net"]} for s in (seats or {}).get(k, [])[:5]]
            for k in ("buy", "sell")
        } if seats else None
        ai_text = gpt.chat(*prompt.build_stock_prompt(ai_info))

    md = generator.render_stock(info, ai_text)
    out = config.REPORT_DIR / f"stock_{code}_{date}.md"
    out.write_text(md, encoding="utf-8")
    log(f"个股报告已生成: {out}")
    if as_json:
        print(json.dumps({k: v for k, v in info.items() if k != "seats"},
                         ensure_ascii=False, indent=1, default=str))


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="AStock-Agent A股游资分析助手")
    parser.add_argument("--date", help="交易日 YYYYMMDD, 默认最近交易日")
    parser.add_argument("--stock", help="个股代码, 生成个股资金分析报告")
    parser.add_argument("--no-ai", action="store_true", help="跳过 LLM 分析")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON")
    args = parser.parse_args()

    if args.stock:
        run_stock(args.stock, args.date, not args.no_ai, args.json)
    else:
        run_daily(args.date, not args.no_ai, args.json)


if __name__ == "__main__":
    main()
