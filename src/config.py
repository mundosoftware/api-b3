from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


load_dotenv("local.env")


class Settings(BaseModel):
    app_name: str = "B3 Watch API"
    database_path: str = "database/app.db"
    server_host: str = "0.0.0.0"
    server_port: int = 8000
    quote_cache_ttl_seconds: int = 60
    check_loop_seconds: int = 30
    check_loop_enabled: bool = True
    default_timezone: str = "America/Sao_Paulo"
    onesignal_app_id: str | None = None
    onesignal_rest_api_key: str | None = None
    onesignal_watch_app_id: str | None = None
    onesignal_watch_rest_api_key: str | None = None
    onesignal_enabled: bool = True
    admin_token: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        import os

        def env_bool(name: str, default: bool) -> bool:
            value = os.getenv(name)
            if value is None:
                return default
            return value.strip().lower() in {"1", "true", "yes", "on"}

        return cls(
            app_name=os.getenv("APP_NAME", cls.model_fields["app_name"].default),
            database_path=os.getenv("DATABASE_PATH", cls.model_fields["database_path"].default),
            server_host=os.getenv("SERVER_HOST", cls.model_fields["server_host"].default),
            server_port=int(os.getenv("SERVER_PORT", cls.model_fields["server_port"].default)),
            quote_cache_ttl_seconds=int(
                os.getenv(
                    "QUOTE_CACHE_TTL_SECONDS",
                    cls.model_fields["quote_cache_ttl_seconds"].default,
                )
            ),
            check_loop_seconds=int(
                os.getenv("CHECK_LOOP_SECONDS", cls.model_fields["check_loop_seconds"].default)
            ),
            check_loop_enabled=env_bool("CHECK_LOOP_ENABLED", cls.model_fields["check_loop_enabled"].default),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", cls.model_fields["default_timezone"].default),
            onesignal_app_id=os.getenv("ONESIGNAL_APP_ID") or None,
            onesignal_rest_api_key=os.getenv("ONESIGNAL_REST_API_KEY") or None,
            onesignal_watch_app_id=os.getenv("ONESIGNAL_WATCH_APP_ID") or None,
            onesignal_watch_rest_api_key=os.getenv("ONESIGNAL_WATCH_REST_API_KEY") or None,
            onesignal_enabled=env_bool("ONESIGNAL_ENABLED", cls.model_fields["onesignal_enabled"].default),
            admin_token=os.getenv("ADMIN_TOKEN") or None,
        )

    @property
    def database_file(self) -> Path:
        return Path(self.database_path)

    @property
    def onesignal_configured(self) -> bool:
        return self.onesignal_ios_configured or self.onesignal_watch_configured

    @property
    def onesignal_ios_configured(self) -> bool:
        return bool(self.onesignal_app_id and self.onesignal_rest_api_key and self.onesignal_enabled)

    @property
    def onesignal_watch_configured(self) -> bool:
        return bool(
            self.onesignal_watch_app_id
            and self.onesignal_watch_rest_api_key
            and self.onesignal_enabled
        )


@lru_cache
def get_settings() -> Settings:
    return Settings.from_env()
