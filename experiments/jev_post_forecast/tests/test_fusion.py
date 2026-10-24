from __future__ import annotations

import unittest

from experiments.jev_post_forecast.fusion import (
    choose_final_candidate,
    combine_risk,
    compose_candidates,
    deterministic_warnings,
)


class FusionTests(unittest.TestCase):
    def test_rule_adjustment_uses_probabilities_materiality_sufficiency_and_room(self) -> None:
        result = compose_candidates(
            last_close=100,
            terminal_return=2,
            low_return=-5,
            high_return=8,
            direction="bullish",
            direction_probabilities={"bullish": 0.7, "neutral": 0.1, "bearish": 0.1, "insufficient": 0.1},
            materiality_score=1.5,
            evidence_sufficient=0.8,
        )
        self.assertAlmostEqual(result["inputs"]["d"], 0.6)
        self.assertAlmostEqual(result["semantic_return_proxy"], 0.24)
        self.assertAlmostEqual(result["candidates"]["semantic_scenario"]["return_percent"], 8)
        self.assertAlmostEqual(result["candidates"]["rule_adjusted"]["return_percent"], 3.44)

    def test_rule_adjustment_clamps_inputs_and_output_to_kronos_band(self) -> None:
        result = compose_candidates(
            last_close=100,
            terminal_return=99,
            low_return=-3,
            high_return=4,
            direction="bearish",
            direction_probabilities={"bullish": 0.0, "bearish": 1.0},
            materiality_score=99,
            evidence_sufficient=99,
        )
        self.assertEqual(result["inputs"]["E"], 4)
        self.assertEqual(result["candidates"]["semantic_scenario"]["return_percent"], -3)
        self.assertEqual(result["candidates"]["rule_adjusted"]["return_percent"], -3)

    def test_neutral_and_insufficient_direction_keep_scenario_at_terminal(self) -> None:
        for direction in ("neutral", "insufficient"):
            result = compose_candidates(
                last_close=25,
                terminal_return=1,
                low_return=-4,
                high_return=5,
                direction=direction,
                direction_probabilities={"bullish": 0.25, "bearish": 0.25},
                materiality_score=2,
                evidence_sufficient=0.1,
            )
            self.assertEqual(result["candidates"]["semantic_scenario"]["return_percent"], 1)

    def test_preferred_insufficient_falls_back_to_kronos(self) -> None:
        candidates = {"kronos": {"target_price": 10}, "semantic_scenario": {"target_price": 11}}
        selected, result = choose_final_candidate("insufficient", candidates)
        self.assertEqual(selected, "kronos")
        self.assertEqual(result["target_price"], 10)

    def test_risk_can_only_escalate(self) -> None:
        self.assertEqual(combine_risk("high", 0), "high")
        self.assertEqual(combine_risk("low", 1), "medium")
        self.assertEqual(combine_risk("medium", 2), "high")

    def test_warning_thresholds_are_deterministic(self) -> None:
        stage1 = {"nouls": {"evidence_sufficient": 0.3, "cost_pressure": 0.70, "governance_risk": 0.69}}
        stage2 = {"nouls": {"evidence_conflict": 0.7}}
        warnings = deterministic_warnings(stage1, stage2)
        self.assertTrue(any("insufficient" in item for item in warnings))
        self.assertTrue(any("cost pressure" in item for item in warnings))
        self.assertTrue(any("meaningful conflict" in item for item in warnings))
        self.assertFalse(any("governance" in item for item in warnings))


if __name__ == "__main__":
    unittest.main()
