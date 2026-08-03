import tempfile
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace

from src.alerts import AlertEngine
from src.config import Settings
from src.database import init_db
from src.models import AlertRuleCreateRequest
from src.repositories import Repository


class FakeTickerService:
    def __init__(self):
        self.calls = 0

    def quote(self, ticker: str, force_refresh: bool = False):
        self.calls += 1
        return {
            "ticker": ticker,
            "name": ticker,
            "asset_type": "stock",
            "last_price": 11.0,
            "daily_change_percent": 1.5,
            "updated_at": "2026-07-31T14:00:00+00:00",
        }


class FakeOneSignal:
    configured = True

    def __init__(self):
        self.messages = []

    def send_push_to_user(self, user_id, title, body, data=None, subscription_ids=None):
        self.messages.append((user_id, title, body, data, subscription_ids))
        return SimpleNamespace(notification_id=f"notification-{len(self.messages)}")


class AlertEngineTest(unittest.TestCase):
    def test_shared_ticker_lookup_for_multiple_users(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                onesignal_app_id="app-id",
                onesignal_rest_api_key="api-key",
            )
            init_db(settings)
            repository = Repository(settings)
            for user_id in ("user-a", "user-b"):
                repository.create_alert(
                    user_id,
                    AlertRuleCreateRequest(
                        ticker="PETR4",
                        metric="price",
                        operator="gte",
                        threshold=10.0,
                        weekdays=[5],
                        start_time="00:00",
                        end_time="23:59",
                        timezone="UTC",
                        frequency_minutes=1,
                        cooldown_minutes=0,
                    ),
                )
                repository.save_device(
                    user_id=user_id,
                    platform="watchos",
                    device_token=f"apns-token-{user_id}",
                    environment="development",
                    onesignal_subscription_id=f"watch-subscription-{user_id}",
                )

            ticker_service = FakeTickerService()
            onesignal = FakeOneSignal()
            engine = AlertEngine(repository, ticker_service, onesignal, settings)
            result = engine.run_due_checks(datetime(2026, 7, 31, 14, 0, tzinfo=UTC))

            self.assertEqual(ticker_service.calls, 1)
            self.assertEqual(result.checked_tickers, 1)
            self.assertEqual(result.evaluated_rules, 2)
            self.assertEqual(result.triggered_rules, 2)
            self.assertEqual(result.notifications_sent, 2)
            self.assertEqual({message[0] for message in onesignal.messages}, {"user-a", "user-b"})
            self.assertEqual(
                {message[4][0] for message in onesignal.messages},
                {"watch-subscription-user-a", "watch-subscription-user-b"},
            )

    def test_notification_preferences_filter_platform_subscriptions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                onesignal_app_id="app-id",
                onesignal_rest_api_key="api-key",
            )
            init_db(settings)
            repository = Repository(settings)
            repository.create_alert(
                "user-a",
                AlertRuleCreateRequest(
                    ticker="PETR4",
                    metric="price",
                    operator="gte",
                    threshold=10.0,
                    weekdays=[5],
                    start_time="00:00",
                    end_time="23:59",
                    timezone="UTC",
                    frequency_minutes=1,
                    cooldown_minutes=0,
                ),
            )
            repository.save_device(
                user_id="user-a",
                platform="ios",
                device_token="ios-subscription",
                environment="production",
                onesignal_subscription_id="ios-subscription",
            )
            repository.save_device(
                user_id="user-a",
                platform="watchos",
                device_token="watch-apns-token",
                environment="development",
                onesignal_subscription_id="watch-subscription",
            )
            repository.update_notification_preferences(
                "user-a",
                SimpleNamespace(ios_enabled=True, watchos_enabled=False),
            )

            ticker_service = FakeTickerService()
            onesignal = FakeOneSignal()
            engine = AlertEngine(repository, ticker_service, onesignal, settings)
            result = engine.run_due_checks(datetime(2026, 7, 31, 14, 0, tzinfo=UTC))

            self.assertEqual(result.notifications_sent, 1)
            self.assertEqual(onesignal.messages[0][4], ["ios-subscription"])


if __name__ == "__main__":
    unittest.main()
