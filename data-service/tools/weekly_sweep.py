# -*- coding: utf-8 -*-
"""周度全策略体检：一次跑完注册表里所有内置策略，结果增量落盘。

用法（在 data-service 容器里跑，进程与 web worker 隔离）：
    docker exec -d -e SWEEP_END=2026-10-09 -e SWEEP_OUT=/tmp/weekly_sweep.json \
        stock-data-service sh -c "python /app/tools/weekly_sweep.py > /tmp/weekly_sweep.log 2>&1"
之后用 tools/sweep_compare.py 与上一版 JSON 出对比表（docs/weekly_sweep_YYYY-MM.md）。

对比纪律：只改一个变量。上一次全市场重跑（2026-10-11）刻意沿用 09 名单的
rebalance/layers/max_codes，只让候选池随日K覆盖变化，否则差异无法归因。
每个策略跑完立即落盘，进程被打断也不丢已完成的结果。
"""
import datetime as dt
import json
import os
import sys
import time

# 同 backfill_fundamental：从任意 cwd 直接跑时要把服务根目录加进 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backtest.engine as eng

# 全市场 pivot 只做一次（默认 60s TTL 会让 29 次调用各重算一遍 3.5M 行）
eng._UNIVERSE_TTL_S = 4 * 3600

from factorlab import analyze
from strategies import REGISTRY

START = dt.date.fromisoformat(os.getenv("SWEEP_START", "2024-03-01"))
END = dt.date.fromisoformat(os.getenv("SWEEP_END", dt.date.today().isoformat()))
MAX_CODES = int(os.getenv("SWEEP_MAX_CODES", "300"))
OUT = os.getenv("SWEEP_OUT", "/tmp/weekly_sweep.json")

NAMES = {s.id: s.name for s in REGISTRY}
IDS = [s.id for s in REGISTRY]


def brief(sid: str, r: dict) -> dict:
    if not isinstance(r, dict) or "error" in r:
        return {"strategy_id": sid, "name": NAMES.get(sid, ""), "error": (r or {}).get("error")}
    ic = r.get("ic_summary") or {}
    icn = r.get("ic_neutral_summary") or {}
    rt = r.get("rating") or {}
    return {
        "strategy_id": sid,
        "name": NAMES.get(sid, ""),
        "ic": ic.get("mean"),
        "icir": ic.get("icir"),
        "t": ic.get("t_stat"),
        "n": ic.get("n"),
        "ic_neutral": icn.get("mean"),
        "t_neutral": icn.get("t_stat"),
        "status": rt.get("status"),
        "dir": rt.get("direction"),
        "grade": rt.get("grade"),
        "conf": rt.get("confidence"),
        "robustness": rt.get("robustness"),
        "mono": r.get("layer_monotonicity"),
        "net": rt.get("net_spread_ann"),
        "cost": rt.get("cost_annualized"),
        "spread_ann": r.get("top_minus_bottom_annualized"),
        "el": r.get("turnover_annualized"),
        "periods": r.get("periods"),
        "codes": r.get("codes_analyzed"),
        "sample": r.get("sample_info"),
    }


def dump(items: list, elapsed: float) -> None:
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({
            "start": START.isoformat(), "end": END.isoformat(),
            "rebalance": "weekly", "max_codes": MAX_CODES, "layers": 5,
            "universe_note": "日均成交额前 300 只,池=当前全市场日K(5531 只)",
            "generated_at": dt.datetime.now().isoformat(),
            "elapsed_s": round(elapsed, 1),
            "items": items,
        }, f, ensure_ascii=False, indent=1)


def main() -> None:
    items = []
    t0 = time.time()
    dump(items, time.time() - t0)
    for i, sid in enumerate(IDS, 1):
        ts = time.time()
        try:
            r = analyze(sid, START, END, rebalance="weekly", max_codes=MAX_CODES)
        except Exception as e:
            r = {"error": f"{type(e).__name__}: {e}"}
        item = brief(sid, r)
        items.append(item)
        dump(items, time.time() - t0)
        print(
            f"[{i}/{len(IDS)}] {sid} ic={item.get('ic')} t={item.get('t')} "
            f"n={item.get('n')} grade={item.get('grade')} status={item.get('status')} "
            f"dir={item.get('dir')} net={item.get('net')} err={item.get('error')} "
            f"({time.time() - ts:.0f}s)",
            flush=True,
        )
    print(f"SWEEP DONE items={len(items)} elapsed={time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
