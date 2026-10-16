"""Metric -> plain-language translation, strategy pattern.

Each translator owns exactly one metric: it knows how to score it and how to
describe it in Chinese. Adding a metric means adding one class — the registry
below never changes (SOLID / open-closed).

The same table exists on the frontend in ``utils/mappers/quant-vm.ts``. The
backend verdict is authoritative; the frontend copy exists so the UI can
explain a metric even before the verdict arrives. The thresholds are pinned
by unit tests on both sides — keep the two in sync.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.models import MetricStatus


@dataclass(frozen=True, slots=True)
class Translation:
    score_delta: float
    text: str
    available: bool


class MetricTranslator(Protocol):
    key: str

    def translate(self, value: float, status: MetricStatus) -> Translation:
        ...


class _Base:
    key = ""

    def translate(self, value: float, status: MetricStatus) -> Translation:
        if status is not MetricStatus.VALID:
            return Translation(
                score_delta=0.0,
                text=f"{self.label}无法计算（{status.value}），已按中性处理，不计入评分",
                available=False,
            )
        return self._valid(value)

    def _valid(self, value: float) -> Translation:  # pragma: no cover - protocol
        raise NotImplementedError


class SharpeTranslator(_Base):
    key = "sharpe_ratio"
    label = "夏普比率"

    def _valid(self, value: float) -> Translation:
        if value < 0:
            return Translation(-20.0, f"夏普比率 {value:.2f}：承担风险没有换来回报", True)
        if value < 1.0:
            return Translation(-5.0, f"夏普比率 {value:.2f}：风险调整后收益一般", True)
        if value < 2.0:
            return Translation(10.0, f"夏普比率 {value:.2f}：每承担一份风险获得的回报较好", True)
        return Translation(20.0, f"夏普比率 {value:.2f}：风险调整后收益优秀", True)


class MaxDrawdownTranslator(_Base):
    key = "max_drawdown"
    label = "最大回撤"

    def _valid(self, value: float) -> Translation:
        worst_yuan = abs(value) * 10_000
        if value > -0.10:
            return Translation(
                10.0,
                f"历史最差情况：每投入1万，最多可能亏 {worst_yuan:.0f} 元，回撤很浅",
                True,
            )
        if value > -0.20:
            return Translation(
                0.0,
                f"历史最差情况：每投入1万，最多可能亏 {worst_yuan:.0f} 元，回撤可接受",
                True,
            )
        if value > -0.35:
            return Translation(
                -10.0,
                f"历史最差情况：每投入1万，最多可能亏 {worst_yuan:.0f} 元，回撤偏深",
                True,
            )
        return Translation(
            -20.0,
            f"历史最差情况：每投入1万，最多可能亏 {worst_yuan:.0f} 元，回撤很深",
            True,
        )


class WinRateTranslator(_Base):
    key = "win_rate"
    label = "胜率"

    def _valid(self, value: float) -> Translation:
        percent = value * 100
        if percent >= 60:
            return Translation(10.0, f"胜率 {percent:.1f}%：多数交易能赚到钱", True)
        if percent >= 45:
            return Translation(0.0, f"胜率 {percent:.1f}%：盈亏大致各半", True)
        return Translation(-10.0, f"胜率 {percent:.1f}%：多数交易以亏损收场", True)


class TotalReturnTranslator(_Base):
    key = "total_return"
    label = "总收益率"

    def _valid(self, value: float) -> Translation:
        percent = value * 100
        if percent > 20:
            return Translation(10.0, f"区间总收益 {percent:.2f}%：表现较好", True)
        if percent > 0:
            return Translation(0.0, f"区间总收益 {percent:.2f}%：小幅盈利", True)
        return Translation(-15.0, f"区间总收益 {percent:.2f}%：区间内亏损", True)


class AlphaTranslator(_Base):
    key = "alpha"
    label = "阿尔法"

    def _valid(self, value: float) -> Translation:
        if value > 0.05:
            return Translation(10.0, f"年化阿尔法 {value:.2f}：明显跑赢基准", True)
        if value >= -0.05:
            return Translation(0.0, f"年化阿尔法 {value:.2f}：与基准大致持平", True)
        return Translation(-10.0, f"年化阿尔法 {value:.2f}：跑输基准", True)


class BetaTranslator(_Base):
    key = "beta"
    label = "贝塔"

    def _valid(self, value: float) -> Translation:
        if 0.8 <= value <= 1.2:
            return Translation(5.0, f"贝塔 {value:.2f}：波动与大盘基本同步", True)
        return Translation(-5.0, f"贝塔 {value:.2f}：波动明显偏离大盘", True)


TRANSLATORS: tuple[MetricTranslator, ...] = (
    SharpeTranslator(),
    MaxDrawdownTranslator(),
    WinRateTranslator(),
    TotalReturnTranslator(),
    AlphaTranslator(),
    BetaTranslator(),
)

_BASE_SCORE = 50.0
_BUY_THRESHOLD = 65.0
_SELL_THRESHOLD = 35.0


@dataclass(frozen=True, slots=True)
class AggregatedVerdict:
    score: int
    reasons: list[str]


def aggregate(metrics: dict[str, tuple[float, MetricStatus]]) -> AggregatedVerdict:
    """Score the six metrics and return 0-100 plus the plain-language reasons."""
    values = {key: value for key, (value, _) in metrics.items()}
    statuses = {key: status for key, (_, status) in metrics.items()}

    score = _BASE_SCORE
    reasons: list[str] = []
    for translator in TRANSLATORS:
        key = translator.key
        if key not in values:
            continue
        result = translator.translate(values[key], statuses[key])
        score += result.score_delta
        reasons.append(result.text)

    bounded = int(max(0.0, min(100.0, round(score))))
    return AggregatedVerdict(score=bounded, reasons=reasons)


def signal_for(score: int) -> str:
    if score >= _BUY_THRESHOLD:
        return "BUY"
    if score <= _SELL_THRESHOLD:
        return "SELL"
    return "HOLD"


def color_class_for(score: int) -> str:
    if score >= _BUY_THRESHOLD:
        return "text-green"
    if score >= _SELL_THRESHOLD:
        return "text-yellow"
    return "text-red"
