import tempfile
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch

from src.alerts import AlertEngine
from src.config import Settings
from src.database import init_db
from src.models import AlertRuleCreateRequest, AlertRuleUpdateRequest
from src.onesignal import OneSignalClient
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

    def __init__(self, next_response=None):
        self.messages = []
        self.deleted_subscriptions = []
        self.next_response = next_response

    def send_push_to_user(self, user_id, title, body, data=None, subscription_ids=None):
        self.messages.append((user_id, title, body, data, subscription_ids))
        if self.next_response is not None:
            return self.next_response
        return SimpleNamespace(
            notification_id=f"notification-{len(self.messages)}",
            invalid_subscription_ids=(),
            all_targeted_subscriptions_invalid=False,
        )

    def delete_subscription(self, subscription_id):
        self.deleted_subscriptions.append(subscription_id)
        return True


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

    def test_disabled_alerts_are_not_evaluated_or_notified(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                onesignal_app_id="app-id",
                onesignal_rest_api_key="api-key",
            )
            init_db(settings)
            repository = Repository(settings)
            alert = repository.create_alert(
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
            updated = repository.update_alert(
                "user-a", alert.id, AlertRuleUpdateRequest(enabled=False)
            )

            onesignal = FakeOneSignal()
            engine = AlertEngine(repository, FakeTickerService(), onesignal, settings)
            result = engine.run_due_checks(datetime(2026, 7, 31, 14, 0, tzinfo=UTC))

            self.assertIsNotNone(updated)
            self.assertFalse(updated.enabled)
            self.assertEqual(result.evaluated_rules, 0)
            self.assertEqual(result.notifications_sent, 0)
            self.assertEqual(onesignal.messages, [])

    def test_alert_notification_text_is_localized(self):
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

            onesignal = FakeOneSignal()
            engine = AlertEngine(repository, FakeTickerService(), onesignal, settings)
            engine.run_due_checks(datetime(2026, 7, 31, 14, 0, tzinfo=UTC))

            _, title, body, _, _ = onesignal.messages[0]
            self.assertEqual(title["pt"], "Alerta PETR4")
            self.assertEqual(title["en"], "PETR4 alert")
            self.assertEqual(body["pt"], "PETR4 está acima de R$ 10,00: R$ 11,00")
            self.assertEqual(body["en"], "PETR4 is above R$ 10.00: R$ 11.00")

    def test_onesignal_payload_preserves_localized_text_and_language(self):
        settings = Settings(
            check_loop_enabled=False,
            onesignal_app_id="app-id",
            onesignal_rest_api_key="api-key",
        )
        client = OneSignalClient(settings)

        with patch("src.onesignal.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"id": "notification-id"}

            client.send_push_to_user(
                user_id="user-a",
                title={"pt": "Alerta PETR4", "en": "PETR4 alert"},
                body={"pt": "Corpo", "en": "Body"},
                subscription_ids=["subscription-id"],
            )
            notification_payload = post.call_args.kwargs["json"]

            client.register_watch_device(
                user_id="user-a",
                apns_token="0" * 64,
                environment="production",
                language="en",
            )
            registration_payload = post.call_args.kwargs["json"]

        self.assertEqual(notification_payload["headings"]["pt"], "Alerta PETR4")
        self.assertEqual(notification_payload["headings"]["en"], "PETR4 alert")
        self.assertEqual(notification_payload["contents"]["pt"], "Corpo")
        self.assertEqual(notification_payload["contents"]["en"], "Body")
        self.assertEqual(registration_payload["language"], "en")

    def test_invalid_subscription_is_removed_after_notification_send(self):
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
                device_token="ios-token",
                environment="production",
                onesignal_subscription_id="stale-subscription",
            )
            repository.save_device(
                user_id="user-a",
                platform="watchos",
                device_token="watch-token",
                environment="production",
                onesignal_subscription_id="watch-subscription",
            )

            onesignal = FakeOneSignal(
                SimpleNamespace(
                    notification_id="notification-1",
                    invalid_subscription_ids=("stale-subscription",),
                    all_targeted_subscriptions_invalid=False,
                )
            )
            engine = AlertEngine(repository, FakeTickerService(), onesignal, settings)
            result = engine.run_due_checks(datetime(2026, 7, 31, 14, 0, tzinfo=UTC))

            self.assertEqual(result.notifications_sent, 1)
            self.assertEqual(onesignal.deleted_subscriptions, ["stale-subscription"])
            self.assertEqual(
                repository.list_enabled_notification_subscription_ids("user-a"),
                ["watch-subscription"],
            )

    def test_all_invalid_targeted_subscriptions_are_removed(self):
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
                device_token="ios-token",
                environment="production",
                onesignal_subscription_id="stale-subscription",
            )

            onesignal = FakeOneSignal(
                SimpleNamespace(
                    notification_id=None,
                    invalid_subscription_ids=(),
                    all_targeted_subscriptions_invalid=True,
                )
            )
            engine = AlertEngine(repository, FakeTickerService(), onesignal, settings)
            result = engine.run_due_checks(datetime(2026, 7, 31, 14, 0, tzinfo=UTC))

            self.assertEqual(result.notifications_sent, 0)
            self.assertEqual(onesignal.deleted_subscriptions, ["stale-subscription"])
            self.assertEqual(repository.list_enabled_notification_subscription_ids("user-a"), [])

    def test_onesignal_response_marks_invalid_subscriptions_for_cleanup(self):
        settings = Settings(
            check_loop_enabled=False,
            onesignal_app_id="app-id",
            onesignal_rest_api_key="api-key",
        )
        client = OneSignalClient(settings)

        with patch("src.onesignal.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {
                "id": "notification-id",
                "errors": {"invalid_subscription_ids": ["stale-subscription"]},
            }
            notification = client.send_push_to_user(
                user_id="user-a",
                title="title",
                body="body",
                subscription_ids=["stale-subscription", "valid-subscription"],
            )

            post.return_value.json.return_value = {
                "recipients": 0,
                "errors": ["All included subscriptions are not subscribed"],
            }
            all_invalid = client.send_push_to_user(
                user_id="user-a",
                title="title",
                body="body",
                subscription_ids=["stale-subscription"],
            )

        self.assertEqual(notification.invalid_subscription_ids, ("stale-subscription",))
        self.assertFalse(notification.all_targeted_subscriptions_invalid)
        self.assertTrue(all_invalid.all_targeted_subscriptions_invalid)


if __name__ == "__main__":
    unittest.main()
