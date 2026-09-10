# -*- coding: utf-8 -*-
"""Enhanced cache with stale-while-revalidate + graceful degradation.

Extends the basic cache.py with:
  * Stale data fallback when fresh fetch fails
  * Multi-tier TTL (fresh / stale / expired)
  * Quality metrics tracking
"""
from __future__ import annotations
import time
from typing import Any, Callable, Optional

import pandas as pd

from core.trace import logger
import cache as base_cache


class EnhancedCache:
    """Cache with stale-while-revalidate pattern."""

    def __init__(self):
        self._stale_window = 3600  # Stale data is acceptable for 1 hour after TTL

    def get_or_fetch_with_fallback(
        self,
        key: str,
        ttl: int,
        fetcher: Callable[[], Any],
        validator: Optional[Callable[[Any], bool]] = None,
    ) -> Any:
        """
        Fetch data with graceful degradation:
        1. Try cache (if fresh, return immediately)
        2. If cache is stale but valid, return stale + async refresh in background
        3. If cache is expired or invalid, fetch fresh
        4. If fresh fetch fails, return stale (if available)
        5. If all fails, return None or empty DataFrame
        """
        # Try getting fresh cache
        cached = base_cache.get(key)
        cache_meta = base_cache.get(f"{key}:meta")

        if cached is not None and cache_meta is not None:
            cache_time = cache_meta.get("time", 0)
            cache_ttl = cache_meta.get("ttl", ttl)
            age = time.time() - cache_time

            # Fresh cache
            if age < cache_ttl:
                logger.debug("cache hit (fresh): %s (age=%.1fs)", key, age)
                return cached

            # Stale but within grace window
            if age < cache_ttl + self._stale_window:
                logger.info("cache hit (stale): %s (age=%.1fs), using stale data", key, age)
                # Return stale immediately; TODO: trigger async refresh
                return cached

            logger.debug("cache expired: %s (age=%.1fs)", key, age)

        # Fetch fresh
        try:
            logger.info("fetching fresh: %s", key)
            fresh = fetcher()

            # Validate fresh data
            is_valid = True
            if validator:
                is_valid = validator(fresh)
            elif isinstance(fresh, pd.DataFrame):
                is_valid = fresh is not None and not fresh.empty

            if is_valid:
                logger.info("fresh fetch succeeded: %s", key)
                base_cache.set(key, fresh, ttl)
                base_cache.set(f"{key}:meta", {"time": time.time(), "ttl": ttl}, ttl + self._stale_window)
                return fresh
            else:
                logger.warning("fresh fetch validation failed: %s", key)

        except Exception as e:
            logger.warning("fresh fetch failed: %s, error: %s", key, e)

        # Fresh fetch failed — return stale if available
        if cached is not None:
            logger.warning("fetch failed, using stale cache: %s", key)
            return cached

        # No stale cache — return empty
        logger.error("fetch failed, no stale cache: %s", key)
        if isinstance(fetcher(), pd.DataFrame):
            return pd.DataFrame()
        return None

    def set_with_quality(self, key: str, value: Any, ttl: int, quality: dict) -> None:
        """Set cache with quality metadata."""
        base_cache.set(key, value, ttl)
        base_cache.set(
            f"{key}:meta",
            {"time": time.time(), "ttl": ttl, "quality": quality},
            ttl + self._stale_window,
        )

    def get_quality(self, key: str) -> Optional[dict]:
        """Get quality metadata for cached data."""
        meta = base_cache.get(f"{key}:meta")
        return meta.get("quality") if meta else None


_enhanced: Optional[EnhancedCache] = None


def enhanced() -> EnhancedCache:
    global _enhanced
    if _enhanced is None:
        _enhanced = EnhancedCache()
    return _enhanced
