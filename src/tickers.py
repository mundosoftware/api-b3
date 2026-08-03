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


class YahooB3SearchClient:
    base_url = "https://query2.finance.yahoo.com/v1/finance/search"

    def search(self, query: str, limit: int = 25) -> list[dict[str, Any]]:
        response = requests.get(
            self.base_url,
            params={
                "q": query,
                "quotesCount": max(1, min(limit, 50)),
                "newsCount": 0,
                "listsCount": 0,
            },
            headers={"User-Agent": "b3-watch-api/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        payload = response.json()

        results: list[dict[str, Any]] = []
        for item in payload.get("quotes", []):
            ticker = self._b3_ticker(item.get("symbol"))
            if not ticker:
                continue
            results.append(
                {
                    "ticker": ticker,
                    "name": item.get("longname")
                    or item.get("shortname")
                    or item.get("name")
                    or ticker,
                    "asset_type": self._asset_type(item),
                    "logo": None,
                    "last_price": None,
                    "daily_change_percent": None,
                    "updated_at": None,
                }
            )
        return results[:limit]

    def _b3_ticker(self, symbol: object) -> str | None:
        if not isinstance(symbol, str):
            return None
        symbol = symbol.upper().strip()
        if not symbol.endswith(".SA"):
            return None
        try:
            return normalize_ticker(symbol.removesuffix(".SA"))
        except ValueError:
            return None

    def _asset_type(self, item: dict[str, Any]) -> str:
        quote_type = str(item.get("quoteType") or "").lower()
        ticker = self._b3_ticker(item.get("symbol")) or ""
        if quote_type == "etf":
            return "etf"
        if ticker.endswith("11"):
            return "fii"
        if ticker.endswith("34") or ticker.endswith("35"):
            return "bdr"
        return "stock"


class TickerService:
    def __init__(
        self,
        repository: Repository | None = None,
        settings: Settings | None = None,
        quote_client: YahooB3QuoteClient | None = None,
        search_client: YahooB3SearchClient | None = None,
    ):
        self.settings = settings or get_settings()
        self.repository = repository or Repository(self.settings)
        self.quote_client = quote_client or YahooB3QuoteClient()
        self.search_client = search_client or YahooB3SearchClient()

    def search(self, query: str | None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 200))
        results = self.repository.list_companies(query=query, limit=limit)
        if not query:
            return results

        seen = {result["ticker"] for result in results}
        exact_ticker = self._exact_ticker_query(query)
        if exact_ticker and exact_ticker in seen:
            return results[:limit]
        if exact_ticker and len(results) < limit:
            try:
                quote = self.quote(exact_ticker)
            except QuoteLookupError:
                pass
            else:
                results.append(quote)
                return results[:limit]

        if len(results) >= limit:
            return results[:limit]

        try:
            discovered = self.search_client.search(query, limit=limit)
        except Exception:
            return results[:limit]

        for company in discovered:
            ticker = company["ticker"]
            if ticker in seen:
                continue
            persisted = self.repository.upsert_company(
                ticker=ticker,
                name=company.get("name"),
                asset_type=company.get("asset_type"),
                logo=company.get("logo"),
            )
            results.append(persisted)
            seen.add(ticker)
            if len(results) >= limit:
                break

        return results[:limit]

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

    def _exact_ticker_query(self, query: str) -> str | None:
        value = query.strip()
        if value.upper().endswith(".SA"):
            value = value[:-3]
        try:
            normalized = normalize_ticker(value)
        except ValueError:
            return None
        if len(normalized) < 4 or not any(char.isdigit() for char in normalized):
            return None
        return normalized

    def _cache_is_fresh(self, updated_at: str | None) -> bool:
        parsed = parse_iso(updated_at)
        if not parsed:
            return False
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return datetime.now(UTC) - parsed <= timedelta(seconds=self.settings.quote_cache_ttl_seconds)
