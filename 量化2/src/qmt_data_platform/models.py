from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Period(str, Enum):
    TICK = "tick"
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    D1 = "1d"


class Adjust(str, Enum):
    NONE = "none"
    FRONT = "front"
    BACK = "back"


class Bar(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    period: Period
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = Field(ge=0)
    amount: float = Field(ge=0)
    pre_close: Optional[float] = None
    source: str = "unknown"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        value = value.strip().upper()
        if "." not in value:
            if value.startswith(("5", "6", "9")):
                value = f"{value}.SH"
            elif value.startswith(("0", "1", "2", "3")):
                value = f"{value}.SZ"
        return value


class SyncRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=5000)
    period: Period = Period.D1
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    adjust: Adjust = Adjust.NONE


class SyncResult(BaseModel):
    provider: str
    requested_symbols: int
    received_rows: int
    written_rows: int
    started_at: datetime
    finished_at: datetime


class Quote(BaseModel):
    symbol: str
    name: Optional[str] = None
    timestamp: datetime
    price: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    pre_close: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    amount: Optional[float] = None
    turnover_pct: Optional[float] = None
    pe_ttm: Optional[float] = None
    pb: Optional[float] = None
    source: str = "unknown"
