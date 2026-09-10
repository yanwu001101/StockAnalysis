from datetime import datetime
from typing import Optional

import requests

from qmt_data_platform.models import Adjust, Bar, Period, Quote
from qmt_data_platform.providers.base import MarketDataProvider


class AStockDataProvider(MarketDataProvider):
    """Direct public endpoints used by the a-stock-data project."""

    name = "astock"
    _periods = {
        Period.M1: "m1",
        Period.M5: "m5",
        Period.M15: "m15",
        Period.M30: "m30",
        Period.H1: "m60",
    }

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}
        )

    def health(self) -> dict[str, object]:
        try:
            quote = self.get_quotes(["000001"])[0]
            return {"provider": self.name, "ready": quote.price is not None, "source": "Tencent"}
        except Exception as exc:
            return {"provider": self.name, "ready": False, "error": str(exc)}

    def get_quotes(self, symbols: list[str]) -> list[Quote]:
        query = ",".join(self._prefix(symbol) for symbol in symbols)
        response = self.session.get("https://qt.gtimg.cn/q=" + query, timeout=15)
        response.raise_for_status()
        quotes = []
        text = self._decode_quote_response(response.content)
        for line in text.splitlines():
            if "=" not in line or '"' not in line:
                continue
            key, payload = line.split("=", 1)
            values = payload.strip().strip(";\"").split("~")
            if len(values) < 47:
                continue
            code = key.rsplit("_", 1)[-1].removeprefix("s_")
            quotes.append(
                Quote(
                    symbol=self._normalize(code),
                    name=self._value(values, 1),
                    timestamp=self._quote_time(values),
                    price=self._number(values, 3),
                    open=self._number(values, 5),
                    high=self._number(values, 33),
                    low=self._number(values, 34),
                    pre_close=self._number(values, 4),
                    change_pct=self._number(values, 32),
                    volume=self._number(values, 36),
                    amount=self._scaled_number(values, 37, 10_000),
                    turnover_pct=self._number(values, 38),
                    pe_ttm=self._number(values, 39),
                    pb=self._number(values, 46),
                    source=self.name,
                )
            )
        return quotes

    def get_bars(
        self,
        symbols: list[str],
        period: Period,
        start: Optional[datetime],
        end: Optional[datetime],
        adjust: Adjust,
    ) -> list[Bar]:
        if period == Period.D1:
            period_key = "day"
        elif period in self._periods:
            period_key = self._periods[period]
        else:
            raise ValueError(f"a-stock-data provider does not support {period.value}")
        adjust_key = {Adjust.NONE: "", Adjust.FRONT: "qfq", Adjust.BACK: "hfq"}[adjust]
        rows: list[Bar] = []
        for symbol in symbols:
            code = self._prefix(symbol)
            url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            parameters = {"param": f"{code},{period_key},,,320,{adjust_key}"}
            response = self.session.get(url, params=parameters, timeout=15)
            response.raise_for_status()
            payload = response.json().get("data", {}).get(code, {})
            records = (
                payload.get(period_key)
                or payload.get(f"qfq{period_key}")
                or payload.get(f"hfq{period_key}")
                or []
            )
            for record in records:
                if len(record) < 6:
                    continue
                text = str(record[0])
                pattern = "%Y-%m-%d %H:%M:%S" if " " in text else "%Y-%m-%d"
                timestamp = datetime.strptime(text, pattern)
                if (start and timestamp < start) or (end and timestamp > end):
                    continue
                rows.append(
                    Bar(
                        symbol=self._normalize(symbol),
                        period=period,
                        timestamp=timestamp,
                        open=float(record[1]),
                        close=float(record[2]),
                        high=float(record[3]),
                        low=float(record[4]),
                        volume=max(0, float(record[5])),
                        amount=0,
                        source=self.name,
                    )
                )
        return rows

    @staticmethod
    def _prefix(symbol: str) -> str:
        code = symbol.upper().replace(".SH", "").replace(".SZ", "")
        code = code.removeprefix("SH").removeprefix("SZ")
        return ("sh" if code.startswith(("5", "6", "9")) else "sz") + code

    @staticmethod
    def _normalize(symbol: str) -> str:
        code = symbol.lower().replace("sh", "").replace("sz", "")
        is_shanghai = symbol.lower().startswith("sh") or code.startswith(("5", "6", "9"))
        return f"{code}.{'SH' if is_shanghai else 'SZ'}"

    @staticmethod
    def _quote_time(values: list[str]) -> datetime:
        if len(values) > 30 and len(values[30]) >= 14:
            try:
                return datetime.strptime(values[30][:14], "%Y%m%d%H%M%S")
            except ValueError:
                pass
        return datetime.now()

    @staticmethod
    def _decode_quote_response(content: bytes) -> str:
        for encoding in ("gbk", "utf-8"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", "replace")

    @staticmethod
    def _value(values: list[str], index: int) -> Optional[str]:
        value = values[index].strip() if index < len(values) else ""
        return value or None

    @classmethod
    def _number(cls, values: list[str], index: int) -> Optional[float]:
        value = cls._value(values, index)
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _scaled_number(
        cls, values: list[str], index: int, multiplier: float
    ) -> Optional[float]:
        value = cls._number(values, index)
        return value * multiplier if value is not None else None
