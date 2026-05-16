# -*- coding: utf-8 -*-
"""Pydantic v2 data models.

Every external feed is parsed into one of these before being persisted or fed
into a strategy. Strict mode catches schema drift early instead of letting
junk values silently produce NaN downstream.
"""
from __future__ import annotations
import datetime as dt
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=False,
        extra="ignore",
    )


# ---------------------------------------------------------------------------
# Market quote (real-time / EOD snapshot)
# ---------------------------------------------------------------------------

class Quote(_Base):
    code: str
    name: str = ""
    price: Optional[Decimal] = None
    pct_change: Optional[Decimal] = None
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    prev_close: Optional[Decimal] = None
    volume: Optional[int] = None
    amount: Optional[Decimal] = None
    turnover: Optional[Decimal] = None
    pe: Optional[Decimal] = None
    pb: Optional[Decimal] = None
    market_cap: Optional[Decimal] = None
    float_cap: Optional[Decimal] = None
    industry: str = ""

    @field_validator("code", mode="before")
    @classmethod
    def _zfill_code(cls, v):
        s = str(v or "").strip()
        digits = "".join(ch for ch in s if ch.isdigit())
        return digits.zfill(6)[-6:]


# ---------------------------------------------------------------------------
# K-line bars
# ---------------------------------------------------------------------------

class KBar(_Base):
    code: str
    trade_date: dt.date
    period: str = "daily"                # daily/weekly/monthly/5min/15min/30min/60min
    open: Decimal
    close: Decimal
    high: Decimal
    low: Decimal
    volume: int
    amount: Optional[Decimal] = None
    pct_change: Optional[Decimal] = None
    turnover: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Fundamentals (报表合并视图)
# ---------------------------------------------------------------------------

class Fundamental(_Base):
    code: str
    report_date: dt.date
    period_type: str = "Q"               # Q / annual / TTM
    revenue: Optional[Decimal] = None
    net_profit: Optional[Decimal] = None
    op_cashflow: Optional[Decimal] = None
    ebit: Optional[Decimal] = None
    total_assets: Optional[Decimal] = None
    total_liab: Optional[Decimal] = None
    total_equity: Optional[Decimal] = None
    current_assets: Optional[Decimal] = None
    current_liab: Optional[Decimal] = None
    fixed_assets: Optional[Decimal] = None
    roe: Optional[Decimal] = None
    gross_margin: Optional[Decimal] = None
    debt_ratio: Optional[Decimal] = None
    current_ratio: Optional[Decimal] = None
    revenue_yoy: Optional[Decimal] = None
    net_profit_yoy: Optional[Decimal] = None
    eps: Optional[Decimal] = None
    bvps: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# Money flow
# ---------------------------------------------------------------------------

class MoneyFlow(_Base):
    code: str
    trade_date: dt.date
    super_large_net: Optional[Decimal] = None
    large_net: Optional[Decimal] = None
    medium_net: Optional[Decimal] = None
    small_net: Optional[Decimal] = None
    main_net: Optional[Decimal] = None


class Northbound(_Base):
    code: str
    trade_date: dt.date
    hold_shares: Optional[int] = None
    hold_market_cap: Optional[Decimal] = None
    hold_ratio: Optional[Decimal] = None
    net_buy: Optional[Decimal] = None


class LhbEntry(_Base):
    code: str
    trade_date: dt.date
    reason: str = ""
    buy_amount: Optional[Decimal] = None
    sell_amount: Optional[Decimal] = None
    net_amount: Optional[Decimal] = None
    seat_type: str = ""                  # "机构" / "游资" / "营业部"
    seat_name: str = ""


class Shareholder(_Base):
    code: str
    report_date: dt.date
    holder_count: Optional[int] = None
    top10_ratio: Optional[Decimal] = None
    institution_ratio: Optional[Decimal] = None


class Dividend(_Base):
    code: str
    ann_date: dt.date
    ex_date: Optional[dt.date] = None
    cash_per_10: Optional[Decimal] = None
    share_per_10: Optional[Decimal] = None
    transfer_per_10: Optional[Decimal] = None


class ConceptMember(_Base):
    concept_code: str
    concept_name: str
    code: str
    weight: Optional[Decimal] = None


class Announcement(_Base):
    code: str
    ann_date: dt.date
    title: str
    type: str = ""
    url: str = ""


# ---------------------------------------------------------------------------
# Strategy scoring contract
# ---------------------------------------------------------------------------

class ScoreResult(_Base):
    score: float = 0.0
    signal: str = "neutral"              # bullish / bearish / neutral
    details: dict = Field(default_factory=dict)
    factors: dict = Field(default_factory=dict)  # raw factor values for transparency
    triggered: bool = False
