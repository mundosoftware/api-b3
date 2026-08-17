import tempfile
import unittest

from src.config import Settings
from src.database import init_db
from src.models import IAPTelemetryEventCreateRequest
from src.repositories import Repository


class IAPTelemetryTest(unittest.TestCase):
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
