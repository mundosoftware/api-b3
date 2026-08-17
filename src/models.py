from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


Metric = Literal["price", "percent"]
Operator = Literal["gte", "lte"]


class CompanyOut(BaseModel):
    ticker: str
    name: str
    asset_type: str
    logo: str | None = None
    last_price: float | None = None
    daily_change_percent: float | None = None
    updated_at: str | None = None


class CompanyListOut(BaseModel):
    result: list[CompanyOut]


class QuoteOut(CompanyOut):
    pass


class UserUpsertRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=80)


class UserOut(BaseModel):
    user_id: str
    display_name: str | None = None
    timezone: str
    created_at: str
    updated_at: str


class DeviceRegistrationRequest(BaseModel):
    apns_token: str = Field(min_length=16, max_length=512)
    environment: Literal["development", "production"] = "production"
    language: Literal["pt", "en"] = "pt"
    device_model: str | None = Field(default=None, max_length=80)
    device_os: str | None = Field(default=None, max_length=40)
    app_version: str | None = Field(default=None, max_length=40)


class IOSDeviceRegistrationRequest(BaseModel):
    onesignal_subscription_id: str = Field(min_length=16, max_length=128)
    language: Literal["pt", "en"] = "pt"
    device_model: str | None = Field(default=None, max_length=80)
    device_os: str | None = Field(default=None, max_length=40)
    app_version: str | None = Field(default=None, max_length=40)


class DeviceRegistrationOut(BaseModel):
    user_id: str
    onesignal_configured: bool
    onesignal_subscription_id: str | None = None


class DeviceUnregisterRequest(BaseModel):
    onesignal_subscription_id: str | None = Field(default=None, min_length=1, max_length=128)
    apns_token: str | None = Field(default=None, min_length=16, max_length=512)

    @model_validator(mode="after")
    def validate_identifier(self):
        if self.onesignal_subscription_id is None and self.apns_token is None:
            raise ValueError("onesignal_subscription_id or apns_token is required")
        return self


class DeviceUnregisterOut(BaseModel):
    user_id: str
    platform: Literal["ios", "watchos"]
    removed_devices: int
    onesignal_deleted: int
    onesignal_errors: list[str] = Field(default_factory=list)


class NotificationPreferencesUpdateRequest(BaseModel):
    ios_enabled: bool | None = None
    watchos_enabled: bool | None = None


class NotificationPreferencesOut(BaseModel):
    user_id: str
    ios_enabled: bool
    watchos_enabled: bool
    ios_registered: bool
    watchos_registered: bool
    updated_at: str


class FavoriteOut(BaseModel):
    ticker: str
    created_at: str
    company: CompanyOut


class FavoriteListOut(BaseModel):
    result: list[FavoriteOut]


class FavoriteCreateRequest(BaseModel):
    ticker: str


class AlertRuleCreateRequest(BaseModel):
    ticker: str
    metric: Metric
    operator: Operator
    threshold: float
    baseline_price: float | None = None
    weekdays: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    start_time: str = Field(default="10:00", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(default="18:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str | None = Field(default=None, max_length=80)
    frequency_minutes: int = Field(default=15, ge=1, le=1440)
    cooldown_minutes: int = Field(default=60, ge=0, le=10080)
    enabled: bool = True

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("at least one weekday is required")
        invalid = [day for day in value if day < 1 or day > 7]
        if invalid:
            raise ValueError("weekdays must use ISO values from 1 to 7")
        return sorted(set(value))


class AlertRuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    metric: Metric | None = None
    operator: Operator | None = None
    threshold: float | None = None
    baseline_price: float | None = None
    weekdays: list[int] | None = None
    start_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str | None = Field(default=None, max_length=80)
    frequency_minutes: int | None = Field(default=None, ge=1, le=1440)
    cooldown_minutes: int | None = Field(default=None, ge=0, le=10080)

    @field_validator("weekdays")
    @classmethod
    def validate_optional_weekdays(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("at least one weekday is required")
        invalid = [day for day in value if day < 1 or day > 7]
        if invalid:
            raise ValueError("weekdays must use ISO values from 1 to 7")
        return sorted(set(value))


class AlertRuleOut(BaseModel):
    id: int
    user_id: str
    ticker: str
    enabled: bool
    metric: Metric
    operator: Operator
    threshold: float
    baseline_price: float | None = None
    weekdays: list[int]
    start_time: str
    end_time: str
    timezone: str
    frequency_minutes: int
    cooldown_minutes: int
    last_checked_at: str | None = None
    last_triggered_at: str | None = None
    last_price: float | None = None
    last_percent_change: float | None = None
    created_at: str
    updated_at: str


class AlertRuleListOut(BaseModel):
    result: list[AlertRuleOut]


class RunChecksOut(BaseModel):
    checked_tickers: int
    evaluated_rules: int
    triggered_rules: int
    notifications_sent: int


class AlertTelemetryStatusOut(BaseModel):
    id: int
    user_id: str
    ticker: str
    enabled: bool
    due: bool
    reason: str
    message: str
    timezone: str
    timezone_fallback: bool
    server_time: str
    local_time: str
    start_time: str
    end_time: str
    weekdays: list[int]
    frequency_minutes: int
    cooldown_minutes: int
    last_checked_at: str | None = None
    last_triggered_at: str | None = None


class AlertTelemetryStatusListOut(BaseModel):
    result: list[AlertTelemetryStatusOut]


class AlertRunLogOut(BaseModel):
    id: int
    run_id: str
    started_at: str
    finished_at: str | None = None
    status: str
    checked_tickers: int
    evaluated_rules: int
    triggered_rules: int
    notifications_sent: int
    failure_reason: str | None = None


class AlertRunLogListOut(BaseModel):
    result: list[AlertRunLogOut]


class AlertEventLogOut(BaseModel):
    id: int
    run_id: str | None = None
    user_id: str
    alert_rule_id: int | None = None
    ticker: str
    event_type: str
    reason: str
    message: str
    rule_timezone: str | None = None
    server_time: str | None = None
    local_time: str | None = None
    price: float | None = None
    percent_change: float | None = None
    created_at: str


class AlertEventLogListOut(BaseModel):
    result: list[AlertEventLogOut]


class NotificationLogOut(BaseModel):
    id: int
    user_id: str
    alert_rule_id: int | None = None
    ticker: str
    title: str
    body: str
    onesignal_notification_id: str | None = None
    status: str
    created_at: str


class NotificationLogListOut(BaseModel):
    result: list[NotificationLogOut]


class IAPTelemetryEventCreateRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    product_id: str | None = Field(default=None, max_length=128)
    product_type: str | None = Field(default=None, max_length=64)
    subscription_group_id: str | None = Field(default=None, max_length=128)
    transaction_id: str | None = Field(default=None, max_length=128)
    original_transaction_id: str | None = Field(default=None, max_length=128)
    offer_id: str | None = Field(default=None, max_length=128)
    offer_type: str | None = Field(default=None, max_length=64)
    storefront: str | None = Field(default=None, max_length=16)
    currency_code: str | None = Field(default=None, max_length=8)
    display_price: str | None = Field(default=None, max_length=32)
    price: float | None = Field(default=None, ge=0)
    trial_days: int | None = Field(default=None, ge=0, le=366)
    status: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=128)
    message: str | None = Field(default=None, max_length=512)
    platform: str | None = Field(default="ios", max_length=16)
    environment: str | None = Field(default=None, max_length=32)
    app_version: str | None = Field(default=None, max_length=40)
    device_model: str | None = Field(default=None, max_length=80)
    device_os: str | None = Field(default=None, max_length=40)
    language: str | None = Field(default=None, max_length=16)
    occurred_at: str | None = Field(default=None, max_length=40)


class IAPTelemetryEventOut(IAPTelemetryEventCreateRequest):
    id: int
    user_id: str
    created_at: str


class IAPTelemetryEventListOut(BaseModel):
    result: list[IAPTelemetryEventOut]


class IAPTelemetryCountOut(BaseModel):
    name: str
    count: int


class IAPTelemetryProductSummaryOut(BaseModel):
    product_id: str | None = None
    event_type: str
    status: str | None = None
    count: int


class IAPTelemetrySummaryOut(BaseModel):
    window_hours: int
    user_id: str | None = None
    product_id: str | None = None
    total_events: int
    by_event_type: list[IAPTelemetryCountOut]
    by_product: list[IAPTelemetryProductSummaryOut]
    latest_events: list[IAPTelemetryEventOut]


class IAPPayingUserOut(BaseModel):
    user_id: str
    product_id: str | None = None
    product_type: str | None = None
    transaction_id: str | None = None
    original_transaction_id: str | None = None
    offer_id: str | None = None
    offer_type: str | None = None
    storefront: str | None = None
    currency_code: str | None = None
    display_price: str | None = None
    price: float | None = None
    status: str | None = None
    event_type: str
    platform: str | None = None
    environment: str | None = None
    app_version: str | None = None
    first_success_at: str
    latest_success_at: str


class IAPPayingUserListOut(BaseModel):
    result: list[IAPPayingUserOut]


class IAPTelemetryOutcomeOut(BaseModel):
    outcome: str
    product_id: str | None = None
    product_type: str | None = None
    event_type: str
    status: str | None = None
    reason: str | None = None
    sample_message: str | None = None
    count: int
    latest_at: str


class IAPTelemetryOutcomeListOut(BaseModel):
    result: list[IAPTelemetryOutcomeOut]


class DeviceTelemetryOut(BaseModel):
    id: int
    user_id: str
    platform: str
    environment: str
    has_apns_token: bool
    apns_token_tail: str | None = None
    has_onesignal_subscription: bool
    onesignal_subscription_id_tail: str | None = None
    device_model: str | None = None
    device_os: str | None = None
    app_version: str | None = None
    created_at: str
    last_seen_at: str


class DeviceTelemetryListOut(BaseModel):
    result: list[DeviceTelemetryOut]


class TelemetryFailureOut(BaseModel):
    source: str
    user_id: str
    alert_rule_id: int | None = None
    ticker: str
    reason: str
    message: str
    created_at: str


class TelemetryFailureListOut(BaseModel):
    result: list[TelemetryFailureOut]
