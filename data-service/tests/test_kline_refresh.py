"""K-line refresh regression: synthetic bars only, no database/network writes."""
from contextlib import contextmanager
import asyncio
import datetime as dt

import pandas as pd
import pytest

import kline_repo
import scheduler


def bars(dates, closes):
    return pd.DataFrame({"日期": dates, "开盘": closes, "收盘": closes,
                         "最高": closes, "最低": closes, "成交量": 100})


@pytest.fixture
def storage(monkeypatch):
    state = {"rows": bars(["2024-01-02", "2024-01-03"], [10., 11.]), "writes": []}

    class Engine:
        @contextmanager
        def connect(self):
            yield self

        begin = connect

        def execute(self, sql, rows):
            state["writes"].append(rows)
            incoming = pd.DataFrame(rows).rename(columns={
                "trade_date": "日期", "open": "开盘", "close": "收盘",
                "high": "最高", "low": "最低", "volume": "成交量"})
            state["rows"] = pd.concat([state["rows"], incoming]).drop_duplicates("日期", keep="last")

    monkeypatch.setattr(kline_repo.db, "get_engine", lambda: Engine())
    monkeypatch.setattr(kline_repo.pd, "read_sql", lambda *a, **kw: state["rows"][["日期", "收盘"]].rename(
        columns={"日期": "trade_date", "收盘": "close"}))
    monkeypatch.setattr(kline_repo, "BASIS_REFRESH_REQUIRED", {})
    monkeypatch.setattr(kline_repo, "get_max_date", lambda *a, **kw: dt.date(2024, 1, 3))
    monkeypatch.setattr(kline_repo, "select_daily", lambda *a: state["rows"].copy())
    monkeypatch.setattr(kline_repo, "select_weekly", lambda *a: state["rows"].copy())
    return state


def test_read_through_preserves_overlap_and_writes_new_tail(storage, monkeypatch):
    fresh = bars(["2024-01-03", "2024-01-04"], [11., 12.])
    monkeypatch.setattr(kline_repo.eastmoney, "fetch_kline", lambda *a, **kw: fresh)
    result = kline_repo.get_daily("600519")
    assert result.iloc[-1]["日期"] == "2024-01-04"
    assert len(storage["writes"]) == 1
    assert len(storage["writes"][0]) == 2  # overlap retained for basis verification
    assert not kline_repo.BASIS_REFRESH_REQUIRED


@pytest.mark.parametrize("klt", [101, 102])
def test_changed_basis_retries_full_history_and_clears_flag(storage, monkeypatch, klt):
    partial = bars(["2024-01-03", "2024-01-04"], [5.5, 6.])
    full = bars(["2024-01-02", "2024-01-03", "2024-01-04"], [5., 5.5, 6.])
    calls = []

    def fetch(code, **kwargs):
        calls.append(kwargs)
        return full

    monkeypatch.setattr(kline_repo.eastmoney, "fetch_kline", fetch)
    assert kline_repo.upsert_with_basis_refresh("600519", partial, klt) == 3
    assert calls == [{"klt": klt, "count": 1000}]
    assert len(storage["writes"]) == 1  # rejected partial never written
    assert list(storage["rows"]["收盘"]) == [5., 5.5, 6.]
    assert not kline_repo.BASIS_REFRESH_REQUIRED


@pytest.mark.parametrize("failure", ["truncated", "empty", "exception"])
def test_incomplete_rebase_preserves_original_series_and_flag(storage, monkeypatch, failure):
    partial = bars(["2024-01-03", "2024-01-04"], [5.5, 6.])

    def fetch(*args, **kwargs):
        if failure == "exception":
            raise RuntimeError("source unavailable")
        return partial if failure == "truncated" else pd.DataFrame()

    monkeypatch.setattr(kline_repo.eastmoney, "fetch_kline", fetch)
    assert kline_repo.upsert_with_basis_refresh("600519", partial) == 0
    assert not storage["writes"]
    assert list(storage["rows"]["收盘"]) == [10., 11.]
    assert (kline_repo.DAILY_TABLE, "600519") in kline_repo.BASIS_REFRESH_REQUIRED


@pytest.mark.parametrize("n", [51, 101])
def test_warmup_processes_every_batch_and_falls_back_only_for_missing(monkeypatch, n):
    codes = [str(600000 + i) for i in range(n)]
    spot = pd.DataFrame({"代码": codes, "总市值_亿": list(range(n, 0, -1)), "成交额": 100})
    frame = bars(["2024-01-02"], [10.])
    calls, writes, fallbacks = [], [], []
    missing = {codes[0], codes[1], codes[2]}  # absent / None / empty DataFrame

    def batch(items, klt, count):
        calls.append((list(items), klt))
        result = {code: frame for code in items}
        if klt == 101:
            result.pop(codes[0], None)
            if codes[1] in result:
                result[codes[1]] = None
            if codes[2] in result:
                result[codes[2]] = pd.DataFrame()
        return result

    monkeypatch.setattr(scheduler.db, "get_engine", lambda: object())
    monkeypatch.setattr(scheduler.cache, "get", lambda _: spot)
    monkeypatch.setattr(scheduler.eastmoney, "batch_klines", batch)
    monkeypatch.setattr(scheduler.kline_repo, "upsert_with_basis_refresh",
                        lambda code, df, klt=101: writes.append((code, klt)) or len(df))
    monkeypatch.setattr(scheduler, "_kline_fallback",
                        lambda items, count: fallbacks.extend(items) or len(items))
    monkeypatch.setattr(scheduler, "WARMUP_BATCH_SIZE", 50)
    scheduler.warmup_klines(top_n=0)
    assert [c for items, klt in calls if klt == 101 for c in items] == codes
    assert set(fallbacks) == missing
    assert {c for c, klt in writes if klt == 101} == set(codes) - missing
    assert {c for c, klt in writes if klt == 102} == set(codes)


def test_async_fallback_retries_basis_without_sync_nested_event_loop(monkeypatch):
    requested, writes = [], []
    flags = {}
    frame = pd.DataFrame({"trade_date": ["2024-01-02"], "close": [10.]})

    async def fetch(sources, code, count):
        requested.append(count)
        return frame

    async def gather(codes, fn, **kwargs):
        return {code: await fn(code) for code in codes}

    def write(code, df):
        writes.append(code)
        if len(writes) == 1:
            flags[(kline_repo.DAILY_TABLE, code)] = 1500
            return 0
        return 1

    monkeypatch.setattr(scheduler, "_first_nonempty", fetch)
    monkeypatch.setattr(scheduler, "gather_codes", gather)
    monkeypatch.setattr(kline_repo, "upsert_daily", write)
    monkeypatch.setattr(kline_repo, "BASIS_REFRESH_REQUIRED", flags)
    assert scheduler._kline_fallback(["600519"], 250) == 1
    assert requested == [250, 1500]
