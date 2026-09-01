import tempfile
import unittest
from datetime import UTC, datetime, timedelta

from src.ai_analysis import DecisionSupportService
from src.application import create_app
from src.candles import CandleService
from src.config import Settings
from src.database import init_db
from src.repositories import Repository


class FakeCandleClient:
    def __init__(self, candles):
        self.candles = candles
        self.calls = []

    def fetch(self, ticker: str, interval: str = "1d", range_name: str = "2y"):
        self.calls.append((ticker, interval, range_name))
        return self.candles


class AIAnalysisTest(unittest.TestCase):
    def test_candle_service_fetches_stores_and_reuses_cached_history(self):
        candles = make_candles(140)
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                kronos_enabled=False,
            )
            init_db(settings)
            repository = Repository(settings)
            client = FakeCandleClient(candles)
            service = CandleService(repository=repository, settings=settings, client=client)

            first = service.history("PETR4", limit=120)
            second = service.history("PETR4", limit=120)

            self.assertEqual(len(first), 120)
            self.assertEqual(len(second), 120)
            self.assertEqual(client.calls, [("PETR4", "1d", "2y")])
            self.assertEqual(first[-1]["close"], candles[-1]["close"])

    def test_decision_support_builds_forecast_levels_and_chart_payload(self):
        candles = make_candles(180, drift=0.18)
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                kronos_enabled=False,
            )
            init_db(settings)
            repository = Repository(settings)
            candle_service = CandleService(
                repository=repository,
                settings=settings,
                client=FakeCandleClient(candles),
            )
            service = DecisionSupportService(
                repository=repository,
                settings=settings,
                candle_service=candle_service,
            )

            analysis = service.analysis("PETR4", horizon=10, force_refresh=True)

            self.assertEqual(analysis["ticker"], "PETR4")
            self.assertEqual(analysis["provider"], "statistical")
            self.assertEqual(len(analysis["forecast"]), 10)
            self.assertEqual(len(analysis["historical"]), 80)
            self.assertGreater(analysis["target_price"], 0)
            self.assertGreaterEqual(analysis["confidence"], 0.35)
            self.assertIn(analysis["outlook"], {"bullish", "neutral", "bearish"})
            self.assertTrue(analysis["drivers"])
            self.assertTrue(analysis["warnings"])

    def test_api_registers_candle_and_ai_analysis_routes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                kronos_enabled=False,
            )
            init_db(settings)
            app = create_app(settings)
            paths = {getattr(route, "path", "") for route in app.routes}

            self.assertIn("/companies/{ticker}/candles", paths)
            self.assertIn("/companies/{ticker}/ai-analysis", paths)


def make_candles(count: int, drift: float = 0.05) -> list[dict]:
    rows = []
    current = datetime(2025, 1, 2, 13, 0, tzinfo=UTC)
    close = 20.0
    while len(rows) < count:
        if current.weekday() < 5:
            open_price = close
            close = close + drift + ((len(rows) % 7) - 3) * 0.015
            high = max(open_price, close) + 0.24
            low = min(open_price, close) - 0.22
            volume = 1_000_000 + len(rows) * 1000
            rows.append(
                {
                    "ticker": "PETR4",
                    "interval": "1d",
                    "timestamp": current.isoformat(),
                    "open": round(open_price, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close, 4),
                    "volume": float(volume),
                    "amount": float(volume) * close,
                    "source": "test",
                }
            )
        current += timedelta(days=1)
    return rows


if __name__ == "__main__":
    unittest.main()
