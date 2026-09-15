# -*- coding: utf-8 -*-
"""排名快照任务:交易时段每 15 分钟落一次全宇宙评分快照。

每次快照 = 宇宙(总市值 ≥50 亿的前 800 只)全部策略评分 + 行情(价/量/额)
+ 因子组分 + 前 120 名的买点区。决策页与评分选股页都从快照读取,
两次刷新之间结果不会自己变化;快照之间的差异可逐组解释。
"""
from __future__ import annotations

import datetime as dt
import time

from core.trace import logger
from decision import snapshot


def run(force: bool = False) -> str | None:
    now = dt.datetime.now()
    if not force and now.weekday() >= 5:
        logger.info("[rank_snapshot] weekend, skip")
        return None
    t0 = time.time()
    sid = snapshot.build(note="scheduled" if not force else "forced")
    if sid:
        logger.info("[rank_snapshot] %s done in %.1fs", sid, time.time() - t0)
    else:
        logger.warning("[rank_snapshot] build returned None")
    return sid
