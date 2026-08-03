import tempfile
import unittest

from src.config import Settings
from src.database import init_db
from src.repositories import Repository
from src.tickers import TickerService


class FakeQuoteClient:
    def __init__(self):
        self.calls: list[str] = []

    def fetch(self, ticker: str):
        self.calls.append(ticker)
        if ticker != "VALE3":
            raise RuntimeError("unexpected ticker")
        return {
            "ticker": "VALE3",
            "name": "Vale S.A.",
            "last_price": 58.91,
            "daily_change_percent": 1.23,
        }


class FakeSearchClient:
    def __init__(self, results=None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, limit: int = 25):
        self.calls.append((query, limit))
        if self.error:
            raise self.error
        return self.results


class TickerServiceSearchTest(unittest.TestCase):
    def test_exact_ticker_search_fetches_and_caches_missing_company(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)
            quote_client = FakeQuoteClient()
            service = TickerService(
                repository=repository,
                settings=settings,
                quote_client=quote_client,
                search_client=FakeSearchClient(),
            )

            self.assertEqual(repository.list_companies("VALE3"), [])

            results = service.search("VALE3")

            self.assertEqual(quote_client.calls, ["VALE3"])
            self.assertEqual(results[0]["ticker"], "VALE3")
            self.assertEqual(results[0]["name"], "Vale S.A.")
            self.assertEqual(repository.list_companies("VALE3")[0]["ticker"], "VALE3")

    def test_company_name_search_enriches_local_catalog_from_external_search(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)
            search_client = FakeSearchClient(
                [
                    {
                        "ticker": "SUZB3",
                        "name": "Suzano S.A.",
                        "asset_type": "stock",
                        "logo": None,
                    }
                ]
            )
            service = TickerService(
                repository=repository,
                settings=settings,
                quote_client=FakeQuoteClient(),
                search_client=search_client,
            )

            results = service.search("Suzano")

            self.assertEqual(search_client.calls, [("Suzano", 50)])
            self.assertEqual(results[0]["ticker"], "SUZB3")
            self.assertEqual(results[0]["name"], "Suzano S.A.")
            self.assertEqual(repository.list_companies("SUZB3")[0]["ticker"], "SUZB3")

    def test_search_returns_local_results_when_external_search_fails(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)
            service = TickerService(
                repository=repository,
                settings=settings,
                quote_client=FakeQuoteClient(),
                search_client=FakeSearchClient(error=RuntimeError("upstream failed")),
            )

            results = service.search("PETR")

            self.assertTrue(any(result["ticker"] == "PETR4" for result in results))


if __name__ == "__main__":
    unittest.main()
