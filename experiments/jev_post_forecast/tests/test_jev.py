from __future__ import annotations

import unittest

from experiments.jev_post_forecast.jev import STAGE1_QUESTION_SPECS, normalize_response


def answer_for_specs(specs, *, ambiguous: bool = False):
    answers = {}
    for name, spec in specs.items():
        if spec["type"] == "choice":
            keys = list(spec["criteria"])
            probabilities = {key: 1 / len(keys) for key in keys} if ambiguous else {key: (1.0 if index == 0 else 0.0) for index, key in enumerate(keys)}
            answers[name] = {"type": "choice", "choice": keys[0], "probabilities": probabilities, "confidence": 0.0 if ambiguous else 1.0}
        elif spec["type"] == "score":
            count = len(spec["criteria"])
            probabilities = {str(index): (1 / count if ambiguous else (1.0 if index == 1 else 0.0)) for index in range(count)}
            answers[name] = {"type": "score", "score": (count - 1) / 2 if ambiguous else 1.0, "probabilities": probabilities, "confidence": 0.0 if ambiguous else 1.0}
        else:
            answers[name] = {"type": "noul", "noul": 0.5 if ambiguous else 0.8}
    return {"model": "jev-1.13.0", "usage": {"input_tokens": 100, "output_tokens": 5}, "answers": answers, "latency_ms": 10}


class JevResponseTests(unittest.TestCase):
    def test_normal_response_retains_distributions_usage_and_cost(self) -> None:
        result = normalize_response(answer_for_specs(STAGE1_QUESTION_SPECS), STAGE1_QUESTION_SPECS)
        self.assertEqual(result["model"], "jev-1.13.0")
        self.assertEqual(result["usage"]["input_tokens"], 100)
        self.assertAlmostEqual(result["estimated_cost_usd"], 0.0000042)
        self.assertIn("semantic_direction", result["choices"])

    def test_ambiguous_response_is_valid_and_keeps_low_clarity(self) -> None:
        result = normalize_response(answer_for_specs(STAGE1_QUESTION_SPECS, ambiguous=True), STAGE1_QUESTION_SPECS)
        self.assertEqual(result["choices"]["semantic_direction"]["confidence"], 0.0)
        self.assertEqual(result["nouls"]["evidence_sufficient"], 0.5)

    def test_malformed_response_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing answer"):
            normalize_response({"answers": {}}, STAGE1_QUESTION_SPECS)
        raw = answer_for_specs(STAGE1_QUESTION_SPECS)
        raw["answers"]["semantic_direction"]["probabilities"] = {"bullish": 0.1}
        with self.assertRaisesRegex(ValueError, "sum to one"):
            normalize_response(raw, STAGE1_QUESTION_SPECS)


if __name__ == "__main__":
    unittest.main()
