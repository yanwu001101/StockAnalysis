"""Node 3 — SentimentAnalystNode.

News & social sentiment. Polarity is a deterministic keyword score — never a
model call — so the number stays reproducible; the model, when configured,
only rewrites the wording.
"""
from __future__ import annotations

from app.domain.models import AgentId, AgentStatus, NewsItem, SentimentSnapshot
from app.agents.nodes._progress import emit

_POSITIVE_TERMS = (
    "利好",
    "增长",
    "超预期",
    "新高",
    "突破",
    "增持",
    "业绩预增",
    "分红",
    "回购",
    "中标",
    "扩产",
    "降息",
    "复苏",
    "获批",
    "扭亏",
)
_NEGATIVE_TERMS = (
    "利空",
    "下滑",
    "亏损",
    "减持",
    "处罚",
    "退市",
    "跌停",
    "爆雷",
    "诉讼",
    "下调",
    "低于预期",
    "降级",
    "停产",
    "问询",
    "违约",
)


def sentiment_node(state: dict) -> dict:
    deps = state["deps"]
    settings = deps.resolved()
    symbol = state["symbol"]

    emit(state, AgentId.SENTIMENT, AgentStatus.RUNNING, 0.30, "正在抓取新闻与舆情…")

    items: list[NewsItem] = []
    try:
        items = list(deps.market_data.fetch_news(symbol, settings.news_limit))
    except Exception as exc:  # noqa: BLE001
        emit(state, AgentId.SENTIMENT, AgentStatus.COMPLETED, 0.50, f"舆情源不可用：{exc}")

    polarity = score_polarity(items)
    snapshot = SentimentSnapshot(
        symbol=symbol,
        items=items,
        polarity=polarity,
        buzz=len(items),
        available=bool(items),
    )

    if not items:
        message = "未抓取到有效舆情，情绪评分按中性处理（不代表真的看平）"
    elif polarity > 0.15:
        message = f"舆情偏暖，{len(items)} 条信息中正面信号占优（极性 {polarity:+.2f}）"
    elif polarity < -0.15:
        message = f"舆情偏冷，{len(items)} 条信息中负面信号占优（极性 {polarity:+.2f}）"
    else:
        message = f"舆情中性，{len(items)} 条信息正负相当（极性 {polarity:+.2f}）"

    emit(state, AgentId.SENTIMENT, AgentStatus.COMPLETED, 0.50, message)
    return {"sentiment": snapshot}


def score_polarity(items: list[NewsItem]) -> float:
    """Signed term balance in [-1, 1]. No evidence -> 0.0, which is not "neutral"."""
    if not items:
        return 0.0
    positive = 0
    negative = 0
    for item in items:
        text = item.title
        positive += sum(text.count(term) for term in _POSITIVE_TERMS)
        negative += sum(text.count(term) for term in _NEGATIVE_TERMS)
    total = positive + negative
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (positive - negative) / total))
