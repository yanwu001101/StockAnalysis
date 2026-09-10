"""龙头识别模块 (设计文档 §3.3)。

龙头评分 = 题材强度x30% + 连板高度x25% + 成交资金x20% + 市场辨识度x15% + 龙虎榜资金x10%
输出: 连板梯队 + 评分靠前的龙头候选 (含定位/优势/风险)。
"""
from __future__ import annotations

import config


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def _percentile(values: list[float], v: float) -> float:
    if not values:
        return 0.5
    return sum(1 for x in values if x <= v) / len(values)


def _parse_zt_stat(stat: str) -> tuple[int, int]:
    """'5/4' -> (5天, 4板); 解析失败返回 (0, 0)。"""
    try:
        days, boards = str(stat).split("/")
        return int(days), int(boards)
    except (ValueError, AttributeError):
        return 0, 0


def _norm_time(t: str) -> str:
    return str(t or "").replace(":", "").ljust(6, "0")[:6]


def build_ladder(zt: list[dict]) -> list[dict]:
    """连板梯队: [{height: 5, stocks: [...]}, ...] 高度降序。"""
    groups: dict[int, list[dict]] = {}
    for s in zt:
        groups.setdefault(s["height"], []).append(s)
    ladder = []
    for h in sorted(groups, reverse=True):
        stocks = sorted(groups[h], key=lambda x: -(x["amount"] or 0))
        ladder.append({"height": h, "count": len(stocks), "stocks": stocks})
    return ladder


def score_dragons(
    zt: list[dict],
    theme_scores: dict[str, float],
    lhb_by_code: dict[str, dict],
    famous_by_code: dict[str, list[str]],
    top_n: int = 10,
) -> list[dict]:
    """对连板股(全首板日取成交额前列)打分, 返回评分降序的龙头候选。"""
    if not zt:
        return []
    cands = [s for s in zt if s["height"] >= 2]
    if not cands:
        cands = sorted(zt, key=lambda x: -(x["amount"] or 0))[:top_n]

    amounts = [s["amount"] or 0 for s in zt]
    max_height = max(s["height"] for s in zt)
    theme_max = max(theme_scores.values()) if theme_scores else 0
    top_theme = max(theme_scores, key=theme_scores.get) if theme_scores else None
    w = config.DRAGON_WEIGHTS

    results = []
    for s in cands:
        days, boards = _parse_zt_stat(s.get("zt_stat"))
        freq = _clamp(boards / days) if days else 0.0
        seal_ratio = _clamp((s.get("seal_amount") or 0) / (s.get("amount") or 1) / 0.5)

        theme_sc = (theme_scores.get(s["industry"], 0) / theme_max) if theme_max else 0.5
        height_sc = s["height"] / max_height if max_height else 0.0
        amount_sc = _percentile(amounts, s["amount"] or 0)
        fame_sc = _clamp(0.5 * freq + 0.3 * min(s["height"] / 5, 1) + 0.2 * seal_ratio)

        lhb = lhb_by_code.get(s["code"])
        famous = famous_by_code.get(s["code"], [])
        if lhb and (lhb.get("lhb_amount") or 0) > 0:
            net_ratio = (lhb.get("net_buy") or 0) / lhb["lhb_amount"]
            lhb_sc = _clamp((net_ratio + 1) / 2 + (0.2 if famous else 0))
        else:
            lhb_sc = 0.4  # 未上榜, 中性略偏低

        score = round(
            100 * (
                w["theme"] * theme_sc
                + w["height"] * height_sc
                + w["amount"] * amount_sc
                + w["fame"] * fame_sc
                + w["lhb"] * lhb_sc
            )
        )

        pros: list[str] = []
        risks: list[str] = []
        if s["height"] == max_height and s["height"] >= 3:
            pros.append(f"{s['height']}连板市场最高度")
        elif s["height"] >= 2:
            pros.append(f"{s['height']}连板")
        if top_theme and s["industry"] == top_theme:
            pros.append("所属板块为当日主线")
        if seal_ratio >= 0.5:
            pros.append("封单坚决, 封成比高")
        if amount_sc >= 0.85:
            pros.append("成交居前, 大资金参与")
        if lhb and (lhb.get("net_buy") or 0) > 0:
            pros.append("龙虎榜资金净买入")
        if famous:
            pros.append(f"知名席位上榜: {'、'.join(famous[:3])}")
        if freq >= 0.6 and days >= 4:
            pros.append(f"近{days}日{boards}板, 辨识度高")

        if s["height"] >= 4:
            risks.append("高位股, 谨防加速赶顶后的分歧")
        if s.get("break_count"):
            risks.append(f"当日炸板{s['break_count']}次, 封板质量一般")
        if _norm_time(s.get("last_time")) >= "143000":
            risks.append("尾盘封板, 稳定性偏弱")
        if freq >= 0.6 and s["height"] >= 3:
            risks.append("获利盘丰厚, 注意兑现压力")
        if lhb and (lhb.get("net_buy") or 0) < 0:
            risks.append("龙虎榜净卖出, 资金存在分歧")
        if not risks:
            risks.append("关注竞价承接是否延续")

        results.append(
            {
                "code": s["code"],
                "name": s["name"],
                "theme": s["industry"],
                "height": s["height"],
                "amount": s["amount"],
                "score": score,
                "factors": {
                    "题材强度": round(theme_sc * 100),
                    "连板高度": round(height_sc * 100),
                    "成交资金": round(amount_sc * 100),
                    "市场辨识度": round(fame_sc * 100),
                    "龙虎榜资金": round(lhb_sc * 100),
                },
                "pros": pros,
                "risks": risks,
            }
        )

    results.sort(key=lambda x: -x["score"])
    results = results[:top_n]

    seen_theme: set[str] = set()
    for i, r in enumerate(results):
        if i == 0:
            r["role"] = "市场龙头" if r["height"] == max_height else "市场龙头候选"
        elif r["theme"] and r["theme"] not in seen_theme:
            r["role"] = "板块龙头"
        else:
            r["role"] = "梯队成员"
        if r["theme"]:
            seen_theme.add(r["theme"])
    return results
