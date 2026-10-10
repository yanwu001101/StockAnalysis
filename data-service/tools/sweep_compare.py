# -*- coding: utf-8 -*-
"""对比两次周度全策略体检结果，输出 markdown 表格与降级/升级清单。

用法: python _sweep_compare.py docs/weekly_sweep_2026-09.json docs/weekly_sweep_2026-10.json
判据沿用 2026-09 名单：🟢 需 |t|>=2 且 经济分级>=B 且 n>=12 且 |ICIR|>=0.3。
"""
import io
import json
import sys


def load(path):
    with io.open(path, encoding="utf-8") as f:
        d = json.load(f)
    items = d.get("items") if isinstance(d, dict) else d
    out = {}
    for it in items:
        sid = it.get("strategy_id") or it.get("id") or it.get("factor_name")
        if sid:
            out[sid] = it
    return out


def num(v):
    return v if isinstance(v, (int, float)) else None


def grade_ok(g):
    return isinstance(g, str) and g in ("A", "B")


def classify(it):
    if not it or it.get("error") or it.get("t") is None:
        return "⚪ 数据不足"
    t, n, icir, g = num(it.get("t")), num(it.get("n")), num(it.get("icir")), it.get("grade")
    if abs(t or 0) >= 2 and grade_ok(g) and (n or 0) >= 12 and abs(icir or 0) >= 0.3:
        return "🟢 加权"
    if abs(t or 0) >= 2:
        return "🟡 统计显著·经济性待验"
    if (t or 0) != 0 and abs(t) >= 1.4:
        return "🟠 边缘（|t|<2）"
    return "🔵 无证据"


def main():
    old = load(sys.argv[1] if len(sys.argv) > 1 else "docs/weekly_sweep_2026-09.json")
    new = load(sys.argv[2] if len(sys.argv) > 2 else "docs/weekly_sweep_2026-10.json")
    ids = sorted(set(old) | set(new), key=lambda s: -abs(num((new.get(s) or {}).get("t")) or 0))
    rows = []
    for sid in ids:
        o, n = old.get(sid) or {}, new.get(sid) or {}
        ot = num(o.get("t"))
        nt = num(n.get("t"))
        rows.append({
            "id": sid,
            "name": n.get("name") or o.get("name") or "",
            "ic_old": num(o.get("ic")), "ic_new": num(n.get("ic")),
            "t_old": ot, "t_new": nt,
            "n_old": o.get("n"), "n_new": n.get("n"),
            "codes_new": n.get("codes"),
            "grade_old": o.get("grade"), "grade_new": n.get("grade"),
            "conf_new": n.get("conf"), "mono_new": n.get("mono"),
            "net_new": n.get("net"), "el_new": n.get("el"),
            "dir_new": n.get("dir"),
            "state": classify(n),
            "state_old": classify(o),
            "dt": (round(nt - ot, 2) if (nt is not None and ot is not None) else None),
            "err_new": n.get("error"),
        })

    print("| 策略 | 旧 t | 新 t | Δt | 新 IC | n | 分级 | conf | mono | 净价差 | 换手 | 态(旧→新) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        f = lambda v, d=2: ("—" if v is None else (f"{v:.{d}f}" if isinstance(v, float) else str(v)))
        print("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} {} |".format(
            (r["name"] or r["id"]), f(r["t_old"]), f(r["t_new"]), f(r["dt"]),
            f(r["ic_new"], 4), r["n_new"] or "—", r["grade_new"] or "—",
            f(r["conf_new"], 1), f(r["mono_new"], 2),
            f((r["net_new"] * 100) if isinstance(r["net_new"], float) else None, 2) + "%",
            f(r["el_new"], 0), r["state_old"], r["state"]))
        if r["err_new"]:
            print("| ↳ 备注 | {}".format(r["err_new"]))

    changed = [r for r in rows if r["state_old"] != r["state"]]
    print("\n## 状态变化（{} 项）".format(len(changed)))
    for r in changed:
        print("- {}：{} → {}（t {}→{}）".format(r["name"] or r["id"], r["state_old"], r["state"],
                                               r["t_old"], r["t_new"]))
    green = [r for r in rows if r["state"].startswith("🟢")]
    print("\n🟢 满足加权判据的策略：{}。".format("、".join(r["name"] or r["id"] for r in green) or "无"))
    n2 = [r for r in rows if r["n_new"] and r["n_new"] < 12]
    print("样本期数 n<12 的策略（结论不得过度承诺）：{}。".format(
        "、".join("{}(n={})".format(r["name"] or r["id"], r["n_new"]) for r in n2) or "无"))


main()
