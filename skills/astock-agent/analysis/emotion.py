"""情绪周期模块 (设计文档 §3.1 市场温度 + §3.5 情绪周期)。

市场温度 = 涨停强度 + 上涨比例 + 成交额变化 + 封板质量 - 跌停惩罚 (0~100)
情绪阶段 = 启动期 / 发酵期 / 高潮期 / 退潮期 / 震荡过渡期 (规则判定, 附依据)
"""
from __future__ import annotations

import config


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def compute_temperature(
    zt_count: int,
    dt_count: int,
    up: float | None,
    down: float | None,
    amount_chg: float | None,
    chg_label: str,
    zb_rate: float | None,
) -> tuple[int, dict]:
    """市场温度 0~100。缺失分量自动按剩余权重归一化。"""
    parts: list[tuple[float, float]] = []  # (得分0~1, 权重)
    comps: dict[str, str] = {}

    zt_sc = _clamp(zt_count / 120)
    parts.append((zt_sc, 40))
    comps["涨停强度"] = f"{zt_count} 家 -> {round(zt_sc * 40)}/40"

    if up is not None and down is not None and (up + down) > 0:
        ratio = up / (up + down)
        parts.append((ratio, 25))
        comps["上涨比例"] = f"{round(ratio * 100)}% -> {round(ratio * 25)}/25"

    if amount_chg is not None:
        amt_sc = _clamp(0.5 + amount_chg * 2.5)
        parts.append((amt_sc, 15))
        comps[chg_label] = f"{round(amount_chg * 100, 1)}% -> {round(amt_sc * 15)}/15"

    if zb_rate is not None:
        seal_sc = _clamp(1 - zb_rate * 1.6)
        parts.append((seal_sc, 20))
        comps["封板质量"] = f"炸板率 {round(zb_rate * 100)}% -> {round(seal_sc * 20)}/20"

    raw = sum(s * w for s, w in parts) / sum(w for _, w in parts) * 100
    penalty = _clamp(dt_count / 40) * 15
    comps["跌停惩罚"] = f"{dt_count} 家 -> -{round(penalty)}"
    temp = int(round(_clamp(raw - penalty, 0, 100)))
    return temp, comps


def market_state(temp: int) -> str:
    if temp >= config.TEMP_STRONG:
        return "强势"
    if temp >= config.TEMP_RANGE:
        return "震荡"
    if temp >= config.TEMP_WEAK:
        return "弱势"
    return "退潮"


_STRATEGY = {
    "启动期": "新题材试错窗口, 积极关注新主线与首板龙头, 小仓位打先手",
    "发酵期": "参与主线核心, 聚焦龙头与卡位股, 避免杂毛跟风票",
    "高潮期": "情绪亢奋, 降低仓位兑现为主, 只保留最核心龙头, 不追高位跟风",
    "退潮期": "空仓或极轻仓等待, 不接力高位股, 等情绪冰点后的新周期",
    "震荡过渡期": "方向不明, 控制出手频率, 轻仓跟踪主线是否重新聚焦",
}


def analyze(
    zt: list[dict],
    dt_pool: list[dict],
    zb: list[dict],
    activity: dict | None,
    index_snap: dict,
    prev_zt: list[dict],
    prev_perf: dict,
    history: list[dict],
) -> dict:
    """综合当日数据 + 前一交易日对比 + 历史快照, 输出情绪分析结果。"""
    zt_count = int((activity or {}).get("real_zt") or len(zt))
    dt_count = int((activity or {}).get("real_dt") or len(dt_pool))
    up = (activity or {}).get("up")
    down = (activity or {}).get("down")

    amount = index_snap.get("amount")
    amount_chg = index_snap.get("amount_chg")
    chg_label = "量能环比" if index_snap.get("chg_basis") == "volume" else "成交额环比"

    zb_rate = len(zb) / (len(zb) + len(zt)) if (zt or zb) else None

    temp, comps = compute_temperature(
        zt_count, dt_count, up, down, amount_chg, chg_label, zb_rate
    )
    state = market_state(temp)

    max_height = max((s["height"] for s in zt), default=0)
    prev_max_height = max((s["height"] for s in prev_zt), default=0)
    first_boards = sum(1 for s in zt if s["height"] == 1)
    prev_zt_count = len(prev_zt)

    promote_rate = None
    if prev_perf.get("codes"):
        today_codes = {s["code"] for s in zt}
        promote_rate = round(
            sum(1 for c in prev_perf["codes"] if c in today_codes) / len(prev_perf["codes"]), 3
        )
    prev_avg_pct = prev_perf.get("avg_pct")

    prev_temp = None
    if history:
        before = [h for h in history if h.get("temperature") is not None]
        if before:
            prev_temp = before[-1]["temperature"]

    # ------------------------------------------------------------------
    # 阶段判定 (规则优先级从高到低), 每条结论附依据
    # ------------------------------------------------------------------
    reasons: list[str] = []
    falling_height = 0 < max_height < prev_max_height
    rising_zt = zt_count > prev_zt_count > 0
    weak_carry = (promote_rate is not None and promote_rate < 0.18) or (
        prev_avg_pct is not None and prev_avg_pct < -1.5
    )
    good_carry = (promote_rate or 0) >= 0.25 and (prev_avg_pct or 0) >= 0

    if (falling_height and weak_carry) or (zt_count and dt_count >= max(20, zt_count * 0.6)):
        phase = "退潮期"
        if falling_height:
            reasons.append(f"连板高度回落 {prev_max_height}板 -> {max_height}板")
        if promote_rate is not None and promote_rate < 0.18:
            reasons.append(f"昨日涨停晋级率仅 {round(promote_rate * 100)}%")
        if prev_avg_pct is not None and prev_avg_pct < -1.5:
            reasons.append(f"昨日涨停股今日平均 {prev_avg_pct}%, 亏钱效应明显")
        if dt_count >= 20:
            reasons.append(f"跌停 {dt_count} 家, 大面频出")
    elif temp >= config.TEMP_STRONG and max_height >= 5 and (
        (zb_rate or 0) > 0.28 or first_boards >= 45
    ):
        phase = "高潮期"
        reasons.append(f"温度 {temp}, 高度 {max_height}板, 首板 {first_boards} 家跟风放量")
        if (zb_rate or 0) > 0.28:
            reasons.append(f"炸板率 {round((zb_rate or 0) * 100)}%, 分歧加大")
    elif good_carry and max_height >= prev_max_height and temp >= config.TEMP_RANGE:
        phase = "发酵期"
        reasons.append(f"晋级率 {round((promote_rate or 0) * 100)}%, 接力有赚钱效应")
        reasons.append(f"高度维持/抬升: {prev_max_height}板 -> {max_height}板")
    elif rising_zt and prev_temp is not None and prev_temp < config.TEMP_RANGE and temp >= prev_temp + 8:
        phase = "启动期"
        reasons.append(f"温度自低位回升 {prev_temp} -> {temp}, 涨停家数放大")
    elif prev_temp is None and temp >= config.TEMP_STRONG and max_height >= 3:
        phase = "发酵期"
        reasons.append("无历史快照, 按当日强度判定: 温度高 + 有高度")
    else:
        phase = "震荡过渡期"
        reasons.append(f"温度 {temp}, 方向信号不明确")
        if promote_rate is not None:
            reasons.append(f"晋级率 {round(promote_rate * 100)}%")

    return {
        "temperature": temp,
        "components": comps,
        "state": state,
        "phase": phase,
        "phase_reasons": reasons,
        "strategy": _STRATEGY[phase],
        "zt_count": zt_count,
        "dt_count": dt_count,
        "zb_count": len(zb),
        "zb_rate": round(zb_rate, 3) if zb_rate is not None else None,
        "up": up,
        "down": down,
        "amount": amount,
        "amount_chg": round(amount_chg, 4) if amount_chg is not None else None,
        "chg_label": chg_label,
        "max_height": max_height,
        "prev_max_height": prev_max_height,
        "first_boards": first_boards,
        "promote_rate": promote_rate,
        "prev_zt_avg_pct": prev_avg_pct,
        "activity": (activity or {}).get("activity"),
    }
