from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from qmt_data_platform.models import Adjust, Bar, Period
from qmt_data_platform.providers.base import MarketDataProvider


class XtQuantMarketDataProvider(MarketDataProvider):
    name = "xtquant"

    _periods = {
        Period.TICK: "tick",
        Period.M1: "1m",
        Period.M5: "5m",
        Period.M15: "15m",
        Period.M30: "30m",
        Period.H1: "1h",
        Period.D1: "1d",
    }
    _adjusts = {Adjust.NONE: "none", Adjust.FRONT: "front", Adjust.BACK: "back"}

    def __init__(self, qmt_path: Optional[Path] = None) -> None:
        self.qmt_path = qmt_path
        try:
            from xtquant import xtdata
        except ImportError as exc:
            raise RuntimeError(
                "xtquant is not importable. Install XtQuant from your QMT distribution "
                "into this Python environment, or set QDP_PROVIDER=mock."
            ) from exc
        self.xtdata = xtdata

    def health(self) -> dict[str, object]:
        try:
            sectors = self.xtdata.get_sector_list()
            return {
                "provider": self.name,
                "ready": True,
                "qmt_path": str(self.qmt_path) if self.qmt_path else None,
                "sector_count": len(sectors),
            }
        except Exception as exc:  # QMT raises vendor-specific exceptions.
            return {"provider": self.name, "ready": False, "error": str(exc)}

    def get_bars(
        self,
        symbols: list[str],
        period: Period,
        start: Optional[datetime],
        end: Optional[datetime],
        adjust: Adjust,
    ) -> list[Bar]:
        start_time = start.strftime("%Y%m%d%H%M%S") if start else ""
        end_time = end.strftime("%Y%m%d%H%M%S") if end else ""
        xt_period = self._periods[period]

        for symbol in symbols:
            self.xtdata.download_history_data(
                symbol, period=xt_period, start_time=start_time, end_time=end_time
            )

        fields = ["time", "open", "high", "low", "close", "volume", "amount", "preClose"]
        payload = self.xtdata.get_market_data_ex(
            field_list=fields,
            stock_list=symbols,
            period=xt_period,
            start_time=start_time,
            end_time=end_time,
            count=-1,
            dividend_type=self._adjusts[adjust],
            fill_data=False,
        )
        return self._normalize(payload, period)

    def _normalize(self, payload: dict[str, Any], period: Period) -> list[Bar]:
        rows: list[Bar] = []
        for symbol, frame in payload.items():
            if frame is None or frame.empty:
                continue
            for index, record in frame.iterrows():
                raw_time = record.get("time", index)
                timestamp = self._timestamp(raw_time)
                rows.append(
                    Bar(
                        symbol=symbol,
                        period=period,
                        timestamp=timestamp,
                        open=float(record["open"]),
                        high=float(record["high"]),
                        low=float(record["low"]),
                        close=float(record["close"]),
                        volume=max(0.0, float(record.get("volume", 0))),
                        amount=max(0.0, float(record.get("amount", 0))),
                        pre_close=self._optional_float(record.get("preClose")),
                        source=self.name,
                    )
                )
        return rows

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            seconds = float(value) / 1000 if value > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(seconds)
        text = str(value)
        for pattern in ("%Y%m%d%H%M%S", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, pattern)
            except ValueError:
                pass
        raise ValueError(f"Unsupported XtQuant timestamp: {value!r}")

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
