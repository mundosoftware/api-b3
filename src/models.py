from typing import Literal

from pydantic import BaseModel, Field, field_validator


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
    device_model: str | None = Field(default=None, max_length=80)
    device_os: str | None = Field(default=None, max_length=40)
    app_version: str | None = Field(default=None, max_length=40)


class IOSDeviceRegistrationRequest(BaseModel):
    onesignal_subscription_id: str = Field(min_length=16, max_length=128)
    device_model: str | None = Field(default=None, max_length=80)
    device_os: str | None = Field(default=None, max_length=40)
    app_version: str | None = Field(default=None, max_length=40)


class DeviceRegistrationOut(BaseModel):
    user_id: str
    onesignal_configured: bool
    onesignal_subscription_id: str | None = None


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
