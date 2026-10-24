from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from experiments.jev_post_forecast.evidence import enforce_evidence_limits, select_historical_cases


class EvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        start = datetime(2025, 1, 1, 13, tzinfo=UTC)
        self.candles = [
            {
                "timestamp": (start + timedelta(days=index)).isoformat(),
                "open": 10 + index / 100,
                "high": 11 + index / 100,
                "low": 9 + index / 100,
                "close": 10 + index / 100,
                "volume": 1,
            }
            for index in range(140)
        ]

    def test_cutoff_is_first_candle_on_day_after_delivery_and_future_is_excluded(self) -> None:
        disclosure = {
            "Data_Entrega": self.candles[100]["timestamp"],
            "Categoria": "Fato Relevante",
            "Assunto": "Material event",
            "Protocolo_Entrega": "1",
        }
        selected = select_historical_cases(self.candles, [disclosure], horizon=10, count=1)
        self.assertEqual(len(selected), 1)
        case = selected[0]
        self.assertEqual(case["cutoff_index"], 101)
        self.assertEqual(case["context"][-1]["timestamp"], self.candles[101]["timestamp"])
        self.assertEqual(case["realized"][0]["timestamp"], self.candles[102]["timestamp"])
        self.assertEqual(case["realized"][-1]["timestamp"], self.candles[111]["timestamp"])

    def test_disclosure_without_ten_future_candles_is_rejected(self) -> None:
        disclosure = {"Data_Entrega": self.candles[135]["timestamp"], "Categoria": "Comunicado ao Mercado"}
        self.assertEqual(select_historical_cases(self.candles, [disclosure], horizon=10), [])

    def test_evidence_is_deduplicated_and_character_limited(self) -> None:
        documents = [
            {"title": "Same", "url": "https://a", "content": "x" * 20_000},
            {"title": "Duplicate", "url": "https://a", "content": "ignored"},
            {"title": "Second", "url": "https://b", "content": "y" * 20_000},
        ]
        limited = enforce_evidence_limits(documents)
        self.assertEqual(len(limited), 2)
        self.assertLessEqual(sum(row["character_count"] for row in limited), 24_000)
        self.assertTrue(all(row["character_count"] <= 8_000 for row in limited))


if __name__ == "__main__":
    unittest.main()
