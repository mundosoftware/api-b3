import asyncio
import tempfile
import unittest

from fastapi import HTTPException

from src.application import create_app
from src.config import Settings
from src.database import init_db
from src.models import FeatureFlagUpdateRequest
from src.repositories import Repository


class FeatureFlagsTest(unittest.TestCase):
    def test_ai_outlook_global_flag_uses_config_default_and_can_be_updated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                ai_outlook_global_enabled=False,
            )
            init_db(settings)
            repository = Repository(settings)

            default_flag = repository.get_feature_flag("ai_outlook", True)
            enabled_flag = repository.update_feature_flag("ai_outlook", True)

            self.assertFalse(default_flag["enabled"])
            self.assertTrue(enabled_flag["enabled"])
            self.assertEqual(enabled_flag["updated_by"], "admin")

    def test_admin_can_disable_ai_outlook_and_api_reports_maintenance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                database_path=f"{tmpdir}/app.db",
                check_loop_enabled=False,
                admin_token="secret",
                kronos_enabled=False,
            )
            init_db(settings)
            app = create_app(settings)
            endpoints = {getattr(route, "name", ""): route.endpoint for route in app.routes}

            async def exercise_routes():
                public_default = await endpoints["get_ai_outlook_feature"]()
                try:
                    await endpoints["admin_update_ai_outlook_feature"](
                        FeatureFlagUpdateRequest(enabled=False),
                    )
                except HTTPException as exc:
                    unauthorized_status = exc.status_code
                else:
                    unauthorized_status = None
                disabled = await endpoints["admin_update_ai_outlook_feature"](
                    FeatureFlagUpdateRequest(enabled=False),
                    x_admin_token="secret",
                )
                public_disabled = await endpoints["get_ai_outlook_feature"]()
                health = await endpoints["health"]()
                try:
                    await endpoints["get_company_ai_analysis"]("PETR4")
                except HTTPException as exc:
                    analysis_status = exc.status_code
                else:
                    analysis_status = None
                return (
                    public_default,
                    unauthorized_status,
                    disabled,
                    public_disabled,
                    health,
                    analysis_status,
                )

            (
                public_default,
                unauthorized_status,
                disabled,
                public_disabled,
                health,
                analysis_status,
            ) = asyncio.run(exercise_routes())

            self.assertTrue(public_default.enabled)
            self.assertEqual(unauthorized_status, 401)
            self.assertFalse(disabled.enabled)
            self.assertFalse(public_disabled.enabled)
            self.assertFalse(health["ai_outlook_global_enabled"])
            self.assertEqual(analysis_status, 503)


if __name__ == "__main__":
    unittest.main()
