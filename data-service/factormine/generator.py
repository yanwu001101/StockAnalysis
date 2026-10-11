# -*- coding: utf-8 -*-
"""候选因子自动生成：模板族 × 原子因子，硬性预算与去重。

搜索空间限制（防爆炸，用户可调预算，其余为硬上限）：
  MAX_DEPTH=4 / MAX_OPERATORS=6 / MAX_VARIABLES=5 / 窗口参数 ∈ 合法集合
  归一化表达式字符串去重 + 同族对称表达式剔除（X+X、X*X）。
方式：RANDOM_SEARCH / GRID_SEARCH（一次出全量候选）；BEAM_SEARCH 由 pipeline
分轮调用 build_stage_candidates（单因子 → 二因子 → 三因子，按快速 IC 反馈收窄）。
"""
from __future__ import annotations

import ast
import json
import random
from dataclasses import dataclass, field

from atoms import ATOMS

MAX_DEPTH = 4
MAX_OPERATORS = 6
MAX_VARIABLES = 5
MAX_WINDOW = 250

# 允许进入模板组合的原子。数学上重复/线性相关的原子不参与自动生成
# （ROC20 ≡ RETURN_20；KDJ_K/KDJ_D 是 KDJ_J 的线性组合——SKILL §6 指标不得
# 重复计权），仍保留在 atoms 目录中供手动表达式使用。
_GENERATION_EXCLUDED = {"ROC20", "KDJ_K", "KDJ_D"}
SEARCH_ATOMS = [a for a in ATOMS.keys() if a not in _GENERATION_EXCLUDED]

# 原子类别 → 时序变化窗口
_TS_WINDOWS = {
    "价格": (5, 20, 60), "收益": (5, 20), "均线": (5, 20), "成交量": (5, 10),
    "波动": (5, 20), "动量": (5, 10), "趋势": (5, 20),
    "相对强弱": (5, 20), "资金": (5, 10),
}

# 适合做条件触发的原子（有自然的多空含义）
_COND_ATOMS = [a for a in SEARCH_ATOMS if a.startswith(("RETURN", "ROC", "RSI", "MOMENTUM"))
               or a in ("MACD", "NET_MONEY_FLOW", "SUPER_LARGE_ORDER_FLOW", "MONEY_FLOW_CHANGE",
                        "MA_SLOPE20", "PRICE_MA_DISTANCE", "MA5_MA20_DISTANCE", "KDJ_J", "CCI14")]


def _windows(atom: str) -> tuple[int, ...]:
    spec = ATOMS.get(atom)
    cat = spec.category if spec else "价格"
    ws = _TS_WINDOWS.get(cat, (5, 20))
    return tuple(w for w in ws if w <= MAX_WINDOW)


@dataclass
class Candidate:
    expression: str
    normalized: str
    family: str            # 单因子/标准化/时序变化/二因子组合/条件因子/三因子组合
    operators: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)

    def meta(self) -> dict:
        return {"operator_list": ",".join(sorted(set(self.operators))),
                "source_factors": ",".join(self.variables),
                "category": self.family}


def normalize_expr(expr: str) -> str:
    """归一化表达式：去空白 + 全大写。原子与算子均注册了大写别名，
    同写法不同大小写/空格的表达式会得到同一键（语义等价的更深层去重
    由相关性聚类完成，如 Close/MA20-1 ≡ (Close-MA20)/MA20）。"""
    return "".join(expr.split()).upper()


def _ops_vars(expr: str) -> tuple[list[str], list[str]]:
    """从 AST 提取算子与变量名列表。"""
    ops: list[str] = []
    vars_: list[str] = []
    binop = {ast.Add: "ADD", ast.Sub: "SUB", ast.Mult: "MUL", ast.Div: "DIV",
             ast.Pow: "POW", ast.Mod: "MOD"}
    cmpop = {ast.Gt: "GT", ast.Lt: "LT", ast.GtE: "GTE", ast.LtE: "LTE",
             ast.Eq: "EQ", ast.NotEq: "NEQ"}
    for node in ast.walk(ast.parse(expr, mode="eval")):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            ops.append(node.func.id.upper())
        elif isinstance(node, ast.BinOp):
            ops.append(binop.get(type(node.op), "BIN"))
        elif isinstance(node, ast.Compare):
            ops.extend(cmpop.get(type(o), "CMP") for o in node.ops)
        elif isinstance(node, ast.BoolOp):
            ops.append("AND" if isinstance(node.op, ast.And) else "OR")
        elif isinstance(node, ast.UnaryOp):
            ops.append("NEG" if isinstance(node.op, ast.USub) else "UNARY")
        elif isinstance(node, ast.IfExp):
            ops.append("IF")
        elif isinstance(node, ast.Name) and node.id.isupper() and node.id in ATOMS:
            vars_.append(node.id)
    return ops, sorted(set(vars_))


def ast_to_json(expr: str) -> str | None:
    """表达式树 → JSON（持久化到 ast_json，支持复现/解释/查公式）。"""
    def conv(node):
        if isinstance(node, ast.Expression):
            return {"t": "Expression", "body": conv(node.body)}
        if isinstance(node, ast.BinOp):
            return {"t": "BinOp", "op": type(node.op).__name__,
                    "l": conv(node.left), "r": conv(node.right)}
        if isinstance(node, ast.UnaryOp):
            return {"t": "UnaryOp", "op": type(node.op).__name__, "v": conv(node.operand)}
        if isinstance(node, ast.Call):
            return {"t": "Call", "fn": node.func.id,
                    "args": [conv(a) for a in node.args]}
        if isinstance(node, ast.Name):
            return {"t": "Name", "id": node.id}
        if isinstance(node, ast.Constant):
            return {"t": "Const", "v": node.value}
        if isinstance(node, ast.Compare):
            return {"t": "Compare", "l": conv(node.left),
                    "ops": [type(o).__name__ for o in node.ops],
                    "cmp": [conv(c) for c in node.comparators]}
        if isinstance(node, ast.BoolOp):
            return {"t": "BoolOp", "op": type(node.op).__name__,
                    "vals": [conv(v) for v in node.values]}
        if isinstance(node, ast.IfExp):
            return {"t": "IfExp", "c": conv(node.test), "a": conv(node.body), "b": conv(node.orelse)}
        return {"t": type(node).__name__}

    try:
        return json.dumps(conv(ast.parse(expr, mode="eval")), ensure_ascii=False)
    except Exception:
        return None


def _check_limits(cand: Candidate) -> bool:
    """深度/算子数/变量数硬上限；对称无意义表达式（X+X、X*X）剔除。"""
    try:
        tree = ast.parse(cand.expression, mode="eval")
    except SyntaxError:
        return False

    def depth(n) -> int:
        kids = ast.iter_child_nodes(n)
        return 1 + max((depth(k) for k in kids), default=0)

    if depth(tree) > 2 * MAX_DEPTH:
        return False
    if len(set(cand.operators)) > MAX_OPERATORS or len(cand.variables) > MAX_VARIABLES:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
            l, r = node.left, node.right
            if ast.dump(l) == ast.dump(r) and isinstance(l, ast.Name):
                return False
        if isinstance(node, ast.Call):
            for a in node.args:
                if isinstance(a, ast.UnaryOp) and isinstance(a.op, ast.USub):
                    return False   # 生成器永不产负窗口（双保险，运行期另有守卫）
    return True


class Generator:
    def __init__(self, method: str, budget: int, seed: int,
                 atoms: list[str] | None = None):
        self.method = method
        self.budget = int(budget)
        self.rng = random.Random(seed)
        self.atoms = atoms or SEARCH_ATOMS   # pipeline 传入按数据可得性过滤后的子集
        self.seen: set[str] = set()
        self.made = 0

    def _push(self, out: list[Candidate], cand: Candidate) -> bool:
        norm = cand.normalized
        if norm in self.seen or self.made >= self.budget:
            return False
        cand.operators, cand.variables = _ops_vars(cand.expression)
        if not _check_limits(cand):
            self.seen.add(norm)   # 非法/重复结构也不再尝试
            return False
        self.seen.add(norm)
        self.made += 1
        out.append(cand)
        return True

    # -- 模板族 ------------------------------------------------------------
    def _stage_singles(self, out: list[Candidate]) -> None:
        for a in self.atoms:
            self._push(out, Candidate(a, normalize_expr(a), "单因子"))
            self._push(out, Candidate(f"rank({a})", normalize_expr(f"rank({a})"), "标准化因子"))
            self._push(out, Candidate(f"zscore({a})", normalize_expr(f"zscore({a})"), "标准化因子"))
        for a in self.atoms:
            for w in _windows(a):
                self._push(out, Candidate(f"delta({a},{w})",
                                          normalize_expr(f"delta({a},{w})"), "时序变化因子"))
                self._push(out, Candidate(f"pct_chg({a},{w})",
                                          normalize_expr(f"pct_chg({a},{w})"), "时序变化因子"))

    def _stage_pairs(self, out, atoms_a, atoms_b, cap: int | None = None) -> None:
        pairs: list[tuple[str, str]] = []
        for a in atoms_a:
            for b in atoms_b:
                if a != b:
                    pairs.append((a, b))
        if self.method == "random" and cap and len(pairs) > cap:
            pairs = self.rng.sample(pairs, cap)
        for a, b in pairs:
            self._push(out, Candidate(f"{a}*{b}", normalize_expr(f"{a}*{b}"), "二因子组合"))
            self._push(out, Candidate(f"{a}-{b}", normalize_expr(f"{a}-{b}"), "二因子组合"))
            self._push(out, Candidate(f"rank({a})*rank({b})",
                                      normalize_expr(f"rank({a})*rank({b})"), "二因子组合"))
            self._push(out, Candidate(f"zscore({a})-zscore({b})",
                                      normalize_expr(f"zscore({a})-zscore({b})"), "二因子组合"))
            self._push(out, Candidate(f"zscore({a})*rank({b})",
                                      normalize_expr(f"zscore({a})*rank({b})"), "二因子组合"))
            self._push(out, Candidate(f"delta(rank({a})-rank({b}),5)",
                                      normalize_expr(f"delta(rank({a})-rank({b}),5)"), "时序变化因子"))
            # 条件因子：动量/资金类原子作触发，成交/波动类原子作载荷
            if a in _COND_ATOMS:
                self._push(out, Candidate(f"IF({a}>0,{b},0)",
                                          normalize_expr(f"IF({a}>0,{b},0)"), "条件因子"))
                self._push(out, Candidate(f"IF({a}>0,rank({b}),0)",
                                          normalize_expr(f"IF({a}>0,rank({b}),0)"), "条件因子"))

    def _stage_triples(self, out, atoms, cap: int | None = None) -> None:
        combos: list[tuple[str, str, str]] = []
        for i, a in enumerate(atoms):
            for b in atoms[i + 1:]:
                for c in atoms:
                    if c not in (a, b):
                        combos.append((a, b, c))
        if self.method == "random" and cap and len(combos) > cap:
            combos = self.rng.sample(combos, cap)
        for a, b, c in combos:
            self._push(out, Candidate(f"rank({a})*rank({b})-rank({c})",
                                      normalize_expr(f"rank({a})*rank({b})-rank({c})"), "三因子组合"))
            self._push(out, Candidate(f"zscore({a})*zscore({b})-zscore({c})",
                                      normalize_expr(f"zscore({a})*zscore({b})-zscore({c})"), "三因子组合"))

    # -- 对外 --------------------------------------------------------------
    def build_all(self) -> list[Candidate]:
        """RANDOM / GRID：一次生成到预算。GRID 按原子字典序系统枚举，
        RANDOM 对二因子大集合随机采样（种子固定，可复现）。"""
        out: list[Candidate] = []
        self._stage_singles(out)
        if self.made < self.budget:
            self._stage_pairs(out, self.atoms, self.atoms,
                             cap=self.budget if self.method == "random" else None)
        if self.made < self.budget:
            self._stage_triples(out, self.atoms,
                                cap=self.budget if self.method == "random" else None)
        return out

    def build_stage(self, stage: int, top_atoms: list[str] | None = None) -> list[Candidate]:
        """BEAM：按轮生成，top_atoms 来自上一轮快速 IC 反馈。"""
        out: list[Candidate] = []
        if stage == 1:
            self._stage_singles(out)
        elif stage == 2:
            atoms = top_atoms or self.atoms[:20]
            self._stage_pairs(out, atoms, atoms)
        elif stage == 3:
            atoms = top_atoms or self.atoms[:10]
            self._stage_triples(out, atoms)
        return out
