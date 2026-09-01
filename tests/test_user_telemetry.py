import asyncio
import tempfile
import unittest

from fastapi import HTTPException

from src.application import create_app
from src.config import Settings
from src.database import init_db
from src.models import AlertRuleCreateRequest, NotificationPreferencesUpdateRequest
from src.repositories import Repository


class UserTelemetryTest(unittest.TestCase):
    def test_user_telemetry_reports_user_counts_and_filters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                ai_outlook_worker_enabled=False,
                admin_token="secret",
                kronos_enabled=False,
            )
            init_db(settings)
            repository = Repository(settings)
            repository.upsert_user(
                "user-a",
                display_name="User A",
                timezone="America/Sao_Paulo",
            )
            repository.update_notification_preferences(
                "user-a",
                NotificationPreferencesUpdateRequest(ai_outlook_enabled=True),
            )
            repository.save_device(
                user_id="user-a",
                platform="ios",
                device_token="subscription-0000000001",
                environment="production",
                onesignal_subscription_id="subscription-0000000001",
            )
            repository.add_favorite("user-a", "PETR4")
            repository.create_alert(
                "user-a",
                AlertRuleCreateRequest(
                    ticker="PETR4",
                    metric="price",
                    operator="gte",
                    threshold=30.0,
                ),
            )
            repository.create_ai_outlook_job("user-a", "PETR4", status="succeeded")
            repository.create_ai_outlook_job("user-a", "VALE3", status="failed")
            repository.upsert_user("user-b")

            app = create_app(settings)
            endpoints = {getattr(route, "name", ""): route.endpoint for route in app.routes}

            async def exercise_routes():
                users = await endpoints["telemetry_users"](
                    x_admin_token="secret",
                    user_id=None,
                    ai_outlook_enabled=None,
                    limit=50,
                )
                enabled = await endpoints["telemetry_users"](
                    x_admin_token="secret",
                    user_id=None,
                    ai_outlook_enabled=True,
                    limit=50,
                )
                one_user = await endpoints["telemetry_users"](
                    x_admin_token="secret",
                    user_id="user-a",
                    ai_outlook_enabled=None,
                    limit=50,
                )
                try:
                    await endpoints["telemetry_users"](
                        x_admin_token=None,
                        user_id=None,
                        ai_outlook_enabled=None,
                        limit=50,
                    )
                except HTTPException as exc:
                    unauthorized_status = exc.status_code
                else:
                    unauthorized_status = None
                return users, enabled, one_user, unauthorized_status

            users, enabled, one_user, unauthorized_status = asyncio.run(exercise_routes())

            self.assertEqual(unauthorized_status, 401)
            self.assertEqual({user.user_id for user in users.result}, {"user-a", "user-b"})
            self.assertEqual([user.user_id for user in enabled.result], ["user-a"])
            self.assertEqual(len(one_user.result), 1)

            default_user = next(user for user in users.result if user.user_id == "user-b")
            self.assertTrue(default_user.ios_enabled)
            self.assertTrue(default_user.watchos_enabled)
            self.assertFalse(default_user.ai_outlook_enabled)
            self.assertEqual(default_user.device_count, 0)
            self.assertEqual(default_user.ai_outlook_job_count, 0)

            user = one_user.result[0]
            self.assertEqual(user.user_id, "user-a")
            self.assertEqual(user.display_name, "User A")
            self.assertEqual(user.timezone, "America/Sao_Paulo")
            self.assertTrue(user.ios_enabled)
            self.assertTrue(user.watchos_enabled)
            self.assertTrue(user.ai_outlook_enabled)
            self.assertTrue(user.ios_registered)
            self.assertFalse(user.watchos_registered)
            self.assertEqual(user.device_count, 1)
            self.assertEqual(user.favorite_count, 1)
            self.assertEqual(user.alert_count, 1)
            self.assertEqual(user.enabled_alert_count, 1)
            self.assertEqual(user.ai_outlook_job_count, 2)
            self.assertEqual(user.ai_outlook_succeeded_count, 1)
            self.assertEqual(user.ai_outlook_failed_count, 1)
            self.assertIsNotNone(user.latest_ai_outlook_job_at)
            self.assertIsNotNone(user.latest_seen_at)


if __name__ == "__main__":
    unittest.main()
