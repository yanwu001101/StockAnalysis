# -*- coding: utf-8 -*-
"""Smoke import + instantiation for every source / pipeline / strategy.

We can't hit the network in unit tests, so these tests only verify the modules
import and instantiate cleanly. Network calls go in test_sources_live.py which
runs against a tagged "integration" pytest mark.
"""
from __future__ import annotations


def test_sources_import_and_instantiate():
    from sources import all_sources
    items = all_sources()
    assert len(items) >= 6
    for s in items:
        assert isinstance(s.name, str) and s.name


def test_source_chain_has_kline_fallback():
    from sources import chain
    seq = list(chain("kline"))
    names = [s.name for s in seq]
    assert "tencent" in names
    assert "sina" in names


def test_pipelines_import():
    from pipelines import (
        spot, kline, fundamental, moneyflow, northbound,
        lhb, shareholder, dividend, concept, news,
    )
    for mod in (spot, kline, fundamental, moneyflow, northbound,
                lhb, shareholder, dividend, concept, news):
        assert mod is not None
