from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="QDP_", extra="ignore", case_sensitive=False
    )

    provider: Literal["auto", "xtquant", "astock", "mock"] = "auto"
    qmt_path: Optional[Path] = None
    database_path: Path = Path("data/market.duckdb")
    parquet_root: Path = Path("data/parquet")
    log_level: str = "INFO"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("qmt_path", mode="before")
    @classmethod
    def empty_path_is_none(cls, value: object) -> object:
        return None if value == "" else value

    def ensure_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.parquet_root.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
