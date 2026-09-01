import asyncio
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from src.ai_analysis import PredictionError
from src.ai_outlook_jobs import AIOutlookJobProcessor
from src.application import create_app
from src.config import Settings
from src.database import init_db
from src.models import AIOutlookJobCreateRequest
from src.repositories import Repository


class FakeDecisionSupport:
    def __init__(self, result=None, failure: Exception | None = None):
        self.result = result or make_analysis()
        self.failure = failure
        self.calls = 0

    def analysis(self, *args, **kwargs):
        self.calls += 1
        if self.failure:
            raise self.failure.__class__(str(self.failure))
        return self.result


class FakeOneSignal:
    configured = True
    ios_configured = True
    watchos_configured = True

    def __init__(self):
        self.messages = []

    def send_push_to_user(
        self, user_id, title, body, data=None, subscription_ids=None, platform="ios"
    ):
        self.messages.append((user_id, title, body, data, subscription_ids, platform))
        return SimpleNamespace(
            notification_id=f"notification-{len(self.messages)}",
            invalid_subscription_ids=(),
            all_targeted_subscriptions_invalid=False,
        )


class AIOutlookJobsTest(unittest.TestCase):
    def test_api_enqueues_reuses_and_reports_ai_outlook_job(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                ai_outlook_worker_enabled=False,
                admin_token="secret",
                kronos_enabled=False,
            )
            init_db(settings)
            app = create_app(settings)
            endpoints = {getattr(route, "name", ""): route.endpoint for route in app.routes}

            async def exercise_routes():
                request = AIOutlookJobCreateRequest(ticker="PETR4", horizon=10)
                created = await endpoints["create_ai_outlook_job"]("user-a", request)
                reused = await endpoints["create_ai_outlook_job"]("user-a", request)
                fetched = await endpoints["get_ai_outlook_job"]("user-a", created.job_id)
                usage = await endpoints["telemetry_ai_outlook_usage"](
                    x_admin_token="secret",
                    user_id=None,
                    ticker=None,
                    hours=24,
                )
                jobs = await endpoints["telemetry_ai_outlook_jobs"](
                    x_admin_token="secret",
                    status_filter=None,
                    user_id=None,
                    ticker=None,
                    limit=100,
                )
                try:
                    await endpoints["telemetry_ai_outlook_jobs"]()
                except HTTPException as exc:
                    unauthorized_status = exc.status_code
                else:
                    unauthorized_status = None
                return created, reused, fetched, usage, jobs, unauthorized_status

            created, reused, fetched, usage, jobs, unauthorized_status = asyncio.run(
                exercise_routes()
            )

            self.assertEqual(created.status, "queued")
            self.assertEqual(reused.job_id, created.job_id)
            self.assertEqual(fetched.job_id, created.job_id)
            self.assertEqual(usage.total_jobs, 1)
            self.assertEqual(usage.by_status[0].name, "queued")
            self.assertEqual(len(jobs.result), 1)
            self.assertEqual(unauthorized_status, 401)

    def test_processor_completes_job_and_notifies_user(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                ai_outlook_retry_delay_seconds=0,
                kronos_enabled=False,
            )
            init_db(settings)
            repository = Repository(settings)
            repository.save_device(
                user_id="user-a",
                platform="ios",
                device_token="subscription-0000000001",
                environment="production",
                onesignal_subscription_id="subscription-0000000001",
            )
            job = repository.create_ai_outlook_job("user-a", "PETR4", max_attempts=3)
            onesignal = FakeOneSignal()
            processor = AIOutlookJobProcessor(
                repository=repository,
                decision_support=FakeDecisionSupport(),
                onesignal=onesignal,
                settings=settings,
            )

            self.assertTrue(processor.run_once())

            completed = repository.get_ai_outlook_job("user-a", job["job_id"])
            notifications = repository.list_notification_logs(user_id="user-a")
            self.assertEqual(completed["status"], "succeeded")
            self.assertEqual(completed["attempt_count"], 1)
            self.assertEqual(completed["result"]["ticker"], "PETR4")
            self.assertEqual(len(onesignal.messages), 1)
            self.assertEqual(notifications[0]["status"], "sent; ios: sent")

    def test_processor_retries_twice_then_fails_and_notifies_user(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                ai_outlook_retry_delay_seconds=0,
                kronos_enabled=False,
            )
            init_db(settings)
            repository = Repository(settings)
            repository.save_device(
                user_id="user-a",
                platform="ios",
                device_token="subscription-0000000001",
                environment="production",
                onesignal_subscription_id="subscription-0000000001",
            )
            job = repository.create_ai_outlook_job("user-a", "PETR4", max_attempts=3)
            decision_support = FakeDecisionSupport(failure=PredictionError("model timed out"))
            onesignal = FakeOneSignal()
            processor = AIOutlookJobProcessor(
                repository=repository,
                decision_support=decision_support,
                onesignal=onesignal,
                settings=settings,
            )

            with patch("logging.exception"):
                self.assertTrue(processor.run_once())
                first_retry = repository.get_ai_outlook_job("user-a", job["job_id"])
                self.assertEqual(first_retry["status"], "queued")
                self.assertEqual(first_retry["attempt_count"], 1)

                self.assertTrue(processor.run_once())
                second_retry = repository.get_ai_outlook_job("user-a", job["job_id"])
                self.assertEqual(second_retry["status"], "queued")
                self.assertEqual(second_retry["attempt_count"], 2)

                self.assertTrue(processor.run_once())
            failed = repository.get_ai_outlook_job("user-a", job["job_id"])
            failures = repository.list_failure_telemetry(user_id="user-a", ticker="PETR4")

            self.assertEqual(failed["status"], "failed")
            self.assertEqual(failed["attempt_count"], 3)
            self.assertIn("model timed out", failed["failure_reason"])
            self.assertEqual(decision_support.calls, 3)
            self.assertEqual(len(onesignal.messages), 1)
            self.assertEqual(onesignal.messages[0][3]["status"], "failed")
            self.assertEqual(failures[0]["source"], "ai_outlook_job")


def make_analysis() -> dict:
    return {
        "ticker": "PETR4",
        "interval": "1d",
        "horizon": 10,
        "lookback": 120,
        "generated_at": "2026-09-01T14:00:00+00:00",
        "source": "yahoo",
        "model_name": "ewma-trend-fallback",
        "provider": "statistical",
        "outlook": "neutral",
        "risk_level": "low",
        "confidence": 0.55,
        "last_close": 30.0,
        "target_price": 30.2,
        "expected_change_percent": 0.66,
        "forecast_low_percent": -1.0,
        "forecast_high_percent": 1.4,
        "support_price": 29.0,
        "resistance_price": 31.0,
        "stop_price": None,
        "take_profit_price": None,
        "summary": "PETR4 is range-bound in the current forecast window.",
        "action": "Wait for a break outside 29.00-31.00 before acting.",
        "drivers": ["Fallback model projects +0.66%."],
        "warnings": ["Forecasts are probabilistic and can be wrong."],
        "historical": [
            {
                "ticker": "PETR4",
                "interval": "1d",
                "timestamp": "2026-08-31T13:00:00+00:00",
                "open": 30.0,
                "high": 30.5,
                "low": 29.8,
                "close": 30.1,
                "volume": 1000.0,
                "amount": 30100.0,
                "source": "test",
                "created_at": "2026-09-01T14:00:00+00:00",
            }
        ],
        "forecast": [
            {
                "timestamp": "2026-09-02T13:00:00+00:00",
                "open": 30.1,
                "high": 30.4,
                "low": 29.9,
                "close": 30.2,
                "volume": 1000.0,
                "amount": 30200.0,
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
