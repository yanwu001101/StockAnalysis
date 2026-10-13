"""Read-only coverage diagnostics, not an exchange-calendar freshness oracle.

Only grouped latest-per-code rows are loaded. Historical and reference-session
coverage are deliberately separate; a complete old table is not a fresh table.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import text

SHANGHAI = dt.timezone(dt.timedelta(hours=8))
REFERENCE_NOTE = "参考日为库内已观测行情日，未接交易所日历；参考日满覆盖不代表已追平最新交易日。"


@dataclass(frozen=True)
class TableSpec:
    date: str
    fields: tuple[str, ...]
    mode: str = "SESSION"
    universe: str = "STOCK"


# Static SQL identifier whitelist. Minute bars have no implemented schema here.
TABLES = {
    "stock_kline_daily": TableSpec("trade_date", ("open", "close", "high", "low", "volume")),
    "stock_kline_weekly": TableSpec("trade_date", ("open", "close", "volume"), "WEEK"),
    "index_kline_daily": TableSpec("trade_date", ("close",), universe="INDEX"),
    "industry_index_daily": TableSpec("trade_date", ("close",), universe="INDUSTRY"),
    "stock_moneyflow": TableSpec("trade_date", ("main_net", "super_large_net")),
    "stock_northbound": TableSpec("trade_date", ("hold_shares", "hold_ratio", "net_buy"), "EVENT"),
    "stock_fundamental": TableSpec("report_date", ("ann_date", "revenue", "net_profit", "roe"), "REPORT"),
    "stock_shareholder": TableSpec("report_date", ("holder_count", "top10_ratio"), "REPORT"),
    "stock_lhb": TableSpec("trade_date", ("net_amount",), "EVENT"),
    "stock_dividend": TableSpec("ann_date", ("ex_date", "cash_per_10"), "EVENT"),
}


def _date(value) -> dt.date | None:
    if value is None:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


def cutoff(now: dt.datetime | None = None) -> tuple[dt.datetime, dt.date]:
    now = now or dt.datetime.now(SHANGHAI)
    # Naive callers are explicitly interpreted as exchange-local, not host-local.
    now = now.replace(tzinfo=SHANGHAI) if now.tzinfo is None else now.astimezone(SHANGHAI)
    day = now.date() if now.time() >= dt.time(16, 30) else now.date() - dt.timedelta(days=1)
    return now, day


def load_latest(conn, table: str, limit_date: dt.date) -> list[dict]:
    spec = TABLES[table]
    # Multiple seats/report variants on the same date: count a code once, and a
    # field once when at least one latest-date record supplies it. Zero is valid.
    flags = ", ".join(f"MAX(CASE WHEN t.{f} IS NOT NULL THEN 1 ELSE 0 END) AS {f}" for f in spec.fields)
    query = f"""SELECT t.code, m.latest_date, {flags}
        FROM {table} t JOIN (
            SELECT code, MAX({spec.date}) AS latest_date FROM {table}
            WHERE {spec.date} <= :cutoff GROUP BY code
        ) m ON t.code=m.code AND t.{spec.date}=m.latest_date
        GROUP BY t.code, m.latest_date"""
    return [dict(row) for row in conn.execute(text(query), {"cutoff": limit_date}).mappings()]


def stock_universe(conn, snapshot) -> tuple[set[str] | None, str]:
    from core.universe import select_codes
    try:
        if snapshot is not None and hasattr(snapshot, "columns"):
            amount_col = next((c for c in ("amount", "成交额") if c in snapshot.columns), None)
            codes = select_codes(snapshot)
            if codes:
                return set(codes), "ACTIVE_SPOT_SNAPSHOT" if amount_col else "SPOT_SNAPSHOT_ACTIVITY_UNKNOWN"
    except (ValueError, TypeError, AttributeError):
        pass
    try:
        codes = {str(row[0]).strip().zfill(6) for row in conn.execute(text("SELECT DISTINCT code FROM stock_info")) if row[0]}
        if codes:
            return codes, "STOCK_INFO_FALLBACK"
    except Exception:
        pass
    return None, "UNKNOWN"


def summarize(rows: list[dict], spec: TableSpec, universe: set[str] | None,
              universe_source: str, anchor: dt.date | None) -> dict:
    by_code = {str(r["code"]): r for r in rows if _date(r.get("latest_date")) is not None}
    scoped = by_code if universe is None else {c: r for c, r in by_code.items() if c in universe}
    size = len(universe) if universe is not None else None
    dates = [_date(r["latest_date"]) for r in scoped.values()]
    latest = max(dates, default=None)
    history = len(scoped)
    event = spec.mode in ("EVENT", "REPORT")
    covered = None
    if anchor is not None and not event:
        covered = sum(d.isocalendar()[:2] == anchor.isocalendar()[:2] if spec.mode == "WEEK"
                      else d == anchor for d in dates)
    pct = lambda n: round(n / size * 100, 1) if size and n is not None else None
    if event:
        status = "EVENT_DRIVEN"
    elif size is None or size == 0 or anchor is None:
        status = "UNKNOWN"
    elif not history:
        status = "NO_DATA"
    elif covered == size:
        status = "COVERED"
    elif covered == 0:
        status = "DELAYED"
    else:
        status = "PARTIAL"
    note = ("事件/报告期数据：没有逐日记录不等于漏采；日期不是实际可获得时间证明。" if event else REFERENCE_NOTE)
    if spec.mode == "WEEK":
        note += " 周线按参考日所在周匹配，可能是未完成周。"
    if universe_source == "STORED_INDUSTRY_CODES":
        note += " 行业分母仅为已入库代码，完整行业目录尚未核验。"
    elif universe_source != "ACTIVE_SPOT_SNAPSHOT" and spec.universe == "STOCK":
        note += " 股票分母非已验证活跃快照。"
    return {
        "status": status, "coverageMode": spec.mode,
        "historyCodes": history, "historyCoveragePct": pct(history),
        "latestDate": latest.isoformat() if latest else None,
        "anchorDate": anchor.isoformat() if anchor else None,
        "anchorSource": "LATEST_OBSERVED_MARKET_SESSION", "calendarVerified": False,
        "eligibleUniverse": size, "universeSource": universe_source,
        "coveredOnAnchor": covered, "latestCoveragePct": pct(covered),
        "staleCodes": history - covered if covered is not None and size is not None else None,
        "missingCodes": size - history if size is not None else None,
        "fieldCoverage": [{"field": f, "presentCodes": sum(bool(r.get(f)) for r in scoped.values()),
                           "eligibleCodes": history,
                           "coveragePct": round(sum(bool(r.get(f)) for r in scoped.values()) / history * 100, 1) if history else None,
                           "scope": "LATEST_RECORD_PER_CODE"} for f in spec.fields],
        "fieldCoverageNote": "每代码最新日期至少一条记录字段非空；不等于数值正确、当日齐全或历史可用。",
        "note": note,
    }


def collect_freshness(conn, snapshot=None, now: dt.datetime | None = None) -> dict:
    now, limit_date = cutoff(now)
    stock_codes, stock_source = stock_universe(conn, snapshot)
    rows, errors = {}, {}
    for table in TABLES:
        try:
            rows[table] = load_latest(conn, table, limit_date)
        except Exception as exc:
            errors[table] = str(exc)[:500]
    # Neither a stale index nor a table-local MAX may silently set its own target.
    observed = [_date(r["latest_date"]) for table in ("stock_kline_daily", "index_kline_daily")
                for r in rows.get(table, []) if _date(r.get("latest_date")) is not None]
    anchor = max(observed, default=None)
    freshness = {}
    for table, spec in TABLES.items():
        codes, source = stock_codes, stock_source
        if spec.universe == "INDEX":
            from pipelines.index_kline import BENCHMARKS
            codes, source = set(BENCHMARKS), "CONFIGURED_BENCHMARKS"
        elif spec.universe == "INDUSTRY":
            codes, source = {str(r["code"]) for r in rows.get(table, [])} or None, "STORED_INDUSTRY_CODES"
        if table in errors:
            freshness[table] = {"status": "FAILED", "error": errors[table],
                                "historyCodes": None, "latestCoveragePct": None,
                                "historyCoveragePct": None, "latestDate": None,
                                "eligibleUniverse": len(codes) if codes is not None else None,
                                "universeSource": source, "anchorDate": anchor.isoformat() if anchor else None}
        else:
            freshness[table] = summarize(rows[table], spec, codes, source, anchor)
    freshness["stock_kline_minute"] = {"status": "UNKNOWN", "latestCoveragePct": None,
                                      "note": "分钟线表尚无已实现的数据契约，未推断字段或覆盖率。"}
    try:
        from kline_repo import BASIS_REFRESH_REQUIRED
        pending = dict(BASIS_REFRESH_REQUIRED)
        basis = {"pendingCount": len(pending), "items": [
            {"table": t, "code": c, "requiredBars": n} for (t, c), n in sorted(pending.items())],
                 "scope": "PROCESS_LOCAL", "note": "仅当前进程的待重定基标志，重启会丢失，不代表全库审计。"}
    except Exception as exc:
        basis = {"pendingCount": None, "items": [], "error": str(exc)[:500]}
    return {"freshness": freshness, "freshnessAnchor": {
        "date": anchor.isoformat() if anchor else None, "source": "LATEST_OBSERVED_MARKET_SESSION",
        "asOf": now.isoformat(timespec="seconds"), "cutoffDate": limit_date.isoformat(),
        "lagCalendarDays": (now.date() - anchor).days if anchor else None,
        "calendarVerified": False, "note": REFERENCE_NOTE,
    }, "basisRefresh": basis}
