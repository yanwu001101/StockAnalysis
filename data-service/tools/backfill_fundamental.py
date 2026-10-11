# -*- coding: utf-8 -*-
"""基本面历史深度回补：按报告期整表拉业绩报表+资产负债表。

背景：`stock_fundamental` 多数股票只有最近 5 期（全表 5534 只、平均 4.27 期/只），
导致 Piotroski n=108、应计利润 n=126、资产增长 n=74、龙虎榜 n=25——基本面类因子
的检验期数被数据卡住，而不是被方法卡住。

用法（容器内，进程与 web worker 隔离）：
    docker exec -d -e BF_FROM=2022-03-31 -e BF_TO=2024-12-31 \
        stock-data-service sh -c "python /app/tools/backfill_fundamental.py > /tmp/bf.log 2>&1"

纪律：
  * 只走 akshare 的东财 datacenter 整表接口——每报告期 2 次请求，不逐股扇出；
  * ann_date 用「最新公告日期」原值，缺失就留空（引擎按法定披露截止日兜底），
    绝不用报告期当日冒充可知时间（前视）；
  * 逐季串行 + 轻微停顿，避免把上游打成限流。
"""
import asyncio
import datetime as dt
import os
import sys
import time

# 直接 `python /app/tools/xxx.py` 时 sys.path[0] 是 tools/，顶层模块（db/pipelines/core）
# 找不到——先把服务根目录插进来，脚本才能从任意 cwd 跑。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from sqlalchemy import text

import db
from core.trace import logger
from pipelines import fundamental as fund_pipe


def quarter_ends_between(start: dt.date, end: dt.date) -> list[dt.date]:
    out: list[dt.date] = []
    for y in range(start.year, end.year + 1):
        for m, d in ((3, 31), (6, 30), (9, 30), (12, 31)):
            qe = dt.date(y, m, d)
            if start <= qe <= end:
                out.append(qe)
    return out


def coverage() -> dict:
    eng = db.get_engine()
    if eng is None:
        return {}
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT COUNT(*), COUNT(DISTINCT code), MIN(report_date), MAX(report_date) "
            "FROM stock_fundamental"
        )).fetchone()
        avg_cnt = conn.execute(text(
            "SELECT AVG(c) FROM (SELECT COUNT(*) c FROM stock_fundamental GROUP BY code) t"
        )).scalar()
        by_q = pd.read_sql(text(
            "SELECT report_date, COUNT(*) n_codes, "
            "  SUM(total_assets IS NOT NULL) has_assets "
            "FROM stock_fundamental GROUP BY report_date ORDER BY report_date"
        ), conn)
    return {
        "rows": int(row[0] or 0), "codes": int(row[1] or 0),
        "avg_periods": round(float(avg_cnt or 0), 2),
        "first_period": str(row[2]), "last_period": str(row[3]),
        "per_quarter": [(str(r["report_date"])[:10], int(r["n_codes"]), int(r["has_assets"] or 0))
                        for _, r in by_q.iterrows()],
    }


def main() -> None:
    frm = dt.date.fromisoformat(os.getenv("BF_FROM", "2022-03-31"))
    to = dt.date.fromisoformat(os.getenv("BF_TO", "2024-12-31"))
    chunk = int(os.getenv("BF_CHUNK", "4"))
    stop = float(os.getenv("BF_SLEEP", "1.0"))

    quarters = quarter_ends_between(frm, to)
    print(f"BF quarters={len(quarters)} {quarters[0]}..{quarters[-1]}", flush=True)
    print("BEFORE", coverage(), flush=True)

    total = 0
    for i in range(0, len(quarters), chunk):
        batch = quarters[i:i + chunk]
        n = 0
        for qe in batch:
            try:
                n += asyncio.run(fund_pipe.run_batch(codes=None, quarters=[qe]))
            except Exception as e:
                print(f"BF {qe} FAILED {type(e).__name__}: {e}", flush=True)
            time.sleep(stop)
        total += n
        print(f"BF done {batch[0]}..{batch[-1]} rows+={n} total={total}", flush=True)

    print("AFTER", coverage(), flush=True)
    print("BF COMPLETE", flush=True)


if __name__ == "__main__":
    main()
