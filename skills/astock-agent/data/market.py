"""行情数据模块 (设计文档 §3.1)。

负责: 交易日历、指数涨跌、两市成交额/量能(含环比)、涨跌家数、板块资金流。
数据源策略: 东财优先, 失败自动降级新浪 (东财行情接口在部分网络下会被限流)。
所有接口失败时返回空值/None, 由上层降级处理, 不抛出中断。
"""
from __future__ import annotations

import datetime as dt
import os
import time
from functools import lru_cache

os.environ.setdefault("TQDM_DISABLE", "1")  # 抑制 akshare 内部进度条

import akshare as ak  # noqa: E402

import config  # noqa: E402

try:  # 部分 tqdm 版本不识别 TQDM_DISABLE, 直接改默认参数兜底
    from tqdm import tqdm as _tqdm

    _tqdm_init = _tqdm.__init__

    def _quiet_init(self, *args, **kwargs):
        kwargs.setdefault("disable", True)
        _tqdm_init(self, *args, **kwargs)

    _tqdm.__init__ = _quiet_init
except Exception:  # noqa: BLE001
    pass


def _retry(func, *args, retries: int | None = None, **kwargs):
    n = retries or config.FETCH_RETRIES
    last = None
    for i in range(1, n + 1):
        try:
            return func(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            last = e
            if i < n:
                time.sleep(config.FETCH_WAIT * i)
    raise last


def _num(v, default=None):
    try:
        f = float(str(v).replace("%", "").replace(",", ""))
    except (TypeError, ValueError):
        return default
    return f if f == f else default  # 过滤 NaN


# ---------------------------------------------------------------------------
# 交易日历
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def trade_dates() -> tuple[str, ...]:
    """全部交易日 (YYYYMMDD, 升序); 接口失败返回空元组。"""
    try:
        df = _retry(ak.tool_trade_date_hist_sina)
        return tuple(
            d.strftime("%Y%m%d") if hasattr(d, "strftime") else str(d).replace("-", "")
            for d in df["trade_date"]
        )
    except Exception:
        return ()


def resolve_trade_date(date: str | None = None) -> str:
    """解析为 <= 指定日期的最近交易日 (YYYYMMDD)。"""
    target = (date or dt.date.today().strftime("%Y%m%d")).replace("-", "")
    dates = trade_dates()
    if dates:
        prior = [d for d in dates if d <= target]
        if prior:
            return prior[-1]
    day = dt.datetime.strptime(target, "%Y%m%d").date()
    while day.weekday() >= 5:  # 日历接口失败时仅跳过周末
        day -= dt.timedelta(days=1)
    return day.strftime("%Y%m%d")


def prev_trade_date(date: str) -> str:
    dates = trade_dates()
    if dates and date in dates:
        i = dates.index(date)
        if i > 0:
            return dates[i - 1]
    day = dt.datetime.strptime(date, "%Y%m%d").date() - dt.timedelta(days=1)
    while day.weekday() >= 5:
        day -= dt.timedelta(days=1)
    return day.strftime("%Y%m%d")


def is_today(date: str) -> bool:
    return date == dt.date.today().strftime("%Y%m%d")


# ---------------------------------------------------------------------------
# 指数与两市成交额/量能
# ---------------------------------------------------------------------------

_INDEXES = [("sh000001", "上证指数"), ("sz399001", "深证成指"), ("sz399006", "创业板指")]
_AMOUNT_SYMS = ("sh000001", "sz399001")  # 两市 = 沪 + 深


def _daily_rows(sym: str) -> list[dict]:
    """指数日线 [{date, close, amount(元|None), volume(股)}], 升序。东财 -> 新浪。"""
    try:
        df = _retry(ak.stock_zh_index_daily_em, symbol=sym, retries=1)
        return [
            {
                "date": str(r["date"]),
                "close": _num(r.get("close")),
                "amount": _num(r.get("amount")),
                "volume": _num(r.get("volume")),
            }
            for _, r in df.iterrows()
        ]
    except Exception:
        pass
    try:
        df = _retry(ak.stock_zh_index_daily, symbol=sym, retries=2)
        return [
            {
                "date": str(r["date"]),
                "close": _num(r.get("close")),
                "amount": None,  # 新浪日线无成交额
                "volume": _num(r.get("volume")),
            }
            for _, r in df.iterrows()
        ]
    except Exception:
        return []


def _index_spot_sina() -> dict[str, dict]:
    """新浪指数实时: {名称: {close, pct, amount(元), volume(股)}}。"""
    try:
        df = _retry(ak.stock_zh_index_spot_sina, retries=2)
    except Exception:
        return {}
    out = {}
    wanted = {name for _, name in _INDEXES}
    for _, r in df.iterrows():
        name = str(r.get("名称", ""))
        if name in wanted:
            out[name] = {
                "close": _num(r.get("最新价")),
                "pct": _num(r.get("涨跌幅")),
                "amount": _num(r.get("成交额")),
                "volume": _num(r.get("成交量")),  # 单位沪深不一致, 由环比自愈逻辑处理
            }
    return out


def _sane_ratio(cur, prev) -> float | None:
    """当日/昨日比值, 自动修正 手/股 等 100 倍单位错位; 无法修正返回 None。"""
    if not cur or not prev:
        return None
    r = cur / prev
    for factor in (1, 100, 0.01):
        if 0.2 < r * factor < 5:
            return r * factor
    return None


def _sane_chg(cur, prev) -> float | None:
    """金额环比 (金额来源一致, 不做单位自愈): 比值在合理区间才返回。"""
    if not cur or not prev:
        return None
    r = cur / prev
    return round(r - 1, 4) if 0.2 < r < 5 else None


def index_snapshot(date: str) -> dict:
    """指定交易日的指数涨跌、两市成交额(元)与量能环比。

    返回 {indexes: [{name, close, pct}], amount, prev_amount,
          amount_chg, chg_basis: "amount"|"volume"|None}
    历史日走日线; 当日日线未生成时用新浪实时补齐。
    """
    dash = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    per: dict[str, tuple[str, dict | None, dict | None]] = {}  # name -> (sym, cur, prev)
    spot_needed = False
    for sym, name in _INDEXES:
        rows = [r for r in _daily_rows(sym) if r["date"] <= dash]
        if not rows:
            spot_needed = True
            per[name] = (sym, None, None)
            continue
        if rows[-1]["date"] == dash:
            per[name] = (sym, rows[-1], rows[-2] if len(rows) >= 2 else None)
        else:
            per[name] = (sym, None, rows[-1])  # 当日未生成, 最后一行即昨日
            spot_needed = True

    spot = _index_spot_sina() if (spot_needed and is_today(date)) else {}

    indexes = []
    amount = prev_amount = 0.0
    vol_ratios: list[float] = []
    for name, (sym, cur, prev) in per.items():
        if cur is not None:
            pct = None
            if prev and prev.get("close"):
                pct = round((cur["close"] - prev["close"]) / prev["close"] * 100, 2)
            entry = {"name": name, "close": cur["close"], "pct": pct}
            cur_amount, cur_volume = cur.get("amount"), cur.get("volume")
        elif name in spot:
            s = spot[name]
            entry = {"name": name, "close": s["close"], "pct": s["pct"]}
            cur_amount, cur_volume = s.get("amount"), s.get("volume")
        else:
            continue
        indexes.append(entry)
        if sym in _AMOUNT_SYMS:
            amount += cur_amount or 0
            if prev:
                prev_amount += prev.get("amount") or 0
                r = _sane_ratio(cur_volume, prev.get("volume"))
                if r is not None:
                    vol_ratios.append(r)

    amount_chg, basis = _sane_chg(amount, prev_amount), "amount"
    if amount_chg is None and vol_ratios:
        amount_chg, basis = round(sum(vol_ratios) / len(vol_ratios) - 1, 4), "volume"
    if amount_chg is None:
        basis = None

    return {
        "indexes": indexes,
        "amount": amount or None,
        "prev_amount": prev_amount or None,
        "amount_chg": amount_chg,
        "chg_basis": basis,
    }


# ---------------------------------------------------------------------------
# 涨跌家数 / 市场活跃度 (仅当日实时有效)
# ---------------------------------------------------------------------------

def market_activity() -> dict | None:
    """乐咕赚钱效应 -> 东财全市场快照统计, 均失败返回 None。"""
    try:
        df = _retry(ak.stock_market_activity_legu, retries=1)
        kv = {str(r["item"]).strip(): r["value"] for _, r in df.iterrows()}

        def g(key):
            return _num(kv.get(key))

        if g("上涨") is not None:
            return {
                "up": g("上涨"),
                "down": g("下跌"),
                "limit_up": g("涨停"),
                "limit_down": g("跌停"),
                "real_zt": g("真实涨停"),
                "real_dt": g("真实跌停"),
                "activity": g("活跃度"),
            }
    except Exception:
        pass
    try:
        df = _retry(ak.stock_zh_a_spot_em, retries=1)
        pcts = [p for p in (_num(v) for v in df["涨跌幅"]) if p is not None]
        if pcts:
            return {
                "up": sum(1 for p in pcts if p > 0),
                "down": sum(1 for p in pcts if p < 0),
                "limit_up": None,
                "limit_down": None,
                "real_zt": None,
                "real_dt": None,
                "activity": None,
            }
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 板块资金流 (东财, 仅当日)
# ---------------------------------------------------------------------------

def sector_flows() -> dict[str, dict]:
    """行业 + 概念板块当日主力净流入: {板块名: {pct, net_inflow, top_stock, kind}}。"""
    flows: dict[str, dict] = {}
    for sector_type, kind in (("行业资金流", "行业"), ("概念资金流", "概念")):
        try:
            df = _retry(ak.stock_sector_fund_flow_rank, indicator="今日",
                        sector_type=sector_type, retries=1)
        except Exception:
            continue
        for _, r in df.iterrows():
            name = str(r.get("名称", "")).strip()
            if not name:
                continue
            flows.setdefault(
                name,
                {
                    "pct": _num(r.get("今日涨跌幅")),
                    "net_inflow": _num(r.get("主力净流入-净额")),
                    "top_stock": str(r.get("今日主力净流入最大股", "") or ""),
                    "kind": kind,
                },
            )
    return flows
