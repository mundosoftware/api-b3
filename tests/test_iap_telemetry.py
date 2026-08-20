import tempfile
import unittest
from datetime import UTC, datetime, timedelta

from src.config import Settings

from src.database import init_db
from src.models import IAPTelemetryEventCreateRequest
from src.repositories import Repository


class IAPTelemetryTest(unittest.TestCase):
    def test_server_trial_lifecycle_and_extension_telemetry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)
            started_at = datetime(2026, 8, 20, tzinfo=UTC)

            first = repository.request_iap_trial("user-a", started_at)
            self.assertEqual(first["product_id"], "trial_7_days")
            self.assertEqual(first["status"], "active")
            self.assertEqual(first["request_count"], 1)
            self.assertEqual(first["current_time"], started_at.isoformat())
            self.assertEqual(first["elapsed_days"], 0)
            self.assertEqual(first["remaining_days"], 7)
            self.assertEqual(first["remaining_seconds"], 7 * 86400)
            self.assertEqual(first["total_trial_days"], 7)

            expired_at = started_at + timedelta(days=7)
            expired = repository.get_iap_trial("user-a", expired_at)
            self.assertEqual(expired["status"], "expired")
            self.assertTrue(expired["can_request"])
            self.assertEqual(expired["elapsed_days"], 7)
            self.assertEqual(expired["remaining_days"], 0)
            self.assertEqual(expired["remaining_seconds"], 0)

            extension = repository.request_iap_trial("user-a", expired_at)
            self.assertEqual(extension["status"], "pending")
            self.assertFalse(extension["can_request"])
            asks = repository.list_iap_telemetry_events(
                product_id="trial_7_days",
                event_type="trial_extension_requested",
            )
            self.assertEqual(len(asks), 1)

    def test_lists_iap_trials_with_elapsed_and_remaining_days(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)
            started_at = datetime(2026, 8, 20, tzinfo=UTC)

            repository.request_iap_trial("user-a", started_at)
            trials = repository.list_iap_trials(
                user_id="user-a",
                status="active",
                now=started_at + timedelta(days=2),
            )

            self.assertEqual(len(trials), 1)
            trial = trials[0]
            self.assertEqual(trial["user_id"], "user-a")
            self.assertEqual(trial["status"], "active")
            self.assertEqual(
                trial["current_time"], (started_at + timedelta(days=2)).isoformat()
            )
            self.assertEqual(trial["elapsed_days"], 2)
            self.assertEqual(trial["remaining_days"], 5)
            self.assertEqual(trial["remaining_seconds"], 5 * 86400)
            self.assertEqual(trial["total_trial_days"], 7)

    def test_adjusts_iap_trial_period_and_records_telemetry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)
            started_at = datetime(2026, 8, 20, tzinfo=UTC)
            adjusted_at = started_at + timedelta(days=2)

            repository.request_iap_trial("user-a", started_at)

            extended = repository.adjust_iap_trial_period(
                "user-a",
                days=3,
                reason="support_extension",
                now=adjusted_at,
            )

            self.assertEqual(extended["status"], "active")
            self.assertEqual(extended["adjustment_days"], 3)
            self.assertEqual(
                extended["previous_ends_at"],
                (started_at + timedelta(days=7)).isoformat(),
            )
            self.assertEqual(
                extended["new_ends_at"],
                (started_at + timedelta(days=10)).isoformat(),
            )
            self.assertFalse(extended["ended"])
            self.assertEqual(extended["remaining_days"], 8)
            self.assertEqual(extended["remaining_seconds"], 8 * 86400)
            self.assertEqual(extended["total_trial_days"], 10)

            deducted = repository.adjust_iap_trial_period(
                "user-a",
                days=-2,
                reason="support_deduction",
                now=adjusted_at,
            )

            self.assertEqual(deducted["status"], "active")
            self.assertEqual(deducted["adjustment_days"], -2)
            self.assertFalse(deducted["ended"])
            self.assertEqual(
                deducted["new_ends_at"],
                (started_at + timedelta(days=8)).isoformat(),
            )
            self.assertEqual(deducted["remaining_days"], 6)
            self.assertEqual(deducted["remaining_seconds"], 6 * 86400)

            ended = repository.adjust_iap_trial_period(
                "user-a",
                days=-10,
                reason="support_end",
                now=adjusted_at,
            )

            self.assertEqual(ended["status"], "expired")
            self.assertTrue(ended["ended"])
            self.assertEqual(ended["new_ends_at"], adjusted_at.isoformat())
            self.assertEqual(ended["remaining_days"], 0)
            self.assertEqual(ended["remaining_seconds"], 0)

            extension_events = repository.list_iap_telemetry_events(
                product_id="trial_7_days",
                event_type="trial_period_extended",
            )
            deduction_events = repository.list_iap_telemetry_events(
                product_id="trial_7_days",
                event_type="trial_period_deducted",
            )
            ended_events = repository.list_iap_telemetry_events(
                product_id="trial_7_days",
                event_type="trial_ended_by_deduction",
            )

            self.assertEqual(extension_events[0]["reason"], "support_extension")
            self.assertEqual(extension_events[0]["trial_days"], 3)
            self.assertEqual(deduction_events[0]["reason"], "support_deduction")
            self.assertEqual(deduction_events[0]["trial_days"], 2)
            self.assertEqual(ended_events[0]["reason"], "support_end")
            self.assertEqual(ended_events[0]["trial_days"], 10)

    def test_records_and_filters_iap_telemetry_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)

            event = repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="products_loaded",
                    product_id="pro_year",
                    product_type="auto_renewable_subscription",
                    subscription_group_id="22314965",
                    offer_id="start_promo",
                    offer_type="promotional",
                    storefront="BRA",
                    currency_code="BRL",
                    display_price="R$ 24,90",
                    price=24.9,
                    trial_days=7,
                    status="available",
                    environment="sandbox",
                    app_version="1.2.0",
                    language="pt",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_succeeded",
                    product_id="pro_year",
                    transaction_id="2000000000000001",
                    original_transaction_id="2000000000000001",
                    status="verified",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="products_loaded",
                    product_id="pro_month",
                    status="available",
                    environment="sandbox",
                ),
            )

            self.assertEqual(event["user_id"], "user-a")
            self.assertEqual(event["product_id"], "pro_year")
            self.assertEqual(event["platform"], "ios")
            self.assertEqual(repository.get_user("user-a")["user_id"], "user-a")

            yearly_events = repository.list_iap_telemetry_events(
                user_id="user-a",
                product_id="pro_year",
                environment="sandbox",
            )

            self.assertEqual(len(yearly_events), 2)
            self.assertEqual(yearly_events[0]["event_type"], "purchase_succeeded")
            self.assertEqual(yearly_events[1]["display_price"], "R$ 24,90")

    def test_summarizes_iap_telemetry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)

            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="product_unavailable",
                    product_id="pro_year",
                    status="missing",
                    reason="storekit_product_not_loaded",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_failed",
                    product_id="pro_year",
                    status="failed",
                    reason="verification_failed",
                    environment="sandbox",
                ),
            )

            summary = repository.summarize_iap_telemetry(
                user_id="user-a",
                product_id="pro_year",
                environment="sandbox",
                hours=24,
            )

            event_counts = {item["name"]: item["count"] for item in summary["by_event_type"]}
            product_counts = {
                (item["product_id"], item["event_type"], item["status"]): item["count"]
                for item in summary["by_product"]
            }

            self.assertEqual(summary["total_events"], 2)
            self.assertEqual(event_counts["product_unavailable"], 1)
            self.assertEqual(event_counts["purchase_failed"], 1)
            self.assertEqual(product_counts[("pro_year", "purchase_failed", "failed")], 1)
            self.assertEqual(len(summary["latest_events"]), 2)

    def test_lists_iap_buying_attempts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)

            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="paywall_view",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_started",
                    product_id="pro_year",
                    status="started",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_failed",
                    product_id="pro_year",
                    status="failed",
                    reason="verification_failed",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="restore_succeeded",
                    product_id="lifetime_unlock",
                    status="verified",
                    environment="sandbox",
                ),
            )

            purchase_attempts = repository.list_iap_buying_attempts(
                user_id="user-a",
                environment="sandbox",
                include_restore=False,
            )
            purchase_and_restore_attempts = repository.list_iap_buying_attempts(
                user_id="user-a",
                environment="sandbox",
            )

            self.assertEqual(
                [event["event_type"] for event in purchase_attempts],
                ["purchase_failed", "purchase_started"],
            )
            self.assertEqual(
                [event["event_type"] for event in purchase_and_restore_attempts],
                ["restore_succeeded", "purchase_failed", "purchase_started"],
            )

    def test_lists_paying_users_from_latest_entitlement_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)

            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_succeeded",
                    product_id="pro_year",
                    product_type="auto_renewable_subscription",
                    transaction_id="2000000000000001",
                    original_transaction_id="2000000000000001",
                    status="verified",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_failed",
                    product_id="pro_year",
                    status="failed",
                    reason="network_timeout",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-b",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_succeeded",
                    product_id="pro_month",
                    status="verified",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-b",
                IAPTelemetryEventCreateRequest(
                    event_type="entitlement_inactive",
                    product_id="pro_month",
                    status="expired",
                    reason="subscription_expired",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-c",
                IAPTelemetryEventCreateRequest(
                    event_type="restore_succeeded",
                    product_id="lifetime_unlock",
                    product_type="non_consumable",
                    status="entitlement_active",
                    environment="sandbox",
                ),
            )

            paying_users = repository.list_iap_paying_users(environment="sandbox")
            paying_keys = {(user["user_id"], user["product_id"]) for user in paying_users}

            self.assertEqual(
                paying_keys,
                {("user-a", "pro_year"), ("user-c", "lifetime_unlock")},
            )
            user_a = next(user for user in paying_users if user["user_id"] == "user-a")
            self.assertEqual(user_a["event_type"], "purchase_succeeded")
            self.assertEqual(user_a["transaction_id"], "2000000000000001")
            self.assertEqual(user_a["first_success_at"], user_a["latest_success_at"])

    def test_groups_iap_success_and_failure_outcomes_by_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(database_path=f"{tmpdir}/app.db", check_loop_enabled=False)
            init_db(settings)
            repository = Repository(settings)

            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_succeeded",
                    product_id="pro_year",
                    status="verified",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-a",
                IAPTelemetryEventCreateRequest(
                    event_type="purchase_failed",
                    product_id="pro_year",
                    status="failed",
                    reason="verification_failed",
                    message="Transaction verification failed",
                    environment="sandbox",
                ),
            )
            repository.record_iap_telemetry_event(
                "user-b",
                IAPTelemetryEventCreateRequest(
                    event_type="product_unavailable",
                    product_id="pro_year",
                    status="missing",
                    reason="storekit_product_not_loaded",
                    message="Loaded products: lifetime_unlock",
                    environment="sandbox",
                ),
            )

            outcomes = repository.list_iap_telemetry_outcomes(
                environment="sandbox",
                hours=24,
            )
            outcome_counts = {
                (item["outcome"], item["event_type"], item["reason"]): item["count"]
                for item in outcomes
            }

            self.assertEqual(outcome_counts[("success", "purchase_succeeded", None)], 1)
            self.assertEqual(
                outcome_counts[("failure", "purchase_failed", "verification_failed")],
                1,
            )
            self.assertEqual(
                outcome_counts[
                    ("failure", "product_unavailable", "storekit_product_not_loaded")
                ],
                1,
            )


if __name__ == "__main__":
    unittest.main()
