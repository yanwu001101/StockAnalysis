# -*- coding: utf-8 -*-
"""因子挖掘（Factor Mining）包。

模块：
  registry  — 原子因子目录（atoms.py 提供实现）与算子注册表元数据
  generator — 候选因子自动生成（模板族 × 原子，预算硬上限）
  pipeline  — 挖掘管线（静态检查 → 快速 IC → 去重 → 完整检验 → 晋级判定）
  jobs      — 任务队列（MySQL 持久化 + 单 worker + 断点续跑）
  repo      — fm_job / fm_factor / fm_factor_cache 持久层

外部入口：api/factormine.py（Flask 蓝图 /api/factormine/*）。
"""
from factormine import repo  # noqa: F401

__all__ = ["repo"]
