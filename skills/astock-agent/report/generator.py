"""复盘报告生成器 (设计文档: 输出层 Markdown 报告)。"""
from __future__ import annotations

DISCLAIMER = (
    "\n\n---\n\n*免责声明: 本报告由 AStock-Agent 程序自动生成, 全部内容仅为公开数据整理与研究参考, "
    "不构成任何投资建议。游资席位风格标签来自民间公开统计, 可能存在误差。市场有风险, 交易需谨慎。*\n"
)

_POSITION_BY_PHASE = {
    "启动期": "2~4 成仓位试错新题材, 单票严格止损",
    "发酵期": "5~7 成仓位聚焦主线核心, 不碰杂毛跟风票",
    "高潮期": "降至 3 成以内, 只保留最核心龙头, 逢冲高兑现",
    "退潮期": "0~1 成观望, 空仓等待新周期, 不接力高位股",
    "震荡过渡期": "2~4 成机动仓位, 降低出手频率",
}


def _dash_date(date: str) -> str:
    return f"{date[:4]}-{date[4:6]}-{date[6:]}"


def yi(v) -> str:
    if not isinstance(v, (int, float)) or not v:
        return "-"
    if abs(v) >= 1e12:
        return f"{v / 1e12:.2f}万亿"
    return f"{v / 1e8:.1f}亿"


def pct(v) -> str:
    return f"{v:+.2f}%" if isinstance(v, (int, float)) else "-"


def _section_market(p: dict) -> list[str]:
    emo, idx = p["emotion"], p["index"]
    lines = ["## 一、市场环境", ""]
    if idx.get("indexes"):
        lines += ["| 指数 | 收盘 | 涨跌幅 |", "| --- | --- | --- |"]
        lines += [f"| {i['name']} | {i.get('close') or '-'} | {pct(i.get('pct'))} |" for i in idx["indexes"]]
        lines.append("")
    chg = emo.get("amount_chg")
    chg_txt = f"{emo.get('chg_label', '环比')} {chg * 100:+.1f}%" if chg is not None else ""
    if emo.get("amount"):
        lines.append(f"- 两市成交额 **{yi(emo['amount'])}**" + (f" ({chg_txt})" if chg_txt else ""))
    elif chg_txt:
        lines.append(f"- {chg_txt}")
    updown = ""
    if emo.get("up") is not None:
        updown = f", 上涨 {int(emo['up'])} 家 / 下跌 {int(emo['down'])} 家"
    lines.append(
        f"- 涨停 **{emo['zt_count']}** 家, 跌停 **{emo['dt_count']}** 家, "
        f"炸板 {emo['zb_count']} 家 (炸板率 {round((emo.get('zb_rate') or 0) * 100)}%){updown}"
    )
    if emo.get("promote_rate") is not None:
        lines.append(
            f"- 接力效应: 昨日涨停晋级率 **{round(emo['promote_rate'] * 100)}%**, "
            f"昨日涨停股今日平均 {pct(emo.get('prev_zt_avg_pct'))}"
        )
    lines.append(
        f"- 市场温度 **{emo['temperature']}/100** -> 状态 **{emo['state']}** · 情绪周期 **{emo['phase']}**"
    )
    lines.append("  - 温度构成: " + "; ".join(f"{k} {v}" for k, v in emo["components"].items()))
    lines.append("  - 周期依据: " + "; ".join(emo["phase_reasons"]))
    lines.append(f"  - 应对策略: {emo['strategy']}")
    return lines


def _section_ladder(p: dict) -> list[str]:
    lines = ["", "## 二、涨停梯队", ""]
    if not p["ladder"]:
        return lines + ["- 今日无涨停数据"]
    for lv in p["ladder"]:
        names = "、".join(f"{s['name']}({s['code']})" for s in lv["stocks"][:8])
        more = f" 等{lv['count']}只" if lv["count"] > 8 else ""
        if lv["height"] >= 2:
            lines.append(f"- **{lv['height']}板** ({lv['count']}只): {names}{more}")
        else:
            top5 = "、".join(f"{s['name']}" for s in lv["stocks"][:5])
            lines.append(f"- **首板** {lv['count']} 只 (成交额前5: {top5})")
    emo = p["emotion"]
    lines.append(
        f"- 市场高度 **{emo['max_height']}板** (昨日 {emo['prev_max_height']}板), 首板 {emo['first_boards']} 家"
    )
    return lines


def _section_theme(p: dict) -> list[str]:
    t = p["theme"]
    lines = ["", "## 三、板块主线与轮动", ""]
    ml = t.get("mainline")
    if ml:
        lines.append(
            f"当前主线: **{ml['name']}** · 状态 **{ml['status']}** · 持续性 {ml['persistence']} · "
            f"核心 {ml['leader']['name']}({ml['leader']['height']}板)"
        )
        lines.append(f"主线风险: {ml['risk']}")
        lines.append("")
    themes = t.get("themes", [])[:8]
    if themes:
        lines += [
            "| 板块 | 涨停数(昨) | 龙头 | 主力净流入 | 连续天数 | 强度 | 状态 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for x in themes:
            lines.append(
                f"| {x['name']} | {x['zt_count']}({x['prev_count']}) "
                f"| {x['leader']['name']}·{x['leader']['height']}板 | {yi(x['net_inflow'])} "
                f"| {x['streak']} | {x['score']} | {x['status']} |"
            )
        risk_lines = [f"{x['name']}: {r}" for x in themes for r in x["risks"][:1]]
        if risk_lines:
            lines.append("")
            lines.append("板块风险: " + "; ".join(risk_lines[:4]))
    return lines


def _section_dragon(p: dict) -> list[str]:
    lines = ["", "## 四、龙头评分", ""]
    if not p["dragons"]:
        return lines + ["- 今日无连板股, 缺乏龙头结构"]
    lines.append("评分模型: 题材强度30% + 连板高度25% + 成交资金20% + 市场辨识度15% + 龙虎榜资金10%")
    lines += ["", "| 股票 | 定位 | 评分 | 高度 | 板块 | 成交额 |", "| --- | --- | --- | --- | --- | --- |"]
    for d in p["dragons"]:
        lines.append(
            f"| {d['name']}({d['code']}) | {d['role']} | **{d['score']}** | {d['height']}板 "
            f"| {d['theme'] or '-'} | {yi(d['amount'])} |"
        )
    lines.append("")
    for d in p["dragons"][:5]:
        lines.append(f"**{d['name']}** ({d['score']}分 · {d['role']})")
        lines.append(f"- 优势: {'; '.join(d['pros']) or '-'}")
        lines.append(f"- 风险: {'; '.join(d['risks']) or '-'}")
    return lines


def _section_capital(p: dict) -> list[str]:
    cap = p["capital"]
    s = cap["summary"]
    lines = ["", "## 五、龙虎榜与游资动向", ""]
    if not s["count"]:
        return lines + ["- 当日无龙虎榜数据(或尚未公布, 一般收盘后 17:00~19:00 更新)"]
    lines.append(
        f"- 上榜 **{s['count']}** 家, 合计净买 **{yi(s['total_net_buy'])}**, "
        f"知名游资活跃度: **{s['hot_money_activity']}**"
    )
    for f in s["famous_active"][:6]:
        lines.append(f"- {f['trader']}: 买入 {'、'.join(f['stocks'][:4])}")
    if cap["top_net_buy"]:
        lines += ["", "| 净买额前列 | 涨跌幅 | 净买额 | 上榜原因 |", "| --- | --- | --- | --- |"]
        for r in cap["top_net_buy"][:8]:
            lines.append(f"| {r['name']}({r['code']}) | {pct(r['pct'])} | {yi(r['net_buy'])} | {(r['reason'] or '')[:18]} |")
    if cap["stocks"]:
        lines.append("")
        lines.append("席位解读(净买额靠前个股):")
        for x in cap["stocks"][:8]:
            famous = f", 买方知名席位: {'、'.join(x['famous_buy'][:3])}" if x["famous_buy"] else ""
            risk = f" 风险: {x['risks'][0]}" if x["risks"] else ""
            lines.append(
                f"- **{x['name']}**: {x['capital_type']} · {x['attitude']} · 净买 {yi(x['net_buy'])}{famous}.{risk}"
            )
    return lines


def _section_risk(p: dict) -> list[str]:
    emo = p["emotion"]
    risks: list[str] = []
    if emo["phase"] in ("高潮期", "退潮期"):
        risks.append(f"情绪处于{emo['phase']}, 接力容错率低, 谨防高位股集体分歧")
    if (emo.get("zb_rate") or 0) > 0.3:
        risks.append(f"炸板率 {round(emo['zb_rate'] * 100)}% 偏高, 封板质量差, 打板胜率下降")
    if emo["dt_count"] >= 15:
        risks.append(f"跌停 {emo['dt_count']} 家, 亏钱效应扩散, 注意规避问题股与高位补跌")
    if emo.get("promote_rate") is not None and emo["promote_rate"] < 0.2:
        risks.append(f"晋级率仅 {round(emo['promote_rate'] * 100)}%, 接力赚钱效应弱")
    if emo.get("amount_chg") is not None and emo["amount_chg"] < -0.1:
        risks.append(f"成交额环比缩量 {abs(round(emo['amount_chg'] * 100))}%, 资金参与度下降")
    for d in p["dragons"][:3]:
        if d["height"] >= 5:
            risks.append(f"高度股 {d['name']} 已 {d['height']} 板, 若断板将压制整体情绪")
            break
    for t in p["theme"].get("themes", [])[:3]:
        for r in t["risks"][:1]:
            risks.append(f"{t['name']}: {r}")
    if not risks:
        risks.append("暂无系统性风险信号, 保持正常节奏, 关注量能与主线聚焦度变化")
    return ["", "## 六、风险提示", ""] + [f"- {r}" for r in risks[:8]]


def _section_watch(p: dict) -> list[str]:
    emo = p["emotion"]
    lines = ["", "## 七、明日观察计划", ""]
    ml = p["theme"].get("mainline")
    if ml:
        lines.append(
            f"- **主线跟踪**: {ml['name']} (状态 {ml['status']}), 核心 {ml['leader']['name']}"
            f"({ml['leader']['height']}板), 看竞价能否继续聚焦资金"
        )
    if p["dragons"]:
        tops = "、".join(f"{d['name']}({d['height']}板/{d['score']}分)" for d in p["dragons"][:3])
        lines.append(f"- **龙头接力**: {tops} —— 高标竞价承接决定明日接力环境")
    zb_active = sorted(p["zb"], key=lambda x: -(x.get("amount") or 0))[:3]
    if zb_active:
        lines.append(
            "- **反包观察**: " + "、".join(s["name"] for s in zb_active)
            + " (炸板股中成交活跃者, 若明日快速修复可能有反包资金)"
        )
    dt_themes = {}
    for s in p["dt"]:
        if s.get("industry"):
            dt_themes[s["industry"]] = dt_themes.get(s["industry"], 0) + 1
    avoid = [k for k, v in sorted(dt_themes.items(), key=lambda kv: -kv[1]) if v >= 2][:3]
    if avoid:
        lines.append(f"- **规避方向**: 跌停集中板块 {'、'.join(avoid)}, 以及连续加速后的高位断板股")
    lines.append(f"- **仓位参考** ({emo['phase']}): {_POSITION_BY_PHASE[emo['phase']]} *(仅供研究参考)*")
    return lines


def render_daily(p: dict, ai_text: str | None) -> str:
    emo = p["emotion"]
    head = [
        f"# A股游资复盘报告 · {_dash_date(p['date'])}",
        "",
        f"> 情绪温度 **{emo['temperature']}/100** · 市场状态 **{emo['state']}** · "
        f"情绪周期 **{emo['phase']}** · 市场高度 **{emo['max_height']}板**",
        "",
    ]
    if p.get("note"):
        head.append(f"> 说明: {p['note']}")
        head.append("")
    body = (
        _section_market(p)
        + _section_ladder(p)
        + _section_theme(p)
        + _section_dragon(p)
        + _section_capital(p)
        + _section_risk(p)
        + _section_watch(p)
    )
    tail = ["", "## 八、AI 复盘观点", ""]
    if ai_text:
        tail.append(ai_text)
    else:
        tail.append("*(未配置 LLM API Key 或调用失败, 本报告为纯规则引擎生成。"
                    "配置环境变量 ASTOCK_LLM_API_KEY 后可启用 AI 复盘。)*")
    return "\n".join(head + body + tail) + DISCLAIMER


def _fmt_time(t) -> str:
    s = str(t or "").replace(":", "")
    return f"{s[:2]}:{s[2:4]}:{s[4:6]}" if len(s) >= 6 else (str(t) or "-")


def render_stock(info: dict, ai_text: str | None) -> str:
    lines = [
        f"# 个股资金分析 · {info['name']}({info['code']}) · {_dash_date(info['date'])}",
        "",
    ]
    zt = info.get("zt")
    if zt:
        turnover = f"{zt['turnover']:.2f}" if isinstance(zt.get("turnover"), (int, float)) else "-"
        lines += [
            f"- 涨停表现: **{zt['height']}连板**, 涨停统计 {zt['zt_stat'] or '-'}, "
            f"首次封板 {_fmt_time(zt['first_time'])}, 炸板 {zt['break_count']} 次",
            f"- 成交额 {yi(zt['amount'])}, 封单 {yi(zt['seal_amount'])}, 换手 {turnover}%",
            f"- 所属板块: {zt['industry'] or '-'}",
        ]
    else:
        lines.append("- 当日未涨停")
    dragon = info.get("dragon")
    if dragon:
        lines.append(
            f"- 龙头评分: **{dragon['score']}** ({dragon['role']}), "
            f"因子: {', '.join(f'{k}{v}' for k, v in dragon['factors'].items())}"
        )
    theme = info.get("theme")
    if theme:
        lines.append(
            f"- 板块环境: {theme['name']} 涨停 {theme['zt_count']} 家, 状态 {theme['status']}, "
            f"强度 {theme['score']}, 连续 {theme['streak']} 天"
        )
    cap = info.get("capital")
    lines.append("")
    lines.append("## 龙虎榜席位")
    if cap:
        lines.append(
            f"- 资金类型 **{cap['capital_type']}** · 态度 **{cap['attitude']}** · "
            f"净买 {yi(cap['net_buy'])} ({cap['reason'] or '-'})"
        )
        if cap["famous_buy"]:
            lines.append(f"- 买方知名席位: {'、'.join(cap['famous_buy'])}")
        if cap["famous_sell"]:
            lines.append(f"- 卖方知名席位: {'、'.join(cap['famous_sell'])}")
        for r in cap["risks"]:
            lines.append(f"- 风险: {r}")
        seats = info.get("seats") or {}
        for key, title in (("buy", "买五席位"), ("sell", "卖五席位")):
            rows = seats.get(key) or []
            if rows:
                lines += ["", f"**{title}**", "", "| 席位 | 买入 | 卖出 | 净额 |", "| --- | --- | --- | --- |"]
                lines += [
                    f"| {s['seat'][:24]} | {yi(s['buy'])} | {yi(s['sell'])} | {yi(s['net'])} |"
                    for s in rows[:5]
                ]
    else:
        lines.append("- 当日未上龙虎榜")
    lines += ["", "## AI 观点", ""]
    lines.append(ai_text or "*(未配置 LLM API Key, 本节略。)*")
    return "\n".join(lines) + DISCLAIMER
