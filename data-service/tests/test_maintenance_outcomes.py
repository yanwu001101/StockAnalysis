"""Maintenance jobs must report evidence, not merely a returned thread.

Every external pipeline and database query is mocked; these tests never launch
the application, scheduler, network requests, or real maintenance work.
"""
import asyncio
import datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import numpy as np
import pandas as pd
import pytest

from config import SchedulerSettings
from core.job_outcome import JobOutcome
from core.universe import select_codes
from jobs import postmarket, weekend


@pytest.fixture
def snapshot():
    return pd.DataFrame({
        "code": ["000003", "600519", "000001", "000002"],
        "market_cap_yi": [3, 10, 4, 100],
        "amount": [100, 100, 100, 0],
    })


@pytest.fixture
def jobs(monkeypatch, snapshot):
    class TradingDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 12)

    monkeypatch.setattr(postmarket, "dt", SimpleNamespace(date=TradingDate, timedelta=datetime.timedelta))
    monkeypatch.setattr(postmarket.settings.sched, "warmup_top_n", 0)
    monkeypatch.setattr(postmarket.spot_pipe, "run", AsyncMock(return_value=snapshot))
    monkeypatch.setattr(postmarket, "_ex_div_codes_today", Mock(return_value=[]))
    pipes = {
        "daily": (postmarket.kline_pipe, "run_daily_batch"),
        "weekly": (postmarket.kline_pipe, "run_weekly_batch"),
        "moneyflow": (postmarket.mf_pipe, "run_batch"),
        "northbound": (postmarket.nb_pipe, "run_batch"),
        "lhb": (postmarket.lhb_pipe, "run"),
        "index": (postmarket.index_kline_pipe, "run"),
        "fundamentals": (weekend.fund_pipe, "run_batch"),
        "shareholder": (weekend.sh_pipe, "run_batch"),
        "dividend": (weekend.div_pipe, "run_batch"),
        "concept": (weekend.concept_pipe, "run"),
    }
    mocks = {}
    for name, (module, attr) in pipes.items():
        mocks[name] = AsyncMock(return_value=10)
        monkeypatch.setattr(module, attr, mocks[name])
    import notifier
    monkeypatch.setattr(notifier, "job_failed", Mock())
    return mocks


def test_zero_limit_means_all_active_not_empty_and_does_not_mutate(snapshot):
    before = snapshot.copy(deep=True)
    assert select_codes(snapshot, 0) == ["600519", "000001", "000003"]
    assert select_codes(snapshot, -1) == select_codes(snapshot, 0)
    assert select_codes(snapshot, 2) == ["600519", "000001"]
    pd.testing.assert_frame_equal(snapshot, before)


def test_universe_deduplicates_valid_codes_and_supports_legacy_columns():
    snapshot = pd.DataFrame({"代码": ["1", "000001", None, "not-a-code", "600519"],
                             "总市值_亿": [2, 2, 50, 60, 100], "成交额": [1, 1, 1, 1, np.inf]})
    assert select_codes(snapshot) == ["000001"]
    assert select_codes(None) == []
    assert select_codes(pd.DataFrame()) == []


def test_top_n_requires_ranking_evidence_but_all_market_does_not():
    snapshot = pd.DataFrame({"code": ["600519", "000001"]})
    assert select_codes(snapshot) == ["000001", "600519"]
    with pytest.raises(ValueError, match="市值"):
        select_codes(snapshot, 1)


def test_scheduler_settings_share_zero_default(monkeypatch):
    monkeypatch.delenv("WARMUP_TOP_N", raising=False)
    assert SchedulerSettings().warmup_top_n == 0
    monkeypatch.setenv("WARMUP_TOP_N", "12")
    assert SchedulerSettings().warmup_top_n == 12


@pytest.mark.parametrize("job,expected_rows", [(postmarket, 60), (weekend, 40)])
def test_success_counts_real_writes_and_full_universe(job, expected_rows, jobs):
    result = asyncio.run(job.run_async())
    assert result["outcome_version"] == 1
    assert result["status"] == "success"
    assert result["rows"] == expected_rows
    assert result["universe_size"] == 3
    assert result["row_semantics"] == "reported_upsert_rows_not_freshness"
    selected = jobs["daily"] if job is postmarket else jobs["fundamentals"]
    assert selected.await_args.args[0] == ["600519", "000001", "000003"]
    assert json.loads(json.dumps(result)) == result


@pytest.mark.parametrize("job", [postmarket, weekend])
@pytest.mark.parametrize("mode", ["zero", "exception"])
def test_all_sources_failed_or_empty_never_reports_success(job, mode, jobs):
    for pipeline in jobs.values():
        if mode == "zero":
            pipeline.return_value = 0
        else:
            pipeline.side_effect = RuntimeError("provider down")
    result = asyncio.run(job.run_async())
    assert result["status"] == "failed"
    assert result["rows"] == 0
    assert result["error"]
    if mode == "zero":
        assert any(s.get("reason") == "no_rows" for s in result["steps"])
    else:
        assert any(s.get("error") == "provider down" for s in result["steps"])


@pytest.mark.parametrize("job", [postmarket, weekend])
def test_partial_keeps_exceptions_and_empty_steps_and_runs_remaining_pipelines(job, jobs):
    failed, empty, last = (("daily", "moneyflow", "index") if job is postmarket
                           else ("fundamentals", "shareholder", "concept"))
    jobs[failed].side_effect = RuntimeError("rate limited")
    jobs[empty].return_value = 0
    result = asyncio.run(job.run_async())
    assert result["status"] == "partial"
    assert result["rows"] > 0
    assert any(s.get("error") == "rate limited" for s in result["steps"])
    assert any(s.get("reason") == "no_rows" for s in result["steps"])
    jobs[last].assert_awaited_once()


@pytest.mark.parametrize("job", [postmarket, weekend])
@pytest.mark.parametrize("mode", ["empty", "exception"])
def test_missing_universe_is_failure_without_launching_pipelines(job, mode, jobs):
    if mode == "empty":
        job.spot_pipe.run.return_value = pd.DataFrame()
    else:
        job.spot_pipe.run.side_effect = RuntimeError("spot down")
    result = asyncio.run(job.run_async())
    assert result["status"] == "failed"
    assert result["universe_size"] == 0
    assert result["steps"][0]["name"] == "universe"
    for pipeline in jobs.values():
        pipeline.assert_not_awaited()


def test_confirmed_weekend_is_skipped_not_failed(monkeypatch, jobs):
    class WeekendDate(datetime.date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 11)
    monkeypatch.setattr(postmarket, "dt", SimpleNamespace(date=WeekendDate, timedelta=datetime.timedelta))
    result = asyncio.run(postmarket.run_async())
    assert result["status"] == "skipped"
    assert result["reason"] == "weekend"
    postmarket.spot_pipe.run.assert_not_awaited()


def test_failed_ex_dividend_query_remains_visible_and_does_not_abort_other_steps(jobs):
    postmarket._ex_div_codes_today.side_effect = RuntimeError("calendar SQL failed")
    result = asyncio.run(postmarket.run_async())
    assert result["status"] == "partial"
    assert any(s["name"] == "ex_dividend_calendar" and s["status"] == "failed" for s in result["steps"])
    jobs["index"].assert_awaited_once()


def test_ex_dividend_refresh_count_is_included_in_result(jobs):
    postmarket._ex_div_codes_today.return_value = ["600519"]
    result = asyncio.run(postmarket.run_async())
    assert result["status"] == "success"
    assert result["rows"] == 70
    assert jobs["daily"].await_count == 2
    assert jobs["daily"].await_args.kwargs["count"] == 6000


@pytest.mark.parametrize("value", [None, True, {}, {"rows": 10}, pd.DataFrame({"rows": [10]}), -1, 1.5])
def test_non_row_pipeline_returns_are_explicit_failures(value):
    outcome = JobOutcome("test")
    asyncio.run(outcome.run_step("invalid", AsyncMock(return_value=value)))
    result = outcome.finish()
    assert result["status"] == "failed"
    assert result["steps"][0]["status"] == "failed"
    assert "有效写入行数" in result["steps"][0]["error"]


def test_numpy_row_count_is_serializable_and_confirmed_noop_does_not_mark_partial():
    outcome = JobOutcome("test")
    asyncio.run(outcome.run_step("rows", AsyncMock(return_value=np.int64(3))))
    outcome.skipped("ex_dividends", "no_ex_dividends")
    result = outcome.finish()
    assert result["status"] == "success"
    assert json.loads(json.dumps(result))["rows"] == 3


@pytest.mark.parametrize("job", [postmarket, weekend])
def test_sync_entrypoint_preserves_outcome_instead_of_swallowing_it(job, jobs):
    result = job.run()
    assert result["outcome_version"] == 1
    assert result["status"] == "success"


@pytest.mark.parametrize("job", [postmarket, weekend])
def test_unexpected_runner_exception_is_returned_as_failed(monkeypatch, job, jobs):
    monkeypatch.setattr(job, "run_async", AsyncMock(side_effect=RuntimeError("unexpected failure")))
    result = job.run()
    assert result["status"] == "failed"
    assert result["steps"][0]["error"] == "unexpected failure"


def test_ex_dividend_calendar_does_not_disguise_unavailable_db_as_empty(monkeypatch):
    from repo import base
    monkeypatch.setattr(base, "engine", lambda: None)
    with pytest.raises(RuntimeError, match="数据库不可用"):
        postmarket._ex_div_codes_today()
