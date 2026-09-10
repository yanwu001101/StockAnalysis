"""Prompt 策略 (设计文档 §4 AI 分析模块)。

约束: 输出必含 市场环境/资金方向/龙头判断/风险分析/明日观察/仓位建议 六节;
禁止 保证盈利/推荐必买/预测确定涨跌。
"""
from __future__ import annotations

import json

SYSTEM_REVIEW = """你是一位资深的A股短线复盘助手, 专注资金行为与情绪周期研究。

工作原则:
- 研究资金, 不是预测价格; 研究概率, 不是追求确定; 控制风险优先于盈利
- 只基于用户提供的数据推理, 不编造数据, 结论要引用具体数字
- 用简体中文 Markdown 输出

输出必须包含以下六个小节(用 ### 作小节标题, 顺序固定):
### 市场环境
### 资金方向
### 龙头判断
### 风险分析
### 明日观察
### 仓位建议

硬性禁止:
- 禁止保证盈利或承诺收益
- 禁止"必买""满仓梭哈"等确定性推荐
- 禁止预测确定性涨跌, 只能给概率化、条件化的判断(如"若竞价承接强则…否则…")
- 仓位建议只能给区间与触发条件, 并在小节末注明"仅供研究参考, 不构成投资建议"

全文控制在 600~900 字。"""

SYSTEM_STOCK = """你是一位资深的A股短线个股分析助手, 专注资金行为研究。

工作原则与禁令:
- 只基于用户提供的数据推理, 不编造数据
- 研究资金行为与概率, 不做确定性涨跌预测, 不保证盈利, 不给"必买"结论
- 用简体中文 Markdown 输出, 400~700 字

输出必须包含(### 小节):
### 资金行为解读
### 所处地位与题材环境
### 核心风险
### 后续观察要点
结尾注明"仅供研究参考, 不构成投资建议"。"""


def _yi(v) -> str:
    return f"{v / 1e8:.2f}亿" if isinstance(v, (int, float)) and v else "未知"


def build_review_payload(payload: dict) -> dict:
    """把完整分析结果裁剪成喂给 LLM 的紧凑 JSON (设计文档 §4 输入格式)。"""
    emo = payload["emotion"]
    theme = payload["theme"]
    ladder_slim = [
        {"height": lv["height"], "stocks": [s["name"] for s in lv["stocks"][:6]]}
        for lv in payload["ladder"]
        if lv["height"] >= 2
    ]
    first = next((lv["count"] for lv in payload["ladder"] if lv["height"] == 1), 0)
    cap = payload["capital"]
    return {
        "date": payload["date"],
        "market": {
            "indexes": payload["index"].get("indexes"),
            "两市成交额": _yi(payload["index"].get("amount")),
            emo.get("chg_label", "成交额环比"): (
                f"{emo['amount_chg'] * 100:+.1f}%" if emo.get("amount_chg") is not None else "未知"
            ),
            "上涨家数": emo.get("up"),
            "下跌家数": emo.get("down"),
            "limit_up": emo["zt_count"],
            "limit_down": emo["dt_count"],
        },
        "emotion": {
            "温度": emo["temperature"],
            "状态": emo["state"],
            "周期": emo["phase"],
            "判定依据": emo["phase_reasons"],
            "炸板率": emo.get("zb_rate"),
            "最高连板": emo["max_height"],
            "昨日涨停晋级率": emo.get("promote_rate"),
            "昨日涨停股今日平均涨幅": emo.get("prev_zt_avg_pct"),
        },
        "ladder": {"连板梯队": ladder_slim, "首板家数": first},
        "hot_themes": [
            {k: t[k] for k in ("name", "zt_count", "streak", "status", "score")}
            | {"leader": f"{t['leader']['name']}({t['leader']['height']}板)"}
            for t in theme["themes"][:5]
        ],
        "mainline": theme.get("mainline"),
        "dragons": [
            {k: d[k] for k in ("name", "code", "height", "theme", "score", "role", "pros", "risks")}
            for d in payload["dragons"][:5]
        ],
        "longhu": {
            "上榜家数": cap["summary"]["count"],
            "合计净买": _yi(cap["summary"]["total_net_buy"]),
            "游资活跃度": cap["summary"]["hot_money_activity"],
            "知名席位动向": cap["summary"]["famous_active"],
            "净买额前5": [
                f"{r['name']} {_yi(r['net_buy'])}" for r in cap["top_net_buy"][:5]
            ],
            "个股解读": [
                {k: s[k] for k in ("name", "capital_type", "attitude", "famous_buy")}
                for s in cap["stocks"][:5]
            ],
        },
    }


def build_review_prompt(payload: dict) -> tuple[str, str]:
    data = build_review_payload(payload)
    user = (
        "以下是今日A股复盘数据(JSON), 请生成今日复盘分析:\n\n```json\n"
        + json.dumps(data, ensure_ascii=False, indent=1)
        + "\n```"
    )
    return SYSTEM_REVIEW, user


def build_stock_prompt(info: dict) -> tuple[str, str]:
    user = (
        "以下是该股票的当日数据(JSON), 请生成个股资金行为分析:\n\n```json\n"
        + json.dumps(info, ensure_ascii=False, indent=1, default=str)
        + "\n```"
    )
    return SYSTEM_STOCK, user
