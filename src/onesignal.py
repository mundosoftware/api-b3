from dataclasses import dataclass
from collections.abc import Mapping, Sequence
from typing import Any

import requests

from src.config import Settings, get_settings


class OneSignalError(RuntimeError):
    pass


@dataclass
class OneSignalRegistration:
    subscription_id: str | None
    raw_response: dict[str, Any]


@dataclass
class OneSignalNotification:
    notification_id: str | None
    raw_response: dict[str, Any]
    invalid_subscription_ids: tuple[str, ...] = ()
    all_targeted_subscriptions_invalid: bool = False


@dataclass(frozen=True)
class OneSignalAppConfig:
    app_id: str
    rest_api_key: str


class OneSignalClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return self.settings.onesignal_configured

    @property
    def ios_configured(self) -> bool:
        return self.settings.onesignal_ios_configured

    @property
    def watchos_configured(self) -> bool:
        return self.settings.onesignal_watch_configured

    def register_watch_device(
        self,
        user_id: str,
        apns_token: str,
        environment: str,
        language: str = "pt",
        device_model: str | None = None,
        device_os: str | None = None,
        app_version: str | None = None,
    ) -> OneSignalRegistration:
        config = self._app_config("watchos")
        if not config:
            return OneSignalRegistration(subscription_id=None, raw_response={"skipped": "not_configured"})

        body: dict[str, Any] = {
            "app_id": config.app_id,
            "identifier": apns_token,
            "device_type": 0,
            "external_user_id": user_id,
            "notification_types": 1,
            "language": language,
        }
        if environment == "development":
            body["test_type"] = 1
        if device_model:
            body["device_model"] = device_model
        if device_os:
            body["device_os"] = device_os
        if app_version:
            body["game_version"] = app_version

        response = requests.post(
            "https://onesignal.com/api/v1/players",
            json=body,
            headers={
                "Authorization": f"Basic {config.rest_api_key}",
                "Content-Type": "application/json",
            },
            timeout=8,
        )
        if response.status_code >= 400:
            raise OneSignalError(f"OneSignal registration failed: {response.status_code} {response.text}")
        payload = response.json()
        return OneSignalRegistration(subscription_id=payload.get("id"), raw_response=payload)

    def send_push_to_user(
        self,
        user_id: str,
        title: str | Mapping[str, str],
        body: str | Mapping[str, str],
        data: dict[str, Any] | None = None,
        subscription_ids: Sequence[str] | None = None,
        platform: str = "ios",
    ) -> OneSignalNotification:
        config = self._app_config(platform)
        if not config:
            return OneSignalNotification(notification_id=None, raw_response={"skipped": "not_configured"})

        payload = {
            "app_id": config.app_id,
            "target_channel": "push",
            "headings": self._localized_text(title),
            "contents": self._localized_text(body),
            "data": data or {},
        }
        if subscription_ids is not None:
            payload["include_subscription_ids"] = list(subscription_ids)
        else:
            payload["include_aliases"] = {"external_id": [user_id]}
        response = requests.post(
            "https://api.onesignal.com/notifications?c=push",
            json=payload,
            headers={
                "Authorization": f"Key {config.rest_api_key}",
                "Content-Type": "application/json",
            },
            timeout=8,
        )
        if response.status_code >= 400:
            raise OneSignalError(f"OneSignal push failed: {response.status_code} {response.text}")
        payload = response.json()
        invalid_subscription_ids = self._invalid_subscription_ids(payload)
        return OneSignalNotification(
            notification_id=payload.get("id"),
            raw_response=payload,
            invalid_subscription_ids=invalid_subscription_ids,
            all_targeted_subscriptions_invalid=self._all_targeted_subscriptions_invalid(
                payload, subscription_ids
            ),
        )

    def delete_subscription(self, subscription_id: str, platform: str = "ios") -> bool:
        config = self._app_config(platform)
        if not config:
            return False

        response = requests.delete(
            f"https://api.onesignal.com/apps/{config.app_id}/subscriptions/{subscription_id}",
            headers={
                "Authorization": f"Key {config.rest_api_key}",
                "Content-Type": "application/json",
            },
            timeout=8,
        )
        if response.status_code == 404:
            return False
        if response.status_code >= 400:
            raise OneSignalError(
                f"OneSignal subscription delete failed: {response.status_code} {response.text}"
            )
        return True

    def _app_config(self, platform: str) -> OneSignalAppConfig | None:
        if platform == "ios":
            if self.settings.onesignal_ios_configured:
                return OneSignalAppConfig(
                    app_id=self.settings.onesignal_app_id or "",
                    rest_api_key=self.settings.onesignal_rest_api_key or "",
                )
            return None

        if platform == "watchos":
            if self.settings.onesignal_watch_configured:
                return OneSignalAppConfig(
                    app_id=self.settings.onesignal_watch_app_id or "",
                    rest_api_key=self.settings.onesignal_watch_rest_api_key or "",
                )
            return None

        raise ValueError(f"unsupported OneSignal platform: {platform}")

    def _localized_text(self, value: str | Mapping[str, str]) -> dict[str, str]:
        if isinstance(value, str):
            return {"en": value, "pt": value}

        localized = dict(value)
        fallback = localized.get("pt") or localized.get("en") or next(iter(localized.values()), "")
        localized.setdefault("pt", fallback)
        localized.setdefault("en", fallback)
        return localized

    def _invalid_subscription_ids(self, payload: dict[str, Any]) -> tuple[str, ...]:
        values: list[str] = []
        self._collect_invalid_subscription_ids(payload.get("errors"), values)
        self._collect_invalid_subscription_ids(payload.get("warnings"), values)
        return tuple(dict.fromkeys(value for value in values if value))

    def _collect_invalid_subscription_ids(self, value: Any, values: list[str]) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized_key = str(key).lower()
                if normalized_key in {"invalid_subscription_ids", "invalid_player_ids"}:
                    values.extend(self._string_values(nested))
                else:
                    self._collect_invalid_subscription_ids(nested, values)
            return

        if isinstance(value, list):
            for item in value:
                self._collect_invalid_subscription_ids(item, values)

    def _string_values(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []

    def _all_targeted_subscriptions_invalid(
        self, payload: dict[str, Any], subscription_ids: Sequence[str] | None
    ) -> bool:
        if not subscription_ids or payload.get("id"):
            return False
        if payload.get("recipients") == 0:
            return True

        errors = str(payload.get("errors", "")).lower()
        return "no valid subscription" in errors or "not subscribed" in errors
