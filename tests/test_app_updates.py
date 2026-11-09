import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.application import create_app
from src.config import Settings
from src.database import init_db
from src.models import AppUpdatePolicyUpdateRequest, AppUpdateTelemetryRequest
from src.repositories import Repository, compare_semantic_versions
from src.versioning import display_version_from_release_tag, validate_release_tag


class AppUpdatesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.settings = Settings(
            database_path=str(root / "app.db"),
            promotion_codes_csv_path=str(root / "missing-codes.csv"),
            admin_token="secret",
            panel_release_tag="RELEASE_9.8.7",
            check_loop_enabled=False,
            ai_outlook_worker_enabled=False,
        )
        init_db(self.settings)
        self.repository = Repository(self.settings)

    def tearDown(self):
        self.temporary.cleanup()

    def policy_request(self, **overrides):
        values = {
            "enabled": True,
            "target_version": "1.3.0",
            "mode": "soft",
            "store_url": "https://apps.apple.com/app/id123456789",
            "title_pt": "Atualização disponível",
            "title_en": "Update available",
            "message_pt": "Uma nova versão está disponível.",
            "message_en": "A new version is available.",
            "update_cta_pt": "Atualizar",
            "update_cta_en": "Update",
            "later_cta_pt": "Mais tarde",
            "later_cta_en": "Later",
        }
        values.update(overrides)
        return AppUpdatePolicyUpdateRequest(**values)

    def test_semantic_version_precedence(self):
        self.assertEqual(compare_semantic_versions("1.2.0", "1.2.0"), 0)
        self.assertLess(compare_semantic_versions("1.2.0", "1.3.0"), 0)
        self.assertGreater(compare_semantic_versions("2.0.0", "1.99.99"), 0)
        self.assertLess(compare_semantic_versions("1.3.0-beta.2", "1.3.0"), 0)
        self.assertEqual(compare_semantic_versions("1.2.0+45", "1.2.0+46"), 0)
        with self.assertRaises(ValueError):
            compare_semantic_versions("1.2", "1.2.0")
        with self.assertRaises(ValueError):
            compare_semantic_versions("01.2.0", "1.2.0")
        with self.assertRaises(ValueError):
            compare_semantic_versions("1.2.0-beta..1", "1.2.0")

    def test_panel_release_tag_uses_required_display_format(self):
        self.assertEqual(
            display_version_from_release_tag("RELEASE_1.2.0"),
            "v.1.2.0",
        )
        with self.assertRaises(ValueError):
            validate_release_tag("v1.2.0")

    def test_disabled_seed_policy_does_not_offer_current_app_version(self):
        decision = self.repository.app_update_decision("1.2.0", language="pt")

        self.assertFalse(decision["available"])
        self.assertEqual(decision["reason"], "disabled")
        self.assertEqual(decision["target_version"], "1.2.0")

    def test_soft_update_is_localized_and_only_offered_to_older_versions(self):
        self.repository.update_app_update_policy(self.policy_request())

        old = self.repository.app_update_decision("1.2.0", language="en")
        current = self.repository.app_update_decision("1.3.0", language="pt-BR")

        self.assertTrue(old["available"])
        self.assertEqual(old["mode"], "soft")
        self.assertEqual(old["text"]["update_cta"], "Update")
        self.assertFalse(current["available"])
        self.assertEqual(current["reason"], "up_to_date")
        self.assertEqual(current["text"]["update_cta"], "Atualizar")

    def test_hard_update_and_modal_interactions_are_recorded(self):
        self.repository.update_app_update_policy(
            self.policy_request(mode="hard", target_version="2.0.0")
        )
        decision = self.repository.app_update_decision("1.2.0")
        event = self.repository.record_app_update_event(
            "update-user",
            AppUpdateTelemetryRequest(
                event_type="modal_shown",
                current_version="1.2.0",
                target_version="2.0.0",
                mode="hard",
                environment="development",
                language="en",
            ),
        )

        self.assertTrue(decision["available"])
        self.assertEqual(decision["mode"], "hard")
        self.assertEqual(event["user_id"], "update-user")
        self.assertEqual(
            self.repository.list_app_update_events(user_id="update-user")[0][
                "event_type"
            ],
            "modal_shown",
        )

    def test_api_exposes_policy_decision_admin_edit_and_telemetry(self):
        with TestClient(create_app(self.settings)) as client:
            self.assertEqual(client.get("/admin/app-update").status_code, 401)
            response = client.put(
                "/admin/app-update",
                headers={"X-Admin-Token": "secret"},
                json=self.policy_request().model_dump(),
            )
            self.assertEqual(response.status_code, 200)

            decision = client.get(
                "/app-update",
                params={"current_version": "1.2.0", "language": "en"},
            )
            self.assertEqual(decision.status_code, 200)
            self.assertEqual(decision.headers["cache-control"], "no-store")
            self.assertTrue(decision.json()["available"])

            recorded = client.post(
                "/users/api-user/app-update/telemetry",
                json={
                    "event_type": "update_tapped",
                    "platform": "ios",
                    "current_version": "1.2.0",
                    "target_version": "1.3.0",
                    "mode": "soft",
                    "environment": "production",
                    "language": "en",
                },
            )
            self.assertEqual(recorded.status_code, 201)

            telemetry = client.get(
                "/admin/telemetry/app-update-events",
                headers={"X-Admin-Token": "secret"},
            )
            self.assertEqual(telemetry.status_code, 200)
            self.assertEqual(telemetry.json()["result"][0]["user_id"], "api-user")

            panel = client.get("/admin")
            self.assertIn("material-symbols-outlined", panel.text)
            self.assertIn('data-page="versions"', panel.text)
            self.assertIn('data-page="telemetry"', panel.text)
            self.assertIn("/admin/telemetry/app-update-events", panel.text)
            self.assertIn('id="logout"', panel.text)
            self.assertIn("v.9.8.7", panel.text)
            self.assertLess(panel.text.index("v.9.8.7"), panel.text.index('id="logout"'))


if __name__ == "__main__":
    unittest.main()
