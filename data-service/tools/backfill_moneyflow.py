# -*- coding: utf-8 -*-
"""个股主力资金流历史加深（新浪 ssl_qsfx_lscjfb，单次大 num）。

为什么需要它：研究链路要按 as-of 取任意历史日的 5 日资金流，而表里原先只有
60.4 天/只——2024~2025 的报告期完全没有数据可取。

用法（容器内）：
    docker exec -d -e MF_DAYS=700 -e MF_CONCURRENCY=10 \
        stock-data-service sh -c "python /app/tools/backfill_moneyflow.py > /tmp/mf.log 2>&1"
"""
import asyncio
import datetime as dt
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

import db

DAYS = int(os.getenv("MF_DAYS", "700"))
BUDGET = int(os.getenv("MF_LIMIT", "0"))           # 0 = 全部


def codes() -> list[str]:
    eng = db.get_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(
            "SELECT code FROM stock_info WHERE code IS NULL OR code NOT LIKE '900%' "
            "AND code NOT LIKE '200%'"
        )).fetchall()
    out = sorted({str(r[0]).zfill(6) for r in rows})
    return out[:BUDGET] if BUDGET else out


def depth() -> dict:
    eng = db.get_engine()
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT COUNT(*) codes, ROUND(AVG(c),1) avg_days, MAX(c) max_days FROM ("
            "  SELECT code, COUNT(*) c FROM stock_moneyflow GROUP BY code"
            ") t"
        )).fetchone()
        span = conn.execute(text(
            "SELECT MIN(trade_date), MAX(trade_date), COUNT(DISTINCT trade_date) FROM stock_moneyflow"
        )).fetchone()
    return {"codes": int(row[0] or 0), "avg_days": float(row[1] or 0),
            "max_days": int(row[2] or 0),
            "span": f"{str(span[0])[:10]}~{str(span[1])[:10]}",
            "distinct_dates": int(span[2] or 0)}


async def main() -> None:
    from pipelines import moneyflow as mf_pipe

    cs = codes()
    print(f"MF codes={len(cs)} days={DAYS}", flush=True)
    print("BEFORE", depth(), flush=True)
    t0 = time.time()
    total = 0
    for i in range(0, len(cs), 500):
        chunk = cs[i:i + 500]
        total += await mf_pipe.run_batch(chunk, days=DAYS)
        print(f"MF progress {min(i + 500, len(cs))}/{len(cs)} rows+={total} "
              f"elapsed={time.time() - t0:.0f}s", flush=True)
    print("AFTER", depth(), flush=True)
    print(f"MF COMPLETE rows={total} elapsed={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
