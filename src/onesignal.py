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


class OneSignalClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def configured(self) -> bool:
        return self.settings.onesignal_configured

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
        if not self.configured:
            return OneSignalRegistration(subscription_id=None, raw_response={"skipped": "not_configured"})

        body: dict[str, Any] = {
            "app_id": self.settings.onesignal_app_id,
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
                "Authorization": f"Basic {self.settings.onesignal_rest_api_key}",
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
    ) -> OneSignalNotification:
        if not self.configured:
            return OneSignalNotification(notification_id=None, raw_response={"skipped": "not_configured"})

        payload = {
            "app_id": self.settings.onesignal_app_id,
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
                "Authorization": f"Key {self.settings.onesignal_rest_api_key}",
                "Content-Type": "application/json",
            },
            timeout=8,
        )
        if response.status_code >= 400:
            raise OneSignalError(f"OneSignal push failed: {response.status_code} {response.text}")
        payload = response.json()
        return OneSignalNotification(notification_id=payload.get("id"), raw_response=payload)

    def _localized_text(self, value: str | Mapping[str, str]) -> dict[str, str]:
        if isinstance(value, str):
            return {"en": value, "pt": value}

        localized = dict(value)
        fallback = localized.get("pt") or localized.get("en") or next(iter(localized.values()), "")
        localized.setdefault("pt", fallback)
        localized.setdefault("en", fallback)
        return localized
