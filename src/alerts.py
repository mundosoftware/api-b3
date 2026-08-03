from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
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
        now = now or datetime.now(UTC)
        due_rules = [rule for rule in self.repository.list_enabled_alerts() if self.is_due(rule, now)]
        rules_by_ticker: dict[str, list[AlertRuleOut]] = defaultdict(list)
        for rule in due_rules:
            rules_by_ticker[rule.ticker].append(rule)

        checked_tickers = 0
        evaluated_rules = 0
        triggered_rules = 0
        notifications_sent = 0

        for ticker, rules in rules_by_ticker.items():
            try:
                quote = self.ticker_service.quote(ticker, force_refresh=True)
            except QuoteLookupError:
                continue

            checked_tickers += 1
            price = float(quote["last_price"])
            daily_change_percent = quote.get("daily_change_percent")
            for rule in rules:
                evaluated_rules += 1
                evaluation = self.evaluate(rule, price, daily_change_percent, now)
                should_notify = evaluation.triggered and not self.in_cooldown(rule, now)
                notification_sent = False
                if should_notify:
                    triggered_rules += 1
                    notification_sent = self.notify(rule, evaluation)
                    if notification_sent:
                        notifications_sent += 1
                self.repository.mark_alert_checked(
                    alert_id=rule.id,
                    price=evaluation.price,
                    percent_change=evaluation.percent_change,
                    baseline_price=evaluation.baseline_price,
                    triggered=notification_sent,
                )

        return RunChecksOut(
            checked_tickers=checked_tickers,
            evaluated_rules=evaluated_rules,
            triggered_rules=triggered_rules,
            notifications_sent=notifications_sent,
        )

    def is_due(self, rule: AlertRuleOut, now: datetime) -> bool:
        local_now = self._local_time(now, rule.timezone)
        if local_now.isoweekday() not in rule.weekdays:
            return False
        if not self._inside_time_window(local_now.time(), rule.start_time, rule.end_time):
            return False

        last_checked = parse_iso(rule.last_checked_at)
        if not last_checked:
            return True
        if last_checked.tzinfo is None:
            last_checked = last_checked.replace(tzinfo=UTC)
        return now - last_checked >= timedelta(minutes=rule.frequency_minutes)

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

        subscription_ids: list[str] | None = None
        if self.onesignal.configured:
            subscription_ids = self.repository.list_enabled_notification_subscription_ids(rule.user_id)
            if not subscription_ids:
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
            notification = self.onesignal.send_push_to_user(
                user_id=rule.user_id,
                title=title,
                body=body,
                subscription_ids=subscription_ids,
                data={
                    "ticker": rule.ticker,
                    "alert_rule_id": rule.id,
                    "metric": rule.metric,
                    "price": evaluation.price,
                    "percent_change": evaluation.percent_change,
                },
            )
            sent = self.onesignal.configured
            self.repository.log_notification(
                user_id=rule.user_id,
                alert_rule_id=rule.id,
                ticker=rule.ticker,
                title=log_title,
                body=log_body,
                onesignal_notification_id=notification.notification_id,
                status="sent" if sent else "onesignal_disabled",
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

    def _local_time(self, now: datetime, timezone: str) -> datetime:
        try:
            return now.astimezone(ZoneInfo(timezone))
        except ZoneInfoNotFoundError:
            return now.astimezone(ZoneInfo(self.settings.default_timezone))

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
