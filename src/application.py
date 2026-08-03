import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

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
    CompanyListOut,
    DeviceRegistrationOut,
    DeviceRegistrationRequest,
    FavoriteCreateRequest,
    FavoriteListOut,
    FavoriteOut,
    IOSDeviceRegistrationRequest,
    NotificationPreferencesOut,
    NotificationPreferencesUpdateRequest,
    QuoteOut,
    RunChecksOut,
    UserOut,
    UserUpsertRequest,
)
from src.onesignal import OneSignalClient, OneSignalError
from src.repositories import Repository
from src.tickers import QuoteLookupError, TickerService


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    repository = Repository(settings)
    ticker_service = TickerService(repository, settings)
    onesignal = OneSignalClient(settings)
    alert_engine = AlertEngine(repository, ticker_service, onesignal, settings)

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
            onesignal_configured=onesignal.configured,
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
            onesignal_configured=onesignal.configured,
            onesignal_subscription_id=request.onesignal_subscription_id,
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
