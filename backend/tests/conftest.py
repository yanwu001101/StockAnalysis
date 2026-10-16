"""Shared fixtures: synthetic market, in-memory stores, recording publisher."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Iterable

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.domain.models import AgentProgressPayload, Bar, QuantVerdictPayload  # noqa: E402
from app.domain.ports import ProgressPublisherPort  # noqa: E402


def make_bars(
    count: int = 260,
    start: dt.date | None = None,
    base_price: float = 50.0,
    seed: int = 7,
) -> list[Bar]:
    """Deterministic business-day price series (no network, no akshare)."""
    import random

    rng = random.Random(seed)
    day = start or dt.date(2025, 1, 2)
    price = base_price
    bars: list[Bar] = []
    while len(bars) < count:
        if day.weekday() < 5:
            drift = rng.uniform(-0.028, 0.03)
            open_price = round(price, 2)
            close_price = round(price * (1.0 + drift), 2)
            high_price = round(max(open_price, close_price) * 1.006, 2)
            low_price = round(min(open_price, close_price) * 0.994, 2)
            bars.append(
                Bar(
                    date=day,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=float(rng.randint(5_000, 90_000) * 100),
                    amount=float(rng.randint(5_000, 90_000) * 100 * close_price),
                )
            )
            price = close_price
        day += dt.timedelta(days=1)
    return bars


class RecordingPublisher:
    """ProgressPublisherPort test double — records every frame."""

    name = "recording"

    def __init__(self) -> None:
        self.progress: list[AgentProgressPayload] = []
        self.verdicts: list[tuple[str, QuantVerdictPayload]] = []
        self.errors: list[tuple[str, str]] = []

    def publish_progress(self, payload: AgentProgressPayload) -> None:
        self.progress.append(payload)

    def publish_verdict(self, task_id: str, payload: QuantVerdictPayload) -> None:
        self.verdicts.append((task_id, payload))

    def publish_error(self, task_id: str, message: str) -> None:
        self.errors.append((task_id, message))

    def messages(self) -> Iterable[str]:
        return [f"{p.agent_id.value}:{p.status.value}:{p.message}" for p in self.progress]


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        data_provider="synthetic",
        persistence="memory",
        cache_backend="memory",
        llm_provider="heuristic",
        kline_lookback_days=260,
        debate_rounds=2,
        initial_capital=1_000_000.0,
    )


@pytest.fixture()
def bars() -> list[Bar]:
    return make_bars(260)


@pytest.fixture()
def publisher() -> RecordingPublisher:
    return RecordingPublisher()
