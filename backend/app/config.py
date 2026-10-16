"""Application settings.

Single source of truth for every runtime knob. No other module in the code
base is allowed to read ``os.environ`` directly — it asks ``get_settings()``.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.models import CostModel


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ app
    app_name: str = "AlphaForge"
    api_v1_prefix: str = "/api/v1"
    ws_v1_prefix: str = "/ws/v1"
    debug: bool = False
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # ------------------------------------------------------------------ LLM
    # The graph is fully functional with llm_provider="heuristic": every node
    # then derives its qualitative text from deterministic rules instead of a
    # model call. Turn it on only when a key is present.
    llm_provider: Literal["openai", "heuristic"] = "heuristic"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.0
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2

    # --------------------------------------------------------- market data
    data_provider: Literal["akshare", "synthetic"] = "akshare"
    kline_lookback_days: int = 500
    benchmark_symbol: str = "000300"
    data_request_timeout_s: float = 20.0
    data_max_retries: int = 3
    data_retry_base_wait_s: float = 0.5
    data_retry_max_wait_s: float = 4.0
    news_limit: int = 10

    # -------------------------------------------------- costs & execution
    commission_rate: float = 0.0003     # 0.03% 双边
    commission_min: float = 5.0         # 单笔最低 5 元
    stamp_tax_rate: float = 0.001       # 0.1% 卖出单边
    transfer_fee_rate: float = 0.00002  # 0.002% 沪市双边
    slippage: float = 0.001             # 0.1% 单边
    lot_size: int = 100                 # 一手 100 股
    initial_capital: float = 1_000_000.0

    # ------------------------------------------------------------ analysis
    debate_rounds: int = 2              # 1..3
    max_concurrent_tasks: int = 4       # semaphore around graph invocations
    # Dev aid: artificial pause (ms) between graph nodes so the progress panel
    # is observable on fast synthetic runs. 0 in production.
    debug_step_delay_ms: float = 0.0
    risk_free_rate: float = 0.02
    trading_days_per_year: int = 252
    min_bars_required: int = 120
    stale_after_days: int = 10          # 最后一根 K 线超过该天数 -> 疑似停牌/退市

    # ---------------------------------------------------------- infra
    persistence: Literal["mongo", "memory"] = "mongo"
    mongo_uri: str = "mongodb://mongo:27017"
    mongo_db: str = "alphaforge"
    mongo_timeout_ms: int = 3_000

    cache_backend: Literal["redis", "memory"] = "redis"
    redis_url: str = "redis://redis:6379/0"
    redis_ttl_seconds: int = 900
    redis_channel_prefix: str = "alphaforge:progress"

    # WebSocket
    ws_heartbeat_interval_s: float = 30.0
    ws_server_ping_interval_s: float = 20.0
    ws_server_ping_timeout_s: float = 20.0
    ws_max_connections_per_task: int = 8

    task_ttl_seconds: int = 3_600

    @property
    def cost_model(self) -> CostModel:
        return CostModel(
            commission_rate=self.commission_rate,
            commission_min=self.commission_min,
            stamp_tax_rate=self.stamp_tax_rate,
            transfer_fee_rate=self.transfer_fee_rate,
            slippage=self.slippage,
            lot_size=self.lot_size,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor. Tests use ``get_settings.cache_clear()``."""
    return Settings()
