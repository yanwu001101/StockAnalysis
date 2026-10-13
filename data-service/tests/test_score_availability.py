"""Research coverage must exclude unavailable scores, but retain genuine zeros."""
import datetime as dt
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

import factorlab
from backtest import engine
from models import ScoreResult


@pytest.mark.parametrize("key", ["no_data", "insufficient_data", "no_lhb", "no_rank"])
@pytest.mark.parametrize("placeholder", [0, 20, 50])
def test_strategy_placeholders_are_not_observations(key, placeholder):
    assert engine._validated_score(ScoreResult(score=placeholder, details={key: True})) == (None, "INSUFFICIENT_DATA")


@pytest.mark.parametrize("value", [None, np.nan, np.inf, -np.inf])
def test_invalid_score_is_failed_not_zero(value):
    assert engine._validated_score(SimpleNamespace(score=value)) == (None, "FAILED")


def test_real_zero_is_a_valid_observation():
    assert engine._validated_score(ScoreResult(score=0, details={"no_data": False})) == (0., "VALID")


def test_cached_missing_stays_missing_without_repeated_computation(monkeypatch):
    monkeypatch.setattr(engine, "_SCORE_CACHE", {})
    monkeypatch.setattr(engine, "_industry_of", lambda _: "")
    calls = []
    def fail(ctx):
        calls.append(ctx.code)
        raise ValueError("synthetic failure")
    strat = SimpleNamespace(id="test", score=fail)
    for _ in range(2):
        assert engine._score_at_cached(strat, {}, "600000", dt.date(2024, 1, 1)) is None
    assert calls == ["600000"]


def test_factor_provider_keeps_zero_and_excludes_missing_and_failures(monkeypatch):
    dates = list(pd.bdate_range("2024-01-01", periods=40).date)
    codes = ["zero", "missing", "failed", "rank_missing"]
    values = {
        "zero": ScoreResult(score=0),
        "missing": ScoreResult(score=0, details={"no_data": True}),
        "rank_missing": ScoreResult(score=20, details={"no_rank": True}),
    }
    def score(ctx):
        if ctx.code == "failed":
            raise ValueError("synthetic failure")
        return values[ctx.code]
    monkeypatch.setattr(engine, "_SCORE_CACHE", {})
    monkeypatch.setattr(engine, "_industry_of", lambda _: "")
    monkeypatch.setattr(factorlab, "by_id", lambda _: SimpleNamespace(id="test", name="test", score=score))
    monkeypatch.setattr(engine, "_trading_days", lambda *a: dates)
    monkeypatch.setattr(engine, "_universe_ohlcv", lambda *a: {"close": pd.DataFrame(index=dates, columns=codes)})
    monkeypatch.setattr(factorlab, "_universe_codes", lambda *a, **kw: codes)
    monkeypatch.setattr(factorlab, "_get_panel", lambda *a: {c: {} for c in codes})
    def analyze(provider, **kwargs):
        assert provider(dates[0], codes).to_dict() == {"zero": 0.}
        return {"observed": 1}
    monkeypatch.setattr(factorlab, "analyze_scores", analyze)
    assert factorlab.analyze("test", dates[0], dates[-1])["observed"] == 1
