import datetime as dt
import numpy as np
import pandas as pd
import pytest
from scipy.stats import t as student_t

import factorlab
from quant_stats import ic_summary, chronological_validation, equal_weight_turnover, cap_bucket_demean


def test_missing_statistics_are_null_not_zero():
    for values in ([], [np.nan, np.inf]):
        result = ic_summary(values)
        assert result['n'] == 0
        assert all(result[k] is None for k in ('mean', 'std', 'icir', 't_stat', 'p_value', 'positive_ratio'))
    assert ic_summary([0])['mean'] == 0
    assert ic_summary([0])['std'] is None
    assert ic_summary([.1] * 12)['t_stat'] is None


def test_two_sided_student_p_and_zero_ic():
    values = np.array([-.06, .02, .03, .08, -.01, .04])
    result = ic_summary(values)
    expected_t = values.mean() / values.std(ddof=1) * np.sqrt(len(values))
    assert result['t_stat'] == pytest.approx(expected_t)
    assert result['p_value'] == pytest.approx(2 * student_t.sf(abs(expected_t), len(values) - 1))
    assert ic_summary([-1, 0, 1])['p_value'] == 1
    assert ic_summary([-1, 0, 1])['negative_ratio'] == pytest.approx(1 / 3)


def test_pairwise_finite_sample_threshold():
    a, b = pd.Series(np.arange(20.)), pd.Series(np.arange(20.))
    b.iloc[:11] = np.nan
    assert factorlab._rank_ic(a, b) is None
    assert factorlab._pearson_ic(a, b) is None
    b.iloc[10] = 10
    assert factorlab._rank_ic(a, b) == pytest.approx(1)


def test_holdout_does_not_choose_direction_from_test():
    dates = pd.bdate_range('2023-01-01', periods=100)
    rows = [{'date': d.date().isoformat(), 'ic': -.05 if i < 70 else .9} for i, d in enumerate(dates)]
    result = chronological_validation(rows)
    assert result['direction_sign'] == -1
    assert result['normalized_test']['mean'] < 0
    assert result['direction_consistent'] is False
    assert len(result['rolling']) == 41
    assert result['rolling'][0]['n'] == 60


def test_holdout_purges_labels_crossing_boundary():
    rows = [{'date': f'2024-01-{i:02}', 'return_end': '2024-02-01', 'ic': .01 * i} for i in range(1, 21)]
    assert chronological_validation(rows)['train']['n'] == 0


def test_one_way_turnover_and_cash():
    assert equal_weight_turnover({}, {'a': .5, 'b': .5}) == 1
    assert equal_weight_turnover({'a': .5, 'b': .5}, {'a': .5, 'c': .5}) == .5
    assert equal_weight_turnover({'a': 1}, {'b': 1}) == 1
    assert equal_weight_turnover({'a': 1}, {'a': 1}) == 0


def test_universe_is_fixed_using_only_start_date_information():
    dates = pd.bdate_range('2024-01-01', periods=5)
    close = pd.DataFrame({'a': [1, 1, 1, 1, 1], 'b': [1, 1, 1, 1, 1]}, index=dates)
    volume = pd.DataFrame({'a': [10] * 5, 'b': [1, 1, 10000, 10000, 10000]}, index=dates)
    assert factorlab._universe_codes(None, close, 1, volume, dates[1].date()) == ['a']


def test_cap_diagnostic_removes_bucket_means():
    caps = pd.Series(np.arange(1., 101))
    out = cap_bucket_demean(caps * 2, caps)
    assert abs(out.mean()) < 1e-12
    assert cap_bucket_demean(caps[:5], caps[:5]).empty


@pytest.fixture
def market(monkeypatch):
    dates = [d.date() for d in pd.bdate_range('2024-01-01', periods=265)]
    codes = [str(600000 + i) for i in range(30)]
    rates = np.linspace(.00005, .0006, 30)
    close = pd.DataFrame(10 * np.exp(np.arange(265)[:, None] * rates), index=dates, columns=codes)
    opens = close.shift(1).fillna(close.iloc[0])
    panel = {'close': close, 'open': opens, 'volume': close * 0 + 1e6}
    monkeypatch.setattr(factorlab.engine, '_trading_days', lambda start, end: [d for d in dates if start <= d <= end])
    monkeypatch.setattr(factorlab.engine, '_universe_ohlcv', lambda *a: panel)
    monkeypatch.setattr(factorlab.engine, '_benchmark_close', lambda *a: None)
    monkeypatch.setattr(factorlab, '_industry_map', lambda: {})
    provider = lambda d, selected: pd.Series(dict(zip(codes, range(30)))).reindex(selected)
    return dates, codes, panel, provider


def test_weekly_annualization_uses_actual_trading_days(market):
    dates, codes, panel, provider = market
    result = factorlab.analyze_scores(provider, dates[0], dates[-1], rebalance='weekly', codes=codes)
    assert 'error' not in result
    years = result['sample_info']['holding_trading_days'] / 252
    for layer in result['layer_stats']:
        assert layer['annualized'] == pytest.approx((1 + layer['total']) ** (1 / years) - 1, abs=1e-7)
    assert result['sample_info']['holding_trading_days'] < result['periods'] * 21
    row = result['ic_series'][0]
    assert row['execution_date'] > row['date']
    assert result['sample_info']['observations'] == sum(r['n'] for r in result['ic_series'])


def test_signal_close_is_not_assumed_execution_price(market):
    dates, codes, panel, provider = market
    # Every t+1 open gaps 10%; the gap must not be earned using a t-close signal.
    panel['open'] *= 1.1
    result = factorlab.analyze_scores(provider, dates[0], dates[-1], rebalance='weekly', codes=codes)
    assert all(layer['total'] < 0 for layer in result['layer_stats'])


def test_both_legs_cost_and_reverse_direction(market):
    dates, codes, panel, provider = market
    result = factorlab.analyze_scores(lambda d, c: -provider(d, c), dates[0], dates[-1], rebalance='weekly', codes=codes)
    rating = result['rating']
    assert rating['direction'] == 'reverse'
    assert rating['adjusted_net_spread_ann'] == pytest.approx(
        rating['adjusted_gross_spread_ann'] - result['turnover_annualized'] * rating['cost_per_turnover'], abs=1e-7)
    layers = result['layer_stats']
    assert result['turnover_annualized'] == pytest.approx(layers[0]['turnover_annualized'] + layers[-1]['turnover_annualized'])
    assert rating['tradability'] is None


def test_coverage_does_not_return_a_fabricated_curve(market):
    dates, codes, panel, provider = market
    result = factorlab.analyze_scores(lambda d, c: pd.Series(dtype=float), dates[0], dates[-1], codes=codes)
    assert result['status'] == 'INSUFFICIENT_DATA'
    assert result['ic_summary']['mean'] is None
    assert result['layer_curves'] == []


def test_batch_and_detail_share_exact_result(market):
    dates, codes, panel, provider = market
    opts = dict(start=dates[0], end=dates[-1], rebalance='weekly', codes=codes)
    batch = factorlab.analyze_scores(provider, **opts)
    detail = factorlab.analyze_scores(provider, **opts)
    assert batch == detail
