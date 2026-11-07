import asyncio
import tempfile
import unittest
from unittest.mock import patch

import requests

from src.application import create_app
from src.config import Settings
from src.database import init_db
from src.operational_notifier import OperationalNotifier, TRADE_ALERT_TEMPLATE_EVENTS


class OperationalNotifierTest(unittest.TestCase):
    def test_template_event_contract_contains_only_approved_whatsapp_events(self):
        self.assertEqual(
            TRADE_ALERT_TEMPLATE_EVENTS,
            {
                "user.created",
                "iap.trial_extension_requested",
            },
        )

    def test_disabled_notifier_does_not_send(self):
        settings = Settings(universal_notifier_enabled=False)
        notifier = OperationalNotifier(settings)
        with patch("src.operational_notifier.requests.post") as post:
            notifier.notify_later(
                event="test.message",
                severity="info",
                title="Test",
                message="Disabled",
            )
        post.assert_not_called()

    def test_enabled_notifier_does_not_queue_an_unmapped_event(self):
        settings = Settings(
            universal_notifier_enabled=True,
            universal_notifier_url="http://notifier.test/v1/events",
        )
        notifier = OperationalNotifier(settings)

        with (
            patch("src.operational_notifier.threading.Thread") as thread,
            self.assertLogs(level="WARNING") as logs,
        ):
            notifier.notify_later(
                event="unknown.event",
                severity="warning",
                title="Unknown",
                message="No approved template",
            )

        thread.assert_not_called()
        self.assertIn("universal_notifier_event_not_mapped", " ".join(logs.output))

    def test_enabled_notifier_queues_a_catalogued_event(self):
        settings = Settings(
            universal_notifier_enabled=True,
            universal_notifier_url="http://notifier.test/v1/events",
        )
        notifier = OperationalNotifier(settings)

        with patch("src.operational_notifier.threading.Thread") as thread:
            notifier.notify_later(
                event="user.created",
                severity="success",
                title="New user",
                message="A new user account was created.",
                subject={"type": "user", "id": "user-123"},
                metadata={"timezone": "America/Fortaleza"},
            )

        thread.assert_called_once()
        payload = thread.call_args.kwargs["args"][0]
        self.assertEqual(payload["system"], "trade-alert")
        self.assertEqual(payload["event"], "user.created")
        self.assertEqual(payload["metadata"]["timezone"], "America/Fortaleza")

    def test_enabled_notifier_silently_ignores_known_non_whatsapp_event(self):
        settings = Settings(
            universal_notifier_enabled=True,
            universal_notifier_url="http://notifier.test/v1/events",
        )
        notifier = OperationalNotifier(settings)

        with patch("src.operational_notifier.threading.Thread") as thread:
            notifier.notify_later(
                event="alert.failure",
                severity="error",
                title="Alert failed",
                message="No push notification was delivered.",
            )

        thread.assert_not_called()

    def test_enabled_notifier_posts_without_exposing_configuration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                universal_notifier_enabled=True,
                universal_notifier_url="http://notifier.test/v1/events",
                universal_notifier_http_token="test-token",
            )
            notifier = OperationalNotifier(settings)
            response = type("Response", (), {"raise_for_status": lambda self: None})()
            with patch("src.operational_notifier.requests.post", return_value=response) as post:
                notifier._send(
                    {
                        "system": "trade-alert",
                        "event": "test.message",
                        "severity": "info",
                        "title": "Test",
                        "message": "Hello",
                    }
                )
            self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")
            self.assertNotIn("test-token", post.call_args.kwargs["json"].get("message", ""))

    def test_delivery_result_logs_a_terminal_template_failure(self):
        settings = Settings(
            universal_notifier_enabled=True,
            universal_notifier_url="http://notifier.test/v1/events",
        )
        notifier = OperationalNotifier(settings)
        response = type(
            "Response",
            (),
            {
                "raise_for_status": lambda self: None,
                "json": lambda self: {
                    "ok": False,
                    "results": [
                        {
                            "reason": "whatsapp_http_error",
                            "templateName": "un_trade_alert_user_created_v1",
                            "retryable": False,
                        }
                    ],
                },
            },
        )()

        with (
            patch("src.operational_notifier.requests.post", return_value=response),
            self.assertLogs(level="WARNING") as logs,
        ):
            notifier._send({"system": "trade-alert", "event": "user.created"})

        message = " ".join(logs.output)
        self.assertIn("whatsapp_http_error", message)
        self.assertIn("un_trade_alert_user_created_v1", message)

    def test_health_reports_notifier_state_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                ai_outlook_worker_enabled=False,
                universal_notifier_enabled=True,
                universal_notifier_url="http://notifier.test/v1/events",
                universal_notifier_http_token="test-token",
            )
            init_db(settings)
            app = create_app(settings)
            endpoints = {getattr(route, "name", ""): route.endpoint for route in app.routes}
            with patch(
                "src.operational_notifier.requests.get",
                side_effect=requests.ConnectionError,
            ):
                health = asyncio.run(endpoints["health"]())
                readiness = asyncio.run(endpoints["readiness"]())

            self.assertEqual(
                health["universal_notifier"],
                {
                    "enabled": True,
                    "configured": True,
                    "reachable": False,
                    "ready": False,
                    "reason": "unreachable",
                },
            )
            self.assertEqual(health["status"], "degraded")
            self.assertEqual(readiness["status"], "degraded")
            self.assertEqual(readiness["universal_notifier"], health["universal_notifier"])
            self.assertNotIn("test-token", str(health))
            self.assertNotIn("notifier.test", str(health))


if __name__ == "__main__":
    unittest.main()
