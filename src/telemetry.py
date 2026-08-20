from datetime import UTC, datetime

from src.alerts import AlertEngine
from src.database import parse_iso
from src.models import AlertTelemetryStatusOut
from src.repositories import Repository


class TelemetryService:
    def __init__(self, repository: Repository, alert_engine: AlertEngine):
        self.repository = repository
        self.alert_engine = alert_engine

    def alert_statuses(
        self,
        user_id: str | None = None,
        ticker: str | None = None,
        enabled: bool | None = None,
        limit: int = 100,
        now: str | None = None,
    ) -> list[AlertTelemetryStatusOut]:
        checked_at = self._parse_now(now)
        alerts = self.repository.list_alerts_for_telemetry(
            user_id=user_id,
            ticker=ticker,
            enabled=enabled,
            limit=limit,
        )
        result: list[AlertTelemetryStatusOut] = []
        for alert in alerts:
            status = self.alert_engine.due_status(alert, checked_at)
            result.append(
                AlertTelemetryStatusOut(
                    id=alert.id,
                    user_id=alert.user_id,
                    ticker=alert.ticker,
                    enabled=alert.enabled,
                    due=status.due,
                    reason=status.reason,
                    message=status.message,
                    timezone=status.timezone,
                    timezone_fallback=status.timezone_fallback,
                    server_time=self._iso(status.server_time),
                    local_time=self._iso(status.local_time),
                    start_time=alert.start_time,
                    end_time=alert.end_time,
                    weekdays=alert.weekdays,
                    frequency_minutes=alert.frequency_minutes,
                    cooldown_minutes=alert.cooldown_minutes,
                    last_checked_at=alert.last_checked_at,
                    last_triggered_at=alert.last_triggered_at,
                )
            )
        return result

    def iap_trial_extension_requests(
        self,
        user_id: str | None = None,
        environment: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return self.repository.list_iap_telemetry_events(
            limit=limit,
            user_id=user_id,
            product_id="trial_7_days",
            event_type="trial_extension_requested",
            environment=environment,
        )

    def _parse_now(self, value: str | None) -> datetime:
        if not value:
            return datetime.now(UTC)
        parsed = parse_iso(value)
        if not parsed:
            return datetime.now(UTC)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _iso(self, value: datetime) -> str:
        return value.replace(microsecond=0).isoformat()
