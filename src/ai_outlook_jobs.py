import asyncio
import logging
from collections import defaultdict
from typing import Any

from src.ai_analysis import DecisionSupportService
from src.config import Settings, get_settings
from src.onesignal import OneSignalClient, OneSignalError
from src.operational_notifier import OperationalNotifier
from src.repositories import Repository


class AIOutlookJobProcessor:
    def __init__(
        self,
        repository: Repository | None = None,
        decision_support: DecisionSupportService | None = None,
        onesignal: OneSignalClient | None = None,
        settings: Settings | None = None,
        operational_notifier: OperationalNotifier | None = None,
    ):
        self.settings = settings or get_settings()
        self.repository = repository or Repository(self.settings)
        self.decision_support = decision_support or DecisionSupportService(
            self.repository,
            self.settings,
        )
        self.onesignal = onesignal or OneSignalClient(self.settings)
        self.operational_notifier = operational_notifier or OperationalNotifier(self.settings)

    def requeue_running_jobs(self) -> int:
        return self.repository.requeue_running_ai_outlook_jobs()

    def notify_succeeded_job(self, job: dict[str, Any]) -> dict[str, Any]:
        if job["status"] != "succeeded":
            return job
        notification_status = self._notify_job(job, succeeded=True)
        return self.repository.update_ai_outlook_job_notification_status(
            job["job_id"],
            notification_status,
        ) or job

    def run_once(self) -> bool:
        job = self.repository.claim_next_ai_outlook_job()
        if job is None:
            return False

        logging.info(
            "ai_outlook_job_started job_id=%s ticker=%s horizon=%s attempt=%s/%s",
            job["job_id"],
            job["ticker"],
            job["horizon"],
            job["attempt_count"],
            job["max_attempts"],
        )
        self.operational_notifier.notify_later(
            event="ai_outlook.attempt",
            severity="info",
            title="AI Outlook job attempt started",
            message="An AI Outlook analysis attempt started.",
            subject={"type": "job", "id": job["job_id"]},
            dedupe_key=f"trade-alert:ai-outlook:{job['job_id']}:attempt:{job['attempt_count']}",
            metadata={
                "ticker": job["ticker"],
                "attempt": job["attempt_count"],
                "max_attempts": job["max_attempts"],
            },
        )
        try:
            result = self.decision_support.analysis(
                job["ticker"],
                interval=job["interval"],
                range_name=job["range"],
                horizon=job["horizon"],
                force_refresh=job["refresh"],
            )
        except Exception as exc:
            logging.exception(
                "ai_outlook_job_attempt_failed job_id=%s ticker=%s attempt=%s/%s",
                job["job_id"],
                job["ticker"],
                job["attempt_count"],
                job["max_attempts"],
            )
            updated = self.repository.fail_ai_outlook_job_attempt(
                job["job_id"],
                failure_reason=str(exc),
                retry_delay_seconds=self.settings.ai_outlook_retry_delay_seconds,
            )
            if updated and updated["status"] == "failed":
                self.operational_notifier.notify_later(
                    event="ai_outlook.failed",
                    severity="error",
                    title="AI Outlook job failed",
                    message="AI Outlook exhausted all retry attempts.",
                    subject={"type": "job", "id": updated["job_id"]},
                    dedupe_key=f"trade-alert:ai-outlook:{updated['job_id']}:failed",
                    metadata={"ticker": updated["ticker"], "attempts": updated["attempt_count"]},
                )
                notification_status = self._notify_job(updated, succeeded=False)
                self.repository.update_ai_outlook_job_notification_status(
                    updated["job_id"],
                    notification_status,
                )
            return True

        completed = self.repository.complete_ai_outlook_job(job["job_id"], result)
        if completed:
            self.operational_notifier.notify_later(
                event="ai_outlook.succeeded",
                severity="success",
                title="AI Outlook job succeeded",
                message="AI Outlook completed successfully.",
                subject={"type": "job", "id": completed["job_id"]},
                dedupe_key=f"trade-alert:ai-outlook:{completed['job_id']}:succeeded",
                metadata={"ticker": completed["ticker"], "provider": result.get("provider", "unknown")},
            )
            notification_status = self._notify_job(completed, succeeded=True)
            self.repository.update_ai_outlook_job_notification_status(
                completed["job_id"],
                notification_status,
            )
            logging.info(
                "ai_outlook_job_succeeded job_id=%s ticker=%s provider=%s",
                completed["job_id"],
                completed["ticker"],
                result.get("provider"),
            )
        return True

    def _notify_job(self, job: dict[str, Any], succeeded: bool) -> str:
        title, body = self._notification_text(job, succeeded)
        data = {
            "type": "ai_outlook",
            "job_id": job["job_id"],
            "ticker": job["ticker"],
            "status": job["status"],
        }

        if not self.onesignal.configured:
            self._log_notification(job, title, body, "onesignal_disabled")
            return "onesignal_disabled"

        subscriptions = self.repository.list_enabled_notification_subscriptions(job["user_id"])
        if not subscriptions:
            self._log_notification(job, title, body, "no_enabled_devices")
            return "no_enabled_devices"

        sent_ids: list[str] = []
        statuses: list[str] = []
        subscriptions_by_platform: dict[str, list[str]] = defaultdict(list)
        for subscription in subscriptions:
            subscriptions_by_platform[subscription["platform"]].append(subscription["subscription_id"])

        for platform, subscription_ids in subscriptions_by_platform.items():
            try:
                notification = self.onesignal.send_push_to_user(
                    user_id=job["user_id"],
                    title=title,
                    body=body,
                    data=data,
                    subscription_ids=subscription_ids,
                    platform=platform,
                )
            except OneSignalError as exc:
                statuses.append(f"{platform}: error: {exc}")
                continue

            notification_id = getattr(notification, "notification_id", None)
            if notification_id:
                sent_ids.append(notification_id)
                statuses.append(f"{platform}: sent")
            else:
                statuses.append(f"{platform}: not_delivered")

        status = "; ".join(statuses) or "not_delivered"
        if sent_ids:
            status = f"sent; {status}"
        self.repository.log_notification(
            user_id=job["user_id"],
            alert_rule_id=None,
            ticker=job["ticker"],
            title=title["pt"],
            body=body["pt"],
            onesignal_notification_id=",".join(sent_ids) or None,
            status=status,
        )
        return status

    def _log_notification(
        self,
        job: dict[str, Any],
        title: dict[str, str],
        body: dict[str, str],
        status: str,
    ) -> None:
        self.repository.log_notification(
            user_id=job["user_id"],
            alert_rule_id=None,
            ticker=job["ticker"],
            title=title["pt"],
            body=body["pt"],
            status=status,
        )

    def _notification_text(
        self, job: dict[str, Any], succeeded: bool
    ) -> tuple[dict[str, str], dict[str, str]]:
        ticker = job["ticker"]
        if succeeded:
            return (
                {
                    "pt": "Perspectiva IA pronta",
                    "en": "AI Outlook is ready",
                },
                {
                    "pt": f"A análise de {ticker} terminou. Abra o app para ver a perspectiva.",
                    "en": f"{ticker} analysis is ready. Open the app to review the outlook.",
                },
            )

        attempts = job["max_attempts"]
        return (
            {
                "pt": "Perspectiva IA não finalizou",
                "en": "AI Outlook did not finish",
            },
            {
                "pt": f"A análise de {ticker} falhou após {attempts} tentativas. Abra o app e tente novamente.",
                "en": f"{ticker} analysis failed after {attempts} attempts. Open the app and try again.",
            },
        )


async def run_ai_outlook_job_loop(
    processor: AIOutlookJobProcessor,
    settings: Settings,
) -> None:
    await asyncio.to_thread(processor.requeue_running_jobs)
    while True:
        try:
            processed = await asyncio.to_thread(processor.run_once)
        except Exception:
            logging.exception("ai_outlook_job_loop failed")
            processed = False

        delay = 0 if processed else max(1, settings.ai_outlook_worker_poll_seconds)
        await asyncio.sleep(delay)
