"""Verdict translator — strategy pattern thresholds (mirrors the TS mapper)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.domain.models import MetricStatus
from app.services.verdict import (
    TRANSLATORS,
    MaxDrawdownTranslator,
    SharpeTranslator,
    aggregate,
    color_class_for,
    signal_for,
)


def _metrics(**overrides: float) -> dict[str, tuple[float, MetricStatus]]:
    base = {
        "sharpe_ratio": 1.5,
        "max_drawdown": -0.12,
        "win_rate": 0.5,
        "total_return": 0.1,
        "alpha": 0.02,
        "beta": 1.0,
    }
    base.update(overrides)
    return {key: (value, MetricStatus.VALID) for key, value in base.items()}


class TestTranslators:
    def test_registry_covers_all_six_metrics(self) -> None:
        assert {t.key for t in TRANSLATORS} == {
            "sharpe_ratio",
            "max_drawdown",
            "win_rate",
            "total_return",
            "alpha",
            "beta",
        }

    def test_max_drawdown_worst_case_wording(self) -> None:
        # -0.15 -> "每投入1万，最多可能亏1500元"（-0.15 > -0.20，回撤可接受，0 分）
        translation = MaxDrawdownTranslator()._valid(-0.15)
        assert "1500" in translation.text
        assert translation.score_delta == 0.0

    def test_uncomputable_metric_is_neutral_not_zero(self) -> None:
        translation = SharpeTranslator().translate(0.0, MetricStatus.INSUFFICIENT_DATA)
        assert translation.available is False
        assert translation.score_delta == 0.0
        assert "无法计算" in translation.text

    def test_aggregate_score_is_bounded(self) -> None:
        worst = aggregate(
            _metrics(
                sharpe_ratio=-5.0,
                max_drawdown=-0.9,
                win_rate=0.0,
                total_return=-0.9,
                alpha=-0.9,
                beta=3.0,
            )
        )
        assert 0 <= worst.score <= 100
        assert worst.score == 0

    def test_aggregate_reasons_include_all_metrics(self) -> None:
        verdict = aggregate(_metrics())
        assert len(verdict.reasons) == 6

    def test_signal_and_color_thresholds(self) -> None:
        # BUY >= 65, SELL <= 35, 其余 HOLD（与前端 mapper 同一组阈值）
        assert signal_for(65) == "BUY"
        assert signal_for(64) == "HOLD"
        assert signal_for(36) == "HOLD"
        assert signal_for(35) == "SELL"
        assert color_class_for(80) == "text-green"
        assert color_class_for(50) == "text-yellow"
        assert color_class_for(10) == "text-red"

    def test_strong_metrics_reach_buy(self) -> None:
        verdict = aggregate(
            _metrics(
                sharpe_ratio=2.5,
                max_drawdown=-0.05,
                win_rate=0.7,
                total_return=0.5,
                alpha=0.2,
                beta=1.0,
            )
        )
        assert verdict.score >= 65
        assert signal_for(verdict.score) == "BUY"
