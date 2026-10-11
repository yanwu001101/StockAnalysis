# -*- coding: utf-8 -*-
"""jobs 包标识。

每个 job 是一个提供 run() 的薄模块（premarket/intraday/postmarket/weekend/
strategy_score/rank_snapshot/daily_push/paper_trade），由 scheduler.py 注册
cron 定时、由 api/admin.py /warmup 提供手动触发——本包不再持有调度逻辑。
"""
