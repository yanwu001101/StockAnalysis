"""Market data adapter — the only module in the code base that imports AkShare.

Reuse notes (ported from the sibling StockAnalysis data-service):
  * AkShare is synchronous, so every call is pushed to a worker thread with
    ``asyncio.to_thread`` to keep FastAPI's event loop free,
  * ``stock_zh_a_hist`` returns volumes in **手**; the domain wants shares, so
    the adapter multiplies by 100. Without this a stock fetched from AkShare
    next to one fetched from another source shows a 100x volume jump,
  * adjustment is ``qfq`` (前复权) — the backtest must never mix two price
    bases, and unadjusted bars silently inject look-ahead around ex-rights,
  * every call is retried with exponential backoff, and every column lookup is
    done by substring so a renamed column degrades to "unknown" instead of
    raising or, worse, silently mapping the wrong field.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time
from typing import Any, Sequence

from app.config import Settings, get_settings
from app.domain.errors import UpstreamDataError
from app.domain.models import (
    Bar,
    FundamentalSnapshot,
    MarketOverview,
    NewsItem,
)
from app.domain.ports import CachePort, MarketDataPort

log = logging.getLogger(__name__)

# ---------------------------------------------------------------- AkShare ops

_KLINE_PERIODS = {"daily", "weekly", "monthly"}


def normalize_symbol(symbol: str) -> str:
    """Accept 600519, sh600519, 600519.SH, sz000001 -> 6 digits."""
    raw = str(symbol).strip()
    for suffix in (".SH", ".SZ", ".BJ", ".sh", ".sz", ".bj"):
        if raw.endswith(suffix):
            raw = raw[: -len(suffix)]
            break
    if len(raw) == 8 and raw[:2].isalpha() and raw[2:].isdigit():
        raw = raw[2:]
    if not raw.isdigit():
        raise ValueError(f"unrecognised symbol: {symbol!r}")
    return raw.zfill(6)


def _parse_date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none", "nat"):
        return None
    for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return dt.datetime.strptime(text[: len(pattern) + 2], pattern).date()
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _to_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _pick_column(columns: Sequence[str], *needles: str) -> str | None:
    """First column whose name contains every needle. Robust to renames."""
    for column in columns:
        text = str(column)
        if all(needle in text for needle in needles):
            return column
    return None


def _pick_percent(row: Any, columns: Sequence[str], *needles: str) -> float | None:
    """Read a percentage column; akshare sometimes stores '15.2%' or '15.2'."""
    column = _pick_column(columns, *needles)
    if column is None:
        return None
    raw = row.get(column) if hasattr(row, "get") else None
    if raw is None:
        return None
    number = _to_float(raw)
    if number is None:
        text = str(raw).strip().rstrip("%")
        number = _to_float(text)
    return number


async def _ak_call(settings: Settings, function_name: str, **kwargs: Any):
    """Call an AkShare function in a worker thread, with backoff retry.

    Returns ``None`` when every attempt fails. AkShare's public surface is not
    stable, so a missing/renamed entry point is a normal outcome, not a bug.
    """
    last_error: Exception | None = None
    for attempt in range(max(settings.data_max_retries, 1)):
        try:
            import akshare as ak  # imported lazily: heavy and optional

            function = getattr(ak, function_name, None)
            if function is None:
                log.debug("akshare has no %s", function_name)
                return None
            return await asyncio.to_thread(function, **kwargs)
        except Exception as exc:  # noqa: BLE001 — akshare raises anything
            last_error = exc
            wait = min(
                settings.data_retry_base_wait_s * (2**attempt),
                settings.data_retry_max_wait_s,
            )
            log.warning(
                "akshare.%s attempt %d failed: %s (retrying in %.1fs)",
                function_name,
                attempt + 1,
                exc,
                wait,
            )
            if attempt + 1 < settings.data_max_retries:
                await asyncio.sleep(wait)
    log.warning("akshare.%s gave up after %d attempts", function_name, settings.data_max_retries)
    if last_error is not None:
        log.debug("akshare.%s last error: %s", function_name, last_error)
    return None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class AkShareMarketDataAdapter:
    """Implements ``MarketDataPort`` on top of AkShare."""

    name = "akshare"

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    # ------------------------------------------------------------ interface

    def fetch_daily_bars(self, symbol: str, lookback_days: int) -> list[Bar]:
        code = normalize_symbol(symbol)
        return self._run(self._fetch_klines(code, lookback_days, period="daily"))

    def fetch_benchmark_bars(self, symbol: str, lookback_days: int) -> list[Bar]:
        code = normalize_symbol(symbol)
        return self._run(self._fetch_index_klines(code, lookback_days))

    def fetch_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        code = normalize_symbol(symbol)
        return self._run(self._fetch_fundamentals(code))

    def fetch_news(self, symbol: str, limit: int) -> list[NewsItem]:
        code = normalize_symbol(symbol)
        return self._run(self._fetch_news(code, limit))

    def fetch_market_overview(self, benchmark_symbol: str) -> MarketOverview:
        code = normalize_symbol(benchmark_symbol)
        return self._run(_fetch_market_overview(code, self._settings))

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _run(coroutine: Any) -> Any:
        """Run an adapter coroutine from sync domain code.

        The graph is executed inside a worker thread by the orchestrator, so
        a fresh event loop is available here. Never call this from the request
        handler's own loop.
        """
        return asyncio.run(coroutine)

    async def _fetch_klines(self, code: str, lookback_days: int, period: str) -> list[Bar]:
        end = dt.date.today()
        multiplier = {"daily": 1.6, "weekly": 10.0, "monthly": 40.0}.get(period, 1.6)
        start = end - dt.timedelta(days=max(int(lookback_days * multiplier), 60))

        frame = await _ak_call(
            self._settings,
            "stock_zh_a_hist",
            symbol=code,
            period=period,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust="qfq",
        )
        if frame is None:
            # Fallback: eastmoney's own endpoint via akshare's daily-index helper
            frame = await _ak_call(
                self._settings,
                "stock_zh_index_daily",
                symbol=(f"sh{code}" if code[0] in "69" else f"sz{code}"),
            )
        return self._bars_from_frame(frame)

    async def _fetch_index_klines(self, code: str, lookback_days: int) -> list[Bar]:
        end = dt.date.today()
        start = end - dt.timedelta(days=max(int(lookback_days * 1.6), 60))
        frame = await _ak_call(
            self._settings,
            "index_zh_a_hist",
            symbol=code,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if frame is None:
            frame = await _ak_call(
                self._settings,
                "stock_zh_index_daily",
                symbol=(f"sh{code}" if code[0] in "69" else f"sz{code}"),
            )
        return self._bars_from_frame(frame)

    @staticmethod
    def _bars_from_frame(frame: Any) -> list[Bar]:
        if frame is None:
            return []
        try:
            rows = list(frame.to_dict(orient="records"))
        except Exception:  # noqa: BLE001 — shape varies by akshare version
            return []
        if not rows:
            return []
        columns = list(frame.columns)

        def pick(*needles: str) -> str | None:
            return _pick_column(columns, *needles)

        col_date = pick("日期") or pick("date", "时间") or pick("交易日期")
        col_open = pick("开盘") or pick("open")
        col_close = pick("收盘") or pick("close")
        col_high = pick("最高") or pick("high")
        col_low = pick("最低") or pick("low")
        col_volume = pick("成交量") or pick("volume")
        col_amount = pick("成交额") or pick("amount")
        if not col_date or not col_close:
            return []

        bars: list[Bar] = []
        for row in rows:
            day = _parse_date(row.get(col_date))
            close = _to_float(row.get(col_close))
            if day is None or close is None or close <= 0:
                continue
            open_price = _to_float(row.get(col_open)) if col_open else None
            high = _to_float(row.get(col_high)) if col_high else None
            low = _to_float(row.get(col_low)) if col_low else None
            volume = _to_float(row.get(col_volume)) if col_volume else None
            amount = _to_float(row.get(col_amount)) if col_amount else None
            bars.append(
                Bar(
                    date=day,
                    open=open_price if open_price and open_price > 0 else close,
                    high=max(high or close, close),
                    low=min(low or close, close),
                    close=close,
                    # 手 -> 股，与其余数据源统一口径
                    volume=(volume or 0.0) * 100.0,
                    amount=amount or 0.0,
                )
            )
        bars.sort(key=lambda bar: bar.date)
        return bars

    async def _fetch_fundamentals(self, code: str) -> FundamentalSnapshot:
        snapshot = FundamentalSnapshot(symbol=code, source="akshare")

        # 1) per-symbol indicator history: ROE / debt ratio / growth
        year = dt.date.today().year - 5
        frame = await _ak_call(
            self._settings,
            "stock_financial_analysis_indicator",
            symbol=code,
            start_year=str(year),
        )
        if frame is not None:
            try:
                rows = list(frame.to_dict(orient="records"))
                columns = list(frame.columns)
                if rows:
                    latest = rows[-1]
                    report_date = None
                    for candidate in (_pick_column(columns, "日期"), _pick_column(columns, "报告期")):
                        if candidate:
                            report_date = _parse_date(latest.get(candidate))
                            if report_date:
                                break
                    snapshot = snapshot.model_copy(
                        update={
                            "roe": _pick_percent(latest, columns, "净资产收益率"),
                            "debt_ratio": _pick_percent(latest, columns, "资产负债率"),
                            "revenue_yoy": _pick_percent(
                                latest, columns, "主营业务收入", "增长率"
                            )
                            or _pick_percent(latest, columns, "营业收入", "增长率"),
                            "net_profit_yoy": _pick_percent(latest, columns, "净利润", "增长率"),
                            "report_date": report_date,
                            "source": "akshare:stock_financial_analysis_indicator",
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("fundamental parse failed for %s: %s", code, exc)

        # 2) valuation: PE / PB / market cap
        valuation = await _ak_call(
            self._settings, "stock_a_indicator_lg", symbol=code
        )
        if valuation is not None:
            try:
                rows = list(valuation.to_dict(orient="records"))
                columns = list(valuation.columns)
                if rows:
                    latest = rows[-1]
                    market_cap = None
                    for needle in ("总市值", "总市值(元)"):
                        column = _pick_column(columns, needle)
                        if column:
                            market_cap = _to_float(latest.get(column))
                            if market_cap is not None:
                                market_cap /= 1e8  # -> 亿元
                            break
                    snapshot = snapshot.model_copy(
                        update={
                            "pe": _to_float(
                                latest.get(_pick_column(columns, "市盈率") or "")
                            )
                            if _pick_column(columns, "市盈率")
                            else None,
                            "pb": _to_float(latest.get(_pick_column(columns, "市净率") or ""))
                            if _pick_column(columns, "市净率")
                            else None,
                            "market_cap_yi": market_cap,
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning("valuation parse failed for %s: %s", code, exc)

        # 3) identity: name / industry
        info = await _ak_call(self._settings, "stock_individual_info_em", symbol=code)
        if info is not None:
            try:
                columns = list(info.columns)
                values: dict[str, Any] = {}
                for row in info.to_dict(orient="records"):
                    key_column = _pick_column(columns, "item") or columns[0]
                    value_column = _pick_column(columns, "value") or columns[-1]
                    key = str(row.get(key_column))
                    values[key] = row.get(value_column)
                industry = next(
                    (str(v) for k, v in values.items() if "行业" in k and v is not None), ""
                )
                name = next(
                    (str(v) for k, v in values.items() if "简称" in k and v is not None), ""
                )
                market_cap = next(
                    (
                        _to_float(v)
                        for k, v in values.items()
                        if "总市值" in k and _to_float(v) is not None
                    ),
                    None,
                )
                snapshot = snapshot.model_copy(
                    update={
                        "name": name or snapshot.name,
                        "industry": industry or snapshot.industry,
                        "market_cap_yi": (
                            market_cap / 1e8
                            if market_cap is not None
                            else snapshot.market_cap_yi
                        ),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("identity parse failed for %s: %s", code, exc)

        return snapshot

    async def _fetch_news(self, code: str, limit: int) -> list[NewsItem]:
        items: list[NewsItem] = []
        for function_name in ("stock_individual_news_em", "stock_news_em"):
            frame = await _ak_call(self._settings, function_name, symbol=code)
            if frame is None:
                continue
            try:
                columns = list(frame.columns)
                col_title = _pick_column(columns, "标题") or _pick_column(columns, "title")
                if not col_title:
                    continue
                col_time = _pick_column(columns, "时间") or _pick_column(columns, "publish")
                col_source = _pick_column(columns, "来源") or _pick_column(columns, "source")
                col_url = _pick_column(columns, "链接") or _pick_column(columns, "url")
                for row in frame.to_dict(orient="records")[:limit]:
                    items.append(
                        NewsItem(
                            title=str(row.get(col_title) or "").strip(),
                            publish_time=_parse_datetime(row.get(col_time)) if col_time else None,
                            source=str(row.get(col_source) or "") if col_source else "",
                            url=str(row.get(col_url) or "") if col_url else "",
                        )
                    )
                if items:
                    break
            except Exception as exc:  # noqa: BLE001
                log.warning("news parse failed for %s via %s: %s", code, function_name, exc)
        return [item for item in items if item.title]


def _parse_datetime(value: Any) -> dt.datetime | None:
    day = _parse_date(value)
    if day is None:
        return None
    return dt.datetime.combine(day, dt.time())


async def _fetch_market_overview(code: str, settings: Settings) -> MarketOverview:
    """Benchmark snapshot + whole-market breadth.

    Benchmark comes from the same index feed the alpha/beta math uses.
    Breadth counts the whole-market spot table (one call, upstream-cached);
    when it is unavailable the fields stay None — never a fabricated 0.
    """
    overview = MarketOverview(
        benchmark_symbol=code,
        benchmark_name="沪深300" if code == "000300" else f"指数 {code}",
    )

    bars = await _ak_call(
        settings,
        "index_zh_a_hist",
        symbol=code,
        period="daily",
        start_date=(dt.date.today() - dt.timedelta(days=10)).strftime("%Y%m%d"),
        end_date=dt.date.today().strftime("%Y%m%d"),
    )
    if bars is not None and len(bars) > 0:
        try:
            rows = list(bars.to_dict(orient="records"))
            columns = list(bars.columns)
            col_date = _pick_column(columns, "日期") or _pick_column(columns, "date")
            col_close = _pick_column(columns, "收盘") or _pick_column(columns, "close")
            if col_date and col_close:
                closes: list[tuple[dt.date, float]] = []
                for row in rows:
                    day = _parse_date(row.get(col_date))
                    value = _to_float(row.get(col_close))
                    if day is not None and value is not None and value > 0:
                        closes.append((day, value))
                closes.sort(key=lambda item: item[0])
                if closes:
                    last_day, last_close = closes[-1]
                    change = None
                    if len(closes) >= 2:
                        prev_close = closes[-2][1]
                        if prev_close > 0:
                            change = last_close / prev_close - 1.0
                    overview = overview.model_copy(
                        update={
                            "last_close": last_close,
                            "change_pct": change,
                            "as_of": last_day.isoformat(),
                        }
                    )
        except Exception as exc:  # noqa: BLE001
            log.warning("benchmark overview parse failed for %s: %s", code, exc)

    spot = await _ak_call(settings, "stock_zh_a_spot_em")
    if spot is not None:
        try:
            columns = list(spot.columns)
            col_pct = _pick_column(columns, "涨跌幅")
            if col_pct:
                advancing = declining = flat = 0
                for row in spot.to_dict(orient="records"):
                    value = _to_float(row.get(col_pct))
                    if value is None:
                        continue
                    if value > 0:
                        advancing += 1
                    elif value < 0:
                        declining += 1
                    else:
                        flat += 1
                overview = overview.model_copy(
                    update={
                        "advancing": advancing,
                        "declining": declining,
                        "flat": flat,
                        "breadth_available": True,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("breadth parse failed: %s", exc)

    return overview


# ---------------------------------------------------------------------------
# Cached decorator — second adapter in the chain, still behind the port
# ---------------------------------------------------------------------------


class CachingMarketDataAdapter:
    """Transparent cache in front of any ``MarketDataPort``."""

    def __init__(self, inner: MarketDataPort, cache: CachePort, ttl_seconds: int) -> None:
        self._inner = inner
        self._cache = cache
        self._ttl = ttl_seconds

    def fetch_daily_bars(self, symbol: str, lookback_days: int) -> list[Bar]:
        return self._cached(f"kline:{symbol}:{lookback_days}", lambda: self._inner.fetch_daily_bars(symbol, lookback_days))

    def fetch_benchmark_bars(self, symbol: str, lookback_days: int) -> list[Bar]:
        return self._cached(
            f"index:{symbol}:{lookback_days}",
            lambda: self._inner.fetch_benchmark_bars(symbol, lookback_days),
        )

    def fetch_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        return self._cached(f"fund:{symbol}", lambda: self._inner.fetch_fundamentals(symbol))

    def fetch_news(self, symbol: str, limit: int) -> list[NewsItem]:
        return self._cached(f"news:{symbol}:{limit}", lambda: self._inner.fetch_news(symbol, limit))

    def fetch_market_overview(self, benchmark_symbol: str) -> MarketOverview:
        return self._cached(
            f"overview:{benchmark_symbol}",
            lambda: self._inner.fetch_market_overview(benchmark_symbol),
        )

    def _cached(self, key: str, loader):  # type: ignore[no-untyped-def]
        raw = self._cache.get(key)
        if raw:
            return _decode(raw)
        value = loader()
        self._cache.set(key, _encode(value), self._ttl)
        return value


# ---------------------------------------------------------------------------
# Synthetic adapter — keeps the graph runnable offline and unit-testable
# ---------------------------------------------------------------------------


class SyntheticMarketDataAdapter:
    """Deterministic geometric-random-walk market. No network, no akshare."""

    name = "synthetic"

    def __init__(self, seed: int = 20260101, base_price: float = 100.0) -> None:
        import random

        self._random = random.Random(seed)
        self._base_price = base_price

    def _walk(self, days: int) -> list[Bar]:
        price = self._base_price
        bars: list[Bar] = []
        today = dt.date.today()
        for offset in range(days, 0, -1):
            day = today - dt.timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            drift = self._random.uniform(-0.03, 0.033)
            open_price = price
            close_price = price * (1.0 + drift)
            high_price = max(open_price, close_price) * (1.0 + abs(self._random.gauss(0, 0.006)))
            low_price = min(open_price, close_price) * (1.0 - abs(self._random.gauss(0, 0.006)))
            bars.append(
                Bar(
                    date=day,
                    open=round(open_price, 2),
                    high=round(high_price, 2),
                    low=round(low_price, 2),
                    close=round(close_price, 2),
                    volume=float(self._random.randint(2_000, 80_000) * 100),
                    amount=float(self._random.randint(2_000, 80_000) * 100 * max(close_price, 1)),
                )
            )
            price = close_price
        return bars

    def fetch_daily_bars(self, symbol: str, lookback_days: int) -> list[Bar]:
        return self._walk(lookback_days)[-lookback_days:]

    def fetch_benchmark_bars(self, symbol: str, lookback_days: int) -> list[Bar]:
        return self._walk(lookback_days)[-lookback_days:]

    def fetch_market_overview(self, benchmark_symbol: str) -> MarketOverview:
        bars = self._walk(10)
        if len(bars) < 2:
            return MarketOverview(
                benchmark_symbol=benchmark_symbol,
                benchmark_name="合成基准",
                breadth_available=False,
            )
        last, prev = bars[-1], bars[-2]
        change = last.close / prev.close - 1.0 if prev.close > 0 else None
        return MarketOverview(
            benchmark_symbol=benchmark_symbol,
            benchmark_name="合成基准",
            last_close=last.close,
            change_pct=change,
            as_of=last.date.isoformat(),
            advancing=None,
            declining=None,
            flat=None,
            breadth_available=False,
        )

    def fetch_fundamentals(self, symbol: str) -> FundamentalSnapshot:
        return FundamentalSnapshot(
            symbol=symbol,
            name=f"Synthetic {symbol}",
            pe=18.5,
            pb=2.3,
            roe=12.7,
            debt_ratio=41.2,
            revenue_yoy=9.4,
            net_profit_yoy=6.1,
            market_cap_yi=3210.0,
            industry="合成数据",
            report_date=dt.date.today(),
            source="synthetic",
        )

    def fetch_news(self, symbol: str, limit: int) -> list[NewsItem]:
        return []


# ---------------------------------------------------------------------------
# JSON codecs for the cache decorator
# ---------------------------------------------------------------------------


def _bar_to_dict(bar: Bar) -> dict[str, Any]:
    return {
        "date": bar.date.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "amount": bar.amount,
    }


def _encode(value: Any) -> str:
    """Serialise the three cached shapes: bars, snapshots, news, overview."""
    import json

    if isinstance(value, Bar):
        return json.dumps({"__kind__": "bar", **_bar_to_dict(value)})
    if isinstance(value, FundamentalSnapshot):
        return json.dumps({"__kind__": "fund", **value.model_dump(mode="json")})
    if isinstance(value, MarketOverview):
        # 缓存用字段名（非 alias）序列化，回读时 model_validate 按字段名校验
        return json.dumps({"__kind__": "overview", **value.model_dump(mode="json")})
    if isinstance(value, NewsItem):
        return json.dumps({"__kind__": "news", **value.model_dump(mode="json")})
    if isinstance(value, list):
        items = list(value)
        if items and isinstance(items[0], Bar):
            return json.dumps(
                {"__kind__": "bars", "items": [_bar_to_dict(bar) for bar in items]}
            )
        return json.dumps(
            {"__kind__": "list", "items": [json.loads(_encode(item)) for item in items]}
        )
    return json.dumps({"__kind__": "raw", "value": value})


def _decode(raw: str) -> Any:
    import json

    payload = json.loads(raw)
    kind = payload.get("__kind__")

    if kind == "bar":
        return Bar(
            date=dt.date.fromisoformat(payload["date"]),
            open=float(payload["open"]),
            high=float(payload["high"]),
            low=float(payload["low"]),
            close=float(payload["close"]),
            volume=float(payload["volume"]),
            amount=float(payload["amount"]),
        )
    if kind == "bars":
        return [
            Bar(
                date=dt.date.fromisoformat(item["date"]),
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]),
                amount=float(item["amount"]),
            )
            for item in payload["items"]
        ]
    if kind == "fund":
        return FundamentalSnapshot(**{k: v for k, v in payload.items() if k != "__kind__"})
    if kind == "overview":
        return MarketOverview.model_validate(
            {k: v for k, v in payload.items() if k != "__kind__"}
        )
    if kind == "news":
        return NewsItem(**{k: v for k, v in payload.items() if k != "__kind__"})
    if kind == "list":
        return [_decode_item(item) for item in payload["items"]]
    return payload.get("value")


def _decode_item(payload: dict[str, Any]) -> Any:
    import json

    return _decode(json.dumps(payload))


def raise_unless_usable(bars: Sequence[Bar], min_bars: int, stale_after_days: int) -> None:
    """Domain guard on raw bars: empty / suspended / delisted / too short."""
    if not bars:
        raise UpstreamDataError("no bars returned by any data source")
    last = max(bar.date for bar in bars)
    today = dt.date.today()
    if (today - last).days > stale_after_days:
        raise UpstreamDataError(
            f"last bar is {last.isoformat()}, { (today - last).days } days old — "
            "the security looks suspended or delisted"
        )
    if len(bars) < min_bars:
        raise UpstreamDataError(f"only {len(bars)} bars available, need {min_bars}")
