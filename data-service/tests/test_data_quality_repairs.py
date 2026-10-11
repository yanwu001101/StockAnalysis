import asyncio
import pandas as pd
import pytest
from core.adjustment_guard import needs_full_refresh
from sources.sina import SinaSource, _mf_sym, _f
from sources.eastmoney import EastmoneySource


def test_partial_adjustment_rebase_is_rejected():
    old = pd.DataFrame({'trade_date': ['2024-01-02', '2024-01-03', '2024-01-04'], 'close': [10, 11, 12]})
    part = old.iloc[1:].copy(); part['close'] *= .5
    assert needs_full_refresh(old, part)
    full = old.copy(); full['close'] *= .5
    assert not needs_full_refresh(old, full)
    assert not needs_full_refresh(old, old.iloc[1:])
    assert needs_full_refresh(old, pd.DataFrame({'trade_date': ['2024-01-05'], 'close': [13]}))


def test_beijing_symbol_and_nonfinite_moneyflow():
    assert _mf_sym('920002') == 'bj920002'
    assert _mf_sym('600519') == 'sh600519'
    assert _f('nan') is None and _f('inf') is None
    assert _f('0') == 0


def test_sina_paginates_history_and_keeps_missing_main_flow(monkeypatch):
    pages = []
    async def get(url, params, **kwargs):
        pages.append(params['page1'])
        dates = pd.bdate_range('2023-01-02', periods=180)[::-1]
        start = (params['page1'] - 1) * 60
        return [{'opendate': str(d.date()), 'r0_net': 1, 'r1_net': None if i == 0 else 2}
                for i, d in enumerate(dates[start:start + 60])]
    monkeypatch.setattr('sources.sina.http_client.get_json', get)
    result = asyncio.run(SinaSource().fetch_moneyflow('600519', days=130))
    assert len(result) == 130 and pages == [1, 2, 3]
    assert result['trade_date'].is_monotonic_increasing
    assert result['main_net'].isna().any()


def test_dividend_fields_match_observed_provider_contract(monkeypatch):
    async def get(*args, **kwargs):
        return {'result': {'data': [{'NOTICE_DATE': '2026-06-01', 'EX_DIVIDEND_DATE': '2026-06-10',
                                     'PRETAX_BONUS_RMB': 6, 'BONUS_RATIO': 0, 'IT_RATIO': 1}]}}
    monkeypatch.setattr('sources.eastmoney.http_client.get_json', get)
    result = asyncio.run(EastmoneySource().fetch_dividend('600519'))
    assert result.iloc[0]['cash_per_10'] == 6
    assert result.iloc[0]['transfer_per_10'] == 1
    assert result.iloc[0]['share_per_10'] == 0


def test_partial_shareholder_update_preserves_other_fields(monkeypatch):
    from repo import shareholder_repo
    captured = {}
    def upsert(*args, **kwargs):
        captured.update(kwargs); captured['cols'] = args[2]; return 1
    monkeypatch.setattr(shareholder_repo, 'upsert', upsert)
    shareholder_repo.upsert_shareholder(pd.DataFrame([{'code': '600519', 'report_date': '2026-06-30', 'holder_count': 123}]))
    assert 'top10_ratio' not in captured['cols']
    assert captured['preserve_non_null'] is True


def test_pk_only_upsert_generates_valid_noop(monkeypatch):
    from contextlib import contextmanager
    from repo import base
    statements = []
    class Engine:
        @contextmanager
        def begin(self):
            yield self
        def execute(self, sql, rows):
            statements.append(str(sql))
    monkeypatch.setattr(base, 'engine', lambda: Engine())
    assert base.upsert('example', [{'id': '1'}], ['id'], update_columns=[]) == 1
    assert 'UPDATE `id`=`id`' in statements[0]
