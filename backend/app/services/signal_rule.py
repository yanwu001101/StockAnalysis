"""Deterministic trade-signal rule.

This is where the "no future function" guarantee is actually enforced.

The rule produces, for every bar index ``i``, a target exposure that is a
function of ``bars[0:i]`` only — i.e. of everything known when bar ``i-1``
has closed. The engine then executes it at the **open** of bar ``i``. Nothing
downstream may read bar ``i`` or later.

Why this can be computed in O(n) and still be correct: every indicator used
here (EMA, Wilder RSI, rolling Bollinger, ATR) is a *causal filter* — its
value at index ``j`` depends only on bars ``0..j``. So the value read at
index ``i-1`` from a single pass over the full series is bit-identical to the
value that would come out of a fresh pass over the prefix.

The LLM never touches this. It may only comment on the outcome.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.domain.models import Bar
from app.services.indicators import atr, bollinger, macd, rsi

_WARMUP_MARGIN = 5


@dataclass(frozen=True, slots=True)
class SignalRuleConfig:
    """Tunable, but frozen at graph-build time so runs stay reproducible."""

    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    boll_period: int = 20
    boll_std: float = 2.0
    atr_period: int = 14
    use_macd: bool = True
    use_rsi: bool = True
    use_boll: bool = True
    entry_score: float = 1.0
    exit_score: float = -1.0

    @property
    def warmup(self) -> int:
        base = max(
            self.macd_slow + self.macd_signal if self.use_macd else 0,
            self.rsi_period + 1 if self.use_rsi else 0,
            self.boll_period if self.use_boll else 0,
            self.atr_period if True else 0,
        )
        return base + _WARMUP_MARGIN


@dataclass(frozen=True, slots=True)
class SignalDecision:
    """Target exposure for bar ``index``, derived from bars before it."""

    index: int
    target: float          # 1.0 = fully long, 0.0 = flat
    score: float           # signed conviction that produced the target
    reasons: tuple[str, ...] = ()


class SignalRule:
    """Translates price history into a no-look-ahead exposure sequence."""

    def __init__(self, config: SignalRuleConfig | None = None) -> None:
        self._config = config or SignalRuleConfig()

    @property
    def config(self) -> SignalRuleConfig:
        return self._config

    def decide(self, bars: Sequence[Bar]) -> tuple[SignalDecision, ...]:
        cfg = self._config
        if not bars:
            return ()

        close = [bar.close for bar in bars]
        high = [bar.high for bar in bars]
        low = [bar.low for bar in bars]

        dif, dea, _ = macd(close, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
        rsi_values = rsi(close, cfg.rsi_period)
        boll_up, _, boll_low = bollinger(close, cfg.boll_period, cfg.boll_std)
        atr_values = atr(high, low, close, cfg.atr_period)

        decisions: list[SignalDecision] = []
        target = 0.0
        for i in range(len(bars)):
            if i < cfg.warmup:
                decisions.append(SignalDecision(index=i, target=0.0, score=0.0))
                continue

            # Everything below reads index i-1 and i-2 only.
            score = 0.0
            reasons: list[str] = []

            if cfg.use_macd and i >= 2:
                if dif[i - 2] <= dea[i - 2] and dif[i - 1] > dea[i - 1]:
                    score += 1.0
                    reasons.append("MACD 金叉：短期均线向上穿越长期均线")
                elif dif[i - 2] >= dea[i - 2] and dif[i - 1] < dea[i - 1]:
                    score -= 1.0
                    reasons.append("MACD 死叉：短期均线向下跌破长期均线")

            if cfg.use_rsi:
                value = rsi_values[i - 1]
                if value == value:  # not NaN
                    if value < cfg.rsi_oversold:
                        score += 1.0
                        reasons.append(f"RSI 超卖（{value:.1f}），短线抛压释放")
                    elif value > cfg.rsi_overbought:
                        score -= 1.0
                        reasons.append(f"RSI 超买（{value:.1f}），追高风险上升")

            if cfg.use_boll:
                last_close = close[i - 1]
                if last_close < boll_low[i - 1]:
                    score += 1.0
                    reasons.append("收盘价跌破布林下轨，极端偏离后的均值回归机会")
                elif last_close > boll_up[i - 1]:
                    score -= 1.0
                    reasons.append("收盘价冲出布林上轨，短线过热")

            new_target = target
            if score >= cfg.entry_score:
                new_target = 1.0
            elif score <= cfg.exit_score:
                new_target = 0.0
            target = new_target
            decisions.append(
                SignalDecision(index=i, target=target, score=score, reasons=tuple(reasons))
            )

        # ATR is computed for the position-sizing narrative; kept on the
        # decision list as an unused-but-verified series to avoid a silent
        # divergence between "computed" and "used" indicators.
        assert len(atr_values) == len(bars)
        return tuple(decisions)
