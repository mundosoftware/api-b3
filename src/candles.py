from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from src.config import Settings, get_settings
from src.database import normalize_ticker, parse_iso
from src.repositories import Repository


SUPPORTED_CANDLE_INTERVALS = {"1d", "1wk", "1mo"}
SUPPORTED_CANDLE_RANGES = {"6mo", "1y", "2y", "5y", "10y", "max"}


class CandleLookupError(RuntimeError):
    pass


class YahooB3CandleClient:
    base_url = "https://query1.finance.yahoo.com/v8/finance/chart"

    def fetch(
        self,
        ticker: str,
        interval: str = "1d",
        range_name: str = "2y",
    ) -> list[dict[str, Any]]:
        normalized = normalize_ticker(ticker)
        if interval not in SUPPORTED_CANDLE_INTERVALS:
            raise ValueError("unsupported candle interval")
        if range_name not in SUPPORTED_CANDLE_RANGES:
            raise ValueError("unsupported candle range")

        response = requests.get(
            f"{self.base_url}/{normalized}.SA",
            params={
                "interval": interval,
                "range": range_name,
                "includePrePost": "false",
                "events": "div,splits",
            },
            headers={"User-Agent": "b3-watch-api/1.0"},
            timeout=12,
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not result:
            error = payload.get("chart", {}).get("error") or {}
            message = error.get("description") or f"No candle result for {normalized}"
            raise CandleLookupError(message)

        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []

        candles: list[dict[str, Any]] = []
        for index, epoch in enumerate(timestamps):
            try:
                open_price = opens[index]
                high_price = highs[index]
                low_price = lows[index]
                close_price = closes[index]
            except IndexError:
                continue
            if None in (open_price, high_price, low_price, close_price):
                continue

            volume = volumes[index] if index < len(volumes) else None
            average_price = (
                float(open_price) + float(high_price) + float(low_price) + float(close_price)
            ) / 4
            amount = float(volume or 0) * average_price
            timestamp = datetime.fromtimestamp(int(epoch), tz=UTC).replace(microsecond=0)
            candles.append(
                {
                    "ticker": normalized,
                    "interval": interval,
                    "timestamp": timestamp.isoformat(),
                    "open": round(float(open_price), 6),
                    "high": round(float(high_price), 6),
                    "low": round(float(low_price), 6),
                    "close": round(float(close_price), 6),
                    "volume": float(volume or 0),
                    "amount": round(amount, 6),
                    "source": "yahoo",
                }
            )

        if not candles:
            raise CandleLookupError(f"No usable candles for {normalized}")
        return candles


class CandleService:
    def __init__(
        self,
        repository: Repository | None = None,
        settings: Settings | None = None,
        client: YahooB3CandleClient | None = None,
    ):
        self.settings = settings or get_settings()
        self.repository = repository or Repository(self.settings)
        self.client = client or YahooB3CandleClient()

    def history(
        self,
        ticker: str,
        interval: str = "1d",
        range_name: str = "2y",
        limit: int = 512,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        normalized = normalize_ticker(ticker)
        if interval not in SUPPORTED_CANDLE_INTERVALS:
            raise ValueError("unsupported candle interval")
        if range_name not in SUPPORTED_CANDLE_RANGES:
            raise ValueError("unsupported candle range")

        limit = max(30, min(limit, 5000))
        cached = self.repository.list_candles(normalized, interval, limit=limit)
        if not force_refresh and len(cached) >= min(limit, 120) and self._cache_is_fresh(cached):
            return cached

        try:
            candles = self.client.fetch(normalized, interval=interval, range_name=range_name)
        except Exception as exc:
            if cached:
                return cached
            raise CandleLookupError(str(exc)) from exc

        self.repository.upsert_candles(normalized, interval, candles, source="yahoo")
        return self.repository.list_candles(normalized, interval, limit=limit)

    def _cache_is_fresh(self, candles: list[dict[str, Any]]) -> bool:
        created_values = [parse_iso(candle.get("created_at")) for candle in candles]
        newest = max((value for value in created_values if value is not None), default=None)
        if newest is None:
            return False
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=UTC)
        return datetime.now(UTC) - newest <= timedelta(seconds=self.settings.candle_cache_ttl_seconds)
