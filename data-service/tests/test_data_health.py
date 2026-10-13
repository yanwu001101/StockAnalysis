"""Synthetic diagnostics only: no live DB, calendar inference or data writes."""
import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from core.data_health import TABLES, collect_freshness, cutoff, load_latest, stock_universe, summarize


ANCHOR = dt.date(2026, 10, 12)


def test_one_current_code_does_not_make_99_old_codes_fresh():
    codes = {f"{i:06}" for i in range(100)}
    rows = [{"code": c, "latest_date": "2026-10-09", "close": 1} for c in sorted(codes)]
    rows[0]["latest_date"] = "2026-10-12"
    out = summarize(rows, TABLES["stock_kline_daily"], codes, "ACTIVE_SPOT_SNAPSHOT", ANCHOR)
    assert out["historyCoveragePct"] == 100
    assert out["latestCoveragePct"] == 1
    assert (out["coveredOnAnchor"], out["staleCodes"], out["missingCodes"], out["status"]) == (1, 99, 0, "PARTIAL")


def test_universe_intersection_unknown_denominator_and_real_empty():
    rows = [{"code": "outside", "latest_date": "2026-10-12", "close": 1}]
    out = summarize(rows, TABLES["stock_kline_daily"], {"inside"}, "TEST", ANCHOR)
    assert out["historyCodes"] == 0
    assert out["latestCoveragePct"] == 0
    assert out["missingCodes"] == 1
    assert out["status"] == "NO_DATA"
    unknown = summarize(rows, TABLES["stock_kline_daily"], None, "UNKNOWN", ANCHOR)
    assert unknown["latestCoveragePct"] is None
    assert unknown["missingCodes"] is None
    assert unknown["status"] == "UNKNOWN"


def test_week_matches_reference_week_and_events_do_not_need_daily_rows():
    rows = [{"code": "a", "latest_date": "2026-10-12"}]
    weekly = summarize(rows, TABLES["stock_kline_weekly"], {"a"}, "TEST", dt.date(2026, 10, 14))
    assert weekly["latestCoveragePct"] == 100
    event = summarize([], TABLES["stock_lhb"], {"a"}, "TEST", ANCHOR)
    assert event["status"] == "EVENT_DRIVEN"
    assert event["latestCoveragePct"] is None
    assert event["staleCodes"] is None


def test_exchange_timezone_cutoff_does_not_invent_holiday_sessions():
    _, day = cutoff(dt.datetime(2026, 10, 12, 8, 29, tzinfo=dt.timezone.utc))
    assert day == dt.date(2026, 10, 11)
    _, day = cutoff(dt.datetime(2026, 10, 12, 8, 30, tzinfo=dt.timezone.utc))
    assert day == ANCHOR
    # No weekday/holiday substitution: calendar verification is explicitly false.
    _, day = cutoff(dt.datetime(2026, 10, 1, 18))
    assert day == dt.date(2026, 10, 1)


@pytest.fixture
def conn():
    eng = create_engine("sqlite://")
    with eng.connect() as connection:
        connection.execute(text("CREATE TABLE stock_info(code TEXT)"))
        connection.execute(text("INSERT INTO stock_info VALUES ('000001'),('000001'),('000002')"))
        for table, spec in TABLES.items():
            fields = ','.join(f'{f} REAL' for f in spec.fields)
            connection.execute(text(f"CREATE TABLE {table}(code TEXT, {spec.date} TEXT, {fields})"))
        yield connection
    eng.dispose()


def test_sql_latest_fields_zero_is_present_old_fields_not_counted_and_codes_deduped(conn):
    conn.execute(text("INSERT INTO stock_moneyflow VALUES ('000001','2026-10-09',8,9),"
                      "('000001','2026-10-12',0,NULL),('000001','2026-10-12',0,NULL),"
                      "('000002','2026-10-13',5,6)"))
    rows = load_latest(conn, "stock_moneyflow", ANCHOR)
    assert len(rows) == 1
    out = summarize(rows, TABLES["stock_moneyflow"], {"000001", "000002"}, "TEST", ANCHOR)
    fields = {r["field"]: r for r in out["fieldCoverage"]}
    assert fields["main_net"]["coveragePct"] == 100
    assert fields["super_large_net"]["coveragePct"] == 0
    assert fields["main_net"]["eligibleCodes"] == 1
    assert out["latestCoveragePct"] == 50


def test_all_old_reference_is_labeled_not_calendar_verified_and_new_stock_advances_anchor(conn):
    conn.execute(text("INSERT INTO index_kline_daily VALUES ('000300','2026-10-09',100)"))
    now = dt.datetime(2026, 10, 12, 18)
    out = collect_freshness(conn, now=now)
    assert out["freshnessAnchor"]["date"] == "2026-10-09"
    assert out["freshnessAnchor"]["lagCalendarDays"] == 3
    assert out["freshnessAnchor"]["calendarVerified"] is False
    conn.execute(text("INSERT INTO stock_kline_daily VALUES ('000001','2026-10-12',1,1,1,1,1),"
                      "('000002','2099-01-01',1,1,1,1,1)"))
    out = collect_freshness(conn, now=now)
    assert out["freshnessAnchor"]["date"] == "2026-10-12"
    assert out["freshness"]["index_kline_daily"]["status"] == "DELAYED"
    assert out["freshness"]["stock_kline_daily"]["latestCoveragePct"] == 50
    assert out["freshness"]["stock_kline_minute"]["status"] == "UNKNOWN"


def test_universe_sources_do_not_pretend_to_be_complete(conn):
    frame = pd.DataFrame({"代码": ["000001", "000001", "000002"], "成交额": [20, 20, 0]})
    assert stock_universe(conn, frame) == ({"000001"}, "ACTIVE_SPOT_SNAPSHOT")
    assert stock_universe(conn, None) == ({"000001", "000002"}, "STOCK_INFO_FALLBACK")
    conn.execute(text("INSERT INTO industry_index_daily VALUES ('i1','2026-10-12',1)"))
    out = collect_freshness(conn, now=dt.datetime(2026, 10, 12, 18))
    assert out["freshness"]["industry_index_daily"]["universeSource"] == "STORED_INDUSTRY_CODES"
    assert out["freshness"]["industry_index_daily"]["eligibleUniverse"] == 1


def test_table_failure_and_basis_flags_are_explicit(conn, monkeypatch):
    import kline_repo
    monkeypatch.setattr(kline_repo, "BASIS_REFRESH_REQUIRED", {("stock_kline_daily", "000001"): 1200})
    conn.execute(text("DROP TABLE stock_moneyflow"))
    out = collect_freshness(conn, now=dt.datetime(2026, 10, 12, 18))
    item = out["freshness"]["stock_moneyflow"]
    assert item["status"] == "FAILED"
    assert item["historyCodes"] is None
    assert item["latestCoveragePct"] is None
    assert out["basisRefresh"]["pendingCount"] == 1
    assert out["basisRefresh"]["scope"] == "PROCESS_LOCAL"


def test_sql_identifiers_not_user_controlled(conn):
    with pytest.raises(KeyError):
        load_latest(conn, "stock_info; DROP TABLE stock_info", ANCHOR)
