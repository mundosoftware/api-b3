from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from experiments.jev_post_forecast.evidence import EvidenceCollector
from experiments.jev_post_forecast.jev import STAGE1_QUESTION_SPECS, STAGE2_QUESTION_SPECS
from experiments.jev_post_forecast.pipeline import ExperimentRunner, _failure
from experiments.jev_post_forecast.storage import JsonCache, PROJECT_ROOT
from experiments.jev_post_forecast.tests.test_jev import answer_for_specs


class RecordingJevClient:
    def __init__(self):
        self.calls = []

    def evaluate(self, state, question_specs):
        self.calls.append((state, question_specs))
        raw = answer_for_specs(question_specs)
        if question_specs is STAGE1_QUESTION_SPECS:
            raw["answers"]["semantic_direction"].update(
                {"choice": "bullish", "probabilities": {"bullish": 0.6, "neutral": 0.15, "bearish": 0.15, "insufficient": 0.1}}
            )
            raw["answers"]["materiality"].update({"score": 2.0, "probabilities": {"0": 0.1, "1": 0.2, "2": 0.6, "3": 0.1}})
        else:
            raw["answers"]["preferred_variant"].update(
                {"choice": "rule_adjusted", "probabilities": {"kronos": 0.2, "semantic_scenario": 0.2, "rule_adjusted": 0.5, "insufficient": 0.1}}
            )
            raw["answers"]["combined_risk"].update({"score": 1.0, "probabilities": {"0": 0.2, "1": 0.7, "2": 0.1}})
        return raw


class FakeKronos:
    seed = 17

    def forecast(self, candles, horizon):
        last = float(candles[-1]["close"])
        start = datetime.fromisoformat(candles[-1]["timestamp"])
        return [
            {"timestamp": (start + timedelta(days=index + 1)).isoformat(), "open": last, "high": last * 1.06, "low": last * 0.95, "close": last * 1.02, "volume": 1}
            for index in range(horizon)
        ], 5.0


class PipelineTests(unittest.TestCase):
    def test_second_pass_gets_only_code_calculated_candidates(self) -> None:
        start = datetime(2025, 1, 1, 13, tzinfo=UTC)
        candles = [
            {"timestamp": (start + timedelta(days=index)).isoformat(), "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1}
            for index in range(100)
        ]
        client = RecordingJevClient()
        with tempfile.TemporaryDirectory() as directory:
            cache = JsonCache(Path(directory))
            runner = ExperimentRunner(
                project_root=PROJECT_ROOT,
                cache=cache,
                jev_client=client,
                evidence_collector=EvidenceCollector(cache),
                kronos_runner=FakeKronos(),
            )
            case = runner._evaluate_case(
                case_id="test",
                ticker="PETR4",
                kind="historical",
                evidence_label="CVM-only",
                cutoff=candles[-1]["timestamp"],
                candles=candles,
                realized=[],
                evidence=[{"source": "CVM", "published_at": candles[-2]["timestamp"], "title": "Fato", "content": "evidence", "content_mode": "metadata", "character_count": 8}],
                horizon=10,
                anchor_disclosure=None,
            )
        self.assertEqual(len(client.calls), 2)
        first_state, _ = client.calls[0]
        second_state, _ = client.calls[1]
        self.assertNotIn("kronos", first_state)
        self.assertNotIn("candidate_targets_calculated_by_code", first_state)
        self.assertEqual(first_state["forecast_horizon_candles"], 10)
        self.assertEqual(second_state["candidate_targets_calculated_by_code"], case["formula_audit"]["candidates"])
        self.assertEqual(case["selection"]["selected_variant"], "rule_adjusted")
        self.assertTrue(any("meaningful conflict" in warning for warning in case["warnings"]))

    def test_timeout_and_rate_limit_are_classified(self) -> None:
        class RateError(Exception):
            status = 429

        self.assertEqual(_failure("PETR4", "live", TimeoutError("request timeout"))["error_type"], "TimeoutError")
        self.assertEqual(_failure("PETR4", "live", RateError("too many"))["error_type"], "RateLimitError")


if __name__ == "__main__":
    unittest.main()
