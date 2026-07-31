from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from src.config import Settings, get_settings
from src.database import normalize_ticker, parse_iso
from src.repositories import Repository


class QuoteLookupError(RuntimeError):
    pass


class YahooB3QuoteClient:
    base_url = "https://query1.finance.yahoo.com/v8/finance/chart"

    def fetch(self, ticker: str) -> dict[str, Any]:
        normalized = normalize_ticker(ticker)
        url = f"{self.base_url}/{normalized}.SA"
        response = requests.get(
            url,
            params={"interval": "1m", "range": "1d"},
            headers={"User-Agent": "b3-watch-api/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not result:
            raise QuoteLookupError(f"No quote result for {normalized}")

        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        if price is None:
            quote_values = (
                result.get("indicators", {})
                .get("quote", [{}])[0]
                .get("close", [])
            )
            price = next((value for value in reversed(quote_values) if value is not None), None)
        if price is None:
            raise QuoteLookupError(f"No price value for {normalized}")

        previous_close = meta.get("chartPreviousClose") or meta.get("previousClose")
        daily_change_percent = None
        if previous_close:
            daily_change_percent = ((float(price) - float(previous_close)) / float(previous_close)) * 100

        return {
            "ticker": normalized,
            "name": meta.get("shortName") or meta.get("symbol") or normalized,
            "last_price": round(float(price), 4),
            "daily_change_percent": round(daily_change_percent, 4)
            if daily_change_percent is not None
            else None,
        }


class TickerService:
    def __init__(
        self,
        repository: Repository | None = None,
        settings: Settings | None = None,
        quote_client: YahooB3QuoteClient | None = None,
    ):
        self.settings = settings or get_settings()
        self.repository = repository or Repository(self.settings)
        self.quote_client = quote_client or YahooB3QuoteClient()

    def search(self, query: str | None, limit: int = 50) -> list[dict[str, Any]]:
        return self.repository.list_companies(query=query, limit=limit)

    def quote(self, ticker: str, force_refresh: bool = False) -> dict[str, Any]:
        normalized = normalize_ticker(ticker)
        cached = self.repository.get_company(normalized)
        if cached and not force_refresh and self._cache_is_fresh(cached.get("updated_at")):
            return cached

        try:
            live_quote = self.quote_client.fetch(normalized)
        except Exception as exc:
            if cached and cached.get("last_price") is not None:
                return cached
            raise QuoteLookupError(str(exc)) from exc

        return self.repository.update_company_quote(
            ticker=normalized,
            last_price=live_quote["last_price"],
            daily_change_percent=live_quote.get("daily_change_percent"),
            name=live_quote.get("name"),
        )

    def _cache_is_fresh(self, updated_at: str | None) -> bool:
        parsed = parse_iso(updated_at)
        if not parsed:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return datetime.now(UTC) - parsed <= timedelta(seconds=self.settings.quote_cache_ttl_seconds)
