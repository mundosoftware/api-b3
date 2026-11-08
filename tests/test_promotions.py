import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from src.application import create_app
from src.config import Settings
from src.database import init_db
from src.models import (
    IAPTelemetryEventCreateRequest,
    PromotionAdminCreateRequest,
    PromotionAdminUpdateRequest,
    PromotionCodeImportItem,
    PromotionCodeImportRequest,
    PromotionRedemptionRequest,
)
from src.repositories import Repository


class PromotionsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        csv_path = root / "codes.csv"
        csv_path.write_text(
            "CODE-ONE,https://apps.apple.com/redeem?code=CODE-ONE\n"
            "CODE-TWO,https://apps.apple.com/redeem?code=CODE-TWO\n",
            encoding="utf-8",
        )
        self.settings = Settings(
            database_path=str(root / "app.db"),
            promotion_codes_csv_path=str(csv_path),
            admin_token="secret",
            check_loop_enabled=False,
            ai_outlook_worker_enabled=False,
        )
        init_db(self.settings)
        self.repository = Repository(self.settings)

    def tearDown(self):
        self.temporary.cleanup()

    def test_trial_engagement_extension_is_automatic_and_one_time(self):
        now = datetime(2026, 11, 7, 12, tzinfo=UTC)
        original = self.repository.request_iap_trial("trial-user", now)

        granted = self.repository.grant_engagement_trial_extension("trial-user", now=now)
        repeated = self.repository.grant_engagement_trial_extension("trial-user", now=now)

        self.assertTrue(granted["granted"])
        self.assertEqual(granted["extension_days"], 7)
        self.assertEqual(
            datetime.fromisoformat(granted["trial"]["ends_at"]),
            datetime.fromisoformat(original["ends_at"]) + timedelta(days=7),
        )
        self.assertFalse(repeated["granted"])
        self.assertEqual(repeated["reason"], "already_granted")

    def test_promotion_reserves_distinct_codes_and_remembers_home_suppression(self):
        now = datetime(2026, 11, 7, 12, tzinfo=UTC)
        first = self.repository.promotion_availability("user-a", now=now)
        second = self.repository.promotion_availability("user-b", now=now)

        self.assertTrue(first["available"])
        self.assertTrue(second["available"])
        self.assertNotEqual(first["promotion"]["code"], second["promotion"]["code"])
        self.repository.dismiss_promotion_on_home(
            "user-a", first["promotion"]["slug"], True
        )
        hidden = self.repository.promotion_availability("user-a", now=now)
        self.assertFalse(hidden["promotion"]["show_on_home"])
        self.assertTrue(hidden["promotion"]["show_on_paywall"])

    def test_prior_purchase_blocks_promotion(self):
        self.repository.record_iap_telemetry_event(
            "buyer",
            IAPTelemetryEventCreateRequest(
                event_type="purchase_succeeded",
                product_id="pro_month",
                status="succeeded",
            ),
        )
        result = self.repository.promotion_availability(
            "buyer", now=datetime(2026, 11, 7, 12, tzinfo=UTC)
        )
        self.assertFalse(result["available"])
        self.assertEqual(result["reason"], "prior_purchase")

    def test_redemption_is_linked_to_reserved_code_and_user(self):
        now = datetime(2026, 11, 7, 12, tzinfo=UTC)
        offer = self.repository.promotion_availability("user-a", now=now)["promotion"]
        result = self.repository.record_promotion_redemption(
            "user-a",
            offer["slug"],
            PromotionRedemptionRequest(
                product_id="lifetime_unlock",
                transaction_id="tx-123",
                original_transaction_id="tx-123",
                offer_id="black-friday",
                environment="sandbox",
            ),
        )
        codes = self.repository.list_promotion_codes_for_admin(offer["id"])
        redeemed = next(code for code in codes if code["status"] == "redeemed")

        self.assertTrue(result["recorded"])
        self.assertEqual(redeemed["redeemed_by_user_id"], "user-a")
        self.assertEqual(redeemed["transaction_id"], "tx-123")
        self.assertFalse(
            self.repository.promotion_availability("user-a", now=now)["available"]
        )

    def test_admin_panel_uses_token_and_updates_campaign_and_code(self):
        promotion = self.repository.list_promotions_for_admin()[0]
        updated = self.repository.update_promotion_for_admin(
            promotion["id"], PromotionAdminUpdateRequest(enabled=False, cta_en="Use code")
        )
        code = self.repository.list_promotion_codes_for_admin(promotion["id"], limit=1)[0]
        disabled = self.repository.update_promotion_code_for_admin(
            promotion["id"], code["id"], False
        )

        self.assertFalse(updated["enabled"])
        self.assertEqual(updated["cta_en"], "Use code")
        self.assertFalse(disabled["enabled"])

        with TestClient(create_app(self.settings)) as client:
            self.assertEqual(client.get("/admin/promotions").status_code, 200)
            self.assertEqual(client.get("/admin/promotions/api").status_code, 401)
            response = client.get(
                "/admin/promotions/api", headers={"X-Admin-Token": "secret"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()[0]["slug"], "black-friday-2026")
            codes_response = client.get(
                f"/admin/promotions/{promotion['id']}/codes",
                headers={"X-Admin-Token": "secret"},
            )
            self.assertEqual(codes_response.headers["cache-control"], "no-store, private")

    def test_admin_can_create_reusable_campaign_and_import_codes(self):
        created = self.repository.create_promotion_for_admin(
            PromotionAdminCreateRequest(
                slug="summer-2027",
                name="Summer 2027",
                product_id="lifetime_unlock",
                starts_at="2027-01-01T00:00:00+00:00",
                ends_at="2027-02-01T00:00:00+00:00",
            )
        )
        result = self.repository.import_promotion_codes_for_admin(
            created["id"],
            PromotionCodeImportRequest(
                codes=[
                    PromotionCodeImportItem(
                        code="SUMMER-ONE",
                        redeem_url="https://apps.apple.com/redeem?code=SUMMER-ONE",
                    )
                ]
            ),
        )

        self.assertFalse(created["enabled"])
        self.assertEqual(result, {"imported": 1, "updated": 0})
        self.assertEqual(
            self.repository.list_promotion_codes_for_admin(created["id"])[0]["code"],
            "SUMMER-ONE",
        )


if __name__ == "__main__":
    unittest.main()
