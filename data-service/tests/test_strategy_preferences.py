import math
import pytest
from strategy_preferences import normalize_weights, paper_weights


def test_weights_keep_true_zero_and_disabled_settings():
    result = normalize_weights({'config': {'a': {'enabled': True, 'weight': 0},
                                           'b': {'enabled': False, 'weight': 10}}})
    assert result == {'a': 0, 'b': 0}


@pytest.mark.parametrize('bad', [None, math.nan, math.inf, -1, True, '10'])
def test_invalid_weights_do_not_turn_into_defaults(bad):
    with pytest.raises(ValueError):
        normalize_weights({'config': {'a': {'enabled': True, 'weight': bad}}})


def test_shared_paper_account_does_not_inherit_arbitrary_users(monkeypatch):
    monkeypatch.delenv('PAPER_WEIGHT_USER_ID', raising=False)
    assert paper_weights({'a': .1}) == {'a': .1}


def test_invalid_explicit_binding_stops_rebalance(monkeypatch):
    monkeypatch.setenv('PAPER_WEIGHT_USER_ID', 'bad')
    with pytest.raises(ValueError):
        paper_weights({'a': .1})


def test_cloud_and_registry_weights_share_ratio_units(monkeypatch):
    from contextlib import contextmanager
    class Engine:
        @contextmanager
        def connect(self):
            yield self
        def execute(self, *args, **kwargs):
            return self
        def fetchone(self):
            return ({'config': {'a': {'enabled': True, 'weight': 12},
                                'disabled': {'enabled': False, 'weight': 30}}},)
    monkeypatch.setenv('PAPER_WEIGHT_USER_ID', '1')
    monkeypatch.setattr('strategy_preferences.db.get_engine', lambda: Engine())
    assert paper_weights({'a': .12, 'new': .08, 'disabled': .3}) == {'a': .12, 'new': .08, 'disabled': 0}
