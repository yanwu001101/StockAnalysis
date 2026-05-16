# -*- coding: utf-8 -*-
"""Centralized configuration via pydantic-settings.

All env vars are read here once at startup. Modules should import `settings`
instead of touching os.environ directly. This makes config testable and
discoverable, and lets us validate required values at boot time.
"""
from __future__ import annotations
import os
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HttpSettings(BaseSettings):
    """HTTP client tuning."""
    model_config = SettingsConfigDict(env_prefix="HTTP_", extra="ignore")

    timeout_s: float = 10.0
    connect_timeout_s: float = 5.0
    max_connections: int = 64
    max_keepalive: int = 32
    http2: bool = True
    verify_ssl: bool = True
    # Per-domain concurrency (used by ratelimit, not connection pool)
    concurrency_default: int = 8


class RateLimitSettings(BaseSettings):
    """Adaptive token-bucket per domain."""
    model_config = SettingsConfigDict(env_prefix="RL_", extra="ignore")

    jitter_min_ms: int = 50
    jitter_max_ms: int = 200
    # When a domain returns 429/418/403 we sleep `cooldown_s` then halve rate
    cooldown_s: float = 5.0
    # After N consecutive 2xx, slowly increase rate back
    speedup_after: int = 30


class RetrySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RETRY_", extra="ignore")

    max_attempts: int = 4
    base_wait_s: float = 0.5
    max_wait_s: float = 8.0


class CircuitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CB_", extra="ignore")

    failure_threshold: float = 0.5       # 50% failure rate trips the breaker
    sample_window: int = 20              # over the last 20 calls
    open_seconds: float = 60.0           # cool-down before half-open probe


class DbSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    db_host: str = Field(default="mysql", alias="DB_HOST")
    db_port: int = Field(default=3306, alias="DB_PORT")
    db_user: str = Field(default="root", alias="DB_USER")
    db_password: str = Field(default="Stock@2024", alias="DB_PASSWORD")
    db_name: str = Field(default="stock_screener", alias="DB_NAME")


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, alias="REDIS_PASSWORD")


class SourceSettings(BaseSettings):
    """Per-source toggles + credentials."""
    model_config = SettingsConfigDict(extra="ignore")

    tushare_token: Optional[str] = Field(default=None, alias="TUSHARE_TOKEN")
    xueqiu_cookie: Optional[str] = Field(default=None, alias="XUEQIU_COOKIE")
    proxy_pool_url: Optional[str] = Field(default=None, alias="PROXY_POOL_URL")
    enable_playwright: bool = Field(default=False, alias="ENABLE_PLAYWRIGHT")


class SchedulerSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    warmup_on_start: bool = Field(default=False, alias="WARMUP_ON_START")
    warmup_delay_sec: int = Field(default=60, alias="WARMUP_DELAY_SEC")
    warmup_top_n: int = Field(default=300, alias="WARMUP_TOP_N")
    warmup_batch_size: int = Field(default=50, alias="WARMUP_BATCH_SIZE")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    env: str = Field(default="dev", alias="APP_ENV")
    tz: str = Field(default="Asia/Shanghai", alias="TZ")

    http: HttpSettings = HttpSettings()
    rl: RateLimitSettings = RateLimitSettings()
    retry: RetrySettings = RetrySettings()
    cb: CircuitSettings = CircuitSettings()
    db: DbSettings = DbSettings()
    redis: RedisSettings = RedisSettings()
    sources: SourceSettings = SourceSettings()
    sched: SchedulerSettings = SchedulerSettings()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


# Convenience: `from config import settings`
settings = get_settings()
