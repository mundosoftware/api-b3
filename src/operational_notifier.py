import logging
import threading
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests

from src.config import Settings, get_settings


class OperationalNotifier:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.universal_notifier_enabled

    @property
    def configured(self) -> bool:
        return self.enabled and bool(self.settings.universal_notifier_url)

    def health_status(self) -> dict[str, object]:
        status: dict[str, object] = {
            "enabled": self.enabled,
            "configured": self.configured,
            "reachable": False,
            "ready": False,
        }
        if not self.configured:
            status["reason"] = "disabled" if not self.enabled else "not_configured"
            return status

        try:
            response = requests.get(
                self._readiness_url(),
                headers=self._auth_headers(),
                timeout=self.settings.universal_notifier_timeout_seconds,
            )
            status["reachable"] = True
            status["ready"] = response.status_code == 200
            if response.status_code != 200:
                status["reason"] = f"http_{response.status_code}"
            return status
        except requests.Timeout:
            status["reason"] = "timeout"
        except requests.RequestException:
            status["reason"] = "unreachable"
        return status

    def notify_later(
        self,
        event: str,
        severity: str,
        title: str,
        message: str,
        subject: dict[str, str] | None = None,
        dedupe_key: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not self.enabled:
            return
        payload = {
            "system": "trade-alert",
            "event": event,
            "severity": severity,
            "title": title,
            "message": message,
            "occurredAt": datetime.now(UTC).isoformat(),
            "subject": subject,
            "dedupeKey": dedupe_key,
            "metadata": metadata or {},
        }
        threading.Thread(target=self._send, args=(payload,), daemon=True).start()

    def _send(self, payload: dict[str, Any]) -> None:
        headers = self._auth_headers()
        headers["Content-Type"] = "application/json"
        try:
            response = requests.post(
                self.settings.universal_notifier_url,
                json=payload,
                headers=headers,
                timeout=self.settings.universal_notifier_timeout_seconds,
            )
            response.raise_for_status()
        except Exception as exc:
            logging.warning("universal_notifier_delivery_failed reason=%s", str(exc)[:256])

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.settings.universal_notifier_http_token:
            headers["Authorization"] = f"Bearer {self.settings.universal_notifier_http_token}"
        return headers

    def _readiness_url(self) -> str:
        parsed = urlsplit(self.settings.universal_notifier_url)
        return urlunsplit((parsed.scheme, parsed.netloc, "/readyz", "", ""))
