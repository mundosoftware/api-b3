from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.config import Settings, get_settings
from src.database import parse_iso
from src.models import AlertRuleOut, RunChecksOut
from src.onesignal import OneSignalClient, OneSignalError
from src.repositories import Repository
from src.tickers import QuoteLookupError, TickerService


@dataclass
class Evaluation:
    triggered: bool
    price: float
    percent_change: float | None
    baseline_price: float | None


@dataclass
class DueStatus:
    due: bool
    reason: str
    message: str
    timezone: str
    timezone_fallback: bool
    server_time: datetime
    local_time: datetime


class AlertEngine:
    def __init__(
        self,
        repository: Repository | None = None,
        ticker_service: TickerService | None = None,
        onesignal: OneSignalClient | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self.repository = repository or Repository(self.settings)
        self.ticker_service = ticker_service or TickerService(self.repository, self.settings)
        self.onesignal = onesignal or OneSignalClient(self.settings)

    def run_due_checks(self, now: datetime | None = None) -> RunChecksOut:
        now = self._server_time(now or datetime.now(UTC))
        run_id = uuid4().hex
        checked_tickers = 0
        evaluated_rules = 0
        triggered_rules = 0
        notifications_sent = 0

        self.repository.log_alert_run_started(run_id, self._iso(now))
        try:
            due_rules = [
                rule for rule in self.repository.list_enabled_alerts() if self.is_due(rule, now)
            ]
            rules_by_ticker: dict[str, list[AlertRuleOut]] = defaultdict(list)
            for rule in due_rules:
                rules_by_ticker[rule.ticker].append(rule)

            for ticker, rules in rules_by_ticker.items():
                try:
                    quote = self.ticker_service.quote(ticker, force_refresh=True)
                except QuoteLookupError as exc:
                    for rule in rules:
                        self._log_rule_event(
                            run_id=run_id,
                            rule=rule,
                            now=now,
                            event_type="failure",
                            reason="quote_lookup_failed",
                            message=str(exc),
                        )
                    continue

                checked_tickers += 1
                price = float(quote["last_price"])
                daily_change_percent = quote.get("daily_change_percent")
                for rule in rules:
                    evaluated_rules += 1
                    evaluation = self.evaluate(rule, price, daily_change_percent, now)
                    blocked_by_cooldown = evaluation.triggered and self.in_cooldown(rule, now)
                    should_notify = evaluation.triggered and not blocked_by_cooldown
                    notification_sent = False
                    if blocked_by_cooldown:
                        self._log_rule_event(
                            run_id=run_id,
                            rule=rule,
                            now=now,
                            event_type="suppressed",
                            reason="cooldown",
                            message="alert condition matched but cooldown is still active",
                            price=evaluation.price,
                            percent_change=evaluation.percent_change,
                        )
                    if should_notify:
                        triggered_rules += 1
                        notification_sent = self.notify(rule, evaluation)
                        if notification_sent:
                            notifications_sent += 1
                        else:
                            self._log_rule_event(
                                run_id=run_id,
                                rule=rule,
                                now=now,
                                event_type="failure",
                                reason="notification_not_delivered",
                                message="alert condition matched but no push notification was delivered",
                                price=evaluation.price,
                                percent_change=evaluation.percent_change,
                            )
                    self.repository.mark_alert_checked(
                        alert_id=rule.id,
                        price=evaluation.price,
                        percent_change=evaluation.percent_change,
                        baseline_price=evaluation.baseline_price,
                        triggered=notification_sent,
                        checked_at=self._iso(now),
                    )

            result = RunChecksOut(
                checked_tickers=checked_tickers,
                evaluated_rules=evaluated_rules,
                triggered_rules=triggered_rules,
                notifications_sent=notifications_sent,
            )
            self.repository.finish_alert_run(
                run_id=run_id,
                finished_at=self._iso(datetime.now(UTC)),
                status="success",
                checked_tickers=checked_tickers,
                evaluated_rules=evaluated_rules,
                triggered_rules=triggered_rules,
                notifications_sent=notifications_sent,
            )
            return result
        except Exception as exc:
            self.repository.finish_alert_run(
                run_id=run_id,
                finished_at=self._iso(datetime.now(UTC)),
                status="error",
                checked_tickers=checked_tickers,
                evaluated_rules=evaluated_rules,
                triggered_rules=triggered_rules,
                notifications_sent=notifications_sent,
                failure_reason=str(exc),
            )
            raise

    def is_due(self, rule: AlertRuleOut, now: datetime) -> bool:
        return self.due_status(rule, now).due

    def due_status(self, rule: AlertRuleOut, now: datetime | None = None) -> DueStatus:
        server_now = self._server_time(now or datetime.now(UTC))
        local_now, resolved_timezone, timezone_fallback = self._local_time(server_now, rule.timezone)
        if not rule.enabled:
            return DueStatus(
                due=False,
                reason="disabled",
                message="alert is disabled",
                timezone=resolved_timezone,
                timezone_fallback=timezone_fallback,
                server_time=server_now,
                local_time=local_now,
            )
        if local_now.isoweekday() not in rule.weekdays:
            return DueStatus(
                due=False,
                reason="outside_weekday",
                message=f"local weekday {local_now.isoweekday()} is not enabled",
                timezone=resolved_timezone,
                timezone_fallback=timezone_fallback,
                server_time=server_now,
                local_time=local_now,
            )
        if not self._inside_time_window(local_now.time(), rule.start_time, rule.end_time):
            return DueStatus(
                due=False,
                reason="outside_window",
                message=(
                    f"local time {local_now.strftime('%H:%M')} is outside "
                    f"{rule.start_time}-{rule.end_time}"
                ),
                timezone=resolved_timezone,
                timezone_fallback=timezone_fallback,
                server_time=server_now,
                local_time=local_now,
            )

        last_checked = parse_iso(rule.last_checked_at)
        if not last_checked:
            return DueStatus(
                due=True,
                reason="due",
                message="alert has never been checked",
                timezone=resolved_timezone,
                timezone_fallback=timezone_fallback,
                server_time=server_now,
                local_time=local_now,
            )
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=UTC)
        elapsed = server_now - last_checked
        required = timedelta(minutes=rule.frequency_minutes)
        if elapsed < required:
            remaining = required - elapsed
            return DueStatus(
                due=False,
                reason="frequency_wait",
                message=f"next check is due in {int(remaining.total_seconds())} seconds",
                timezone=resolved_timezone,
                timezone_fallback=timezone_fallback,
                server_time=server_now,
                local_time=local_now,
            )
        return DueStatus(
            due=True,
            reason="due",
            message="alert is inside window and frequency interval elapsed",
            timezone=resolved_timezone,
            timezone_fallback=timezone_fallback,
            server_time=server_now,
            local_time=local_now,
        )

    def evaluate(
        self,
        rule: AlertRuleOut,
        price: float,
        daily_change_percent: float | None,
        now: datetime | None = None,
    ) -> Evaluation:
        if rule.metric == "price":
            triggered = self._compare(price, rule.operator, rule.threshold)
            return Evaluation(
                triggered=triggered,
                price=price,
                percent_change=daily_change_percent,
                baseline_price=rule.baseline_price,
            )

        baseline = rule.baseline_price
        if baseline is None:
            baseline = rule.last_price
        if baseline is None or baseline == 0:
            return Evaluation(
                triggered=False,
                price=price,
                percent_change=0.0,
                baseline_price=price,
            )

        percent_change = ((price - baseline) / baseline) * 100
        triggered = self._compare(percent_change, rule.operator, rule.threshold)
        return Evaluation(
            triggered=triggered,
            price=price,
            percent_change=round(percent_change, 4),
            baseline_price=baseline,
        )

    def in_cooldown(self, rule: AlertRuleOut, now: datetime) -> bool:
        if rule.cooldown_minutes <= 0:
            return False
        last_triggered = parse_iso(rule.last_triggered_at)
        if not last_triggered:
            return False
        if last_triggered.tzinfo is None:
            last_triggered = last_triggered.replace(tzinfo=UTC)
        return now - last_triggered < timedelta(minutes=rule.cooldown_minutes)

    def notify(self, rule: AlertRuleOut, evaluation: Evaluation) -> bool:
        title, body = self._notification_text(rule, evaluation)
        log_title = title["pt"]
        log_body = body["pt"]

        subscription_records: list[dict[str, str]] | None = None
        if self.onesignal.configured:
            subscription_records = self.repository.list_enabled_notification_subscriptions(rule.user_id)
            if not subscription_records:
                self.repository.log_notification(
                    user_id=rule.user_id,
                    alert_rule_id=rule.id,
                    ticker=rule.ticker,
                    title=log_title,
                    body=log_body,
                    status="no_enabled_devices",
                )
                return False

        try:
            notifications: list[object] = []
            removed_devices = 0
            data = {
                "ticker": rule.ticker,
                "alert_rule_id": rule.id,
                "metric": rule.metric,
                "price": evaluation.price,
                "percent_change": evaluation.percent_change,
            }

            if subscription_records is None:
                notifications.append(
                    self.onesignal.send_push_to_user(
                        user_id=rule.user_id,
                        title=title,
                        body=body,
                        data=data,
                    )
                )
            else:
                subscriptions_by_platform: dict[str, list[str]] = defaultdict(list)
                for record in subscription_records:
                    subscriptions_by_platform[record["platform"]].append(record["subscription_id"])

                for platform, subscription_ids in subscriptions_by_platform.items():
                    notification = self.onesignal.send_push_to_user(
                        user_id=rule.user_id,
                        title=title,
                        body=body,
                        subscription_ids=subscription_ids,
                        platform=platform,
                        data=data,
                    )
                    notifications.append(notification)
                    removed_devices += self._cleanup_stale_subscriptions(
                        rule.user_id, notification, subscription_ids, platform
                    )

            notification_ids = [
                notification.notification_id
                for notification in notifications
                if getattr(notification, "notification_id", None)
            ]
            sent = self.onesignal.configured and bool(notification_ids)
            status = "sent" if sent else ("not_delivered" if self.onesignal.configured else "onesignal_disabled")
            if removed_devices:
                status = f"{status}; removed_stale_devices={removed_devices}"
            self.repository.log_notification(
                user_id=rule.user_id,
                alert_rule_id=rule.id,
                ticker=rule.ticker,
                title=log_title,
                body=log_body,
                onesignal_notification_id=",".join(notification_ids) or None,
                status=status,
            )
            return sent
        except OneSignalError as exc:
            self.repository.log_notification(
                user_id=rule.user_id,
                alert_rule_id=rule.id,
                ticker=rule.ticker,
                title=log_title,
                body=log_body,
                status=f"error: {exc}",
            )
            return False

    def _cleanup_stale_subscriptions(
        self,
        user_id: str,
        notification: object,
        attempted_subscription_ids: list[str] | None,
        platform: str,
    ) -> int:
        stale_ids = set(getattr(notification, "invalid_subscription_ids", ()) or ())
        if getattr(notification, "all_targeted_subscriptions_invalid", False):
            stale_ids.update(attempted_subscription_ids or [])
        if not stale_ids:
            return 0

        for subscription_id in stale_ids:
            try:
                self.onesignal.delete_subscription(subscription_id, platform=platform)
            except OneSignalError:
                pass
        return self.repository.delete_devices_by_subscription_ids(
            user_id, sorted(stale_ids), platform=platform
        )

    def _notification_text(
        self, rule: AlertRuleOut, evaluation: Evaluation
    ) -> tuple[dict[str, str], dict[str, str]]:
        title = {
            "pt": f"Alerta {rule.ticker}",
            "en": f"{rule.ticker} alert",
        }

        if rule.metric == "price":
            body = {
                "pt": (
                    f"{rule.ticker} está "
                    f"{'acima de' if rule.operator == 'gte' else 'abaixo de'} "
                    f"{self._format_currency(rule.threshold, 'pt')}: "
                    f"{self._format_currency(evaluation.price, 'pt')}"
                ),
                "en": (
                    f"{rule.ticker} is "
                    f"{'above' if rule.operator == 'gte' else 'below'} "
                    f"{self._format_currency(rule.threshold, 'en')}: "
                    f"{self._format_currency(evaluation.price, 'en')}"
                ),
            }
            return title, body

        percent = evaluation.percent_change or 0.0
        body = {
            "pt": (
                f"{rule.ticker} "
                f"{'subiu' if rule.operator == 'gte' else 'caiu'} "
                f"{self._format_percent(rule.threshold, 'pt')}: "
                f"{self._format_percent(percent, 'pt')}"
            ),
            "en": (
                f"{rule.ticker} moved "
                f"{'up' if rule.operator == 'gte' else 'down'} "
                f"{self._format_percent(rule.threshold, 'en')}: "
                f"{self._format_percent(percent, 'en')}"
            ),
        }
        return title, body

    def _format_currency(self, value: float, language: str) -> str:
        return f"R$ {self._format_decimal(value, language)}"

    def _format_percent(self, value: float, language: str) -> str:
        return f"{self._format_decimal(value, language)}%"

    def _format_decimal(self, value: float, language: str) -> str:
        formatted = f"{value:.2f}"
        if language == "pt":
            return formatted.replace(".", ",")
        return formatted

    def _server_time(self, now: datetime) -> datetime:
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now.astimezone(UTC)

    def _iso(self, value: datetime) -> str:
        return value.replace(microsecond=0).isoformat()

    def _local_time(self, now: datetime, timezone: str) -> tuple[datetime, str, bool]:
        try:
            return now.astimezone(ZoneInfo(timezone)), timezone, False
        except ZoneInfoNotFoundError:
            fallback = self.settings.default_timezone
            return now.astimezone(ZoneInfo(fallback)), fallback, True

    def _log_rule_event(
        self,
        run_id: str,
        rule: AlertRuleOut,
        now: datetime,
        event_type: str,
        reason: str,
        message: str,
        price: float | None = None,
        percent_change: float | None = None,
    ) -> None:
        status = self.due_status(rule, now)
        self.repository.log_alert_event(
            run_id=run_id,
            user_id=rule.user_id,
            alert_rule_id=rule.id,
            ticker=rule.ticker,
            event_type=event_type,
            reason=reason,
            message=message,
            rule_timezone=status.timezone,
            server_time=self._iso(status.server_time),
            local_time=self._iso(status.local_time),
            price=price,
            percent_change=percent_change,
        )

    def _inside_time_window(self, current: time, start: str, end: str) -> bool:
        start_time = self._parse_hhmm(start)
        end_time = self._parse_hhmm(end)
        if start_time <= end_time:
            return start_time <= current <= end_time
        return current >= start_time or current <= end_time

    def _parse_hhmm(self, value: str) -> time:
        hour, minute = value.split(":")
        return time(hour=int(hour), minute=int(minute))

    def _compare(self, value: float, operator: str, threshold: float) -> bool:
        if operator == "gte":
            return value >= threshold
        return value <= threshold
