from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiments.jev_post_forecast.cli import main
from experiments.jev_post_forecast.report import cases_csv, render_report
from experiments.jev_post_forecast.storage import load_json


PACKAGE = Path(__file__).resolve().parents[1]
FIXTURE = PACKAGE / "fixtures" / "report_run.json"
SNAPSHOT = Path(__file__).with_name("snapshots") / "report_sections.txt"


class ReportTests(unittest.TestCase):
    def test_structural_snapshot_and_credential_absence(self) -> None:
        html = render_report(load_json(FIXTURE))
        expected_sections = SNAPSHOT.read_text(encoding="utf-8").splitlines()
        cursor = 0
        for section in expected_sections:
            cursor = html.index(section, cursor) + len(section)
        lowered = html.lower()
        self.assertNotIn("authorization: bearer", lowered)
        self.assertNotIn("typesafe_api_key", lowered)
        self.assertIn("localStorage", html)
        self.assertIn("review.json", html)

    def test_csv_has_one_row_per_candidate(self) -> None:
        result = cases_csv(load_json(FIXTURE))
        self.assertEqual(len(result.strip().splitlines()), 4)
        self.assertIn("rule_adjusted", result)

    def test_report_only_never_constructs_experiment_runner(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch(
            "experiments.jev_post_forecast.cli.ExperimentRunner", side_effect=AssertionError("must not run")
        ):
            status = main(["--mode", "report-only", "--input", str(FIXTURE), "--output", directory])
            self.assertEqual(status, 0)
            generated = load_json(Path(directory) / "run.json")
            self.assertEqual(generated, load_json(FIXTURE))
            self.assertTrue((Path(directory) / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
