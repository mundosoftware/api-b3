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
    candle_cache_ttl_seconds: int = 3600
    prediction_cache_ttl_seconds: int = 900
    check_loop_seconds: int = 30
    check_loop_enabled: bool = True
    default_timezone: str = "America/Sao_Paulo"
    ai_outlook_global_enabled: bool = True
    kronos_enabled: bool = True
    kronos_required: bool = False
    kronos_repo_path: str | None = None
    kronos_model_name: str = "NeoQuasar/Kronos-base"
    kronos_tokenizer_name: str = "NeoQuasar/Kronos-Tokenizer-base"
    kronos_max_context: int = 512
    kronos_sample_count: int = 4
    kronos_temperature: float = 1.0
    kronos_top_p: float = 0.9
    kronos_device: str | None = None
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
            candle_cache_ttl_seconds=int(
                os.getenv(
                    "CANDLE_CACHE_TTL_SECONDS",
                    cls.model_fields["candle_cache_ttl_seconds"].default,
                )
            ),
            prediction_cache_ttl_seconds=int(
                os.getenv(
                    "PREDICTION_CACHE_TTL_SECONDS",
                    cls.model_fields["prediction_cache_ttl_seconds"].default,
                )
            ),
            check_loop_seconds=int(
                os.getenv("CHECK_LOOP_SECONDS", cls.model_fields["check_loop_seconds"].default)
            ),
            check_loop_enabled=env_bool("CHECK_LOOP_ENABLED", cls.model_fields["check_loop_enabled"].default),
            default_timezone=os.getenv("DEFAULT_TIMEZONE", cls.model_fields["default_timezone"].default),
            ai_outlook_global_enabled=env_bool(
                "AI_OUTLOOK_GLOBAL_ENABLED",
                cls.model_fields["ai_outlook_global_enabled"].default,
            ),
            kronos_enabled=env_bool("KRONOS_ENABLED", cls.model_fields["kronos_enabled"].default),
            kronos_required=env_bool("KRONOS_REQUIRED", cls.model_fields["kronos_required"].default),
            kronos_repo_path=os.getenv("KRONOS_REPO_PATH") or None,
            kronos_model_name=os.getenv(
                "KRONOS_MODEL_NAME",
                cls.model_fields["kronos_model_name"].default,
            ),
            kronos_tokenizer_name=os.getenv(
                "KRONOS_TOKENIZER_NAME",
                cls.model_fields["kronos_tokenizer_name"].default,
            ),
            kronos_max_context=int(
                os.getenv("KRONOS_MAX_CONTEXT", cls.model_fields["kronos_max_context"].default)
            ),
            kronos_sample_count=int(
                os.getenv("KRONOS_SAMPLE_COUNT", cls.model_fields["kronos_sample_count"].default)
            ),
            kronos_temperature=float(
                os.getenv("KRONOS_TEMPERATURE", cls.model_fields["kronos_temperature"].default)
            ),
            kronos_top_p=float(os.getenv("KRONOS_TOP_P", cls.model_fields["kronos_top_p"].default)),
            kronos_device=os.getenv("KRONOS_DEVICE") or None,
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
