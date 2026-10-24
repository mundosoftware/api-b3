from __future__ import annotations

import os
import sqlite3
import unittest
from pathlib import Path

from experiments.jev_post_forecast.evidence import EvidenceCollector, evidence_state
from experiments.jev_post_forecast.jev import TypeSafeJevClient
from experiments.jev_post_forecast.pipeline import KronosRunner
from experiments.jev_post_forecast.storage import DEFAULT_CACHE_DIR, JsonCache, PROJECT_ROOT


RUN = os.environ.get("RUN_JEV_KRONOS_INTEGRATION") == "1"


@unittest.skipUnless(RUN, "set RUN_JEV_KRONOS_INTEGRATION=1")
class IntegrationSmokeTests(unittest.TestCase):
    def test_cached_petr4_kronos_inference(self) -> None:
        database = PROJECT_ROOT / "database" / "local-ai.db"
        if not database.exists():
            self.skipTest("database/local-ai.db is not available")
        connection = sqlite3.connect(database)
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT timestamp, open, high, low, close, volume, amount FROM candles WHERE ticker='PETR4' AND interval='1d' ORDER BY timestamp DESC LIMIT 120"
        ).fetchall()
        connection.close()
        candles = [dict(row) for row in reversed(rows)]
        if len(candles) < 90:
            self.skipTest("not enough cached PETR4 candles")
        forecast, _ = KronosRunner(PROJECT_ROOT, seed=17).forecast(candles, 2)
        self.assertEqual(len(forecast), 2)

    def test_yahoo_and_cvm_retrieval(self) -> None:
        collector = EvidenceCollector(JsonCache(DEFAULT_CACHE_DIR / "integration", refresh=True))
        self.assertGreater(len(collector.candles("PETR4")), 90)
        self.assertTrue(collector.cvm_records("PETR4", [2025]))

    @unittest.skipUnless(os.environ.get("TYPESAFE_API_KEY"), "TYPESAFE_API_KEY is required")
    def test_one_live_jev_request(self) -> None:
        client = TypeSafeJevClient()
        from experiments.jev_post_forecast.jev import STAGE1_QUESTION_SPECS

        state = evidence_state(
            [{"source": "fixture", "published_at": "2026-01-01", "title": "Routine notice", "content": "Routine administrative notice.", "content_mode": "metadata"}],
            "PETR4",
            "2026-01-02T00:00:00+00:00",
            "live",
        )
        response = client.evaluate(state, STAGE1_QUESTION_SPECS)
        self.assertIn("answers", response)


if __name__ == "__main__":
    unittest.main()
