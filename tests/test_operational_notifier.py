import asyncio
import tempfile
import unittest
from unittest.mock import patch

import requests

from src.application import create_app
from src.config import Settings
from src.database import init_db
from src.operational_notifier import OperationalNotifier


class OperationalNotifierTest(unittest.TestCase):
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
