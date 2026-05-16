# -*- coding: utf-8 -*-
"""Strategy framework.

Every strategy:
  * Receives a StrategyContext with all data already loaded (DI'd by the runner).
  * Returns a ScoreResult (defined in models.py) with score, signal, details.
  * Has a pydantic Params class for tunable thresholds — no magic numbers.

This separation lets us unit-test each strategy with hand-crafted fixtures
without ever touching the network or DB.
"""
from __future__ import annotations
import abc
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd
from pydantic import BaseModel

from models import ScoreResult


@dataclass
class StrategyContext:
    """Per-code data bag. Members are optional — strategies guard for empty DFs."""
    code: str
    name: str = ""
    industry: str = ""
    price: float = 0.0
    market_cap_yi: float = 0.0
    daily_df: Optional[pd.DataFrame] = None           # 日K (Chinese cols)
    weekly_df: Optional[pd.DataFrame] = None
    fundamental_df: Optional[pd.DataFrame] = None     # multi-period rows
    moneyflow_df: Optional[pd.DataFrame] = None
    northbound_df: Optional[pd.DataFrame] = None
    lhb_df: Optional[pd.DataFrame] = None
    shareholder_df: Optional[pd.DataFrame] = None
    dividend_df: Optional[pd.DataFrame] = None
    sector_rank: Optional[float] = None               # 0 (top) to 1 (bottom)
    sector_rank_n: int = 0
    has_earnings_announcement: bool = False
    extras: dict = field(default_factory=dict)


class Params(BaseModel):
    """Each strategy subclasses Params to declare its tunables."""
    class Config:
        extra = "allow"


class AbstractStrategy(abc.ABC):
    id: str = "abstract"
    name: str = "Abstract Strategy"
    default_weight: float = 0.0
    Params: type[Params] = Params

    def __init__(self, params: Params | None = None):
        self.params = params or self.Params()

    @abc.abstractmethod
    def score(self, ctx: StrategyContext) -> ScoreResult:
        ...

    @staticmethod
    def _bullish(score: float, threshold: float = 60) -> str:
        if score >= threshold:
            return "bullish"
        if score <= 25:
            return "bearish"
        return "neutral"
