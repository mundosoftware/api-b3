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


if __name__ == "__main__":
    unittest.main()
