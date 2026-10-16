"""Signal rule — the "no future function" guarantee, tested by mutation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.signal_rule import SignalRule

from tests.conftest import make_bars


class TestNoLookAhead:
    def test_decisions_before_i_ignore_bars_after_i(self) -> None:
        """Mutating every bar after index 100 must not move decisions <= 100."""
        bars = make_bars(300, seed=11)
        rule = SignalRule()
        baseline = rule.decide(bars)

        mutated = list(bars)
        for index in range(101, len(mutated)):
            bar = mutated[index]
            mutated[index] = bar.model_copy(
                update={
                    "open": bar.open * 3.0,
                    "high": bar.high * 3.0,
                    "low": bar.low * 0.2,
                    "close": bar.close * 3.0,
                }
            )
        after = rule.decide(mutated)

        for index in range(0, 101):
            assert baseline[index].target == after[index].target
            assert baseline[index].score == after[index].score

    def test_warmup_is_flat(self) -> None:
        bars = make_bars(120)
        rule = SignalRule()
        decisions = rule.decide(bars)
        warmup = rule.config.warmup
        for index in range(warmup):
            assert decisions[index].target == 0.0

    def test_rule_is_deterministic(self) -> None:
        bars = make_bars(200)
        assert SignalRule().decide(bars) == SignalRule().decide(bars)
