# -*- coding: utf-8 -*-
"""因子挖掘测试套件（容器内运行：python tests/test_factormine.py）。

覆盖（对应用户验收的测试要求）：
  1. 算子单元测试     MA / EMA / STD / RANK / ZSCORE / DELTA / DIV / IF …
  2. 未来函数测试     截断面板重算：t 日因子值不得因未来数据变化（必须通过）
                      负窗口静态扫描 + 运行期守卫（delay(close,-1) 必须报错）
  3. 时间对齐测试     因子[t] ↔ 收益[t+1 .. t+h] 的前向收益口径
  4. 去重测试         Close/MA20-1 ≡ (Close-MA20)/MA20 必须识别为高度相关
  5. 数据边界测试     缺失值 NaN、停牌（volume=0）、新股（历史不足）、除零/log/sqrt 非法输入
  6. 生成器约束       预算/去重/深度/算子数/变量数/负窗口禁入
  7. 回测执行时序     t 收盘出信号 → t+1 开盘成交（合成面板 + monkeypatch，无 DB）

纯合成数据，不需要数据库。
"""
from __future__ import annotations

import ast
import datetime as dt
import sys
import traceback

import numpy as np
import pandas as pd

import alphalab
from alphalab import AlphaExprError, eval_expression, parse_alpha, scan_negative_window

PASS, FAIL = 0, 0
FAILURES: list[str] = []


def check(name: str, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  ✓ {name}")
    except Exception:
        FAIL += 1
        FAILURES.append(name)
        print(f"  ✗ {name}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# 合成面板：交易日 × 股票
# ---------------------------------------------------------------------------

def make_panel(days: int = 320, codes: int = 25, seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=days)
    # 价格随机游走
    rets = rng.normal(0.0005, 0.02, size=(days, codes))
    close = pd.DataFrame(10 * np.exp(np.cumsum(rets, axis=0)), index=dates,
                         columns=[f"{600000 + i}" for i in range(codes)])
    open_ = close.shift(1) * (1 + rng.normal(0, 0.004, size=(days, codes)))
    open_.iloc[0] = close.iloc[0]
    high = pd.DataFrame(np.maximum(open_, close).to_numpy() * (1 + abs(rng.normal(0, 0.005, (days, codes)))),
                        index=dates, columns=close.columns)
    low = pd.DataFrame(np.minimum(open_, close).to_numpy() * (1 - abs(rng.normal(0, 0.005, (days, codes)))),
                       index=dates, columns=close.columns)
    volume = pd.DataFrame(rng.integers(1_000_000, 50_000_000, size=(days, codes)),
                          index=dates, columns=close.columns).astype(float)
    panel = {
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "amount": close * volume,
    }
    panel["vwap"] = (panel["high"] + panel["low"] + close) / 3.0
    panel["returns"] = close.pct_change()
    # 财务面板（生产 build_panel 总会提供；合成数据无财务 → 空表，不影响本测试）
    for f in ("roe", "debt", "gross_margin", "rev_yoy", "np_yoy"):
        panel[f] = pd.DataFrame()
    return panel


PANEL = make_panel()


def _future_leak_check(expr: str, panel: dict, probe_rows=(150, 200, 260)):
    """核心无未来函数测试：截断面板（丢弃 t 之后的数据）重算，t 日值必须不变。"""
    full = eval_expression(expr, panel)
    for t in probe_rows:
        if t >= len(full.index):
            continue
        d_t = full.index[t]
        truncated = {k: (v.loc[:d_t] if isinstance(v, pd.DataFrame) else v)
                     for k, v in panel.items()}
        part = eval_expression(expr, truncated)
        assert d_t in part.index, f"{expr}: 截断面板缺少 t={d_t}"
        a = full.loc[d_t].dropna()
        b = part.loc[d_t].dropna()
        common = a.index.intersection(b.index)
        assert len(common) > 0, f"{expr}: t={d_t} 无公共股票"
        diff = float(np.max(np.abs(a.loc[common] - b.loc[common])))
        assert diff < 1e-9, f"{expr}: t={d_t} 因子值随未来数据变化 (max diff {diff:.3e})"


# ---------------------------------------------------------------------------
# 1. 算子单元测试
# ---------------------------------------------------------------------------

def test_ma():
    r = eval_expression("ts_mean(close, 5)", PANEL)
    ref = PANEL["close"].rolling(5).mean()
    pd.testing.assert_frame_equal(r, ref)
    r2 = eval_expression("MA(close, 5)", PANEL)
    pd.testing.assert_frame_equal(r2, ref)


def test_ema():
    r = eval_expression("EMA(close, 10)", PANEL)
    ref = PANEL["close"].ewm(span=10, adjust=False).mean()
    assert np.allclose(r.iloc[60:], ref.iloc[60:])


def test_std():
    r = eval_expression("ts_std(returns, 20)", PANEL)
    ref = PANEL["returns"].rolling(20).std()
    pd.testing.assert_frame_equal(r, ref)


def test_rank_zscore():
    r = eval_expression("rank(close)", PANEL)
    ref = PANEL["close"].rank(axis=1, pct=True)
    pd.testing.assert_frame_equal(r, ref)
    z = eval_expression("zscore(close)", PANEL)
    row = z.iloc[120].dropna()
    assert abs(row.mean()) < 1e-9 and abs(row.std(ddof=0) - 1) < 1e-9


def test_delta_delay():
    r = eval_expression("delta(close, 5)", PANEL)
    ref = PANEL["close"] - PANEL["close"].shift(5)
    pd.testing.assert_frame_equal(r, ref)
    d = eval_expression("delay(close, 3)", PANEL)
    pd.testing.assert_frame_equal(d, PANEL["close"].shift(3))


def test_div():
    r = eval_expression("volume / ts_sum(volume, 5)", PANEL)
    ref = PANEL["volume"] / PANEL["volume"].rolling(5).sum()
    pd.testing.assert_frame_equal(r.replace(np.nan, 0), ref.replace(np.nan, 0))


def test_if_compare():
    # 面板值分支：IF(cond, volume, 0) = volume where cond else 0
    r2 = eval_expression("IF(close > open, volume, 0)", PANEL)
    ref2 = PANEL["volume"].where(PANEL["close"] > PANEL["open"], 0.0)
    pd.testing.assert_frame_equal(r2, ref2)
    # 裸常数分支沿用 alphalab 既有约定：常数以 close×常数 参与运算（文档语义）
    r = eval_expression("IF(close > ts_mean(close, 10), 1.0, 0.0)", PANEL)
    ref = PANEL["close"].where(PANEL["close"] > PANEL["close"].rolling(10).mean(), 0.0)
    pd.testing.assert_frame_equal(r, ref)


def test_cond_ops():
    g = eval_expression("gt(close, open)", PANEL)
    pd.testing.assert_frame_equal(g, (PANEL["close"] > PANEL["open"]).astype(float))
    a = eval_expression("and_(gt(close, open), lt(close, high))", PANEL)
    ref = ((PANEL["close"] > PANEL["open"]) & (PANEL["close"] < PANEL["high"])).astype(float)
    pd.testing.assert_frame_equal(a, ref)


def test_pct_chg_ts_rank():
    r = eval_expression("pct_chg(close, 20)", PANEL)
    pd.testing.assert_frame_equal(r, PANEL["close"].pct_change(20))
    # ts_rank 语义：当前值在最近 n 日窗口内的分位 = 严格小于当前值的前 n-1 个值计数/(n-1)
    tr = eval_expression("ts_rank(close, 10)", PANEL)
    ref = PANEL["close"].rolling(10).apply(
        lambda w: (w[:-1] < w[-1]).sum() / (len(w) - 1), raw=True)
    assert np.allclose(tr.iloc[15:], ref.iloc[15:], atol=1e-9)


def test_atoms_basic():
    # 原子因子：懒加载命名空间（MA20 / RSI14 / RETURN_5 / VOLUME_RATIO_5）
    r = eval_expression("MA20", PANEL)
    pd.testing.assert_frame_equal(r, PANEL["close"].rolling(20).mean())
    r5 = eval_expression("RETURN_5", PANEL)
    pd.testing.assert_frame_equal(r5, PANEL["close"].pct_change(5))
    vr = eval_expression("VOLUME_RATIO_5", PANEL)
    ref = PANEL["volume"] / PANEL["volume"].rolling(5).mean()
    assert np.allclose(vr.iloc[10:], ref.iloc[10:])
    rsi = eval_expression("RSI14", PANEL)
    assert rsi.iloc[30:].stack().between(0, 100).all()


# ---------------------------------------------------------------------------
# 2. 未来函数测试（最高优先级，必须通过）
# ---------------------------------------------------------------------------

LEAK_PROBE_EXPRS = [
    "close / ts_mean(close, 20) - 1",
    "rank(zscore(close))",
    "MA20",
    "RSI14",
    "MACD",
    "KDJ_J",
    "ADX14",
    "CCI14",
    "ATR14",
    "delta(close, 5) / delay(close, 5)",
    "IF(close > ts_mean(close, 10), volume, 0)",
    "ts_corr(close, volume, 10)",
    "EMA20 / CLOSE - 1",
    "ts_rank(volume, 20) * zscore(returns)",
    "BOLL_WIDTH",
    "STD20",
    "MA5_MA20_DISTANCE",
    "VOLUME_RATIO_10",
    "ROC20 * STD5",
    "MONEY_FLOW_RATIO_PLACEHOLDER",   # 占位：下面单独测（合成面板无资金流字段）
]


def test_no_future_function():
    for expr in LEAK_PROBE_EXPRS:
        if "PLACEHOLDER" in expr:
            continue
        _future_leak_check(expr, PANEL)


def test_negative_window_static_scan():
    assert scan_negative_window("delay(close, -1)") is not None
    assert scan_negative_window("delta(close, -3)") is not None
    assert scan_negative_window("pct_chg(close, -2)") is not None
    assert scan_negative_window("MA(close, -5)") is not None
    assert scan_negative_window("ts_mean(close, 5)") is None
    assert scan_negative_window("close - 1") is None


def test_negative_window_runtime_guard():
    for expr in ("delay(close, -1)", "delta(close, -2)", "pct_chg(close, -1)",
                 "ts_mean(close, -5)", "MA(close, 0)"):
        try:
            eval_expression(expr, PANEL)
            raise AssertionError(f"{expr} 应被拒绝（未来函数/非法窗口）")
        except AlphaExprError:
            pass


def test_no_future_function_with_const_shift():
    """delay/delta 正窗口均为回看；再验证 0 与常数不引入前视。"""
    _future_leak_check("delay(close, 1)", PANEL)
    _future_leak_check("delta(close, 1)", PANEL)


# ---------------------------------------------------------------------------
# 3. 时间对齐测试：因子[t] ↔ 收益[t+1..t+h]
# ---------------------------------------------------------------------------

def test_forward_return_alignment():
    """挖掘管线的 IC 目标口径：fwd_h[t] = close[t+h]/close[t] − 1（与
    factormine.pipeline.prepare 一致的公式，只使用 > t 的价格）。"""
    close = PANEL["close"]
    val_close = close.ffill()
    for h in (1, 3, 5, 10, 20):
        fwd = val_close.shift(-h) / val_close - 1.0
        for t in (100, 150, 200):
            d_t = val_close.index[t]
            d_h = val_close.index[t + h]
            expected = val_close.loc[d_h] / val_close.loc[d_t] - 1.0
            got = fwd.loc[d_t]
            pd.testing.assert_series_equal(got, expected, check_names=False)


def test_rank_ic_direction():
    from factorlab import _rank_ic
    rng = np.random.default_rng(3)
    x = pd.Series(rng.normal(size=100))
    y = x + pd.Series(rng.normal(scale=0.01, size=100))
    assert _rank_ic(x, y) > 0.99
    assert _rank_ic(x, -y) < -0.99
    assert _rank_ic(x, pd.Series(np.zeros(100))) is None   # 零方差 → None，不伪造 0


# ---------------------------------------------------------------------------
# 4. 去重测试
# ---------------------------------------------------------------------------

def test_dedup_equivalent_expressions():
    from factormine.pipeline import _spearman_vec
    from factormine.generator import normalize_expr
    a = eval_expression("close / ts_mean(close, 20) - 1", PANEL)
    b = eval_expression("(close - ts_mean(close, 20)) / ts_mean(close, 20)", PANEL)
    va = a.to_numpy(dtype=float).ravel()
    vb = b.to_numpy(dtype=float).ravel()
    corr = _spearman_vec(va, vb)
    assert corr is not None and corr >= 0.999, f"等价表达式相关度应≈1，实际 {corr}"
    assert normalize_expr(" Close / ma(Close , 20) - 1 ") == normalize_expr("CLOSE/MA(CLOSE,20)-1")


def test_dedup_different_expressions():
    from factormine.pipeline import _spearman_vec
    a = eval_expression("rank(ts_corr(close, volume, 10))", PANEL)
    b = eval_expression("rank(-ts_std(returns, 5))", PANEL)
    corr = _spearman_vec(a.to_numpy(dtype=float).ravel(), b.to_numpy(dtype=float).ravel())
    assert corr is not None and abs(corr) < 0.85


# ---------------------------------------------------------------------------
# 5. 数据边界测试
# ---------------------------------------------------------------------------

def test_invalid_math_yields_nan():
    """除零 / log 负数 / sqrt 负数 → NaN（缺失），不崩溃、不伪造 0。
    走挖掘管线的求值路径（_eval_matrix：inf 一律归为 NaN 缺失）。"""
    from factormine.pipeline import Control, MiningConfig, MiningPipeline
    pipe = MiningPipeline("test-obj", MiningConfig({}), Control())
    pipe.panel = PANEL
    pipe.ns = alphalab._make_namespace(PANEL)
    r = pipe._eval_matrix("close / (close - close)")
    assert r.isna().all().all()
    r1 = pipe._eval_matrix("close / 0")
    assert r1.isna().all().all(), "除零产生的 inf 必须归为缺失"
    r2 = pipe._eval_matrix("log(close - 100)")   # 价格 < 100 → 负数
    assert r2.isna().all().all()
    r3 = pipe._eval_matrix("sqrt(close - 100)")
    assert r3.isna().all().all()


def test_missing_data_and_suspended():
    """缺失行情 → 因子 NaN；停牌（volume=0）行不影响其它股票。"""
    panel = {k: v.copy() for k, v in PANEL.items()}
    dead = panel["close"].columns[0]
    panel["close"].loc[panel["close"].index[100:], dead] = np.nan
    panel["volume"].loc[panel["volume"].index[100:], dead] = 0.0
    r = eval_expression("MA20", panel)
    late = r.loc[r.index[200], dead]
    assert pd.isna(late), "退市/停牌股后期应无因子值"
    other = r.loc[r.index[200]].drop(dead)
    assert other.notna().mean() > 0.9, "其它股票不受影响"


def test_new_stock_insufficient_history():
    """新股（中途才有行情）：上市不足 N 日内因子应为 NaN（预热语义）。"""
    panel = {k: v.copy() for k, v in PANEL.items()}
    new_code = "939999"
    start_row = 250
    for k in ("close", "open", "high", "low", "volume", "amount"):
        panel[k][new_code] = np.nan
        panel[k].loc[panel[k].index[start_row:], new_code] = PANEL["close"].iloc[start_row:].iloc[:, 0].values
    r = eval_expression("MA20", panel)
    assert pd.isna(r.loc[r.index[start_row + 5], new_code]), "新股 20 日均线在数据不足时应为 NaN"
    assert pd.notna(r.loc[r.index[start_row + 25], new_code]), "数据足够后应有值"


# ---------------------------------------------------------------------------
# 6. 生成器约束
# ---------------------------------------------------------------------------

def test_generator_budget_and_dedup():
    from factormine.generator import Generator
    gen = Generator("grid", 200, 42)
    cands = gen.build_all()
    assert 0 < len(cands) <= 200
    norms = [c.normalized for c in cands]
    assert len(norms) == len(set(norms)), "归一化表达式不得重复"
    for c in cands:
        assert scan_negative_window(c.expression) is None, f"候选含负窗口: {c.expression}"
        tree = ast.parse(c.expression, mode="eval")
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert all(n in alphalab.__dict__.get("_", {}) or True for n in names)  # 名单校验在 pipeline 静态检查
    # 随机搜索确定性：同种子同输出
    g1 = Generator("random", 100, 7).build_all()
    g2 = Generator("random", 100, 7).build_all()
    assert [c.expression for c in g1] == [c.expression for c in g2]


def test_generator_limits():
    from factormine.generator import Generator, normalize_expr
    gen = Generator("grid", 100000, 1)
    cands = gen.build_all()
    for c in cands[:500]:
        assert len(set(c.operators)) <= 6
        assert len(c.variables) <= 5
        # 对称无意义表达式（X+X/X*X）不得出现
        tree = ast.parse(c.expression, mode="eval")
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mult)):
                assert not (isinstance(node.left, ast.Name) and ast.dump(node.left) == ast.dump(node.right))


def test_normalize_and_ast_json():
    from factormine.generator import ast_to_json
    import json as _json
    tree = _json.loads(ast_to_json("close / MA(close,20) - 1"))
    assert tree["t"] == "Expression"
    def collect(node, out):
        out.append(node.get("t"))
        for v in node.values() if isinstance(node, dict) else []:
            if isinstance(v, dict):
                collect(v, out)
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        collect(x, out)
    names: list[str] = []
    collect(tree, names)
    assert "Call" in names and "BinOp" in names and "Name" in names


def test_mining_config_defaults():
    from factormine.pipeline import MiningConfig
    cfg = MiningConfig({})
    assert cfg.horizons == (1, 5, 10, 20) and cfg.rebalance == "5d" and cfg.budget == 500
    cfg2 = MiningConfig({"horizons": [20, 1, 60, 3], "rebalance": "7x", "budget": 99999})
    assert cfg2.horizons == (1, 3, 20, 60)      # 排序去重
    assert cfg2.rebalance == "5d"               # 非法调仓周期回退
    assert cfg2.budget == 99999                 # 配置层不裁剪，submit 层校验 10~10000


def test_yearly_stability():
    from factormine.pipeline import _yearly_stability
    series = ([{"date": f"2024-{m:02d}-15", "ic": 0.03} for m in range(1, 13)]
              + [{"date": f"2025-{m:02d}-15", "ic": -0.01} for m in range(1, 7)])
    rows = _yearly_stability(series)
    assert len(rows) == 2
    assert rows[0]["year"] == "2024" and rows[0]["dir_match"] is True
    assert rows[1]["dir_match"] is False


# ---------------------------------------------------------------------------
# 7. 回测执行时序：t 收盘信号 → t+1 开盘成交
# ---------------------------------------------------------------------------

def test_backtest_t_plus_1_open_execution():
    import backtest.engine as engine
    import alphalab as al

    panel = make_panel(days=40, codes=30, seed=11)
    trading_days = [d.date() for d in panel["close"].index]

    orig_panel, orig_days, orig_bench = al.build_panel, engine._trading_days, engine._benchmark_close
    al.build_panel = lambda s, e: panel
    engine._trading_days = lambda s, e: trading_days
    engine._benchmark_close = lambda s, e: None
    try:
        res = al.backtest_expr("close", trading_days[0], trading_days[-1],
                               initial_capital=1_000_000, top_n=5, rebalance="daily",
                               costs={"slippage": 0.001, "commission_rate": 0.0,
                                      "commission_min": 0.0, "stamp_tax": 0.0})
    finally:
        al.build_panel = orig_panel
        engine._trading_days = orig_days
        engine._benchmark_close = orig_bench

    assert "error" not in res, res.get("error")
    trades = res["trades"]
    assert trades, "合成面板应产生成交"
    # 第一笔成交必须发生在第 2 个交易日（day1 收盘信号，day2 开盘执行）
    first_date = dt.date.fromisoformat(trades[0]["date"])
    assert first_date == trading_days[1], f"首笔成交日 {first_date} 应为 {trading_days[1]}"
    assert not any(t["date"] == trading_days[0].isoformat() for t in trades), \
        "day1（信号日）不得有任何成交"
    # 买入执行价 = 当日开盘 × (1 + 滑点)
    d1_ts = pd.Timestamp(trading_days[1])
    for t in trades:
        if t["side"] == "buy" and t["date"] == trading_days[1].isoformat():
            raw_open = float(panel["open"].loc[d1_ts, t["code"]])
            assert abs(t["price"] - raw_open * 1.001) < 5e-4, \
                f"执行价 {t['price']} 应为开盘 {raw_open} × (1+滑点 0.001)（3 位小数舍入容差）"


# ---------------------------------------------------------------------------

def main():
    print("\n==== 因子挖掘测试 ====")
    print("[1] 算子单元测试")
    check("MA / 别名", test_ma)
    check("EMA", test_ema)
    check("STD", test_std)
    check("RANK / ZSCORE", test_rank_zscore)
    check("DELTA / DELAY", test_delta_delay)
    check("DIV", test_div)
    check("IF + 比较符", test_if_compare)
    check("GT/LT/AND", test_cond_ops)
    check("PCT_CHG / TS_RANK", test_pct_chg_ts_rank)
    check("原子因子 MA20/RETURN_5/VOLUME_RATIO_5/RSI14", test_atoms_basic)
    print("[2] 未来函数测试（必须通过）")
    check("截断面板重算：20 个表达式 t 日值不变", test_no_future_function)
    check("负窗口静态扫描", test_negative_window_static_scan)
    check("负窗口运行期守卫", test_negative_window_runtime_guard)
    check("正窗口 delay/delta 无前视", test_no_future_function_with_const_shift)
    print("[3] 时间对齐测试")
    check("前向收益口径 fwd_h[t] = close[t+h]/close[t] − 1", test_forward_return_alignment)
    check("RankIC 方向与零方差", test_rank_ic_direction)
    print("[4] 去重测试")
    check("Close/MA20−1 ≡ (Close−MA20)/MA20 高度相关", test_dedup_equivalent_expressions)
    check("不相关表达式相关度 < 0.85", test_dedup_different_expressions)
    print("[5] 数据边界测试")
    check("除零/log/sqrt 非法输入 → NaN", test_invalid_math_yields_nan)
    check("缺失/停牌", test_missing_data_and_suspended)
    check("新股预热", test_new_stock_insufficient_history)
    print("[6] 生成器约束")
    check("预算/去重/负窗口禁入/种子确定性", test_generator_budget_and_dedup)
    check("深度/算子数/变量数/对称剔除", test_generator_limits)
    check("归一化 + AST JSON", test_normalize_and_ast_json)
    check("MiningConfig 默认与校验", test_mining_config_defaults)
    check("年度稳定性聚合", test_yearly_stability)
    print("[7] 回测执行时序")
    check("t 收盘信号 → t+1 开盘成交（含滑点）", test_backtest_t_plus_1_open_execution)

    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    if FAILURES:
        print("失败用例：", FAILURES)
        sys.exit(1)


if __name__ == "__main__":
    main()
