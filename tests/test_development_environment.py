import tempfile
import unittest

from fastapi.testclient import TestClient

from src.application import create_app
from src.config import Settings


class DevelopmentEnvironmentTest(unittest.TestCase):
    def test_health_and_openapi_identify_prefixed_development_environment(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(
                app_name="B3 Watch API Development",
                app_environment="development",
                api_root_path="/dev",
                database_path=f"{tmpdir}/app-dev.db",
                check_loop_enabled=False,
                ai_outlook_worker_enabled=False,
                kronos_enabled=False,
                onesignal_enabled=False,
            )
            app = create_app(settings)

            with TestClient(app, root_path="/dev") as client:
                health = client.get("/health")
                openapi = client.get("/openapi.json")

            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["environment"], "development")
            self.assertEqual(health.json()["api_root_path"], "/dev")
            self.assertEqual(openapi.status_code, 200)
            self.assertEqual(openapi.json()["info"]["title"], "B3 Watch API Development")
            self.assertEqual(openapi.json()["servers"], [{"url": "/dev"}])


if __name__ == "__main__":
    unittest.main()
