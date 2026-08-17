import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query, Response, status
from fastapi.concurrency import run_in_threadpool

from src.alerts import AlertEngine
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
    CompanyListOut,
    DeviceTelemetryListOut,
    DeviceRegistrationOut,
    DeviceRegistrationRequest,
    DeviceUnregisterOut,
    DeviceUnregisterRequest,
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
    NotificationPreferencesOut,
    NotificationPreferencesUpdateRequest,
    NotificationLogListOut,
    QuoteOut,
    RunChecksOut,
    TelemetryFailureListOut,
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
    onesignal = OneSignalClient(settings)
    alert_engine = AlertEngine(repository, ticker_service, onesignal, settings)
    telemetry = TelemetryService(repository, alert_engine)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        init_db(settings)
        task: asyncio.Task | None = None
        if settings.check_loop_enabled:
            task = asyncio.create_task(_check_loop(alert_engine, settings))
        try:
            yield
        finally:
            if task:
                task.cancel()
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
        return {
            "status": "ok",
            "onesignal_configured": onesignal.configured,
            "onesignal_ios_configured": onesignal.ios_configured,
            "onesignal_watchos_configured": onesignal.watchos_configured,
            "check_loop_enabled": settings.check_loop_enabled,
        }

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
