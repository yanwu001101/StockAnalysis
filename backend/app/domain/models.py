"""Domain value objects **and** the wire contract.

Split into two clearly separated sections:

1. Domain value objects — what the agents and the backtest engine pass
   around internally.
2. Wire contracts — the DTOs the frontend's ``types/quant.d.ts`` mirrors
   exactly. These are the only models allowed to cross the HTTP boundary.

Every wire DTO is ``frozen`` and camelCase-aliased so that FastAPI serialises
it with the exact keys the TypeScript side declares.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Shared scalar helpers
# ---------------------------------------------------------------------------

_MAX_ABS = 1e12


def _round4(value: float) -> float:
    """Deterministic 4-decimal rounding that never emits ``-0.0``.

    Two runs over identical inputs must produce byte-identical payloads;
    ``-0.0`` and ``0.0`` serialise differently and break snapshot equality.
    """
    rounded = round(float(value), 4)
    if rounded == 0:
        return 0.0
    return rounded


def _finite_or_zero(value: float) -> float:
    """Clamp non-finite numbers to the sentinel 0.0.

    The wire contract declares ``number``, and JSON has no NaN/Infinity. The
    producer must therefore never emit one — see ``MetricStatusMap`` for how
    "we could not compute this" is communicated instead.
    """
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return min(max(number, -_MAX_ABS), _MAX_ABS)


Metric = Annotated[float, AfterValidator(_finite_or_zero), AfterValidator(_round4)]


def _utc_now_ms() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp() * 1000)


class Signal(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class ColorClass(str, Enum):
    # Note the deliberate clash with the A-share price convention:
    #   * charts use 红涨 / 绿跌 (#F85149 up, #3FB950 down)
    #   * verdicts use risk semantics: green = safe, red = dangerous
    GREEN = "text-green"
    YELLOW = "text-yellow"
    RED = "text-red"


class MetricStatus(str, Enum):
    VALID = "VALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    FAILED = "FAILED"


class AgentId(str, Enum):
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    TECHNICAL = "technical"
    RISK = "risk"


class AgentStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ===========================================================================
# 1. Domain value objects
# ===========================================================================


class CostModel(BaseModel):
    """A-share execution costs. Rates are fractions, not percentages."""

    model_config = ConfigDict(frozen=True)

    commission_rate: float = Field(default=0.0003, ge=0.0, le=0.01)
    commission_min: float = Field(default=5.0, ge=0.0)
    stamp_tax_rate: float = Field(default=0.001, ge=0.0, le=0.01)
    transfer_fee_rate: float = Field(default=0.00002, ge=0.0, le=0.01)
    slippage: float = Field(default=0.001, ge=0.0, le=0.05)
    lot_size: int = Field(default=100, ge=1)

    @field_validator("commission_rate", "stamp_tax_rate", "transfer_fee_rate", "slippage")
    @classmethod
    def _finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("rate must be finite")
        return value


class Bar(BaseModel):
    """One adjusted daily bar. Volumes are in shares (手 x 100)."""

    model_config = ConfigDict(frozen=True)

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float = 0.0

    @property
    def tradeable(self) -> bool:
        return (
            self.volume > 0
            and self.open > 0
            and self.close > 0
            and self.high > 0
            and self.low > 0
        )


class FundamentalSnapshot(BaseModel):
    """Point-in-time fundamentals. ``None`` means unknown, never zero."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    name: str = ""
    pe: float | None = None
    pb: float | None = None
    roe: float | None = None          # percent, e.g. 15.2
    debt_ratio: float | None = None   # percent, e.g. 42.7
    revenue_yoy: float | None = None  # percent
    net_profit_yoy: float | None = None  # percent
    market_cap_yi: float | None = None   # 亿元
    industry: str = ""
    report_date: date | None = None
    source: str = "unknown"


class NewsItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    publish_time: datetime | None = None
    source: str = ""
    url: str = ""


class SentimentSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    items: list[NewsItem] = Field(default_factory=list)
    # [-1, 1]; 0.0 = no evidence collected, not "neutral by analysis"
    polarity: float = 0.0
    buzz: int = 0
    source: str = "unknown"
    available: bool = False


class TechnicalSnapshot(BaseModel):
    """Latest values of the deterministic indicator set."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    last_date: date | None = None
    last_close: float = 0.0
    dif: float = 0.0
    dea: float = 0.0
    macd_hist: float = 0.0
    rsi14: float = 50.0
    boll_upper: float = 0.0
    boll_mid: float = 0.0
    boll_lower: float = 0.0
    atr14: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0
    volume_ratio: float = 1.0


class DebaterSide(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"


class DebateEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    round: int
    side: DebaterSide
    argument: str
    conviction: float = Field(default=0.5, ge=0.0, le=1.0)


class RiskProfile(str, Enum):
    AGGRESSIVE = "AGGRESSIVE"
    CONSERVATIVE = "CONSERVATIVE"
    NEUTRAL = "NEUTRAL"


class RiskAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile: RiskProfile
    position_scale: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str = ""


class Trade(BaseModel):
    """One executed fill. Dates are market dates, prices are fill prices."""

    model_config = ConfigDict(frozen=True)

    date: date
    side: Literal["BUY", "SELL"]
    shares: int
    price: float          # fill price, slippage already applied
    commission: float
    stamp_tax: float
    transfer_fee: float
    cash_flow: float      # negative on BUY, positive on SELL
    pnl: float | None = None  # realised PnL on SELL only


# ===========================================================================
# 2. Wire contracts (mirrored 1:1 by frontend/src/types/quant.d.ts)
# ===========================================================================


class QuantMetricsDTO(BaseModel):
    """The six headline numbers.

    Every field is a plain float because that is what the contract says. A
    float cannot express "uncomputable", so the accompanying
    ``MetricStatusMap`` carries that information instead — never a silent 0.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    sharpe_ratio: Metric = Field(serialization_alias="sharpeRatio")
    max_drawdown: Metric = Field(serialization_alias="maxDrawdown")
    win_rate: Metric = Field(serialization_alias="winRate")
    total_return: Metric = Field(serialization_alias="totalReturn")
    alpha: Metric
    beta: Metric


class MetricStatusMap(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    sharpe_ratio: MetricStatus = Field(
        default=MetricStatus.VALID, serialization_alias="sharpeRatio"
    )
    max_drawdown: MetricStatus = Field(
        default=MetricStatus.VALID, serialization_alias="maxDrawdown"
    )
    win_rate: MetricStatus = Field(
        default=MetricStatus.VALID, serialization_alias="winRate"
    )
    total_return: MetricStatus = Field(
        default=MetricStatus.VALID, serialization_alias="totalReturn"
    )
    alpha: MetricStatus = MetricStatus.VALID
    beta: MetricStatus = MetricStatus.VALID

    def as_dict(self) -> dict[str, str]:
        return {
            "sharpeRatio": self.sharpe_ratio.value,
            "maxDrawdown": self.max_drawdown.value,
            "winRate": self.win_rate.value,
            "totalReturn": self.total_return.value,
            "alpha": self.alpha.value,
            "beta": self.beta.value,
        }


class HumanReadableVerdict(BaseModel):
    """Plain-language verdict. 0-100, higher is safer."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    score: int = Field(default=50, ge=0, le=100)
    signal: Signal = Signal.HOLD
    reasons: list[str] = Field(default_factory=list)
    color_class: ColorClass = Field(
        default=ColorClass.YELLOW, serialization_alias="colorClass"
    )


class AgentProgressPayload(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    task_id: str = Field(serialization_alias="taskId")
    agent_id: AgentId = Field(serialization_alias="agentId")
    agent_name: str = Field(serialization_alias="agentName")
    status: AgentStatus = AgentStatus.PENDING
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str = ""
    timestamp: int = Field(default_factory=_utc_now_ms)


class ChartMarker(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str          # YYYY-MM-DD, must match the candle x-axis exactly
    price: float
    action: Literal["BUY", "SELL"]
    reason: str


class TradeDTO(BaseModel):
    """One closed round trip, flattened for the trade-log panel."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    date: str
    side: Literal["BUY", "SELL"]
    shares: int
    price: float
    commission: float
    stamp_tax: float = Field(serialization_alias="stampTax")
    transfer_fee: float = Field(serialization_alias="transferFee")
    pnl: float | None = None


class DebateDTO(BaseModel):
    """One debate turn, for the replay panel."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    round: int
    side: Literal["BULL", "BEAR"]
    argument: str
    conviction: float


class SystemStats(BaseModel):
    """Agent fleet health for the command center."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    total: int = 0
    running: int = 0
    completed: int = 0
    failed: int = 0
    success_rate: float = Field(default=0.0, serialization_alias="successRate")


class MarketOverview(BaseModel):
    """Benchmark snapshot + breadth. Nulls mean "not available", never 0."""

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    benchmark_symbol: str = Field(serialization_alias="benchmarkSymbol")
    benchmark_name: str = Field(serialization_alias="benchmarkName")
    last_close: float | None = Field(default=None, serialization_alias="lastClose")
    change_pct: float | None = Field(default=None, serialization_alias="changePct")
    as_of: str = ""
    advancing: int | None = None
    declining: int | None = None
    flat: int | None = None
    breadth_available: bool = Field(default=False, serialization_alias="breadthAvailable")


class QuantVerdictPayload(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    raw_metrics: QuantMetricsDTO = Field(serialization_alias="rawMetrics")
    human_verdict: HumanReadableVerdict = Field(serialization_alias="humanVerdict")
    chart_markers: list[ChartMarker] = Field(
        default_factory=list, serialization_alias="chartMarkers"
    )
    # Extra, non-breaking fields: the frontend ignores unknown keys but the
    # UI needs provenance to avoid rendering a fabricated 0.0 as a real one.
    metric_status: MetricStatusMap = Field(
        default_factory=MetricStatusMap, serialization_alias="metricStatus"
    )
    symbol: str = ""
    # [open, close, low, high] per bar — ECharts order; `dates` has the same
    # length and order so the chart can align markPoint coordinates exactly.
    candles: list[list[float]] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    # Mark-to-market equity aligned 1:1 with `dates` (backtest lab curve).
    equity_curve: list[float] = Field(
        default_factory=list, serialization_alias="equityCurve"
    )
    trades: list[TradeDTO] = Field(default_factory=list)
    debate: list[DebateDTO] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --------------------------------------------------------------- WS envelope

WsPayloadType = Literal["progress", "verdict", "heartbeat", "error"]


class WsEnvelope(BaseModel):
    """Every WebSocket frame is wrapped so the client can dispatch on one tag."""

    model_config = ConfigDict(frozen=True)

    type: WsPayloadType
    task_id: str = Field(serialization_alias="taskId")
    payload: AgentProgressPayload | QuantVerdictPayload | dict[str, str]


class AnalysisTask(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(serialization_alias="taskId")
    symbol: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: int = Field(default_factory=_utc_now_ms)
    updated_at: int = Field(default_factory=_utc_now_ms)
    error: str | None = None
    verdict: QuantVerdictPayload | None = None


class AnalyzeRequest(BaseModel):
    symbol: str = Field(min_length=6, max_length=10, examples=["600519"])
    # 回测实验室可选覆盖项；缺省时用服务端 Settings 的成本模型。
    backtest: BacktestOverrides | None = None

    @field_validator("symbol")
    @classmethod
    def _digits_only(cls, value: str) -> str:
        raw = value.strip()
        for suffix in (".SH", ".SZ", ".sh", ".sz", ".BJ", ".bj"):
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)]
                break
        raw = raw.lstrip("shSHszSZbjBJ") if raw[:2].isalpha() and raw[2:].isdigit() else raw
        if not raw.isdigit():
            raise ValueError("symbol must be 6 digits, e.g. 600519")
        return raw.zfill(6)


class BacktestOverrides(BaseModel):
    """Per-request backtest knobs (回测实验室). All fields optional.

    请求体统一 camelCase（与响应一致）；``populate_by_name=True`` 保证 Python
    侧按字段名构造同样可行。
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    initial_capital: float | None = Field(
        default=None, gt=0, le=1e12, validation_alias="initialCapital"
    )
    commission_rate: float | None = Field(
        default=None, ge=0, le=0.01, validation_alias="commissionRate"
    )
    commission_min: float | None = Field(
        default=None, ge=0, validation_alias="commissionMin"
    )
    stamp_tax_rate: float | None = Field(
        default=None, ge=0, le=0.01, validation_alias="stampTaxRate"
    )
    transfer_fee_rate: float | None = Field(
        default=None, ge=0, le=0.01, validation_alias="transferFeeRate"
    )
    slippage: float | None = Field(default=None, ge=0, le=0.05)
    lot_size: int | None = Field(default=None, ge=1, validation_alias="lotSize")
    start_date: date | None = Field(default=None, validation_alias="startDate")
    end_date: date | None = Field(default=None, validation_alias="endDate")

    @field_validator("start_date", "end_date")
    @classmethod
    def _window_order(cls, value: date | None) -> date | None:
        return value

    @model_validator(mode="after")
    def _check_window(self) -> "BacktestOverrides":
        if self.start_date is not None and self.end_date is not None:
            if self.end_date < self.start_date:
                raise ValueError("end_date must not be earlier than start_date")
        return self

    def resolved_window(self) -> tuple[date | None, date | None]:
        return self.start_date, self.end_date

    def apply_to(self, cost: CostModel) -> CostModel:
        """Layer the overrides on top of the server cost model."""
        updates: dict[str, float | int] = {}
        if self.commission_rate is not None:
            updates["commission_rate"] = self.commission_rate
        if self.commission_min is not None:
            updates["commission_min"] = self.commission_min
        if self.stamp_tax_rate is not None:
            updates["stamp_tax_rate"] = self.stamp_tax_rate
        if self.transfer_fee_rate is not None:
            updates["transfer_fee_rate"] = self.transfer_fee_rate
        if self.slippage is not None:
            updates["slippage"] = self.slippage
        if self.lot_size is not None:
            updates["lot_size"] = self.lot_size
        return cost.model_copy(update=updates) if updates else cost


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    task_id: str = Field(serialization_alias="taskId")
    symbol: str
    status: TaskStatus = TaskStatus.PENDING
