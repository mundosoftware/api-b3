import tempfile
import unittest

from src.config import Settings
from src.database import init_db
from src.models import NotificationPreferencesUpdateRequest
from src.repositories import Repository


class UserPreferencesTest(unittest.TestCase):
    def test_ai_outlook_is_disabled_by_default_and_can_be_enabled(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)

            default_preferences = repository.get_notification_preferences("user-a")

            self.assertFalse(default_preferences["ai_outlook_enabled"])

            updated = repository.update_notification_preferences(
                "user-a",
                NotificationPreferencesUpdateRequest(ai_outlook_enabled=True),
            )

            self.assertTrue(updated["ai_outlook_enabled"])
            self.assertTrue(updated["ios_enabled"])
            self.assertTrue(updated["watchos_enabled"])

    def test_device_telemetry_reports_ai_outlook_activation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)
            repository.save_device(
                user_id="user-a",
                platform="ios",
                device_token="ios-subscription",
                environment="production",
                onesignal_subscription_id="ios-subscription",
            )
            repository.update_notification_preferences(
                "user-a",
                NotificationPreferencesUpdateRequest(ai_outlook_enabled=True),
            )

            telemetry = repository.list_device_telemetry(user_id="user-a")

            self.assertEqual(len(telemetry), 1)
            self.assertTrue(telemetry[0]["ai_outlook_enabled"])


if __name__ == "__main__":
    unittest.main()
