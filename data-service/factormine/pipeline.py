# -*- coding: utf-8 -*-
"""因子挖掘管线。

阶段（用户可见的「研究过程」漏斗，逐级计数写入 job progress）：
  GENERATE   候选生成（模板族×原子，预算硬上限，归一化去重）
  STATIC     表达式合法性 + 负窗口静态泄漏扫描（LEAKAGE 即淘汰）
  QUICK      逐候选向量化求值 → 覆盖率/方差检查 → 多 horizon 快速 IC/RankIC/ICIR
             → 透明门槛（|RankIC|≥min_ic 且 |ICIR|≥0.15）→ 按 |RankIC| 保留前 keep_pct
  DEDUP      幸存者 Spearman 相关聚类（|corr|≥0.85 归簇，含与已入库因子比对），每簇取最优
  VALIDATE   簇代表进 factorlab.analyze_scores 完整检验（IC/RankIC/ICIR/分层/衰减/
             牛熊/行业中性/评级，与内置策略同一引擎）→ 样本内/外拆分、年度稳定性、
             Walk Forward（Top-K）、成本敏感性 → 客观判定 PASS / WATCH / REJECT

时间语义（SKILL §22，无未来函数）：
  * 因子值 = t 日收盘可知（所有算子向后窗口，负窗口静态+运行期双层拦截）；
  * IC 目标 = val_close[t+h] / val_close[t] − 1（h 个交易日后收盘）；
  * 停牌（volume==0）与上市不足 N 日的股票从截面中剔除（eligibility mask）；
  * 组合执行语义由 alphalab.backtest_expr / backtest.engine 保证 t+1 开盘成交。

性能：面板一次加载裁剪到宇宙；原子懒加载缓存全任务共享；前向收益按 horizon
预计算一次；每候选只做几次面板级向量化运算；逐候选 checkpoint 落库（断点续跑）。
"""
from __future__ import annotations

import datetime as dt
import json
import time

import numpy as np
import pandas as pd
from sqlalchemy import text

import alphalab
import atoms as atoms_mod
import db
from backtest import engine
from core.trace import logger
from factorlab import ENGINE_VERSION, _ic_summary_block, _pearson_ic, _rank_ic, _winsorize_zscore

from factormine import repo
from factormine.generator import Candidate, Generator, ast_to_json, normalize_expr
from factormine.generator import SEARCH_ATOMS as gen_SEARCH_ATOMS

QUICK_DATES_CAP = 120          # 快速 IC 最多抽样的调仓日数
DEDUP_DATES = 30               # 相关性比对使用的抽样日期数
QUICK_CHECKPOINT_EVERY = 20    # 快速阶段批量落库间隔（个）
QUICK_CHECKPOINT_S = 5.0       # 快速阶段批量落库间隔（秒）
EARLY_ABORT_DATES = 25         # 主 horizon 预检日期数（快速淘汰明显无效因子）
EARLY_ABORT_FACTOR = 3.0       # 预检 |IC| 低于 min_ic/该倍数 → 提前淘汰

REASON_INVALID = "表达式无效"
REASON_LEAKAGE = "未来函数"
REASON_MISSING = "数据缺失率过高"
REASON_ZEROVAR = "因子无区分度（零方差）"
REASON_QUICK = "快速筛选未达标"
REASON_DEDUP = "与高相关因子重复"
REASON_FULL = "完整检验未通过"


def _has_stat(value) -> bool:
    return value is not None and bool(np.isfinite(value))


def _abs_at_least(value, threshold: float) -> bool:
    return _has_stat(value) and abs(value) >= threshold


def _round_stat(value, digits: int):
    return round(value, digits) if _has_stat(value) else None


def _fmt_stat(value, digits: int = 2) -> str:
    return f"{value:.{digits}f}" if _has_stat(value) else "—"


class PauseRequested(Exception):
    pass


class CancelRequested(Exception):
    pass


class Control:
    """jobs.py 注入的暂停/取消信号。"""

    def __init__(self):
        self.pause = False
        self.cancel = False

    def check(self):
        if self.cancel:
            raise CancelRequested()
        if self.pause:
            raise PauseRequested()


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

class MiningConfig:
    """挖掘配置（API 层已做范围校验；这里给默认值与派生量）。"""

    def __init__(self, raw: dict):
        today = dt.date.today()
        self.market: list[str] = raw.get("market") or ["hs"]
        self.exclude_st: bool = bool(raw.get("exclude_st", True))
        self.exclude_delisting: bool = bool(raw.get("exclude_delisting", True))
        self.exclude_suspended: bool = bool(raw.get("exclude_suspended", True))
        self.min_listed_days: int = int(raw.get("min_listed_days", 120))
        self.start_date = dt.date.fromisoformat(str(raw.get("start_date") or (today - dt.timedelta(days=730)))[:10])
        self.end_date = dt.date.fromisoformat(str(raw.get("end_date") or today.isoformat())[:10])
        horizons = raw.get("horizons") or [1, 5, 10, 20]
        self.horizons: tuple[int, ...] = tuple(sorted({int(h) for h in horizons if 1 <= int(h) <= 60}))
        self.rebalance: str = raw.get("rebalance") or "5d"
        if self.rebalance.endswith("d") and self.rebalance[:-1].isdigit():
            pass
        elif self.rebalance not in ("daily", "weekly", "monthly"):
            self.rebalance = "5d"
        self.budget: int = int(raw.get("budget") or 500)
        self.method: str = raw.get("method") or "random"
        if self.method not in ("random", "grid", "beam"):
            self.method = "random"
        self.max_codes: int = int(raw.get("max_codes") or 300)
        self.layers: int = max(2, min(int(raw.get("layers") or 5), 10))
        self.neutralize: bool = bool(raw.get("neutralize", True))
        self.keep_pct: float = min(max(float(raw.get("keep_pct") or 0.2), 0.05), 0.5)
        self.max_missing_rate: float = min(max(float(raw.get("max_missing_rate") or 0.6), 0.2), 0.95)
        self.dedup_threshold: float = min(max(float(raw.get("dedup_threshold") or 0.85), 0.5), 0.99)
        self.full_validate_limit: int = int(raw.get("full_validate_limit") or 60)
        self.oos_ratio: float = min(max(float(raw.get("oos_ratio") or 0.25), 0.1), 0.5)
        self.wf_top_k: int = int(raw.get("wf_top_k") or 10)
        self.wf_test_years: float = max(float(raw.get("wf_test_years") or 1.0), 0.5)
        self.seed: int = int(raw.get("seed") or 20260919)
        # 客观判定阈值（页面公开展示，可调）
        th = raw.get("thresholds") or {}
        self.min_ic: float = float(th.get("min_ic", 0.02))
        self.min_icir: float = float(th.get("min_icir", 0.3))
        self.min_t: float = float(th.get("min_t", 2.0))
        self.min_periods: int = int(th.get("min_periods", 12))
        self.min_oos_ic: float = float(th.get("min_oos_ic", 0.01))

    def core_hash(self) -> str:
        """影响数据口径的配置子集（缓存 key 的一部分）。"""
        core = {
            "engine_version": ENGINE_VERSION,
            "layers": self.layers, "neutralize": self.neutralize,
            "oos_ratio": self.oos_ratio,
            "market": sorted(self.market), "st": self.exclude_st, "dl": self.exclude_delisting,
            "sus": self.exclude_suspended, "mld": self.min_listed_days,
            "s": self.start_date.isoformat(), "e": self.end_date.isoformat(),
            "h": list(self.horizons), "rb": self.rebalance, "mc": self.max_codes,
        }
        return json.dumps(core, sort_keys=True, ensure_ascii=False)

    def public(self) -> dict:
        return {
            "market": self.market, "exclude_st": self.exclude_st,
            "exclude_delisting": self.exclude_delisting, "exclude_suspended": self.exclude_suspended,
            "min_listed_days": self.min_listed_days, "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(), "horizons": list(self.horizons),
            "rebalance": self.rebalance, "budget": self.budget, "method": self.method,
            "max_codes": self.max_codes, "layers": self.layers, "neutralize": self.neutralize,
            "keep_pct": self.keep_pct, "max_missing_rate": self.max_missing_rate,
            "dedup_threshold": self.dedup_threshold, "full_validate_limit": self.full_validate_limit,
            "oos_ratio": self.oos_ratio, "wf_top_k": self.wf_top_k,
            "wf_test_years": self.wf_test_years, "seed": self.seed,
            "thresholds": {"min_ic": self.min_ic, "min_icir": self.min_icir, "min_t": self.min_t,
                           "min_periods": self.min_periods, "min_oos_ic": self.min_oos_ic},
        }


_MARKET_PREFIXES = {
    "hs": ("60", "00", "30", "68"),    # 沪深 A 股（含创业板/科创板）
    "cyb": ("30", "68"),               # 创业板
    "kcb": ("68",),                    # 科创板
    "bjs": ("43", "83", "87", "92"),   # 北交所
}


def _board_ok(code: str, markets: list[str]) -> bool:
    c = str(code).zfill(6)
    for m in markets:
        if c.startswith(_MARKET_PREFIXES.get(m, ())):
            return True
    return False


# ---------------------------------------------------------------------------
# 管线主体
# ---------------------------------------------------------------------------

class MiningPipeline:
    def __init__(self, job_id: str, config: MiningConfig, control: Control):
        self.job_id = job_id
        self.cfg = config
        self.ctl = control
        self.progress = repo._empty_progress()
        self._last_ckpt = 0.0
        self._vec_by_id: dict[str, np.ndarray] = {}   # QUICK_PASS 幸存者降维向量
        self._wf_used = 0                              # Walk Forward 名额
        # 准备阶段产物
        self.panel: dict[str, pd.DataFrame] = {}
        self.ns = None
        self.eligibility: pd.DataFrame | None = None
        self.rebal_dates: list[dt.date] = []
        self.quick_dates: list[dt.date] = []
        self.fwd: dict[int, pd.DataFrame] = {}
        self.dedup_dates: list[dt.date] = []
        self.is_split: dt.date | None = None
        self.date_pos: dict[dt.date, int] = {}
        self.library_vecs: list[tuple[str, np.ndarray]] = []

    # ---- 进度 ----
    def _bump(self, **kw):
        self.progress.update({k: self.progress.get(k, 0) + v for k, v in kw.items()
                              if isinstance(v, int)})

    def _checkpoint(self, phase: str, force: bool = False):
        now = time.time()
        if force or now - self._last_ckpt >= QUICK_CHECKPOINT_S:
            self._last_ckpt = now
            repo.update_progress(self.job_id, self.progress, phase)

    def _flush_quick_rows(self, rows: list[dict]):
        if rows:
            repo.update_factors_bulk(rows)
            rows.clear()
            self._checkpoint("QUICK")

    # ---- 阶段 0：数据准备 ----
    def prepare(self) -> None:
        cfg = self.cfg
        trading_days = engine._trading_days(cfg.start_date, cfg.end_date)
        if len(trading_days) < 60:
            raise ValueError(f"研究区间交易日不足（{len(trading_days)} < 60），请扩大时间范围")
        panel_full = atoms_mod.build_extended_panel(cfg.start_date, cfg.end_date)
        if not panel_full or "close" not in panel_full:
            raise ValueError("行情面板为空——请先运行数据刷新（后台任务/预热）")
        close_all = panel_full["close"]

        # 市场板块过滤
        cols = [c for c in close_all.columns if _board_ok(c, cfg.market)]
        if len(cols) < 50:
            raise ValueError(f"所选市场板块内股票过少（{len(cols)}），请检查板块选择")

        # ST / 退市整理过滤（按股票名称）
        name_map = _stock_names()
        if cfg.exclude_st or cfg.exclude_delisting:
            def _bad(name: str) -> bool:
                n = (name or "").upper()
                return (cfg.exclude_st and ("ST" in n)) or \
                       (cfg.exclude_delisting and ("退" in (name or "")))
            cols = [c for c in cols if not _bad(name_map.get(c, ""))]

        # 流动性宇宙（日均成交额，缺失用 close×volume 代理）
        if "amount" in panel_full and panel_full["amount"] is not None and not panel_full["amount"].empty:
            liq_src = panel_full["amount"][cols] if cols else panel_full["amount"]
        else:
            liq_src = close_all[cols] * panel_full["volume"][cols]
        liq = liq_src.mean().sort_values(ascending=False)
        universe = [c for c in liq.dropna().head(cfg.max_codes).index if c in close_all.columns]
        if len(universe) < 50:
            raise ValueError(f"流动性宇宙过小（{len(universe)}），请放宽时间范围或市场过滤")

        self.panel = atoms_mod.restrict_panel(panel_full, universe)
        self.ns = alphalab._make_namespace(self.panel)   # 原子懒加载缓存，全任务共享
        close = self.panel["close"]
        volume = self.panel["volume"]

        # eligibility：上市满 N 日 + 未停牌（无未来数据：都用 <= t 的信息）
        # 「上市日」以 K 线全表首次交易日为准（股票静态事实，非未来数据）：
        # 面板开始前已有 >= N 条记录的视为老股直接通过；面板内才出现的数据
        # （次新/新股）按面板内位置预热 N 个交易日。
        listed_mask = pd.DataFrame(True, index=close.index, columns=close.columns)
        if cfg.min_listed_days > 0:
            day_pos = np.arange(len(close.index))
            first_pos = _panel_first_pos(close)
            listed_arr = np.zeros((len(close.index), len(close.columns)), dtype=bool)
            first_dates, pre_rows = _kline_history(cfg.start_date)
            codes_arr = list(close.columns)
            for j, code in enumerate(codes_arr):
                fd = first_dates.get(code)
                if fd is not None and fd < cfg.start_date and pre_rows.get(code, 0) >= cfg.min_listed_days:
                    listed_arr[:, j] = True
                else:
                    listed_arr[:, j] = (day_pos - first_pos[j]) >= cfg.min_listed_days
            listed_mask = pd.DataFrame(listed_arr, index=close.index, columns=close.columns)
        if cfg.exclude_suspended:
            self.eligibility = listed_mask & close.notna() & (volume.fillna(0) > 0)
        else:
            self.eligibility = listed_mask & close.notna()

        val_close = close.ffill()
        for h in cfg.horizons:
            # t 收盘因子 → t+h 交易日收盘前向收益（只用 > t 的价格，无重叠泄漏）
            self.fwd[h] = (val_close.shift(-h) / val_close - 1.0)

        self.rebal_dates = engine._rebalance_dates(trading_days, cfg.rebalance)
        if len(self.rebal_dates) < 5:
            raise ValueError(f"调仓日过少（{len(self.rebal_dates)}）——请缩短调仓周期或扩大区间")
        self.quick_dates = _even_sample(self.rebal_dates[:-1], QUICK_DATES_CAP)
        self.dedup_dates = _even_sample(self.rebal_dates[:-1], DEDUP_DATES)
        self.date_pos = {d: i for i, d in enumerate(trading_days)}
        # 样本内/外切分日（按交易日比例；因子只用各自区段日期的截面）
        split_i = int(len(trading_days) * (1.0 - cfg.oos_ratio))
        self.is_split = trading_days[max(split_i - 1, 0)]

        # 已入库因子向量（相关性比对种子）
        self._load_library_vectors()

    def _load_library_vectors(self):
        try:
            lib = repo.list_factors(in_library=True, limit=100)
        except Exception:
            lib = []
        for f in lib:
            try:
                m = self._eval_matrix(f["expression"])
                vec = self._reduced_vector(m)
                if vec is not None:
                    self.library_vecs.append((f["id"], vec))
            except Exception:
                continue

    # ---- 求值 ----
    def _eval_matrix(self, expr: str) -> pd.DataFrame:
        """整面板求值（共享懒加载命名空间）。抛 alphalab.AlphaExprError 表示表达式无效。"""
        code_obj = alphalab.parse_alpha(expr, self.ns)
        res = eval(code_obj, {"__builtins__": {}}, self.ns)
        if isinstance(res, pd.Series):
            res = res.to_frame()
        if not isinstance(res, pd.DataFrame):
            raise alphalab.AlphaExprError("表达式结果不是面板矩阵")
        res = res.astype(float)
        if not res.index.is_monotonic_increasing:
            res = res.sort_index()
        return res.replace([np.inf, -np.inf], np.nan)

    def _reduced_vector(self, matrix: pd.DataFrame) -> np.ndarray | None:
        """相关性比对用降维向量：抽样调仓日 × 宇宙 展平。"""
        idx = [pd.Timestamp(d) for d in self.dedup_dates if pd.Timestamp(d) in matrix.index]
        if len(idx) < 5:
            return None
        sub = matrix.loc[idx]
        v = sub.to_numpy(dtype=float).ravel()
        v = v[~np.isnan(v)]
        if len(v) < 500 or float(np.std(v)) <= 1e-12:
            return None
        return v

    # ---- 阶段 1+2：候选生成 + 静态检查 ----
    def ensure_candidates(self) -> None:
        existing = repo.count_factors(self.job_id)
        if existing > 0:
            self.progress["generated"] = existing
            return
        # 数据可得性过滤：当前数据源不支持的原子不进入生成（不浪费预算，不伪造数据）
        try:
            avail = atoms_mod.availability()["atoms"]
            usable = [a for a in gen_SEARCH_ATOMS
                      if avail.get(a, {}).get("status") in ("ok", "limited")]
        except Exception:
            usable = list(gen_SEARCH_ATOMS)
        dropped = sorted(set(gen_SEARCH_ATOMS) - set(usable))
        if dropped:
            logger.info("[factormine] %s atoms excluded (data unavailable): %s",
                        self.job_id, ",".join(dropped))
        gen = Generator(self.cfg.method, self.cfg.budget, self.cfg.seed, atoms=usable)
        if self.cfg.method == "beam":
            self._run_beam(gen)
        else:
            self._insert_candidates(gen.build_all())
        self._checkpoint("GENERATE", force=True)

    def _insert_candidates(self, cands: list[Candidate]) -> int:
        rows: list[dict] = []
        seq0 = repo.next_factor_seq(self.job_id)
        for i, c in enumerate(cands):
            fid = repo.make_factor_id(seq0 + i)
            row = {"id": fid, "job_id": self.job_id, "seq": seq0 + i,
                   "expression": c.expression, "normalized_expression": c.normalized[:500],
                   "ast_json": ast_to_json(c.expression), "status": "PENDING",
                   "data_version": repo.data_version(), **c.meta()}
            # 静态检查：合法性 + 负窗口泄漏（不依赖面板，逐条即刻判）
            leak = alphalab.scan_negative_window(c.expression)
            if leak:
                row.update(status="REJECTED", reject_reason=REASON_LEAKAGE, reject_detail=leak)
                self._bump(leakage=1)
            else:
                try:
                    alphalab.parse_alpha(c.expression, self.ns)
                except alphalab.AlphaExprError as e:
                    row.update(status="REJECTED", reject_reason=REASON_INVALID,
                               reject_detail=str(e)[:200])
                    self._bump(invalid_expr=1)
                except Exception as e:
                    row.update(status="REJECTED", reject_reason=REASON_INVALID,
                               reject_detail=f"解析异常: {e}"[:200])
                    self._bump(invalid_expr=1)
            rows.append(row)
        repo.insert_factors(rows)
        self._bump(generated=len(rows))
        self.progress["tested"] = self.progress.get("tested", 0)
        return len(rows)

    def _run_beam(self, gen: Generator):
        """BEAM_SEARCH：单因子轮 → 快速 IC 反馈 → 二因子轮 → 三因子轮。
        中断续跑：从 checkpoint 的 beam_stage 继续（top_atoms 由库内 QUICK_PASS
        重算）。"""
        stage = 1
        while stage <= 3 and gen.made < gen.budget:
            self.ctl.check()
            cands = gen.build_stage(stage, None if stage == 1 else self._beam_atoms())
            if not cands:
                break
            self._insert_candidates(cands)
            self.quick_stage()
            stage += 1
            self.progress["beam_stage"] = stage
            self._checkpoint("GENERATE", force=True)

    def _beam_atoms(self) -> list[str] | None:
        """上一轮快速 IC 最强的原子（beam 反馈）。"""
        atoms_score: dict[str, float] = {}
        for f in repo.list_factors(job_id=self.job_id, status="QUICK_PASS", limit=1000,
                                   order="rank_ic"):
            for a in (f.get("source_factors") or "").split(","):
                if a:
                    atoms_score[a] = max(atoms_score.get(a, 0.0),
                                         abs(f.get("quick_rank_ic") or 0.0))
            if len(atoms_score) >= 20:
                break
        ranked = [a for a, _ in sorted(atoms_score.items(), key=lambda kv: -kv[1])]
        return ranked[:20] or None

    # ---- 阶段 3：快速筛选 ----
    def quick_stage(self) -> None:
        pending = repo.list_factors(job_id=self.job_id, status="PENDING",
                                    limit=100000, order="seq")
        cfg = self.cfg
        primary_h = cfg.horizons[0]
        n_total = max(len(pending), 1)
        keep_cap = max(int(cfg.budget * cfg.keep_pct), 10)

        batch: list[dict] = []
        last_flush = time.time()
        done_in_stage = 0
        for f in pending:
            self.ctl.check()
            done_in_stage += 1
            row = self._quick_one(f, primary_h)
            batch.append(row)
            self._bump(tested=1)
            if row["status"] == "REJECTED":
                reason = row.get("reject_reason")
                key = {REASON_INVALID: "invalid_expr", REASON_LEAKAGE: "leakage",
                       REASON_MISSING: "data_missing", REASON_ZEROVAR: "zero_variance",
                       REASON_QUICK: "quick_rejected"}.get(reason, "quick_rejected")
                self._bump(**{key: 1})
            elif row["status"] == "QUICK_PASS":
                self._bump(quick_passed=1)
            if len(batch) >= QUICK_CHECKPOINT_EVERY or time.time() - last_flush > QUICK_CHECKPOINT_S:
                self._flush_quick_rows(batch)
                last_flush = time.time()
                self._checkpoint("QUICK", force=True)
                logger.info("[factormine] %s quick %d/%d", self.job_id,
                            done_in_stage, n_total)
        self._flush_quick_rows(batch)
        self._checkpoint("QUICK", force=True)

        # 透明门槛 + 按 |RankIC| 保留前 keep_pct：超额 QUICK_PASS 降级为 REJECTED
        passed = repo.list_factors(job_id=self.job_id, status="QUICK_PASS",
                                   limit=1000000, order="rank_ic")
        if len(passed) > keep_cap:
            for f in passed[keep_cap:]:
                self.ctl.check()
                repo.update_factor(f["id"], status="REJECTED", reject_reason=REASON_QUICK,
                                   reject_detail=f"保留比例 {cfg.keep_pct:.0%} 之外"
                                                 f"（|RankIC| 排名 {keep_cap} 名之后）")
                self._bump(quick_rejected=1, quick_passed=-1)
        self._checkpoint("QUICK", force=True)

    def _quick_one(self, f: dict, primary_h: int) -> dict:
        """单候选快速筛选：缓存 → 求值 → 覆盖/方差 → 快速 IC。返回 UPDATE 行。"""
        cfg = self.cfg
        expr = f["expression"]
        ck = repo.cache_key(f["normalized_expression"], cfg.core_hash(), repo.data_version())
        hit = repo.cache_get(ck)
        row: dict = {"id": f["id"]}
        if hit and hit.get("quick"):
            q = hit["quick"]
            if q.get("status") == "QUICK_PASS":
                row.update(status="QUICK_PASS", missing_rate=q.get("missing_rate"),
                           quick_rank_ic=q.get("quick_rank_ic"),
                           quick_icir=q.get("quick_icir"),
                           pearson_ic=q.get("pearson_ic"))
            else:
                row.update(status="REJECTED",
                           reject_reason=q.get("reject_reason", REASON_QUICK),
                           reject_detail=(q.get("reject_detail") or "")[:200],
                           missing_rate=q.get("missing_rate"))
            return row

        def _reject(reason: str, detail: str, missing: float | None = None) -> dict:
            out = {"id": f["id"], "status": "REJECTED", "reject_reason": reason,
                   "reject_detail": detail[:200]}
            if missing is not None:
                out["missing_rate"] = missing
            return out

        try:
            matrix = self._eval_matrix(expr)
        except alphalab.AlphaExprError as e:
            return _reject(REASON_INVALID, str(e))
        except Exception as e:
            return _reject(REASON_INVALID, f"求值失败: {e}")

        matrix = matrix.where(self.eligibility)
        if primary_h not in self.fwd:
            return _reject(REASON_QUICK, "horizon 未预计算")
        fwd = self.fwd[primary_h]

        # 预热感知：跳过表达式内最长回看窗口之前的调仓日（MA250 类原子不被误杀，
        # 也不被 NaN 污染 IC）。窗口超出研究区间的因子如实判「数据不足」。
        warmup = _expr_max_window(expr)
        idx_all = [d for d in self.quick_dates
                   if self.date_pos.get(d, 0) >= warmup + 5]
        if len(idx_all) < 10:
            return _reject(REASON_MISSING,
                           f"预热窗口 {warmup} 日后仅剩 {len(idx_all)} 个可评估调仓日"
                           "——表达式回看窗口过长或研究区间过短")
        idx = [pd.Timestamp(d) for d in idx_all if pd.Timestamp(d) in matrix.index]
        if len(idx) < 5:
            return _reject(REASON_MISSING, f"可评估调仓日不足（{len(idx)}）")

        # 覆盖率（抽样调仓日的截面覆盖）
        cov = matrix.loc[idx].notna().mean(axis=1)
        missing_rate = float(1.0 - cov.mean())
        if missing_rate > cfg.max_missing_rate:
            return _reject(REASON_MISSING,
                           f"截面缺失率 {missing_rate:.0%} > 上限 {cfg.max_missing_rate:.0%}",
                           missing=missing_rate)

        # 零方差检查（截面无区分度；只看有值的日子，全 NaN 行不计入）
        stds = matrix.loc[idx].std(axis=1)
        valid_stds = stds.dropna()
        if len(valid_stds) < 5 or float((valid_stds > 1e-12).mean()) < 0.8:
            return _reject(REASON_ZEROVAR, "多数调仓日截面方差为 0", missing=missing_rate)

        # 快速 IC：主 horizon 预检（明显无效提前止损，省算力）
        ics = self._ic_over_dates(matrix, fwd, idx[:EARLY_ABORT_DATES])
        pre = [x for x in ics if x is not None]
        if len(pre) >= 10 and float(np.mean(np.abs(pre))) < cfg.min_ic / EARLY_ABORT_FACTOR:
            detail = (f"预检 |RankIC| 均值 {abs(float(np.mean(pre))):.4f} "
                      f"< min_ic/{EARLY_ABORT_FACTOR:.0f}，提前淘汰")
            return _reject(REASON_QUICK, detail, missing=missing_rate)

        # 全量快速 IC（主 horizon）
        ics_main = self._ic_over_dates(matrix, fwd, idx)
        ics_arr = np.array([x for x in ics_main if x is not None], dtype=float)
        if len(ics_arr) < 10:
            return _reject(REASON_QUICK, f"有效 IC 期数不足（{len(ics_arr)}）", missing=missing_rate)
        summ = _ic_summary_block(ics_arr)
        # Pearson IC（截面去极值后线性相关）
        pearson = self._pearson_over_dates(matrix, fwd, idx)
        pearson_mean = float(np.mean([x for x in pearson if x is not None])) \
            if any(x is not None for x in pearson) else None
        gate_ok = _abs_at_least(summ["mean"], cfg.min_ic) and _abs_at_least(summ["icir"], 0.15)
        q = {"status": "QUICK_PASS" if gate_ok else "REJECTED",
             "reject_reason": None if gate_ok else REASON_QUICK,
             "missing_rate": missing_rate,
             "quick_rank_ic": _round_stat(summ["mean"], 4),
             "quick_icir": summ["icir"],
             "pearson_ic": pearson_mean,
             "reject_detail": None if gate_ok else
                 f"RankIC {_fmt_stat(summ['mean'], 4)} / ICIR {_fmt_stat(summ['icir'])} "
                 f"未达门槛或统计量不可计算（主 horizon {primary_h} 日，n={len(ics_arr)}）"}
        if not gate_ok:
            out = {"id": f["id"], "status": "REJECTED", "reject_reason": REASON_QUICK,
                   "reject_detail": q["reject_detail"], "missing_rate": missing_rate,
                   "quick_rank_ic": q["quick_rank_ic"],
                   "quick_icir": q["quick_icir"], "pearson_ic": pearson_mean}
        else:
            out = {"id": f["id"], "status": "QUICK_PASS", "missing_rate": missing_rate,
                   "quick_rank_ic": q["quick_rank_ic"],
                   "quick_icir": q["quick_icir"], "pearson_ic": pearson_mean}
        # 结果缓存（快速层）
        repo.cache_put(ck, q, None)
        # 幸存者保留降维向量供去重
        if q["status"] == "QUICK_PASS":
            vec = self._reduced_vector(matrix)
            if vec is not None:
                self._vec_by_id[f["id"]] = vec
        return out

    def _ic_over_dates(self, matrix: pd.DataFrame, fwd: pd.DataFrame,
                       dates) -> list[float | None]:
        out = []
        for d in dates:
            d_ts = pd.Timestamp(d)
            if d_ts not in fwd.index or d_ts not in matrix.index:
                out.append(None)
                continue
            fa = matrix.loc[d_ts].dropna()
            fb = fwd.loc[d_ts]
            out.append(_rank_ic(fa, fb))
        return out

    def _pearson_over_dates(self, matrix: pd.DataFrame, fwd: pd.DataFrame,
                            dates) -> list[float | None]:
        out = []
        for d in dates:
            d_ts = pd.Timestamp(d)
            if d_ts not in fwd.index or d_ts not in matrix.index:
                out.append(None)
                continue
            fa = _winsorize_zscore(matrix.loc[d_ts].dropna())
            fb = fwd.loc[d_ts]
            out.append(_pearson_ic(fa, fb))
        return out

    # ---- 阶段 4：相关性去重 ----
    def dedup_stage(self) -> list[dict]:
        """返回进入完整验证的代表列表。"""
        cfg = self.cfg
        passed = repo.list_factors(job_id=self.job_id, status="QUICK_PASS",
                                   limit=100000, order="rank_ic")
        clusters: list[dict] = []   # {"key": id, "vec": vec}
        reps: list[dict] = []
        for f in passed:
            self.ctl.check()
            fid = f["id"]
            vec = self._vec_by_id.get(fid)
            if vec is None:
                try:
                    vec = self._reduced_vector(self._eval_matrix(f["expression"]))
                except Exception:
                    vec = None
            best_corr, best_cluster = 0.0, None
            if vec is not None:
                for c in clusters:
                    corr = _spearman_vec(vec, c["vec"])
                    if corr is not None and abs(corr) >= cfg.dedup_threshold \
                            and abs(corr) > abs(best_corr):
                        best_corr, best_cluster = corr, c["key"]
                if best_cluster is None:
                    for lib_id, lib_vec in self.library_vecs:
                        corr = _spearman_vec(vec, lib_vec)
                        if corr is not None and abs(corr) >= cfg.dedup_threshold \
                                and abs(corr) > abs(best_corr):
                            best_corr, best_cluster = corr, lib_id
            if best_cluster is not None:
                cid = next((i for i, c in enumerate(clusters) if c["key"] == best_cluster), -1)
                repo.update_factor(fid, status="REJECTED", reject_reason=REASON_DEDUP,
                                   cluster_id=cid,   # -1 表示与已入库因子重复
                                   cluster_corr=round(float(best_corr), 3),
                                   reject_detail=f"与 {best_cluster} 的因子值 Spearman 相关 "
                                                 f"{best_corr:+.2f} ≥ {cfg.dedup_threshold}，保留其中更优者")
                self._bump(dedup_removed=1)
            else:
                cid = len(clusters)
                clusters.append({"key": fid, "vec": vec})
                repo.update_factor(fid, cluster_id=cid, cluster_rep=1)
                self._bump(dedup_kept=1)
                reps.append(f)
        self._checkpoint("DEDUP", force=True)
        return reps

    # ---- 阶段 5：完整检验 ----
    def validate_stage(self, reps: list[dict]) -> None:
        cfg = self.cfg
        reps_sorted = reps[: cfg.full_validate_limit]
        for i, f in enumerate(reps_sorted):
            self.ctl.check()
            try:
                self._full_validate(f)
            except CancelRequested:
                raise
            except PauseRequested:
                raise
            except Exception as e:
                logger.warning("[factormine] full validate %s failed: %s", f["id"], e)
                repo.update_factor(f["id"], status="REJECTED", reject_reason=REASON_FULL,
                                   reject_detail=f"完整检验异常: {e}"[:200])
                self._bump(errors=1, reject=1)
            self._checkpoint("VALIDATE", force=True)
            logger.info("[factormine] %s validated %d/%d", self.job_id, i + 1, len(reps_sorted))

    def _full_validate(self, f: dict) -> None:
        from factorlab import analyze_scores
        cfg = self.cfg
        expr = f["expression"]
        ck = repo.cache_key(f["normalized_expression"], cfg.core_hash(), repo.data_version())
        hit = repo.cache_get(ck)
        if hit and hit.get("stats"):
            stats = hit["stats"]
        else:
            matrix = self._eval_matrix(expr).where(self.eligibility)
            codes = [c for c in matrix.columns if c in self.panel["close"].columns]

            def provider(d: dt.date, codes_list: list[str]) -> pd.Series:
                d_ts = pd.Timestamp(d)
                if d_ts not in matrix.index:
                    return pd.Series(dtype=float)
                return matrix.loc[d_ts].reindex(codes_list).dropna()

            stats = analyze_scores(provider, start=cfg.start_date, end=cfg.end_date,
                                   rebalance=cfg.rebalance, layers=cfg.layers,
                                   horizons=cfg.horizons, neutralize=cfg.neutralize,
                                   factor_name=f["id"], codes=codes,
                                   include_pearson=True)
            if "error" in stats:
                repo.update_factor(f["id"], status="REJECTED", reject_reason=REASON_FULL,
                                   reject_detail=str(stats["error"])[:200])
                self._bump(reject=1)
                return
            repo.cache_put(ck, None, _slim_stats(stats))

        # —— 样本内 / 样本外：同一 ic_series 按切分日拆分（同一引擎同一结果源）——
        ic_series = stats.get("ic_series") or []
        is_ics = np.array([x["ic"] for x in ic_series
                           if x.get("return_end", x["date"]) < self.is_split.isoformat()], dtype=float)
        oos_ics = np.array([x["ic"] for x in ic_series if x["date"] >= self.is_split.isoformat()], dtype=float)
        is_block = _ic_summary_block(is_ics)
        oos_block = _ic_summary_block(oos_ics) if len(oos_ics) >= 3 else None

        # —— 年度稳定性（按 IC 序列年份聚合）——
        yearly = _yearly_stability(ic_series)
        is_ic = is_block["mean"]
        direction = "neutral" if not _has_stat(is_ic) or is_ic == 0 else ("positive" if is_ic > 0 else "reverse")
        pass_years = sum(1 for y in yearly if y["dir_match"] and abs(y["ic_mean"]) >= 0.01)
        stability = f"{pass_years}/{len(yearly)}" if yearly else None

        # —— 成本敏感性：毛多空 − 换手×单次成本（bps 明细）——
        spread_ann = stats.get("top_minus_bottom_annualized")
        turnover = stats.get("turnover_annualized")
        has_economics = _has_stat(spread_ann) and _has_stat(turnover)
        dir_mult = 1.0 if direction == "positive" else (-1.0 if direction == "reverse" else 1.0)
        cost_table = [{"bps": b,
                       "net_spread_ann": round(dir_mult * spread_ann - turnover * b / 10000.0, 4)
                                         if has_economics else None}
                      for b in (0, 10, 20, 30, 50)]
        net20 = next(c["net_spread_ann"] for c in cost_table if c["bps"] == 20)

        # —— Walk Forward（Top-K 才做，控制算力）——
        wf = None
        if self._wf_quota() > 0 and _has_stat(is_ic):
            wf = self._walk_forward(f, is_ic)
            self._use_wf_quota()

        # —— 客观判定（阈值全部公开可配）——
        reasons: list[str] = []
        if is_block["n"] < cfg.min_periods:
            reasons.append(f"样本不足（{is_block['n']} 期 < {cfg.min_periods}）")
        if not _abs_at_least(is_block["t_stat"], cfg.min_t):
            reasons.append(f"统计证据不足（t={_fmt_stat(is_block['t_stat'])}，门槛 {cfg.min_t}）")
        if not _abs_at_least(is_ic, cfg.min_ic):
            reasons.append(f"样本内 RankIC {_fmt_stat(is_ic, 4)} 未达门槛或不可计算")
        if not _abs_at_least(is_block["icir"], cfg.min_icir):
            reasons.append(f"ICIR {_fmt_stat(is_block['icir'])} 未达门槛或不可计算")
        oos_ok = oos_block is not None and _has_stat(oos_block["mean"]) and _has_stat(is_ic) and \
            np.sign(oos_block["mean"]) == np.sign(is_ic) and abs(oos_block["mean"]) >= cfg.min_oos_ic
        if oos_block is None:
            reasons.append("样本外有效数据不足")
        elif not oos_ok:
            reasons.append(f"样本外失效（OOS RankIC {_fmt_stat(oos_block['mean'], 4)}）")
        if net20 is None:
            reasons.append("收益或换手不可计算，成本敏感性缺失")
        elif net20 <= 0:
            reasons.append(f"成本后多空收益消失（20bps 净价差 {net20:+.4f}）")
        if _abs_at_least(is_block["t_stat"], cfg.min_t) and is_block["n"] >= cfg.min_periods \
                and _abs_at_least(is_ic, cfg.min_ic) and _abs_at_least(is_block["icir"], cfg.min_icir) \
                and oos_ok and net20 is not None and net20 > 0:
            verdict = "PASS"
        elif is_block["n"] >= 6 and (_abs_at_least(is_block["icir"], cfg.min_icir) or _abs_at_least(is_ic, cfg.min_ic)):
            verdict = "WATCH"
        else:
            verdict = "REJECT"
        stable_ratio = None
        if yearly:
            stable_ratio = round(pass_years / len(yearly), 2)

        update = {
            "id": f["id"], "status": "VALIDATED", "verdict": verdict,
            "reject_reason": None if verdict != "REJECT" else REASON_FULL,
            "reject_detail": None if verdict != "REJECT" else "；".join(reasons)[:200],
            "rank_ic": _round_stat(is_ic, 4), "icir": _round_stat(is_block["icir"], 3),
            "t_stat": is_block["t_stat"], "ic_positive_ratio": is_block["positive_ratio"],
            "oos_rank_ic": _round_stat(oos_block["mean"], 4) if oos_block else None,
            "pearson_ic": (stats.get("ic_pearson_summary") or {}).get("mean"),
            "stability": stability, "direction": direction,
            "stability_years_json": json.dumps(yearly, ensure_ascii=False),
        }
        stats_out = dict(stats)
        stats_out.update({
            "is_summary": is_block, "oos_summary": oos_block,
            "oos_start": self.is_split.isoformat(),
            "yearly_stability": yearly, "stability_ratio": stable_ratio,
            "cost_table": cost_table, "walk_forward": wf,
            "expression": expr, "factor_id": f["id"],
            "rebalance_period_ic_note": "ic_summary 为调仓周期前向收益的 RankIC；"
                                        "decay 为按 horizon（交易日）的前向 IC",
        })
        update["stats_json"] = json.dumps(repo.json_safe(_slim_stats(stats_out)), ensure_ascii=False)
        repo.update_factors_bulk([update])
        self._bump(full_validated=1, **{verdict.lower(): 1})

    def _wf_quota(self) -> int:
        return max(self.cfg.wf_top_k - self._wf_used, 0)

    def _use_wf_quota(self):
        self._wf_used += 1

    def _walk_forward(self, f: dict, is_ic: float) -> list[dict] | None:
        """滚动窗口：每个验证窗口用 analyze_scores（同一引擎）统计
        RankIC 均值 / 多空年化 / 最高层回撤；稳定窗口 = 方向与样本内一致且 |IC|≥min_ic。"""
        from factorlab import analyze_scores
        cfg = self.cfg
        matrix = self._eval_matrix(f["expression"]).where(self.eligibility)
        codes = [c for c in matrix.columns if c in self.panel["close"].columns]

        def provider(d, codes_list):
            d_ts = pd.Timestamp(d)
            if d_ts not in matrix.index:
                return pd.Series(dtype=float)
            return matrix.loc[d_ts].reindex(codes_list).dropna()

        trading_days = engine._trading_days(cfg.start_date, cfg.end_date)
        win_len = int(len(trading_days) * cfg.wf_test_years / (1.0 + cfg.wf_test_years))
        win_len = max(win_len, 60)
        rows: list[dict] = []
        pos = 0
        while pos + win_len <= len(trading_days):
            self.ctl.check()
            w_start, w_end = trading_days[pos], trading_days[pos + win_len - 1]
            train_end = trading_days[max(pos - 1, 0)]
            res = analyze_scores(provider, start=w_start, end=w_end,
                                 rebalance=cfg.rebalance, layers=cfg.layers,
                                 horizons=(cfg.horizons[0],), neutralize=False,
                                 factor_name=f["id"], codes=codes)
            if "error" not in res:
                icm = res["ic_summary"]["mean"]
                top_dd = res["layer_stats"][-1]["max_drawdown"] if res.get("layer_stats") else None
                rows.append({
                    "train": f"{cfg.start_date.isoformat()}~{train_end.isoformat()}",
                    "test": f"{w_start.isoformat()}~{w_end.isoformat()}",
                    "ic_mean": icm, "icir": res["ic_summary"]["icir"],
                    "n": res["ic_summary"]["n"],
                    "spread_ann": res.get("top_minus_bottom_annualized"),
                    "top_max_drawdown": top_dd,
                    "stable": bool(_has_stat(icm) and _has_stat(is_ic) and
                                   np.sign(icm) == np.sign(is_ic) and abs(icm) >= cfg.min_ic),
                })
            pos += win_len
        return rows or None


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _panel_first_pos(close: pd.DataFrame) -> np.ndarray:
    """每只股票在面板内首个有效收盘的位置（无数据 → len(index)）。"""
    arr = close.notna().to_numpy()
    first_pos = np.full(arr.shape[1], arr.shape[0], dtype=float)
    for j in range(arr.shape[1]):
        nz = np.flatnonzero(arr[:, j])
        if len(nz):
            first_pos[j] = nz[0]
    return first_pos


_KLINE_HISTORY: tuple[float, dict[str, dt.date], dict[str, int]] | None = None


def _kline_history(panel_start: dt.date, ttl_s: float = 3600.0) -> tuple[dict[str, dt.date], dict[str, int]]:
    """K 线全表里每只股票的首次交易日与面板开始前的记录数（缓存 1 小时）。"""
    global _KLINE_HISTORY
    now = time.time()
    if _KLINE_HISTORY and now - _KLINE_HISTORY[0] < ttl_s:
        return _KLINE_HISTORY[1], _KLINE_HISTORY[2]
    eng = db.get_engine()
    first_dates: dict[str, dt.date] = {}
    pre_rows: dict[str, int] = {}
    if eng is not None:
        try:
            with eng.connect() as conn:
                rows = conn.execute(text(
                    "SELECT code, MIN(trade_date), "
                    "SUM(CASE WHEN trade_date < :s THEN 1 ELSE 0 END) "
                    "FROM stock_kline_daily GROUP BY code"),
                    {"s": panel_start}).fetchall()
            for code, fd, n in rows:
                c = str(code).zfill(6)
                first_dates[c] = fd
                pre_rows[c] = int(n or 0)
        except Exception as e:
            logger.warning("[factormine] kline history query failed: %s", e)
    _KLINE_HISTORY = (now, first_dates, pre_rows)
    return first_dates, pre_rows


def _expr_max_window(expr: str) -> int:
    """表达式内最长回看窗口（原子自带窗口 + 数值窗口参数），用于预热感知。"""
    from atoms import ATOMS
    max_w = 20
    try:
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in ATOMS:
                max_w = max(max_w, int(ATOMS[node.id].window))
            elif isinstance(node, ast.Call):
                for a in node.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, (int, float)) \
                            and 1 <= a.value <= MAX_WINDOW_NUM:
                        max_w = max(max_w, int(a.value))
    except Exception:
        pass
    return max_w


MAX_WINDOW_NUM = 250


def _spearman_vec(a: np.ndarray, b: np.ndarray) -> float | None:
    n = min(len(a), len(b))
    if n < 500:
        return None
    ra = pd.Series(a[:n]).rank()
    rb = pd.Series(b[:n]).rank()
    if ra.std() <= 0 or rb.std() <= 0:
        return None
    return float(ra.corr(rb))


def _even_sample(dates: list[dt.date], cap: int) -> list[dt.date]:
    if len(dates) <= cap:
        return list(dates)
    idx = np.linspace(0, len(dates) - 1, cap).astype(int)
    return [dates[i] for i in dict.fromkeys(idx.tolist())]


def _stock_names() -> dict[str, str]:
    eng = db.get_engine()
    if eng is None:
        return {}
    try:
        with eng.connect() as conn:
            rows = conn.execute(text("SELECT code, name FROM stock_info")).fetchall()
        return {str(r[0]).zfill(6): (r[1] or "") for r in rows}
    except Exception:
        return {}


def _yearly_stability(ic_series: list[dict]) -> list[dict]:
    if not ic_series:
        return []
    by_year: dict[str, list[float]] = {}
    for x in ic_series:
        by_year.setdefault(x["date"][:4], []).append(x["ic"])
    overall_sign = np.sign(np.mean([x["ic"] for x in ic_series]))
    out = []
    for y in sorted(by_year):
        arr = np.array(by_year[y], dtype=float)
        m = float(arr.mean())
        out.append({"year": y, "ic_mean": round(m, 4), "n": len(arr),
                    "positive_ratio": round(float((arr > 0).mean()), 2),
                    "dir_match": bool(np.sign(m) == overall_sign and overall_sign != 0)})
    return out


def _slim_stats(stats: dict) -> dict:
    """完整检验结果落库前的瘦身钩子：当前保留全部字段（含 ic_series，供详情图表）。"""
    return stats
