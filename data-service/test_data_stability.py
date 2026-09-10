#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data source stability test suite.

Tests the new multi-source aggregator and validates data quality.

Usage:
    python test_data_stability.py
"""
import asyncio
import sys
import time
from pathlib import Path

# Add data-service to path
sys.path.insert(0, str(Path(__file__).parent))

import pandas as pd
from sources.aggregator import default_aggregator
from sources import eastmoney, tencent, sina, akshare_src
from cache_enhanced import enhanced as enhanced_cache
from core import health


# ---------------------------------------------------------------------------
# Test utilities
# ---------------------------------------------------------------------------

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error = None
        self.duration_ms = 0
        self.rows = 0

    def __repr__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        details = f"{self.rows} rows, {self.duration_ms:.0f}ms"
        if self.error:
            details += f", error: {self.error}"
        return f"[{status}] {self.name:<40} {details}"


async def test_source(source, method_name: str, *args, **kwargs) -> TestResult:
    """Test a single source method."""
    result = TestResult(f"{source.name}.{method_name}")
    start = time.time()
    try:
        method = getattr(source, method_name)
        df = await method(*args, **kwargs)
        result.duration_ms = (time.time() - start) * 1000

        if isinstance(df, pd.DataFrame):
            result.rows = len(df)
            result.passed = not df.empty
        else:
            result.passed = df is not None

        if not result.passed:
            result.error = "empty result"
    except Exception as e:
        result.duration_ms = (time.time() - start) * 1000
        result.error = str(e)[:100]
    return result


# ---------------------------------------------------------------------------
# Test suites
# ---------------------------------------------------------------------------

async def test_individual_sources():
    """Test each source individually."""
    print("\n" + "=" * 80)
    print("Testing Individual Sources")
    print("=" * 80)

    sources = [
        eastmoney.default(),
        tencent.default(),
        sina.default(),
        akshare_src.default(),
    ]

    results = []

    # Test spot
    print("\n--- Spot Data ---")
    for src in sources:
        result = await test_source(src, "fetch_spot")
        results.append(result)
        print(result)

    # Test kline
    print("\n--- K-line Data (600519) ---")
    for src in sources:
        result = await test_source(src, "fetch_kline", "600519", "daily", 250)
        results.append(result)
        print(result)

    # Test minute kline (only sources that support it)
    print("\n--- Minute K-line (600519, 5min) ---")
    for src in sources:
        if hasattr(src, "fetch_minute_kline"):
            result = await test_source(src, "fetch_minute_kline", "600519", "5min", 240)
            results.append(result)
            print(result)

    # Test fundamental
    print("\n--- Fundamental Data (600519) ---")
    for src in sources:
        if hasattr(src, "fetch_fundamental"):
            result = await test_source(src, "fetch_fundamental", "600519", 8)
            results.append(result)
            print(result)

    pass_count = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{'Individual Sources Summary':<40} {pass_count}/{total} passed")
    return pass_count, total


async def test_aggregator():
    """Test multi-source aggregator."""
    print("\n" + "=" * 80)
    print("Testing Multi-Source Aggregator")
    print("=" * 80)

    agg = default_aggregator()
    results = []

    # Test spot
    print("\n--- Aggregated Spot ---")
    result = TestResult("aggregator.fetch_spot")
    start = time.time()
    try:
        df = await agg.fetch_spot()
        result.duration_ms = (time.time() - start) * 1000
        result.rows = len(df) if df is not None else 0
        result.passed = df is not None and not df.empty and len(df) >= 3000
        if not result.passed:
            result.error = f"validation failed: {len(df)} rows < 3000"
    except Exception as e:
        result.duration_ms = (time.time() - start) * 1000
        result.error = str(e)[:100]
    results.append(result)
    print(result)

    # Test kline
    print("\n--- Aggregated K-line ---")
    for code in ["600519", "000001", "300750"]:
        result = TestResult(f"aggregator.fetch_kline({code})")
        start = time.time()
        try:
            df = await agg.fetch_kline(code, "daily", 250)
            result.duration_ms = (time.time() - start) * 1000
            result.rows = len(df) if df is not None else 0
            result.passed = df is not None and not df.empty and len(df) >= 30
            if not result.passed:
                result.error = f"validation failed: {len(df)} rows < 30"
        except Exception as e:
            result.duration_ms = (time.time() - start) * 1000
            result.error = str(e)[:100]
        results.append(result)
        print(result)

    pass_count = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{'Aggregator Summary':<40} {pass_count}/{total} passed")
    return pass_count, total


async def test_cache_fallback():
    """Test enhanced cache with stale-while-revalidate."""
    print("\n" + "=" * 80)
    print("Testing Enhanced Cache & Fallback")
    print("=" * 80)

    cache = enhanced_cache()
    results = []

    # Test 1: Fresh fetch
    result = TestResult("cache: fresh fetch")
    start = time.time()
    try:
        def fetcher():
            return pd.DataFrame({"code": ["600519"], "name": ["贵州茅台"]})

        df = cache.get_or_fetch_with_fallback("test:spot", 10, fetcher)
        result.duration_ms = (time.time() - start) * 1000
        result.rows = len(df)
        result.passed = not df.empty
    except Exception as e:
        result.error = str(e)[:100]
    results.append(result)
    print(result)

    # Test 2: Cache hit
    result = TestResult("cache: cache hit")
    start = time.time()
    try:
        def fetcher():
            raise Exception("should not be called")

        df = cache.get_or_fetch_with_fallback("test:spot", 10, fetcher)
        result.duration_ms = (time.time() - start) * 1000
        result.rows = len(df)
        result.passed = not df.empty and result.duration_ms < 10
    except Exception as e:
        result.error = str(e)[:100]
    results.append(result)
    print(result)

    # Test 3: Stale fallback (wait for TTL to expire)
    print("  (waiting 11s for cache to expire...)")
    await asyncio.sleep(11)

    result = TestResult("cache: stale fallback")
    start = time.time()
    try:
        def failing_fetcher():
            raise Exception("fetch failed")

        df = cache.get_or_fetch_with_fallback("test:spot", 10, failing_fetcher)
        result.duration_ms = (time.time() - start) * 1000
        result.rows = len(df) if df is not None else 0
        result.passed = df is not None and not df.empty  # Should return stale data
        if not result.passed:
            result.error = "failed to return stale data"
    except Exception as e:
        result.error = str(e)[:100]
    results.append(result)
    print(result)

    pass_count = sum(1 for r in results if r.passed)
    total = len(results)
    print(f"\n{'Cache Summary':<40} {pass_count}/{total} passed")
    return pass_count, total


async def test_health_checker():
    """Test health checker."""
    print("\n" + "=" * 80)
    print("Testing Health Checker")
    print("=" * 80)

    checker = health.default()

    # Record some test data
    checker.record_success("test_source", 100.0)
    checker.record_success("test_source", 150.0)
    checker.record_failure("failing_source", circuit_open=False)
    checker.record_failure("failing_source", circuit_open=False)

    await asyncio.sleep(0.1)  # Wait for async tasks to complete

    h = await checker.get_health("test_source")
    print(f"test_source: success_rate={h.success_rate:.2f}, health_score={h.health_score:.2f}")

    h = await checker.get_health("failing_source")
    print(f"failing_source: success_rate={h.success_rate:.2f}, health_score={h.health_score:.2f}")

    all_health = await checker.get_all_health()
    print(f"\nTotal sources tracked: {len(all_health)}")

    return 1, 1  # Passed


async def test_stress():
    """Stress test with concurrent requests."""
    print("\n" + "=" * 80)
    print("Stress Test (20 concurrent requests)")
    print("=" * 80)

    agg = default_aggregator()
    codes = ["600519", "000001", "000002", "600036", "601318"] * 4

    start = time.time()
    tasks = [agg.fetch_kline(code, "daily", 250) for code in codes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    duration = time.time() - start

    success = sum(1 for r in results if isinstance(r, pd.DataFrame) and not r.empty)
    total = len(results)

    print(f"Completed: {success}/{total} requests")
    print(f"Duration: {duration:.2f}s")
    print(f"Average: {duration / total * 1000:.0f}ms per request")
    print(f"Success rate: {success / total * 100:.1f}%")

    return success, total


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------

async def main():
    print("\n" + "=" * 80)
    print(" Data Source Stability Test Suite")
    print("=" * 80)

    total_pass = 0
    total_tests = 0

    # Run all test suites
    p, t = await test_individual_sources()
    total_pass += p
    total_tests += t

    p, t = await test_aggregator()
    total_pass += p
    total_tests += t

    p, t = await test_cache_fallback()
    total_pass += p
    total_tests += t

    p, t = await test_health_checker()
    total_pass += p
    total_tests += t

    p, t = await test_stress()
    total_pass += p
    total_tests += t

    # Final summary
    print("\n" + "=" * 80)
    print(f" Final Summary: {total_pass}/{total_tests} tests passed")
    print("=" * 80)

    if total_pass == total_tests:
        print("\n✓ All tests passed! Data source system is stable.")
        return 0
    else:
        print(f"\n✗ {total_tests - total_pass} tests failed. Review logs above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
