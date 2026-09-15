# -*- coding: utf-8 -*-
"""排名快照:一次全宇宙评分的不可变记录。

每个快照记录:
  头表 rank_snapshot       计算时间 / 交易日 / 行情时间 / 行情来源 / 宇宙大小 / 权重口径
  明细 rank_snapshot_item  每只股票的行情(价/量/额)、综合分、排名、各策略分、因子组分、
                           买点区与买点状态、日K截止日期

设计原则:
  * 快照落库后不改写。同一 snapshot_id 下任何读取都得到同样的结果。
  * 综合分用默认权重;明细里保存了每个策略的原始分,前端用户自定义权重时
    由 groups.composite_from() 在快照数据上重算,依然确定。
  * 买点区来自 pro_signal 的 forecast 层(日K结构:价值区/POC/ATR),买点状态
    用快照时刻的实时价判断 —— "评分高"与"进入买点"是两个独立字段。
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import time
from typing import Optional

import pandas as pd

import cache
import spot_meta
from decision import groups
from repo.base import fetch_df, upsert

log = logging.getLogger(__name__)

HEADER_TABLE = "rank_snapshot"
ITEM_TABLE = "rank_snapshot_item"

HEADER_COLS = ["snapshot_id", "trade_date", "slot", "computed_at", "quote_time", "quote_source",
               "universe_n", "scored_n", "buyzone_n", "weights_key", "elapsed_ms", "status", "note"]
ITEM_COLS = ["snapshot_id", "code", "name", "industry", "price", "pct_change", "volume", "amount",
             "market_cap_yi", "roe", "debt_ratio", "composite", "rank", "signal", "sector_rank_pct",
             "kline_date", "strategy_json", "group_json", "buy_json", "extra_json"]

# 默认宇宙:总市值 ≥ MIN_CAP 亿 的前 UNIVERSE_N 只(按市值降序);买点区只算综合分前 BUYZONE_N 只
UNIVERSE_N = 800
MIN_CAP_YI = 50.0
BUYZONE_N = 120
LATEST_KEY = "decision:latest_snapshot"

DDL = """CREATE TABLE IF NOT EXISTS `rank_snapshot` (
    `snapshot_id` VARCHAR(20) NOT NULL COMMENT 'YYYYMMDD-HHMM',
    `trade_date` DATE NOT NULL,
    `slot` VARCHAR(5) NOT NULL COMMENT 'HH:MM',
    `computed_at` DATETIME NOT NULL,
    `quote_time` DATETIME NULL COMMENT '行情快照抓取时间',
    `quote_source` VARCHAR(60) NULL,
    `universe_n` INT NOT NULL DEFAULT 0,
    `scored_n` INT NOT NULL DEFAULT 0,
    `buyzone_n` INT NOT NULL DEFAULT 0,
    `weights_key` VARCHAR(40) NOT NULL DEFAULT 'default',
    `elapsed_ms` INT NOT NULL DEFAULT 0,
    `status` VARCHAR(16) NOT NULL DEFAULT 'ok',
    `note` VARCHAR(255) NULL,
    PRIMARY KEY (`snapshot_id`),
    INDEX `idx_rs_date` (`trade_date`, `computed_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE IF NOT EXISTS `rank_snapshot_item` (
    `snapshot_id` VARCHAR(20) NOT NULL,
    `code` VARCHAR(10) NOT NULL,
    `name` VARCHAR(50) NULL,
    `industry` VARCHAR(50) NULL,
    `price` DECIMAL(12,3) NULL,
    `pct_change` DECIMAL(8,3) NULL,
    `volume` DECIMAL(20,2) NULL,
    `amount` DECIMAL(20,2) NULL,
    `market_cap_yi` DECIMAL(14,2) NULL,
    `roe` DECIMAL(10,2) NULL,
    `debt_ratio` DECIMAL(10,2) NULL,
    `composite` DECIMAL(8,2) NOT NULL DEFAULT 0,
    `rank` INT NOT NULL DEFAULT 0,
    `signal` VARCHAR(10) NULL,
    `sector_rank_pct` DECIMAL(6,4) NULL,
    `kline_date` DATE NULL COMMENT '因子计算所用日K截止日',
    `strategy_json` MEDIUMTEXT NULL,
    `group_json` TEXT NULL,
    `buy_json` TEXT NULL,
    `extra_json` TEXT NULL COMMENT '趋势持续性/波动/流动性等辅助指标',
    PRIMARY KEY (`snapshot_id`, `code`),
    INDEX `idx_rsi_code` (`code`, `snapshot_id`),
    INDEX `idx_rsi_rank` (`snapshot_id`, `rank`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;"""


# ---------------------------------------------------------------------------
# 买点状态
# ---------------------------------------------------------------------------

BUY_STATE_LABEL = {
    "in_zone": "进入买点",
    "near_above": "临近买点·等小幅回踩",
    "wait_pullback": "等待回踩",
    "extended": "远离买点·不追高",
    "below_zone": "跌破买点区·等企稳",
    "invalidated": "跌破失效位·买点失效",
    "no_zone": "无有效买点区",
    "bearish": "方向偏空·不建仓",
}

# 买点质量分(0-100):进入买点区最高;远离/失效最低。与综合评分无关。
BUY_QUALITY = {
    "in_zone": 90, "near_above": 74, "wait_pullback": 55, "below_zone": 50,
    "extended": 25, "invalidated": 8, "no_zone": 40, "bearish": 15,
}


def entry_zone(direction: str, fc: dict, extra: dict) -> tuple[list | None, float | None, str]:
    """决策层买点区(与 pro_signal 的"价值区参考"区分)。

    趋势向上的股票很少回到 60 日价值区下沿,若用价值区做买点则强势股永远"远离买点"。
    这里按"回踩到短期均线 / 成交密集区"定义可操作的建仓区:
      up   : [max(价值区下沿, MA20), max(POC, VWAP20, MA10)]   失效位 = min(区下沿, MA20) × 0.985
      flat : [价值区下沿, POC]                                  失效位 = pro_signal 给出的失效位
      down : 不给买点(方向偏空不建仓)
    返回 (zone, invalid_level, basis)。
    """
    r2 = lambda x: round(float(x), 2)
    anchors = fc.get("anchors") or {}
    va = anchors.get("value_area") or [None, None]
    val, poc, vwap20 = va[0], anchors.get("poc"), anchors.get("vwap20")
    ma10, ma20 = (extra or {}).get("ma10"), (extra or {}).get("ma20")
    if direction == "down":
        return None, None, "方向偏空,不给买点区"
    if direction == "up":
        lo_c = [x for x in (val, ma20) if x]
        hi_c = [x for x in (poc, vwap20, ma10) if x]
        if not lo_c or not hi_c:
            ref = fc.get("buy_ref")
            return (ref, fc.get("invalid_level"), "锚点不足,沿用价值区参考") if ref else (None, None, "锚点不足")
        lo, hi = max(lo_c), max(hi_c)
        if lo > hi:
            lo, hi = hi * 0.99, hi
        inv = min(lo, ma20 or lo) * 0.985
        return [r2(lo), r2(hi)], r2(inv), "回踩区 = [max(价值区下沿, MA20), max(POC, VWAP20, MA10)];失效 = 区下沿/MA20 之下 1.5%"
    ref = fc.get("buy_ref")
    return (ref, fc.get("invalid_level"), "震荡区间:价值区下沿 ~ POC") if ref else (None, None, "无区间")


def buy_state(price: float, buy_ref, invalid_level, direction: str) -> dict:
    """由实时价 + 买点区判断当前买点状态,返回 {state, label, dist_pct, quality}。

    dist_pct:现价相对买点区的偏离(%),>0 在区上方,<0 在区下方,0 在区内。
    """
    if direction == "down":
        return {"state": "bearish", "label": BUY_STATE_LABEL["bearish"], "dist_pct": None,
                "quality": BUY_QUALITY["bearish"]}
    if not buy_ref or not price or price <= 0:
        return {"state": "no_zone", "label": BUY_STATE_LABEL["no_zone"], "dist_pct": None,
                "quality": BUY_QUALITY["no_zone"]}
    lo, hi = float(buy_ref[0]), float(buy_ref[1])
    if lo > hi:
        lo, hi = hi, lo
    if lo <= price <= hi:
        st, dist = "in_zone", 0.0
    elif price > hi:
        dist = (price - hi) / hi * 100
        st = "near_above" if dist <= 1.5 else ("wait_pullback" if dist <= 5 else "extended")
    else:
        dist = (price - lo) / lo * 100
        st = "invalidated" if (invalid_level and price < float(invalid_level)) else "below_zone"
    q = BUY_QUALITY[st]
    if direction == "up" and st in ("in_zone", "near_above"):
        q = min(100, q + 5)
    return {"state": st, "label": BUY_STATE_LABEL[st], "dist_pct": round(dist, 2), "quality": q}


# ---------------------------------------------------------------------------
# 构建
# ---------------------------------------------------------------------------

def _now() -> dt.datetime:
    return dt.datetime.now()


def make_snapshot_id(ts: dt.datetime) -> str:
    return ts.strftime("%Y%m%d-%H%M")


def _spot_frame():
    """返回 (spot_df, meta)。优先 redis 里的 warm spot;冷则触发一次抓取。"""
    df = cache.get("spot")
    if df is None or not hasattr(df, "columns") or df.empty:
        try:
            from app import fetch_spot
            df = fetch_spot()
        except Exception as e:
            log.warning("[snapshot] fetch_spot failed: %s", e)
            df = None
    meta = spot_meta.get() or {}
    return df, meta


def _num(v, default=None):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return f


def _daily_extras(df: pd.DataFrame, live_price: float, name: str) -> dict:
    """由日K尾部算趋势持续性与风险辅助量(全部只用已收盘数据,无未来函数)。

    above_ma20_pct  近 20 日收盘位于 MA20 上方的比例(趋势持续性)
    ma20_slope_pct  MA20 近 5 日斜率(%)
    ret20_pct       近 20 日涨幅(%)
    atr_pct         14 日 ATR / 收盘(%),波动率
    dd20_pct        近 20 日收盘最大回撤(%)
    amt20_yi        近 20 日日均成交额估算(亿;库内成交量单位为股 → ×收盘)
    """
    from indicators import calc_atr
    out = {"above_ma20_pct": None, "ma20_slope_pct": None, "ret20_pct": None,
           "atr_pct": None, "dd20_pct": None, "amt20_yi": None,
           "ma5": None, "ma10": None, "ma20": None,
           "is_st": "ST" in str(name or "").upper()}
    try:
        c = pd.to_numeric(df["收盘"], errors="coerce").astype(float)
        h = pd.to_numeric(df["最高"], errors="coerce").astype(float)
        l = pd.to_numeric(df["最低"], errors="coerce").astype(float)
        v = pd.to_numeric(df["成交量"], errors="coerce").astype(float)
        if len(c) >= 25:
            ma20 = c.rolling(20).mean()
            out["ma5"] = round(float(c.tail(5).mean()), 3)
            out["ma10"] = round(float(c.tail(10).mean()), 3)
            out["ma20"] = round(float(ma20.iloc[-1]), 3)
            tail_c, tail_m = c.tail(20), ma20.tail(20)
            out["above_ma20_pct"] = round(float((tail_c > tail_m).mean()), 3)
            if ma20.iloc[-6] and ma20.iloc[-6] > 0:
                out["ma20_slope_pct"] = round(float(ma20.iloc[-1] / ma20.iloc[-6] - 1) * 100, 2)
            if c.iloc[-21] and c.iloc[-21] > 0:
                out["ret20_pct"] = round(float(c.iloc[-1] / c.iloc[-21] - 1) * 100, 2)
            atr = calc_atr(h, l, c, 14).iloc[-1]
            if atr == atr and c.iloc[-1] > 0:
                out["atr_pct"] = round(float(atr / c.iloc[-1]) * 100, 2)
            t20 = c.tail(20)
            peak = t20.cummax()
            out["dd20_pct"] = round(float(((t20 / peak) - 1).min()) * 100, 2)
            out["amt20_yi"] = round(float((v.tail(20) * c.tail(20)).mean() / 1e8), 2)
    except Exception:
        pass
    return out


def _select_universe(spot: pd.DataFrame, universe_n: int, min_cap: float) -> pd.DataFrame:
    df = spot.copy()
    code_col = "代码" if "代码" in df.columns else "code"
    cap_col = "总市值_亿" if "总市值_亿" in df.columns else ("market_cap_yi" if "market_cap_yi" in df.columns else None)
    df[code_col] = df[code_col].astype(str).str.zfill(6)
    if cap_col:
        df[cap_col] = pd.to_numeric(df[cap_col], errors="coerce")
        df = df[df[cap_col] >= min_cap]
        df = df.sort_values(cap_col, ascending=False, na_position="last")
    df = df.drop_duplicates(code_col)
    return df.head(universe_n)


def build(universe_n: int = UNIVERSE_N, min_cap: float = MIN_CAP_YI,
          buyzone_n: int = BUYZONE_N, note: str | None = None) -> Optional[str]:
    """构建并落库一次排名快照;返回 snapshot_id(失败返回 None)。"""
    from api.strategies_v2 import _bulk_load_panels, _load_ctx, _score_all, _latest_fundamental_metrics
    from pro_signal import pro_signal

    t0 = time.time()
    spot, qmeta = _spot_frame()
    if spot is None or not hasattr(spot, "columns") or spot.empty:
        log.warning("[snapshot] no spot data — abort")
        return None

    uni = _select_universe(spot, universe_n, min_cap)
    code_col = "代码" if "代码" in uni.columns else "code"
    name_col = "名称" if "名称" in uni.columns else "name"
    ind_col = "行业" if "行业" in uni.columns else "industry"
    price_col = "最新价" if "最新价" in uni.columns else "price"
    chg_col = "涨跌幅" if "涨跌幅" in uni.columns else "pct_change"
    vol_col = "成交量" if "成交量" in uni.columns else "volume"
    amt_col = "成交额" if "成交额" in uni.columns else "amount"
    cap_col = "总市值_亿" if "总市值_亿" in uni.columns else "market_cap_yi"

    codes = uni[code_col].tolist()
    panels = {}
    for s in range(0, len(codes), 500):
        try:
            panels.update(_bulk_load_panels(codes[s:s + 500]))
        except Exception as e:
            log.warning("[snapshot] bulk load chunk failed: %s", e)

    rows: list[dict] = []
    ctx_map = {}
    for _, r in uni.iterrows():
        code = str(r[code_col]).zfill(6)
        ctx = panels.get(code)
        if ctx is None:
            try:
                ctx = _load_ctx(code)
            except Exception:
                continue
        if ctx.daily_df is None or len(ctx.daily_df) < 20:
            continue
        if not ctx.industry and ind_col in r.index:
            ctx.industry = str(r.get(ind_col) or "")
        if not ctx.market_cap_yi:
            ctx.market_cap_yi = _num(r.get(cap_col), 0) or 0
        live_price = _num(r.get(price_col)) or _num(ctx.price) or 0.0
        try:
            composite, signal, _d, out_list = _score_all(ctx)
        except Exception as e:
            log.debug("[snapshot] score %s failed: %s", code, e)
            continue
        roe, debt = _latest_fundamental_metrics(ctx)
        strat = [{"id": it["id"], "score": it.get("score", 0), "signal": it.get("signal"),
                  "triggered": bool(it.get("triggered")), "weight": it.get("weight", 0),
                  "no_data": bool(it.get("no_data")) or bool((it.get("details") or {}).get("disabled"))}
                 for it in out_list]
        try:
            kline_date = pd.to_datetime(ctx.daily_df["日期"].iloc[-1]).date()
        except Exception:
            kline_date = None
        rows.append({
            "snapshot_id": None, "code": code,
            "name": str(r.get(name_col) or ctx.name or code)[:50],
            "industry": str(r.get(ind_col) or ctx.industry or "")[:50],
            "price": live_price, "pct_change": _num(r.get(chg_col)),
            "volume": _num(r.get(vol_col)), "amount": _num(r.get(amt_col)),
            "market_cap_yi": _num(ctx.market_cap_yi), "roe": roe, "debt_ratio": debt,
            "composite": float(composite), "rank": 0, "signal": signal,
            "sector_rank_pct": _num(ctx.sector_rank), "kline_date": kline_date,
            "strategy_json": json.dumps(strat, ensure_ascii=False, separators=(",", ":")),
            "group_json": json.dumps(groups.group_scores(strat), ensure_ascii=False, separators=(",", ":")),
            "buy_json": None,
            "extra_json": json.dumps(_daily_extras(ctx.daily_df, live_price, r.get(name_col) or ctx.name),
                                     ensure_ascii=False, separators=(",", ":")),
        })
        ctx_map[code] = ctx

    if not rows:
        log.warning("[snapshot] nothing scored — abort")
        return None
    # 本次计算时间 = 评分完成时刻(行情时间单独记录在 quote_time)
    computed_at = _now().replace(microsecond=0)
    sid = make_snapshot_id(computed_at)
    for row in rows:
        row["snapshot_id"] = sid

    # 排名:综合分降序,同分按代码,保证确定性
    rows.sort(key=lambda x: (-x["composite"], x["code"]))
    for i, row in enumerate(rows, 1):
        row["rank"] = i

    # 买点区:只给前 buyzone_n 只算(pro_signal 九维 + forecast),其余 buy_json 留空
    bz = 0
    for row in rows[:buyzone_n]:
        ctx = ctx_map.get(row["code"])
        if ctx is None:
            continue
        try:
            res = pro_signal(ctx)
            fc = res.forecast or {}
            extra = json.loads(row["extra_json"]) if row.get("extra_json") else {}
            zone, inv, basis = entry_zone(res.direction, fc, extra)
            st = buy_state(row["price"], zone, inv, res.direction)
            row["buy_json"] = json.dumps({
                "buy_ref": zone, "sell_ref": fc.get("sell_ref"),
                "invalid_level": inv, "zone_basis": basis,
                "pro_buy_ref": fc.get("buy_ref"), "pro_invalid_level": fc.get("invalid_level"),
                "invalidation": (f"收盘有效跌破 {inv}:回踩买点逻辑失效,不接、不补仓" if inv else fc.get("invalidation")),
                "expected_target": fc.get("expected_target"),
                "direction": res.direction, "label": res.label,
                "pro_composite": res.composite, "pro_confidence": res.confidence,
                "atr14": (fc.get("anchors") or {}).get("atr14"),
                "kline_close": res.price,
                **st,
            }, ensure_ascii=False, separators=(",", ":"))
            bz += 1
        except Exception as e:
            log.debug("[snapshot] buyzone %s failed: %s", row["code"], e)

    header = {
        "snapshot_id": sid,
        "trade_date": computed_at.date(),
        "slot": computed_at.strftime("%H:%M"),
        "computed_at": computed_at,
        "quote_time": qmeta.get("fetched_at"),
        "quote_source": qmeta.get("source"),
        "universe_n": len(uni), "scored_n": len(rows), "buyzone_n": bz,
        "weights_key": "default",
        "elapsed_ms": int((time.time() - t0) * 1000),
        "status": "ok", "note": note,
    }
    n_items = upsert(ITEM_TABLE, rows, ITEM_COLS, update_columns=ITEM_COLS[2:])
    n_head = upsert(HEADER_TABLE, [header], HEADER_COLS, update_columns=HEADER_COLS[1:])
    if not n_head:
        log.warning("[snapshot] header upsert failed for %s", sid)
        return None
    cache.set(LATEST_KEY, sid, 24 * 3600)
    log.info("[snapshot] %s: universe=%d scored=%d buyzone=%d in %.1fs (items=%d)",
             sid, len(uni), len(rows), bz, time.time() - t0, n_items)
    return sid


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------

def _header_rows(df: pd.DataFrame) -> list[dict]:
    out = []
    for _, r in df.iterrows():
        out.append({
            "snapshot_id": r["snapshot_id"],
            "trade_date": str(r["trade_date"]),
            "slot": r["slot"],
            "computed_at": str(r["computed_at"]),
            "quote_time": str(r["quote_time"]) if r.get("quote_time") is not None and not pd.isna(r.get("quote_time")) else None,
            "quote_source": r.get("quote_source"),
            "universe_n": int(r.get("universe_n") or 0),
            "scored_n": int(r.get("scored_n") or 0),
            "buyzone_n": int(r.get("buyzone_n") or 0),
            "weights_key": r.get("weights_key"),
            "elapsed_ms": int(r.get("elapsed_ms") or 0),
            "status": r.get("status"),
        })
    return out


def latest_id() -> Optional[str]:
    sid = cache.get(LATEST_KEY)
    if isinstance(sid, str) and sid:
        return sid
    df = fetch_df(f"SELECT snapshot_id FROM {HEADER_TABLE} WHERE status='ok' "
                  "ORDER BY computed_at DESC LIMIT 1")
    if df.empty:
        return None
    sid = str(df.iloc[0]["snapshot_id"])
    cache.set(LATEST_KEY, sid, 3600)
    return sid


def header(snapshot_id: str) -> Optional[dict]:
    df = fetch_df(f"SELECT * FROM {HEADER_TABLE} WHERE snapshot_id=:s", {"s": snapshot_id})
    rows = _header_rows(df)
    return rows[0] if rows else None


def headers(trade_date: dt.date | str | None = None, limit: int = 40) -> list[dict]:
    if trade_date:
        df = fetch_df(f"SELECT * FROM {HEADER_TABLE} WHERE trade_date=:d AND status='ok' "
                      "ORDER BY computed_at ASC", {"d": str(trade_date)})
    else:
        df = fetch_df(f"SELECT * FROM {HEADER_TABLE} WHERE status='ok' "
                      "ORDER BY computed_at DESC LIMIT :n", {"n": int(limit)})
    return _header_rows(df)


def recent_ids(n: int = 8, before: str | None = None) -> list[str]:
    """最近 n 个快照 id,时间升序。before 给定时只取更早的(用于'上一快照')。"""
    if before:
        df = fetch_df(f"SELECT snapshot_id FROM {HEADER_TABLE} WHERE status='ok' AND snapshot_id < :b "
                      "ORDER BY computed_at DESC LIMIT :n", {"b": before, "n": int(n)})
    else:
        df = fetch_df(f"SELECT snapshot_id FROM {HEADER_TABLE} WHERE status='ok' "
                      "ORDER BY computed_at DESC LIMIT :n", {"n": int(n)})
    ids = [str(x) for x in df["snapshot_id"].tolist()] if not df.empty else []
    return list(reversed(ids))


def _parse_item(r) -> dict:
    def _j(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        try:
            return json.loads(v)
        except Exception:
            return None
    return {
        "snapshot_id": r["snapshot_id"],
        "code": str(r["code"]).zfill(6),
        "name": r.get("name") or "",
        "industry": r.get("industry") or "",
        "price": _num(r.get("price")),
        "pct_change": _num(r.get("pct_change")),
        "volume": _num(r.get("volume")),
        "amount": _num(r.get("amount")),
        "market_cap_yi": _num(r.get("market_cap_yi")),
        "roe": _num(r.get("roe")),
        "debt_ratio": _num(r.get("debt_ratio")),
        "composite": _num(r.get("composite"), 0.0),
        "rank": int(r.get("rank") or 0),
        "signal": r.get("signal"),
        "sector_rank_pct": _num(r.get("sector_rank_pct")),
        "kline_date": str(r["kline_date"]) if r.get("kline_date") is not None and not pd.isna(r.get("kline_date")) else None,
        "strategies": _j(r.get("strategy_json")) or [],
        "groups": _j(r.get("group_json")) or {},
        "buy": _j(r.get("buy_json")),
        "extra": _j(r.get("extra_json")) or {},
    }


def items(snapshot_id: str, limit: int | None = None) -> list[dict]:
    sql = f"SELECT * FROM {ITEM_TABLE} WHERE snapshot_id=:s ORDER BY `rank` ASC"
    params = {"s": snapshot_id}
    if limit:
        sql += " LIMIT :n"
        params["n"] = int(limit)
    df = fetch_df(sql, params)
    return [_parse_item(r) for _, r in df.iterrows()] if not df.empty else []


def items_multi(snapshot_ids: list[str], top_rank: int | None = None) -> dict[str, list[dict]]:
    """多个快照的明细,{snapshot_id: [items]}。top_rank 限定只取排名 ≤ N 的行。"""
    if not snapshot_ids:
        return {}
    marks = ",".join(f":s{i}" for i in range(len(snapshot_ids)))
    params = {f"s{i}": s for i, s in enumerate(snapshot_ids)}
    sql = f"SELECT * FROM {ITEM_TABLE} WHERE snapshot_id IN ({marks})"
    if top_rank:
        sql += " AND `rank` <= :r"
        params["r"] = int(top_rank)
    sql += " ORDER BY snapshot_id, `rank`"
    df = fetch_df(sql, params)
    out: dict[str, list[dict]] = {s: [] for s in snapshot_ids}
    if df.empty:
        return out
    for _, r in df.iterrows():
        out.setdefault(str(r["snapshot_id"]), []).append(_parse_item(r))
    return out


def history(code: str, n: int = 24) -> list[dict]:
    """单只股票最近 n 个快照的轨迹(时间升序),含快照头的时间/来源。"""
    df = fetch_df(
        f"SELECT i.*, h.computed_at, h.quote_time, h.quote_source, h.slot, h.trade_date "
        f"FROM {ITEM_TABLE} i JOIN {HEADER_TABLE} h ON h.snapshot_id = i.snapshot_id "
        "WHERE i.code=:c AND h.status='ok' ORDER BY h.computed_at DESC LIMIT :n",
        {"c": str(code).zfill(6), "n": int(n)})
    if df.empty:
        return []
    out = []
    for _, r in df.iterrows():
        it = _parse_item(r)
        it["computed_at"] = str(r["computed_at"])
        it["quote_time"] = str(r["quote_time"]) if r.get("quote_time") is not None and not pd.isna(r.get("quote_time")) else None
        it["quote_source"] = r.get("quote_source")
        it["slot"] = r.get("slot")
        it["trade_date"] = str(r["trade_date"])
        out.append(it)
    return list(reversed(out))
