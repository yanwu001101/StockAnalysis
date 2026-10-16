"""Node 4 — TechnicalAnalystNode.

Computes the indicator snapshot. Every number is a causal function of the
bars, so the snapshot is safe to show the user as "what the market looks like
as of the last close".
"""
from __future__ import annotations

from app.agents.nodes._progress import emit
from app.domain.models import AgentId, AgentStatus, TechnicalSnapshot
from app.services.indicators import atr, bollinger, macd, rsi, sma


def technical_node(state: dict) -> dict:
    bars = state["bars"]

    emit(state, AgentId.TECHNICAL, AgentStatus.RUNNING, 0.55, "计算 MACD / RSI / 布林带 / ATR…")

    if len(bars) < 30:
        message = f"仅有 {len(bars)} 根 K 线，指标窗口不足，技术面结论仅供参考"
        emit(state, AgentId.TECHNICAL, AgentStatus.COMPLETED, 0.60, message)
        return {"technical": None, "warnings": [message]}

    close = [bar.close for bar in bars]
    high = [bar.high for bar in bars]
    low = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]

    dif, dea, hist = macd(close)
    rsi_values = rsi(close)
    boll_up, boll_mid, boll_low = bollinger(close)
    atr_values = atr(high, low, close)
    ma20 = sma(close, 20)
    ma60 = sma(close, 60)

    recent_volume = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else 0.0
    volume_ratio = volumes[-1] / recent_volume if recent_volume > 0 else 1.0

    snapshot = TechnicalSnapshot(
        symbol=state["symbol"],
        last_date=bars[-1].date,
        last_close=close[-1],
        dif=float(dif[-1]),
        dea=float(dea[-1]),
        macd_hist=float(hist[-1]),
        rsi14=float(rsi_values[-1]) if rsi_values[-1] == rsi_values[-1] else 50.0,
        boll_upper=float(boll_up[-1]) if boll_up[-1] == boll_up[-1] else close[-1],
        boll_mid=float(boll_mid[-1]) if boll_mid[-1] == boll_mid[-1] else close[-1],
        boll_lower=float(boll_low[-1]) if boll_low[-1] == boll_low[-1] else close[-1],
        atr14=float(atr_values[-1]) if atr_values[-1] == atr_values[-1] else 0.0,
        ma20=float(ma20[-1]) if ma20[-1] == ma20[-1] else close[-1],
        ma60=float(ma60[-1]) if ma60[-1] == ma60[-1] else close[-1],
        volume_ratio=float(volume_ratio),
    )

    message = (
        f"MACD 柱 {snapshot.macd_hist:+.2f}，RSI {snapshot.rsi14:.1f}，"
        f"现价 {snapshot.last_close:.2f} 相对20日均线 "
        f"{'在上' if snapshot.last_close >= snapshot.ma20 else '在下'}"
    )
    emit(state, AgentId.TECHNICAL, AgentStatus.COMPLETED, 0.70, message)
    return {"technical": snapshot}
