import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool

from src.ai_analysis import DecisionSupportService, PredictionError
from src.ai_outlook_jobs import AIOutlookJobProcessor, run_ai_outlook_job_loop
from src.alerts import AlertEngine
from src.candles import CandleLookupError, CandleService
from src.config import Settings, get_settings
from src.database import init_db
from src.models import (
    AlertRuleCreateRequest,
    AlertRuleListOut,
    AlertRuleOut,
    AlertRuleUpdateRequest,
    AlertEventLogListOut,
    AlertRunLogListOut,
    AlertTelemetryStatusListOut,
    AIOutlookJobCreateRequest,
    AIOutlookJobListOut,
    AIOutlookJobOut,
    AIOutlookJobStatus,
    AIOutlookUsageSummaryOut,
    CandleInterval,
    CandleListOut,
    CandleRange,
    CompanyListOut,
    DecisionSupportOut,
    DeviceTelemetryListOut,
    DeviceRegistrationOut,
    DeviceRegistrationRequest,
    DeviceUnregisterOut,
    DeviceUnregisterRequest,
    FeatureFlagOut,
    FeatureFlagUpdateRequest,
    FavoriteCreateRequest,
    FavoriteListOut,
    FavoriteOut,
    IOSDeviceRegistrationRequest,
    IAPPayingUserListOut,
    IAPTelemetryEventCreateRequest,
    IAPTelemetryEventListOut,
    IAPTelemetryEventOut,
    IAPTelemetryOutcomeListOut,
    IAPTelemetrySummaryOut,
    IAPTrialAdjustmentOut,
    IAPTrialAdjustmentRequest,
    IAPTrialRequestOut,
    IAPTrialStatusOut,
    IAPTrialTelemetryListOut,
    NotificationPreferencesOut,
    NotificationPreferencesUpdateRequest,
    NotificationLogListOut,
    QuoteOut,
    RunChecksOut,
    TelemetryFailureListOut,
    UserTelemetryListOut,
    UserOut,
    UserUpsertRequest,
)
from src.onesignal import OneSignalClient, OneSignalError
from src.repositories import Repository
from src.telemetry import TelemetryService
from src.tickers import QuoteLookupError, TickerService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    repository = Repository(settings)
    ticker_service = TickerService(repository, settings)
    candle_service = CandleService(repository, settings)
    decision_support = DecisionSupportService(repository, settings, candle_service)
    onesignal = OneSignalClient(settings)
    alert_engine = AlertEngine(repository, ticker_service, onesignal, settings)
    ai_outlook_processor = AIOutlookJobProcessor(
        repository,
        decision_support,
        onesignal,
        settings,
    )
    telemetry = TelemetryService(repository, alert_engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(settings)
        tasks: list[asyncio.Task] = []
        if settings.check_loop_enabled:
            tasks.append(asyncio.create_task(_check_loop(alert_engine, settings)))
        if settings.ai_outlook_worker_enabled:
            tasks.append(asyncio.create_task(run_ai_outlook_job_loop(ai_outlook_processor, settings)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

    def require_admin(x_admin_token: str | None) -> None:
        if settings.admin_token and x_admin_token != settings.admin_token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid admin token")

    @app.get("/health")
    async def health() -> dict[str, object]:
        ai_outlook_enabled = repository.ai_outlook_feature_enabled()
        return {
            "status": "ok",
            "onesignal_configured": onesignal.configured,
            "onesignal_ios_configured": onesignal.ios_configured,
            "onesignal_watchos_configured": onesignal.watchos_configured,
            "check_loop_enabled": settings.check_loop_enabled,
            "ai_outlook_global_enabled": ai_outlook_enabled,
            "ai_outlook_worker_enabled": settings.ai_outlook_worker_enabled,
            "ai_outlook_job_max_attempts": settings.ai_outlook_job_max_attempts,
            "kronos_enabled": settings.kronos_enabled,
        }

    @app.get("/features/ai-outlook", response_model=FeatureFlagOut)
    async def get_ai_outlook_feature() -> FeatureFlagOut:
        return FeatureFlagOut(
            **repository.get_feature_flag(
                "ai_outlook",
                settings.ai_outlook_global_enabled,
            )
        )

    @app.get("/companies/search", response_model=CompanyListOut)
    async def search_companies(
        q: str = Query(default="", max_length=40),
        limit: int = Query(default=25, ge=1, le=200),
    ) -> CompanyListOut:
        return CompanyListOut(result=ticker_service.search(q, limit))

    @app.get("/companies", response_model=CompanyListOut)
    async def list_companies(limit: int = Query(default=100, ge=1, le=200)) -> CompanyListOut:
        return CompanyListOut(result=ticker_service.search(None, limit))

    @app.get("/companies/{ticker}", response_model=QuoteOut)
    async def get_company_quote(
        ticker: str, refresh: bool = Query(default=False)
    ) -> QuoteOut:
        try:
            return QuoteOut(**ticker_service.quote(ticker, force_refresh=refresh))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except QuoteLookupError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.get("/companies/{ticker}/candles", response_model=CandleListOut)
    async def get_company_candles(
        ticker: str,
        interval: CandleInterval = Query(default="1d"),
        range_name: CandleRange = Query(default="2y", alias="range"),
        limit: int = Query(default=512, ge=30, le=5000),
        refresh: bool = Query(default=False),
    ) -> CandleListOut:
        try:
            candles = await run_in_threadpool(
                candle_service.history,
                ticker,
                interval,
                range_name,
                limit,
                refresh,
            )
            return CandleListOut(result=candles)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except CandleLookupError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.get("/companies/{ticker}/ai-analysis", response_model=DecisionSupportOut)
    async def get_company_ai_analysis(
        ticker: str,
        interval: CandleInterval = Query(default="1d"),
        range_name: CandleRange = Query(default="2y", alias="range"),
        horizon: int = Query(default=10, ge=1, le=60),
        refresh: bool = Query(default=False),
    ) -> DecisionSupportOut:
        if not repository.ai_outlook_feature_enabled():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI Outlook is temporarily unavailable",
            )
        try:
            analysis = await run_in_threadpool(
                decision_support.analysis,
                ticker,
                interval,
                range_name,
                horizon,
                refresh,
            )
            return DecisionSupportOut(**analysis)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        except (CandleLookupError, PredictionError) as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.post(
        "/users/{user_id}/ai-outlook/jobs",
        response_model=AIOutlookJobOut,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_ai_outlook_job(
        user_id: str,
        request: AIOutlookJobCreateRequest,
    ) -> AIOutlookJobOut:
        if not repository.ai_outlook_feature_enabled():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI Outlook is temporarily unavailable",
            )
        try:
            active_job = repository.find_active_ai_outlook_job(
                user_id=user_id,
                ticker=request.ticker,
                interval=request.interval,
                range_name=request.range,
                horizon=request.horizon,
            )
            if active_job:
                return AIOutlookJobOut(**active_job)

            cached = None
            if not request.refresh:
                cached = decision_support.cached_analysis(
                    request.ticker,
                    interval=request.interval,
                    horizon=request.horizon,
                )
            job = repository.create_ai_outlook_job(
                user_id=user_id,
                ticker=request.ticker,
                interval=request.interval,
                range_name=request.range,
                horizon=request.horizon,
                refresh=request.refresh,
                max_attempts=settings.ai_outlook_job_max_attempts,
                result=cached,
            )
            return AIOutlookJobOut(**job)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.get("/users/{user_id}/ai-outlook/jobs/{job_id}", response_model=AIOutlookJobOut)
    async def get_ai_outlook_job(user_id: str, job_id: str) -> AIOutlookJobOut:
        job = repository.get_ai_outlook_job(user_id, job_id)
        if not job:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AI Outlook job not found")
        return AIOutlookJobOut(**job)

    @app.put("/users/{user_id}", response_model=UserOut)
    async def upsert_user(user_id: str, request: UserUpsertRequest) -> UserOut:
        return UserOut(**repository.upsert_user(user_id, request.display_name, request.timezone))

    @app.post("/users/{user_id}/devices/watchos", response_model=DeviceRegistrationOut)
    async def register_watch_device(
        user_id: str, request: DeviceRegistrationRequest
    ) -> DeviceRegistrationOut:
        try:
            registration = onesignal.register_watch_device(
                user_id=user_id,
                apns_token=request.apns_token,
                environment=request.environment,
                language=request.language,
                device_model=request.device_model,
                device_os=request.device_os,
                app_version=request.app_version,
            )
        except OneSignalError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
        repository.save_device(
            user_id=user_id,
            platform="watchos",
            device_token=request.apns_token,
            environment=request.environment,
            onesignal_subscription_id=registration.subscription_id,
            device_model=request.device_model,
            device_os=request.device_os,
            app_version=request.app_version,
        )
        return DeviceRegistrationOut(
            user_id=user_id,
            onesignal_configured=onesignal.watchos_configured,
            onesignal_subscription_id=registration.subscription_id,
        )

    @app.post("/users/{user_id}/devices/ios", response_model=DeviceRegistrationOut)
    async def register_ios_device(
        user_id: str, request: IOSDeviceRegistrationRequest
    ) -> DeviceRegistrationOut:
        repository.save_device(
            user_id=user_id,
            platform="ios",
            device_token=request.onesignal_subscription_id,
            environment="production",
            onesignal_subscription_id=request.onesignal_subscription_id,
            device_model=request.device_model,
            device_os=request.device_os,
            app_version=request.app_version,
        )
        return DeviceRegistrationOut(
            user_id=user_id,
            onesignal_configured=onesignal.ios_configured,
            onesignal_subscription_id=request.onesignal_subscription_id,
        )

    @app.post("/users/{user_id}/devices/{platform}/unregister", response_model=DeviceUnregisterOut)
    async def unregister_device(
        user_id: str,
        platform: Literal["ios", "watchos"],
        request: DeviceUnregisterRequest,
    ) -> DeviceUnregisterOut:
        subscription_ids = []
        if request.onesignal_subscription_id:
            subscription_ids.append(request.onesignal_subscription_id)
        subscription_ids.extend(
            repository.list_device_subscription_ids(
                user_id=user_id,
                platform=platform,
                apns_token=request.apns_token,
                onesignal_subscription_id=request.onesignal_subscription_id,
            )
        )
        subscription_ids = list(dict.fromkeys(subscription_ids))

        onesignal_deleted = 0
        onesignal_errors: list[str] = []
        for subscription_id in subscription_ids:
            try:
                if onesignal.delete_subscription(subscription_id, platform=platform):
                    onesignal_deleted += 1
            except OneSignalError as exc:
                onesignal_errors.append(str(exc))

        removed_devices = repository.delete_devices(
            user_id=user_id,
            platform=platform,
            apns_token=request.apns_token,
            subscription_ids=subscription_ids,
        )
        return DeviceUnregisterOut(
            user_id=user_id,
            platform=platform,
            removed_devices=removed_devices,
            onesignal_deleted=onesignal_deleted,
            onesignal_errors=onesignal_errors,
        )

    @app.get("/users/{user_id}/notification-preferences", response_model=NotificationPreferencesOut)
    async def get_notification_preferences(user_id: str) -> NotificationPreferencesOut:
        return NotificationPreferencesOut(**repository.get_notification_preferences(user_id))

    @app.put("/users/{user_id}/notification-preferences", response_model=NotificationPreferencesOut)
    async def update_notification_preferences(
        user_id: str, request: NotificationPreferencesUpdateRequest
    ) -> NotificationPreferencesOut:
        return NotificationPreferencesOut(
            **repository.update_notification_preferences(user_id, request)
        )

    @app.post(
        "/users/{user_id}/iap/telemetry",
        response_model=IAPTelemetryEventOut,
        status_code=status.HTTP_201_CREATED,
    )
    async def record_iap_telemetry(
        user_id: str, request: IAPTelemetryEventCreateRequest
    ) -> IAPTelemetryEventOut:
        return IAPTelemetryEventOut(**repository.record_iap_telemetry_event(user_id, request))

    @app.get("/users/{user_id}/iap/trial", response_model=IAPTrialStatusOut)
    async def get_iap_trial(user_id: str) -> IAPTrialStatusOut:
        return IAPTrialStatusOut(**repository.get_iap_trial(user_id))

    @app.post("/users/{user_id}/iap/trial", response_model=IAPTrialRequestOut)
    async def request_iap_trial(user_id: str) -> IAPTrialRequestOut:
        return IAPTrialRequestOut(**repository.request_iap_trial(user_id))

    @app.get("/users/{user_id}/favorites", response_model=FavoriteListOut)
    async def list_favorites(user_id: str) -> FavoriteListOut:
        return FavoriteListOut(result=repository.list_favorites(user_id))

    @app.post(
        "/users/{user_id}/favorites",
        response_model=FavoriteOut,
        status_code=status.HTTP_201_CREATED,
    )
    async def add_favorite(user_id: str, request: FavoriteCreateRequest) -> FavoriteOut:
        try:
            return FavoriteOut(**repository.add_favorite(user_id, request.ticker))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.delete("/users/{user_id}/favorites/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_favorite(user_id: str, ticker: str) -> Response:
        repository.delete_favorite(user_id, ticker)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.get("/users/{user_id}/alerts", response_model=AlertRuleListOut)
    async def list_alerts(
        user_id: str, ticker: str | None = Query(default=None)
    ) -> AlertRuleListOut:
        return AlertRuleListOut(result=repository.list_alerts(user_id, ticker))

    @app.post(
        "/users/{user_id}/alerts",
        response_model=AlertRuleOut,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_alert(user_id: str, request: AlertRuleCreateRequest) -> AlertRuleOut:
        try:
            return repository.create_alert(user_id, request)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    @app.patch("/users/{user_id}/alerts/{alert_id}", response_model=AlertRuleOut)
    async def update_alert(
        user_id: str, alert_id: int, request: AlertRuleUpdateRequest
    ) -> AlertRuleOut:
        updated = repository.update_alert(user_id, alert_id, request)
        if not updated:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
        return updated

    @app.delete("/users/{user_id}/alerts/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_alert(user_id: str, alert_id: int) -> Response:
        repository.delete_alert(user_id, alert_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @app.post("/admin/run-checks", response_model=RunChecksOut)
    async def run_checks(x_admin_token: str | None = Header(default=None)) -> RunChecksOut:
        require_admin(x_admin_token)
        return await run_in_threadpool(alert_engine.run_due_checks)

    @app.get("/admin/features/ai-outlook", response_model=FeatureFlagOut)
    async def admin_get_ai_outlook_feature(
        x_admin_token: str | None = Header(default=None),
    ) -> FeatureFlagOut:
        require_admin(x_admin_token)
        return FeatureFlagOut(
            **repository.get_feature_flag(
                "ai_outlook",
                settings.ai_outlook_global_enabled,
            )
        )

    @app.put("/admin/features/ai-outlook", response_model=FeatureFlagOut)
    async def admin_update_ai_outlook_feature(
        request: FeatureFlagUpdateRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> FeatureFlagOut:
        require_admin(x_admin_token)
        return FeatureFlagOut(
            **repository.update_feature_flag(
                "ai_outlook",
                request.enabled,
                updated_by="admin",
            )
        )

    @app.get("/admin/telemetry/alert-status", response_model=AlertTelemetryStatusListOut)
    async def telemetry_alert_status(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        ticker: str | None = Query(default=None),
        enabled: bool | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
        now: str | None = Query(default=None),
    ) -> AlertTelemetryStatusListOut:
        require_admin(x_admin_token)
        return AlertTelemetryStatusListOut(
            result=telemetry.alert_statuses(
                user_id=user_id,
                ticker=ticker,
                enabled=enabled,
                limit=limit,
                now=now,
            )
        )

    @app.get("/admin/telemetry/alert-runs", response_model=AlertRunLogListOut)
    async def telemetry_alert_runs(
        x_admin_token: str | None = Header(default=None),
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> AlertRunLogListOut:
        require_admin(x_admin_token)
        return AlertRunLogListOut(
            result=repository.list_alert_run_logs(limit=limit, status=status_filter)
        )

    @app.get("/admin/telemetry/alert-events", response_model=AlertEventLogListOut)
    async def telemetry_alert_events(
        x_admin_token: str | None = Header(default=None),
        event_type: str | None = Query(default=None),
        reason: str | None = Query(default=None),
        user_id: str | None = Query(default=None),
        ticker: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> AlertEventLogListOut:
        require_admin(x_admin_token)
        return AlertEventLogListOut(
            result=repository.list_alert_event_logs(
                limit=limit,
                event_type=event_type,
                reason=reason,
                user_id=user_id,
                ticker=ticker,
            )
        )

    @app.get("/admin/telemetry/notifications", response_model=NotificationLogListOut)
    async def telemetry_notifications(
        x_admin_token: str | None = Header(default=None),
        status_filter: str | None = Query(default=None, alias="status"),
        failures_only: bool = Query(default=False),
        user_id: str | None = Query(default=None),
        ticker: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> NotificationLogListOut:
        require_admin(x_admin_token)
        return NotificationLogListOut(
            result=repository.list_notification_logs(
                limit=limit,
                status=status_filter,
                failures_only=failures_only,
                user_id=user_id,
                ticker=ticker,
            )
        )

    @app.get("/admin/telemetry/ai-outlook/jobs", response_model=AIOutlookJobListOut)
    async def telemetry_ai_outlook_jobs(
        x_admin_token: str | None = Header(default=None),
        status_filter: AIOutlookJobStatus | None = Query(default=None, alias="status"),
        user_id: str | None = Query(default=None),
        ticker: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> AIOutlookJobListOut:
        require_admin(x_admin_token)
        return AIOutlookJobListOut(
            result=repository.list_ai_outlook_jobs(
                limit=limit,
                status=status_filter,
                user_id=user_id,
                ticker=ticker,
            )
        )

    @app.get("/admin/telemetry/ai-outlook/usage", response_model=AIOutlookUsageSummaryOut)
    async def telemetry_ai_outlook_usage(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        ticker: str | None = Query(default=None),
        hours: int = Query(default=24, ge=1, le=8760),
    ) -> AIOutlookUsageSummaryOut:
        require_admin(x_admin_token)
        return AIOutlookUsageSummaryOut(
            **repository.summarize_ai_outlook_usage(
                hours=hours,
                user_id=user_id,
                ticker=ticker,
            )
        )

    @app.get("/admin/telemetry/iap-events", response_model=IAPTelemetryEventListOut)
    async def telemetry_iap_events(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        product_id: str | None = Query(default=None),
        event_type: str | None = Query(default=None),
        status_filter: str | None = Query(default=None, alias="status"),
        environment: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> IAPTelemetryEventListOut:
        require_admin(x_admin_token)
        return IAPTelemetryEventListOut(
            result=repository.list_iap_telemetry_events(
                limit=limit,
                user_id=user_id,
                product_id=product_id,
                event_type=event_type,
                status=status_filter,
                environment=environment,
            )
        )

    @app.get("/admin/telemetry/iap-trial-extension-asks", response_model=IAPTelemetryEventListOut)
    async def telemetry_iap_trial_extension_asks(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        environment: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> IAPTelemetryEventListOut:
        require_admin(x_admin_token)
        return IAPTelemetryEventListOut(
            result=telemetry.iap_trial_extension_requests(
                user_id=user_id, environment=environment, limit=limit
            )
        )

    @app.get("/admin/telemetry/iap-trials", response_model=IAPTrialTelemetryListOut)
    async def telemetry_iap_trials(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        status_filter: Literal["active", "expired", "pending"] | None = Query(
            default=None, alias="status"
        ),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> IAPTrialTelemetryListOut:
        require_admin(x_admin_token)
        return IAPTrialTelemetryListOut(
            result=repository.list_iap_trials(
                limit=limit,
                user_id=user_id,
                status=status_filter,
            )
        )

    @app.post(
        "/admin/telemetry/iap-trials/{user_id}/adjust",
        response_model=IAPTrialAdjustmentOut,
    )
    async def adjust_iap_trial(
        user_id: str,
        request: IAPTrialAdjustmentRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> IAPTrialAdjustmentOut:
        require_admin(x_admin_token)
        try:
            return IAPTrialAdjustmentOut(
                **repository.adjust_iap_trial_period(
                    user_id=user_id,
                    days=request.days,
                    reason=request.reason,
                )
            )
        except ValueError as exc:
            if "not found" in str(exc):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
                ) from exc
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    @app.get("/admin/telemetry/iap-buying-attempts", response_model=IAPTelemetryEventListOut)
    async def telemetry_iap_buying_attempts(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        product_id: str | None = Query(default=None),
        status_filter: str | None = Query(default=None, alias="status"),
        environment: str | None = Query(default=None),
        hours: int | None = Query(default=None, ge=1, le=8760),
        include_restore: bool = Query(default=True),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> IAPTelemetryEventListOut:
        require_admin(x_admin_token)
        return IAPTelemetryEventListOut(
            result=repository.list_iap_buying_attempts(
                limit=limit,
                user_id=user_id,
                product_id=product_id,
                status=status_filter,
                environment=environment,
                hours=hours,
                include_restore=include_restore,
            )
        )

    @app.get("/admin/telemetry/iap-paying-users", response_model=IAPPayingUserListOut)
    async def telemetry_iap_paying_users(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        product_id: str | None = Query(default=None),
        environment: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> IAPPayingUserListOut:
        require_admin(x_admin_token)
        return IAPPayingUserListOut(
            result=repository.list_iap_paying_users(
                limit=limit,
                user_id=user_id,
                product_id=product_id,
                environment=environment,
            )
        )

    @app.get("/admin/telemetry/iap-outcomes", response_model=IAPTelemetryOutcomeListOut)
    async def telemetry_iap_outcomes(
        x_admin_token: str | None = Header(default=None),
        outcome: Literal["all", "success", "failure"] = Query(default="all"),
        user_id: str | None = Query(default=None),
        product_id: str | None = Query(default=None),
        environment: str | None = Query(default=None),
        hours: int = Query(default=24, ge=1, le=8760),
    ) -> IAPTelemetryOutcomeListOut:
        require_admin(x_admin_token)
        return IAPTelemetryOutcomeListOut(
            result=repository.list_iap_telemetry_outcomes(
                outcome=outcome,
                hours=hours,
                user_id=user_id,
                product_id=product_id,
                environment=environment,
            )
        )

    @app.get("/admin/telemetry/iap-summary", response_model=IAPTelemetrySummaryOut)
    async def telemetry_iap_summary(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        product_id: str | None = Query(default=None),
        environment: str | None = Query(default=None),
        hours: int = Query(default=24, ge=1, le=8760),
    ) -> IAPTelemetrySummaryOut:
        require_admin(x_admin_token)
        return IAPTelemetrySummaryOut(
            **repository.summarize_iap_telemetry(
                hours=hours,
                user_id=user_id,
                product_id=product_id,
                environment=environment,
            )
        )

    @app.get("/admin/telemetry/devices", response_model=DeviceTelemetryListOut)
    async def telemetry_devices(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        platform: Literal["ios", "watchos"] | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> DeviceTelemetryListOut:
        require_admin(x_admin_token)
        return DeviceTelemetryListOut(
            result=repository.list_device_telemetry(
                limit=limit,
                user_id=user_id,
                platform=platform,
            )
        )

    @app.get("/admin/telemetry/users", response_model=UserTelemetryListOut)
    async def telemetry_users(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        ai_outlook_enabled: bool | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> UserTelemetryListOut:
        require_admin(x_admin_token)
        return UserTelemetryListOut(
            result=repository.list_user_telemetry(
                limit=limit,
                user_id=user_id,
                ai_outlook_enabled=ai_outlook_enabled,
            )
        )

    @app.get("/admin/telemetry/failures", response_model=TelemetryFailureListOut)
    async def telemetry_failures(
        x_admin_token: str | None = Header(default=None),
        user_id: str | None = Query(default=None),
        ticker: str | None = Query(default=None),
        limit: int = Query(default=100, ge=1, le=500),
    ) -> TelemetryFailureListOut:
        require_admin(x_admin_token)
        return TelemetryFailureListOut(
            result=repository.list_failure_telemetry(
                limit=limit,
                user_id=user_id,
                ticker=ticker,
            )
        )

    # Legacy compatibility routes.
    @app.get("/get-ticker/{ticker}")
    async def legacy_get_ticker(ticker: str) -> dict[str, object]:
        try:
            return {"data": ticker_service.quote(ticker)}
        except QuoteLookupError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    @app.get("/get-tickers")
    async def legacy_get_tickers() -> dict[str, object]:
        return {"result": [{"data": company} for company in ticker_service.search(None, 200)]}

    @app.get("/get-stocks-by-order/{order}")
    async def legacy_get_stocks_by_order(order: str) -> dict[str, object]:
        order_map = {
            "ticker": "ticker",
            "valor_cota": "last_price",
            "valorCota": "last_price",
            "oscilacaoCota": "daily_change_percent",
            "oscilacao_cota": "daily_change_percent",
        }
        sort_key = order_map.get(order)
        if not sort_key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="unsupported order")
        companies = ticker_service.search(None, 200)
        companies.sort(key=lambda item: (item.get(sort_key) is None, item.get(sort_key)))
        return {"result": [{"data": company} for company in companies]}

    return app


async def _check_loop(alert_engine: AlertEngine, settings: Settings) -> None:
    while True:
        await asyncio.sleep(settings.check_loop_seconds)
        try:
            await run_in_threadpool(alert_engine.run_due_checks)
        except Exception:
            logging.exception("background alert check failed")
