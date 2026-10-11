# -*- coding: utf-8 -*-
"""Operator Registry：算子元数据（名称/参数/输入输出/横截面/时序/未来函数风险）。

实现全部来自 alphalab._make_namespace（单一求值引擎，SKILL §20），本模块只登记
元数据供三处使用：
  1. GET /api/factormine/operators —— 前端算子手册
  2. 生成器约束（哪些算子可进模板）
  3. 静态泄漏说明（future_risk 标注）

kind: ts=时间序列（向后窗口） / cross=横截面 / math=逐元素 / cond=条件
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OperatorSpec:
    name: str
    kind: str            # ts / cross / math / cond
    signature: str
    desc: str
    allows_cross: bool   # 是否允许横截面计算（rank/zscore 类）
    allows_ts: bool      # 是否允许时间序列计算（rolling/shift 类）
    future_risk: str     # none / negative_window（仅当用户显式写负窗口，运行期拦截）
    aliases: tuple = ()


def _reg() -> list[OperatorSpec]:
    S = OperatorSpec
    return [
        # —— 时序 ——
        S("TS_MEAN", "ts", "TS_MEAN(x, n)", "n 日均值", False, True, "none", ("MA", "MEAN", "ROLLING_MEAN")),
        S("TS_STD", "ts", "TS_STD(x, n)", "n 日标准差", False, True, "none", ("STD", "ROLLING_STD")),
        S("TS_SUM", "ts", "TS_SUM(x, n)", "n 日求和", False, True, "none", ()),
        S("TS_MAX", "ts", "TS_MAX(x, n)", "n 日最大", False, True, "none", ("MAX", "ROLLING_MAX")),
        S("TS_MIN", "ts", "TS_MIN(x, n)", "n 日最小", False, True, "none", ("MIN", "ROLLING_MIN")),
        S("TS_MEDIAN", "ts", "TS_MEDIAN(x, n)", "n 日中位数", False, True, "none", ("MEDIAN",)),
        S("TS_RANK", "ts", "TS_RANK(x, n)", "当前值在最近 n 日内的分位（0~1）", False, True, "none", ()),
        S("DELAY", "ts", "DELAY(x, n)", "n 天前的值（n ≥ 1）", False, True, "negative_window", ("SHIFT",)),
        S("DELTA", "ts", "DELTA(x, n)", "x − DELTA(x, n)（n ≥ 1）", False, True, "negative_window", ("DIFF",)),
        S("PCT_CHG", "ts", "PCT_CHG(x, n)", "n 日累计涨跌幅（n ≥ 1）", False, True, "negative_window", ()),
        S("TS_CORR", "ts", "TS_CORR(x, y, n)", "逐股 n 日滚动相关", False, True, "none", ()),
        S("EMA", "ts", "EMA(x, n)", "n 日指数均线", False, True, "none", ()),
        S("SLOPE", "ts", "SLOPE(x, n)", "n 日相对斜率（每日均摊涨跌幅）", False, True, "none", ()),
        # —— 截面 ——
        S("RANK", "cross", "RANK(x)", "截面百分位秩（0~1）", True, False, "none", ("PERCENTILE",)),
        S("ZSCORE", "cross", "ZSCORE(x)", "截面 z 分数", True, False, "none", ()),
        # —— 数学 ——
        S("ABS", "math", "ABS(x)", "绝对值", True, True, "none", ()),
        S("LOG", "math", "LOG(x)", "自然对数（自动防负：非正值 → NaN）", True, True, "none", ()),
        S("SQRT", "math", "SQRT(x)", "平方根（负值 → NaN）", True, True, "none", ()),
        S("POW", "math", "POW(x, a)", "幂（** 运算符等价）", True, True, "none", ()),
        S("SIGN", "math", "SIGN(x)", "符号（−1/0/1）", True, True, "none", ()),
        # —— 条件 ——
        S("GT", "cond", "GT(a, b)", "a > b", True, True, "none", ()),
        S("LT", "cond", "LT(a, b)", "a < b", True, True, "none", ()),
        S("GTE", "cond", "GTE(a, b)", "a ≥ b", True, True, "none", ()),
        S("LTE", "cond", "LTE(a, b)", "a ≤ b", True, True, "none", ()),
        S("AND", "cond", "AND(a, b)", "逻辑与（也可直接写 a & b）", True, True, "none", ()),
        S("OR", "cond", "OR(a, b)", "逻辑或（也可直接写 a | b）", True, True, "none", ()),
        S("IF", "cond", "IF(cond, a, b)", "条件取值；cond 可直接写 close > MA20 等比较式",
          True, True, "none", ()),
    ]


OPERATOR_REGISTRY: list[OperatorSpec] = _reg()

# 四则运算（AST 里的 BinOp）不在函数注册表内，单独说明
BUILTIN_OPS = [
    {"name": "ADD (+)", "kind": "math", "desc": "逐元素相加"},
    {"name": "SUB (-)", "kind": "math", "desc": "逐元素相减"},
    {"name": "MUL (*)", "kind": "math", "desc": "逐元素相乘"},
    {"name": "DIV (/)", "kind": "math", "desc": "逐元素相除（除以 0 → NaN，不报错不伪造）"},
    {"name": "NEG (-x)", "kind": "math", "desc": "取负（反向因子写法，如 -PCT_CHG(CLOSE,20)）"},
    {"name": "a > b 等", "kind": "cond", "desc": "python 比较符直接可用，返回布尔面板"},
]


def operators_payload() -> dict:
    return {
        "operators": [
            {"name": o.name, "kind": o.kind, "signature": o.signature, "desc": o.desc,
             "aliases": list(o.aliases), "allows_cross": o.allows_cross,
             "allows_ts": o.allows_ts,
             "future_risk": o.future_risk,
             "future_risk_note": "仅当显式传入负数窗口时构成未来函数；"
                                 "静态扫描与运行期守卫双重拦截并淘汰（LEAKAGE）"
             if o.future_risk != "none" else "无（向后窗口）"}
            for o in OPERATOR_REGISTRY
        ],
        "builtin": BUILTIN_OPS,
        "notes": [
            "全部算子由 alphalab 命名空间提供（与「因子检验」同一求值引擎），表达式可直接互用。",
            "窗口参数 n 必须 ≥ 1；负窗口（如 DELAY(CLOSE,-1)）在静态检查阶段即被标记 LEAKAGE 淘汰。",
            "除零、log 负数、sqrt 负数一律产生 NaN（缺失），后续缺失率检查会如实淘汰，不会伪造 0。",
        ],
    }
