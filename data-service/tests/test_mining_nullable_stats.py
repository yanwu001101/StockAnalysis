import pytest
from factormine.pipeline import _abs_at_least, _round_stat, _fmt_stat, MiningConfig


@pytest.mark.parametrize('value', [None, float('nan'), float('inf')])
def test_missing_statistics_never_pass_thresholds(value):
    assert not _abs_at_least(value, .3)
    assert _round_stat(value, 4) is None
    assert _fmt_stat(value) == '—'


def test_real_zero_keeps_its_value():
    assert _round_stat(0, 4) == 0
    assert _fmt_stat(0) == '0.00'


def test_mining_cache_includes_engine_and_statistical_settings():
    from factorlab import ENGINE_VERSION
    base = MiningConfig({})
    assert ENGINE_VERSION in base.core_hash()
    assert base.core_hash() != MiningConfig({'layers': 3}).core_hash()
    assert base.core_hash() != MiningConfig({'neutralize': False}).core_hash()
