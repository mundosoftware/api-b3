import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from src.config import Settings, get_settings
from src.database import Database, normalize_ticker, parse_iso, utc_now_iso
from src.models import (
    AlertRuleCreateRequest,
    AlertRuleOut,
    AlertRuleUpdateRequest,
    IAPTelemetryEventCreateRequest,
    NotificationPreferencesUpdateRequest,
)


def company_from_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "ticker": row["ticker"],
        "name": row["name"],
        "asset_type": row["asset_type"],
        "logo": row["logo"],
        "last_price": row["last_price"],
        "daily_change_percent": row["daily_change_percent"],
        "updated_at": row["updated_at"],
    }


def alert_from_row(row: sqlite3.Row) -> AlertRuleOut:
    weekdays = [int(day) for day in row["weekdays"].split(",") if day]
    return AlertRuleOut(
        id=row["id"],
        user_id=row["user_id"],
        ticker=row["ticker"],
        enabled=bool(row["enabled"]),
        metric=row["metric"],
        operator=row["operator"],
        threshold=row["threshold"],
        baseline_price=row["baseline_price"],
        weekdays=weekdays,
        start_time=row["start_time"],
        end_time=row["end_time"],
        timezone=row["timezone"],
        frequency_minutes=row["frequency_minutes"],
        cooldown_minutes=row["cooldown_minutes"],
        last_checked_at=row["last_checked_at"],
        last_triggered_at=row["last_triggered_at"],
        last_price=row["last_price"],
        last_percent_change=row["last_percent_change"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def identifier_tail(value: str | None) -> str | None:
    if not value:
        return None
    return value[-8:]


IAP_BUYING_ATTEMPT_EVENT_TYPES = (
    "purchase_started",
    "purchase_pending",
    "purchase_succeeded",
    "purchase_failed",
    "purchase_cancelled",
)
IAP_RESTORE_ATTEMPT_EVENT_TYPES = (
    "restore_started",
    "restore_succeeded",
    "restore_failed",
)
IAP_SUCCESS_EVENT_TYPES = (
    "purchase_succeeded",
    "restore_succeeded",
    "entitlement_active",
    "subscription_started",
    "subscription_renewed",
    "transaction_verified",
)
IAP_SUCCESS_STATUSES = (
    "verified",
    "active",
    "entitlement_active",
    "subscribed",
    "paid",
    "trial_active",
    "success",
    "succeeded",
)
IAP_FAILURE_EVENT_TYPES = (
    "product_unavailable",
    "purchase_failed",
    "purchase_cancelled",
    "restore_failed",
    "transaction_unverified",
    "entitlement_inactive",
    "subscription_expired",
    "subscription_cancelled",
    "subscription_revoked",
    "purchase_refunded",
    "refund_succeeded",
)
IAP_FAILURE_STATUSES = (
    "missing",
    "failed",
    "cancelled",
    "unverified",
    "inactive",
    "expired",
    "revoked",
    "refunded",
)
IAP_INACTIVE_EVENT_TYPES = (
    "entitlement_inactive",
    "subscription_expired",
    "subscription_cancelled",
    "subscription_revoked",
    "purchase_refunded",
    "refund_succeeded",
)
IAP_INACTIVE_STATUSES = (
    "inactive",
    "expired",
    "cancelled",
    "revoked",
    "refunded",
    "unverified",
)
IAP_TRIAL_PRODUCT_ID = "trial_7_days"
IAP_TRIAL_DAYS = 7
IAP_TRIAL_REACTIVATION_DELAY = timedelta(hours=24)


class Repository:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.database = Database(self.settings)

    def upsert_user(
        self, user_id: str, display_name: str | None = None, timezone: str | None = None
    ) -> dict[str, Any]:
        now = utc_now_iso()
        insert_timezone = timezone or self.settings.default_timezone
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO users(user_id, display_name, timezone, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, users.display_name),
                    timezone = COALESCE(?, users.timezone),
                    updated_at = excluded.updated_at
                """,
                (user_id, display_name, insert_timezone, now, now, timezone),
            )
            row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row)

    def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_iap_trial(self, user_id: str, now: datetime | None = None) -> dict[str, Any]:
        checked_at = self._coerce_utc(now or datetime.now(UTC)).replace(microsecond=0)
        self.upsert_user(user_id)
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM iap_trials WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                return self._trial_response(None, checked_at)

            trial = self._normalize_iap_trial_status(db, dict(row), checked_at)
            return self._trial_response(trial, checked_at)

    def request_iap_trial(self, user_id: str, now: datetime | None = None) -> dict[str, Any]:
        requested_at = self._coerce_utc(now or datetime.now(UTC)).replace(microsecond=0)
        current = self.get_iap_trial(user_id, requested_at)
        if current["status"] in {"active", "pending"}:
            return current

        if current["request_count"] == 0:
            starts_at = requested_at
            ends_at = starts_at + timedelta(days=IAP_TRIAL_DAYS)
            trial_status = "active"
            next_available_at = None
            message = "Trial activated."
        else:
            starts_at = None
            ends_at = None
            trial_status = "pending"
            next_available_at = requested_at + IAP_TRIAL_REACTIVATION_DELAY
            message = "Trial extension request received; wait for activation."

        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO iap_trials(
                    user_id, product_id, status, starts_at, ends_at,
                    next_available_at, request_count, last_requested_at,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    status = excluded.status,
                    starts_at = excluded.starts_at,
                    ends_at = excluded.ends_at,
                    next_available_at = excluded.next_available_at,
                    request_count = excluded.request_count,
                    last_requested_at = excluded.last_requested_at,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    IAP_TRIAL_PRODUCT_ID,
                    trial_status,
                    starts_at.isoformat() if starts_at else None,
                    ends_at.isoformat() if ends_at else None,
                    next_available_at.isoformat() if next_available_at else None,
                    current["request_count"] + 1,
                    requested_at.isoformat(),
                    requested_at.isoformat(),
                    requested_at.isoformat(),
                ),
            )

        self.record_iap_telemetry_event(
            user_id,
            IAPTelemetryEventCreateRequest(
                event_type=(
                    "trial_started"
                    if trial_status == "active"
                    else "trial_extension_requested"
                ),
                product_id=IAP_TRIAL_PRODUCT_ID,
                product_type="server_trial",
                trial_days=IAP_TRIAL_DAYS,
                status=trial_status,
                message=message,
                platform="ios",
                occurred_at=requested_at.isoformat(),
            ),
        )
        response = self.get_iap_trial(user_id, requested_at)
        response["message"] = message
        return response

    def list_iap_trials(
        self,
        limit: int = 100,
        user_id: str | None = None,
        status: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        checked_at = self._coerce_utc(now or datetime.now(UTC)).replace(microsecond=0)
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        result: list[dict[str, Any]] = []
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM iap_trials
                {where}
                ORDER BY updated_at DESC, user_id
                LIMIT 1000
                """,
                params,
            ).fetchall()
            for row in rows:
                trial = self._normalize_iap_trial_status(db, dict(row), checked_at)
                if status and trial["status"] != status:
                    continue
                result.append(self._trial_response(trial, checked_at, include_user=True))
                if len(result) >= limit:
                    break
        return result

    def adjust_iap_trial_period(
        self,
        user_id: str,
        days: int,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if days == 0:
            raise ValueError("days must not be zero")

        checked_at = self._coerce_utc(now or datetime.now(UTC)).replace(microsecond=0)

        with self.database.connect() as db:
            row = db.execute("SELECT * FROM iap_trials WHERE user_id = ?", (user_id,)).fetchone()
            if row is None:
                raise ValueError("trial not found")

            trial = self._normalize_iap_trial_status(db, dict(row), checked_at)
            previous_ends_at = trial["ends_at"]
            starts_at = parse_iso(trial["starts_at"]) or checked_at
            ends_at = parse_iso(trial["ends_at"])
            status = trial["status"]
            ended = False

            if days > 0:
                if status == "active" and ends_at and ends_at > checked_at:
                    new_ends_at = ends_at + timedelta(days=days)
                else:
                    new_ends_at = checked_at + timedelta(days=days)
                    if not trial["starts_at"]:
                        starts_at = checked_at
                status = "active"
                event_type = "trial_period_extended"
            else:
                if status != "active" or not ends_at or ends_at <= checked_at:
                    new_ends_at = checked_at
                    status = "expired"
                    ended = True
                else:
                    new_ends_at = ends_at + timedelta(days=days)
                    if new_ends_at <= checked_at:
                        new_ends_at = checked_at
                        status = "expired"
                        ended = True
                    else:
                        status = "active"
                event_type = "trial_ended_by_deduction" if ended else "trial_period_deducted"

            db.execute(
                """
                UPDATE iap_trials
                SET status = ?, starts_at = ?, ends_at = ?, next_available_at = NULL, updated_at = ?
                WHERE user_id = ?
                """,
                (
                    status,
                    starts_at.replace(microsecond=0).isoformat(),
                    new_ends_at.replace(microsecond=0).isoformat(),
                    checked_at.isoformat(),
                    user_id,
                ),
            )
            row = db.execute("SELECT * FROM iap_trials WHERE user_id = ?", (user_id,)).fetchone()
            adjusted = dict(row)

        message = (
            f"Adjusted server trial by {days} day(s)."
            if not ended
            else f"Server trial ended after deducting {abs(days)} day(s)."
        )
        self.record_iap_telemetry_event(
            user_id,
            IAPTelemetryEventCreateRequest(
                event_type=event_type,
                product_id=IAP_TRIAL_PRODUCT_ID,
                product_type="server_trial",
                trial_days=abs(days),
                status=status,
                reason=reason or "admin_adjustment",
                message=message,
                platform="admin",
                occurred_at=checked_at.isoformat(),
            ),
        )

        response = self._trial_response(adjusted, checked_at, include_user=True)
        response.update(
            adjustment_days=days,
            previous_ends_at=previous_ends_at,
            new_ends_at=adjusted["ends_at"],
            ended=ended,
            message=message,
        )
        return response

    def _normalize_iap_trial_status(
        self, db: sqlite3.Connection, trial: dict[str, Any], checked_at: datetime
    ) -> dict[str, Any]:
        if trial["status"] == "active" and trial["ends_at"]:
            ends_at = parse_iso(trial["ends_at"])
            if ends_at and checked_at >= self._coerce_utc(ends_at):
                db.execute(
                    "UPDATE iap_trials SET status = 'expired', updated_at = ? WHERE user_id = ?",
                    (checked_at.isoformat(), trial["user_id"]),
                )
                trial["status"] = "expired"
                trial["updated_at"] = checked_at.isoformat()
        elif trial["status"] == "pending" and trial["next_available_at"]:
            next_available_at = parse_iso(trial["next_available_at"])
            if next_available_at and checked_at >= self._coerce_utc(next_available_at):
                starts_at = checked_at
                ends_at = starts_at + timedelta(days=IAP_TRIAL_DAYS)
                db.execute(
                    """
                    UPDATE iap_trials
                    SET status = 'active', starts_at = ?, ends_at = ?,
                        next_available_at = NULL, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        starts_at.isoformat(),
                        ends_at.isoformat(),
                        starts_at.isoformat(),
                        trial["user_id"],
                    ),
                )
                trial.update(
                    status="active",
                    starts_at=starts_at.isoformat(),
                    ends_at=ends_at.isoformat(),
                    next_available_at=None,
                    updated_at=starts_at.isoformat(),
                )
        return trial

    def _trial_response(
        self,
        trial: dict[str, Any] | None,
        checked_at: datetime | None = None,
        include_user: bool = False,
    ) -> dict[str, Any]:
        checked_at = self._coerce_utc(checked_at or datetime.now(UTC)).replace(microsecond=0)
        if trial is None:
            response = {
                "product_id": IAP_TRIAL_PRODUCT_ID,
                "status": "expired",
                "starts_at": None,
                "ends_at": None,
                "next_available_at": None,
                "request_count": 0,
                "can_request": True,
                "current_time": checked_at.isoformat(),
                "elapsed_days": 0,
                "remaining_days": 0,
                "remaining_seconds": 0,
                "total_trial_days": IAP_TRIAL_DAYS,
                "message": None,
            }
            if include_user:
                response.update(
                    user_id="",
                    last_requested_at=None,
                    created_at=None,
                    updated_at=None,
                )
            return response
        status = trial["status"]
        starts_at = parse_iso(trial["starts_at"])
        ends_at = parse_iso(trial["ends_at"])
        elapsed_seconds = 0
        remaining_seconds = 0
        total_seconds = IAP_TRIAL_DAYS * 86400
        if starts_at:
            starts_at = self._coerce_utc(starts_at)
            elapsed_until = min(
                checked_at,
                self._coerce_utc(ends_at) if ends_at else checked_at,
            )
            elapsed_seconds = max(0, int((elapsed_until - starts_at).total_seconds()))
        if ends_at:
            ends_at = self._coerce_utc(ends_at)
            if starts_at:
                total_seconds = max(0, int((ends_at - starts_at).total_seconds()))
            if status == "active":
                remaining_seconds = max(0, int((ends_at - checked_at).total_seconds()))

        response = {
            "product_id": trial["product_id"],
            "status": status,
            "starts_at": trial["starts_at"],
            "ends_at": trial["ends_at"],
            "next_available_at": trial["next_available_at"],
            "request_count": trial["request_count"],
            "can_request": status == "expired",
            "current_time": checked_at.isoformat(),
            "elapsed_days": elapsed_seconds // 86400,
            "remaining_days": (remaining_seconds + 86399) // 86400,
            "remaining_seconds": remaining_seconds,
            "total_trial_days": (total_seconds + 86399) // 86400,
            "message": None,
        }
        if include_user:
            response.update(
                user_id=trial["user_id"],
                last_requested_at=trial["last_requested_at"],
                created_at=trial["created_at"],
                updated_at=trial["updated_at"],
            )
        return response

    def _coerce_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def list_companies(self, query: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        query = (query or "").strip().upper()
        limit = max(1, min(limit, 200))
        with self.database.connect() as db:
            if query:
                rows = db.execute(
                    """
                    SELECT * FROM companies
                    WHERE ticker LIKE ? OR UPPER(name) LIKE ?
                    ORDER BY
                        CASE WHEN ticker = ? THEN 0 WHEN ticker LIKE ? THEN 1 ELSE 2 END,
                        ticker
                    LIMIT ?
                    """,
                    (f"%{query}%", f"%{query}%", query, f"{query}%", limit),
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM companies ORDER BY ticker LIMIT ?", (limit,)).fetchall()
            return [company_from_row(row) for row in rows]

    def get_company(self, ticker: str) -> dict[str, Any] | None:
        normalized = normalize_ticker(ticker)
        with self.database.connect() as db:
            row = db.execute("SELECT * FROM companies WHERE ticker = ?", (normalized,)).fetchone()
            return company_from_row(row) if row else None

    def update_company_quote(
        self,
        ticker: str,
        last_price: float,
        daily_change_percent: float | None,
        name: str | None = None,
        logo: str | None = None,
    ) -> dict[str, Any]:
        return self.upsert_company(
            ticker=ticker,
            name=name,
            logo=logo,
            last_price=last_price,
            daily_change_percent=daily_change_percent,
        )

    def upsert_company(
        self,
        ticker: str,
        name: str | None = None,
        asset_type: str | None = None,
        logo: str | None = None,
        last_price: float | None = None,
        daily_change_percent: float | None = None,
    ) -> dict[str, Any]:
        normalized = normalize_ticker(ticker)
        existing = self.get_company(normalized)
        resolved_asset_type = asset_type or (existing["asset_type"] if existing else "stock")
        updated_at = utc_now_iso() if last_price is not None or daily_change_percent is not None else None
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO companies(ticker, name, asset_type, logo, last_price, daily_change_percent, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name = COALESCE(excluded.name, companies.name),
                    asset_type = COALESCE(excluded.asset_type, companies.asset_type),
                    logo = COALESCE(excluded.logo, companies.logo),
                    last_price = COALESCE(excluded.last_price, companies.last_price),
                    daily_change_percent = COALESCE(
                        excluded.daily_change_percent,
                        companies.daily_change_percent
                    ),
                    updated_at = COALESCE(excluded.updated_at, companies.updated_at)
                """,
                (
                    normalized,
                    name or normalized,
                    resolved_asset_type,
                    logo,
                    last_price,
                    daily_change_percent,
                    updated_at,
                ),
            )
            row = db.execute("SELECT * FROM companies WHERE ticker = ?", (normalized,)).fetchone()
            return company_from_row(row)

    def add_favorite(self, user_id: str, ticker: str) -> dict[str, Any]:
        self.upsert_user(user_id)
        normalized = normalize_ticker(ticker)
        now = utc_now_iso()
        with self.database.connect() as db:
            self._ensure_company(db, normalized)
            db.execute(
                """
                INSERT INTO favorites(user_id, ticker, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, ticker) DO NOTHING
                """,
                (user_id, normalized, now),
            )
            return self._favorite_row(db, user_id, normalized)

    def delete_favorite(self, user_id: str, ticker: str) -> bool:
        normalized = normalize_ticker(ticker)
        with self.database.connect() as db:
            cursor = db.execute(
                "DELETE FROM favorites WHERE user_id = ? AND ticker = ?",
                (user_id, normalized),
            )
            return cursor.rowcount > 0

    def list_favorites(self, user_id: str) -> list[dict[str, Any]]:
        self.upsert_user(user_id)
        with self.database.connect() as db:
            rows = db.execute(
                """
                SELECT f.created_at, c.*
                FROM favorites f
                JOIN companies c ON c.ticker = f.ticker
                WHERE f.user_id = ?
                ORDER BY f.created_at DESC
                """,
                (user_id,),
            ).fetchall()
            return [
                {
                    "ticker": row["ticker"],
                    "created_at": row["created_at"],
                    "company": company_from_row(row),
                }
                for row in rows
            ]

    def create_alert(self, user_id: str, request: AlertRuleCreateRequest) -> AlertRuleOut:
        user = self.upsert_user(user_id, timezone=request.timezone)
        ticker = normalize_ticker(request.ticker)
        now = utc_now_iso()
        weekdays = ",".join(str(day) for day in request.weekdays)
        rule_timezone = request.timezone or user["timezone"] or self.settings.default_timezone
        with self.database.connect() as db:
            self._ensure_company(db, ticker)
            db.execute(
                """
                INSERT INTO alert_rules(
                    user_id, ticker, enabled, metric, operator, threshold, baseline_price,
                    weekdays, start_time, end_time, timezone, frequency_minutes, cooldown_minutes,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    ticker,
                    int(request.enabled),
                    request.metric,
                    request.operator,
                    request.threshold,
                    request.baseline_price,
                    weekdays,
                    request.start_time,
                    request.end_time,
                    rule_timezone,
                    request.frequency_minutes,
                    request.cooldown_minutes,
                    now,
                    now,
                ),
            )
            row = db.execute(
                "SELECT * FROM alert_rules WHERE id = last_insert_rowid()"
            ).fetchone()
            return alert_from_row(row)

    def update_alert(
        self, user_id: str, alert_id: int, request: AlertRuleUpdateRequest
    ) -> AlertRuleOut | None:
        updates: dict[str, Any] = {}
        for field in (
            "enabled",
            "metric",
            "operator",
            "threshold",
            "baseline_price",
            "start_time",
            "end_time",
            "timezone",
            "frequency_minutes",
            "cooldown_minutes",
        ):
            value = getattr(request, field)
            if value is not None:
                updates[field] = int(value) if field == "enabled" else value
        if request.weekdays is not None:
            updates["weekdays"] = ",".join(str(day) for day in request.weekdays)
        if not updates:
            return self.get_alert(user_id, alert_id)
        updates["updated_at"] = utc_now_iso()
        set_clause = ", ".join(f"{field} = ?" for field in updates)
        values = list(updates.values())
        values.extend([user_id, alert_id])
        with self.database.connect() as db:
            cursor = db.execute(
                f"UPDATE alert_rules SET {set_clause} WHERE user_id = ? AND id = ?",
                values,
            )
            if cursor.rowcount == 0:
                return None
            row = db.execute(
                "SELECT * FROM alert_rules WHERE user_id = ? AND id = ?",
                (user_id, alert_id),
            ).fetchone()
            return alert_from_row(row)

    def get_alert(self, user_id: str, alert_id: int) -> AlertRuleOut | None:
        with self.database.connect() as db:
            row = db.execute(
                "SELECT * FROM alert_rules WHERE user_id = ? AND id = ?",
                (user_id, alert_id),
            ).fetchone()
            return alert_from_row(row) if row else None

    def list_alerts(self, user_id: str, ticker: str | None = None) -> list[AlertRuleOut]:
        self.upsert_user(user_id)
        params: list[Any] = [user_id]
        where = "WHERE user_id = ?"
        if ticker:
            where += " AND ticker = ?"
            params.append(normalize_ticker(ticker))
        with self.database.connect() as db:
            rows = db.execute(
                f"SELECT * FROM alert_rules {where} ORDER BY ticker, id DESC",
                params,
            ).fetchall()
            return [alert_from_row(row) for row in rows]

    def delete_alert(self, user_id: str, alert_id: int) -> bool:
        with self.database.connect() as db:
            cursor = db.execute(
                "DELETE FROM alert_rules WHERE user_id = ? AND id = ?",
                (user_id, alert_id),
            )
            return cursor.rowcount > 0

    def list_enabled_alerts(self) -> list[AlertRuleOut]:
        with self.database.connect() as db:
            rows = db.execute(
                "SELECT * FROM alert_rules WHERE enabled = 1 ORDER BY ticker, id"
            ).fetchall()
            return [alert_from_row(row) for row in rows]

    def list_alerts_for_telemetry(
        self,
        user_id: str | None = None,
        ticker: str | None = None,
        enabled: bool | None = None,
        limit: int = 100,
    ) -> list[AlertRuleOut]:
        limit = max(1, min(limit, 500))
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if ticker:
            conditions.append("ticker = ?")
            params.append(normalize_ticker(ticker))
        if enabled is not None:
            conditions.append("enabled = ?")
            params.append(int(enabled))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM alert_rules
                {where}
                ORDER BY updated_at DESC, id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [alert_from_row(row) for row in rows]

    def mark_alert_checked(
        self,
        alert_id: int,
        price: float,
        percent_change: float | None,
        baseline_price: float | None = None,
        triggered: bool = False,
        checked_at: str | None = None,
    ) -> None:
        now = checked_at or utc_now_iso()
        with self.database.connect() as db:
            if triggered:
                db.execute(
                    """
                    UPDATE alert_rules SET
                        last_checked_at = ?,
                        last_triggered_at = ?,
                        last_price = ?,
                        last_percent_change = ?,
                        baseline_price = COALESCE(baseline_price, ?),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, price, percent_change, baseline_price, now, alert_id),
                )
            else:
                db.execute(
                    """
                    UPDATE alert_rules SET
                        last_checked_at = ?,
                        last_price = ?,
                        last_percent_change = ?,
                        baseline_price = COALESCE(baseline_price, ?),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (now, price, percent_change, baseline_price, now, alert_id),
                )

    def save_device(
        self,
        user_id: str,
        platform: str,
        device_token: str,
        environment: str,
        onesignal_subscription_id: str | None,
        device_model: str | None = None,
        device_os: str | None = None,
        app_version: str | None = None,
    ) -> None:
        if platform not in {"ios", "watchos"}:
            raise ValueError("unsupported device platform")
        self.upsert_user(user_id)
        now = utc_now_iso()
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO user_devices(
                    user_id, platform, apns_token, onesignal_subscription_id,
                    environment, device_model, device_os, app_version,
                    created_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, platform, apns_token) DO UPDATE SET
                    onesignal_subscription_id = COALESCE(
                        excluded.onesignal_subscription_id,
                        user_devices.onesignal_subscription_id
                    ),
                    environment = excluded.environment,
                    device_model = COALESCE(excluded.device_model, user_devices.device_model),
                    device_os = COALESCE(excluded.device_os, user_devices.device_os),
                    app_version = COALESCE(excluded.app_version, user_devices.app_version),
                    last_seen_at = excluded.last_seen_at
                """,
                (
                    user_id,
                    platform,
                    device_token,
                    onesignal_subscription_id,
                    environment,
                    device_model,
                    device_os,
                    app_version,
                    now,
                    now,
                ),
            )

    def get_notification_preferences(self, user_id: str) -> dict[str, Any]:
        self.upsert_user(user_id)
        now = utc_now_iso()
        with self.database.connect() as db:
            self._ensure_notification_preferences(db, user_id, now)
            row = db.execute(
                """
                SELECT
                    p.user_id,
                    p.ios_enabled,
                    p.watchos_enabled,
                    p.updated_at,
                    EXISTS(
                        SELECT 1 FROM user_devices d
                        WHERE d.user_id = p.user_id
                            AND d.platform = 'ios'
                            AND d.onesignal_subscription_id IS NOT NULL
                            AND d.onesignal_subscription_id != ''
                    ) AS ios_registered,
                    EXISTS(
                        SELECT 1 FROM user_devices d
                        WHERE d.user_id = p.user_id
                            AND d.platform = 'watchos'
                            AND d.onesignal_subscription_id IS NOT NULL
                            AND d.onesignal_subscription_id != ''
                    ) AS watchos_registered
                FROM notification_preferences p
                WHERE p.user_id = ?
                """,
                (user_id,),
            ).fetchone()
            return self._preference_dict(row)

    def update_notification_preferences(
        self, user_id: str, request: NotificationPreferencesUpdateRequest
    ) -> dict[str, Any]:
        self.upsert_user(user_id)
        now = utc_now_iso()
        with self.database.connect() as db:
            self._ensure_notification_preferences(db, user_id, now)
            if request.ios_enabled is not None or request.watchos_enabled is not None:
                db.execute(
                    """
                    UPDATE notification_preferences SET
                        ios_enabled = COALESCE(?, ios_enabled),
                        watchos_enabled = COALESCE(?, watchos_enabled),
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        None if request.ios_enabled is None else int(request.ios_enabled),
                        None if request.watchos_enabled is None else int(request.watchos_enabled),
                        now,
                        user_id,
                    ),
                )
            row = db.execute(
                """
                SELECT
                    p.user_id,
                    p.ios_enabled,
                    p.watchos_enabled,
                    p.updated_at,
                    EXISTS(
                        SELECT 1 FROM user_devices d
                        WHERE d.user_id = p.user_id
                            AND d.platform = 'ios'
                            AND d.onesignal_subscription_id IS NOT NULL
                            AND d.onesignal_subscription_id != ''
                    ) AS ios_registered,
                    EXISTS(
                        SELECT 1 FROM user_devices d
                        WHERE d.user_id = p.user_id
                            AND d.platform = 'watchos'
                            AND d.onesignal_subscription_id IS NOT NULL
                            AND d.onesignal_subscription_id != ''
                    ) AS watchos_registered
                FROM notification_preferences p
                WHERE p.user_id = ?
                """,
                (user_id,),
            ).fetchone()
            return self._preference_dict(row)

    def list_enabled_notification_subscription_ids(self, user_id: str) -> list[str]:
        return [
            subscription["subscription_id"]
            for subscription in self.list_enabled_notification_subscriptions(user_id)
        ]

    def list_enabled_notification_subscriptions(self, user_id: str) -> list[dict[str, str]]:
        preferences = self.get_notification_preferences(user_id)
        platforms: list[str] = []
        if preferences["ios_enabled"]:
            platforms.append("ios")
        if preferences["watchos_enabled"]:
            platforms.append("watchos")
        if not platforms:
            return []

        placeholders = ",".join("?" for _ in platforms)
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT platform, onesignal_subscription_id
                FROM user_devices
                WHERE user_id = ?
                    AND platform IN ({placeholders})
                    AND onesignal_subscription_id IS NOT NULL
                    AND onesignal_subscription_id != ''
                GROUP BY platform, onesignal_subscription_id
                ORDER BY platform, MAX(last_seen_at) DESC
                """,
                (user_id, *platforms),
            ).fetchall()
            return [
                {
                    "platform": row["platform"],
                    "subscription_id": row["onesignal_subscription_id"],
                }
                for row in rows
            ]

    def list_device_subscription_ids(
        self,
        user_id: str,
        platform: str,
        apns_token: str | None = None,
        onesignal_subscription_id: str | None = None,
    ) -> list[str]:
        conditions = [
            "user_id = ?",
            "platform = ?",
            "onesignal_subscription_id IS NOT NULL",
            "onesignal_subscription_id != ''",
        ]
        params: list[Any] = [user_id, platform]
        identifier_conditions: list[str] = []
        identifier_params: list[Any] = []
        if apns_token is not None:
            identifier_conditions.append("apns_token = ?")
            identifier_params.append(apns_token)
        if onesignal_subscription_id is not None:
            identifier_conditions.append("onesignal_subscription_id = ?")
            identifier_params.append(onesignal_subscription_id)
        if identifier_conditions:
            conditions.append(f"({' OR '.join(identifier_conditions)})")
            params.extend(identifier_params)

        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT DISTINCT onesignal_subscription_id
                FROM user_devices
                WHERE {" AND ".join(conditions)}
                """,
                params,
            ).fetchall()
            return [row["onesignal_subscription_id"] for row in rows]

    def delete_devices(
        self,
        user_id: str,
        platform: str,
        apns_token: str | None = None,
        subscription_ids: Sequence[str] | None = None,
    ) -> int:
        if apns_token is None and not subscription_ids:
            raise ValueError("a device token or subscription id is required")

        conditions = ["user_id = ?", "platform = ?"]
        params: list[Any] = [user_id, platform]
        identifier_conditions: list[str] = []
        identifier_params: list[Any] = []
        if apns_token is not None:
            identifier_conditions.append("apns_token = ?")
            identifier_params.append(apns_token)
        if subscription_ids:
            unique_ids = list(dict.fromkeys(subscription_ids))
            placeholders = ",".join("?" for _ in unique_ids)
            identifier_conditions.append(f"onesignal_subscription_id IN ({placeholders})")
            identifier_params.extend(unique_ids)
        conditions.append(f"({' OR '.join(identifier_conditions)})")
        params.extend(identifier_params)

        with self.database.connect() as db:
            cursor = db.execute(
                f"DELETE FROM user_devices WHERE {' AND '.join(conditions)}",
                params,
            )
            return cursor.rowcount

    def delete_devices_by_subscription_ids(
        self, user_id: str, subscription_ids: Sequence[str], platform: str | None = None
    ) -> int:
        unique_ids = list(
            dict.fromkeys(subscription_id for subscription_id in subscription_ids if subscription_id)
        )
        if not unique_ids:
            return 0

        placeholders = ",".join("?" for _ in unique_ids)
        conditions = ["user_id = ?", f"onesignal_subscription_id IN ({placeholders})"]
        params: list[Any] = [user_id, *unique_ids]
        if platform is not None:
            conditions.append("platform = ?")
            params.append(platform)

        with self.database.connect() as db:
            cursor = db.execute(
                f"""
                DELETE FROM user_devices
                WHERE {" AND ".join(conditions)}
                """,
                params,
            )
            return cursor.rowcount

    def log_notification(
        self,
        user_id: str,
        alert_rule_id: int,
        ticker: str,
        title: str,
        body: str,
        status: str,
        onesignal_notification_id: str | None = None,
    ) -> None:
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO notification_log(
                    user_id, alert_rule_id, ticker, title, body,
                    onesignal_notification_id, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    alert_rule_id,
                    normalize_ticker(ticker),
                    title,
                    body,
                    onesignal_notification_id,
                    status,
                    utc_now_iso(),
                ),
            )

    def log_alert_run_started(self, run_id: str, started_at: str) -> None:
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO alert_run_log(run_id, started_at, status)
                VALUES (?, ?, 'running')
                ON CONFLICT(run_id) DO NOTHING
                """,
                (run_id, started_at),
            )

    def finish_alert_run(
        self,
        run_id: str,
        finished_at: str,
        status: str,
        checked_tickers: int,
        evaluated_rules: int,
        triggered_rules: int,
        notifications_sent: int,
        failure_reason: str | None = None,
    ) -> None:
        with self.database.connect() as db:
            db.execute(
                """
                UPDATE alert_run_log SET
                    finished_at = ?,
                    status = ?,
                    checked_tickers = ?,
                    evaluated_rules = ?,
                    triggered_rules = ?,
                    notifications_sent = ?,
                    failure_reason = ?
                WHERE run_id = ?
                """,
                (
                    finished_at,
                    status,
                    checked_tickers,
                    evaluated_rules,
                    triggered_rules,
                    notifications_sent,
                    failure_reason,
                    run_id,
                ),
            )

    def log_alert_event(
        self,
        user_id: str,
        alert_rule_id: int,
        ticker: str,
        event_type: str,
        reason: str,
        message: str,
        run_id: str | None = None,
        rule_timezone: str | None = None,
        server_time: str | None = None,
        local_time: str | None = None,
        price: float | None = None,
        percent_change: float | None = None,
    ) -> None:
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO alert_event_log(
                    run_id, user_id, alert_rule_id, ticker, event_type,
                    reason, message, rule_timezone, server_time, local_time,
                    price, percent_change, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    user_id,
                    alert_rule_id,
                    normalize_ticker(ticker),
                    event_type,
                    reason,
                    message,
                    rule_timezone,
                    server_time,
                    local_time,
                    price,
                    percent_change,
                    utc_now_iso(),
                ),
            )

    def list_alert_run_logs(
        self, limit: int = 100, status: str | None = None
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM alert_run_log
                {where}
                ORDER BY started_at DESC, id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_alert_event_logs(
        self,
        limit: int = 100,
        event_type: str | None = None,
        reason: str | None = None,
        user_id: str | None = None,
        ticker: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        conditions: list[str] = []
        params: list[Any] = []
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if reason:
            conditions.append("reason = ?")
            params.append(reason)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if ticker:
            conditions.append("ticker = ?")
            params.append(normalize_ticker(ticker))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM alert_event_log
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_notification_logs(
        self,
        limit: int = 100,
        status: str | None = None,
        failures_only: bool = False,
        user_id: str | None = None,
        ticker: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        conditions: list[str] = []
        params: list[Any] = []
        if status:
            conditions.append("status LIKE ?")
            params.append(f"{status}%")
        if failures_only:
            conditions.append("status NOT LIKE 'sent%'")
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if ticker:
            conditions.append("ticker = ?")
            params.append(normalize_ticker(ticker))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM notification_log
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def record_iap_telemetry_event(
        self, user_id: str, request: IAPTelemetryEventCreateRequest
    ) -> dict[str, Any]:
        self.upsert_user(user_id)
        now = utc_now_iso()
        payload = request.model_dump()
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO iap_telemetry_events(
                    user_id, event_type, product_id, product_type, subscription_group_id,
                    transaction_id, original_transaction_id, offer_id, offer_type,
                    storefront, currency_code, display_price, price, trial_days,
                    status, reason, message, platform, environment, app_version,
                    device_model, device_os, language, occurred_at, created_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    user_id,
                    payload["event_type"],
                    payload["product_id"],
                    payload["product_type"],
                    payload["subscription_group_id"],
                    payload["transaction_id"],
                    payload["original_transaction_id"],
                    payload["offer_id"],
                    payload["offer_type"],
                    payload["storefront"],
                    payload["currency_code"],
                    payload["display_price"],
                    payload["price"],
                    payload["trial_days"],
                    payload["status"],
                    payload["reason"],
                    payload["message"],
                    payload["platform"],
                    payload["environment"],
                    payload["app_version"],
                    payload["device_model"],
                    payload["device_os"],
                    payload["language"],
                    payload["occurred_at"],
                    now,
                ),
            )
            row = db.execute(
                "SELECT * FROM iap_telemetry_events WHERE id = last_insert_rowid()"
            ).fetchone()
            return dict(row)

    def list_iap_telemetry_events(
        self,
        limit: int = 100,
        user_id: str | None = None,
        product_id: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        environment: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        where, params = self._iap_telemetry_filters(
            user_id=user_id,
            product_id=product_id,
            event_type=event_type,
            status=status,
            environment=environment,
            since=since,
        )
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM iap_telemetry_events
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def summarize_iap_telemetry(
        self,
        hours: int = 24,
        user_id: str | None = None,
        product_id: str | None = None,
        environment: str | None = None,
    ) -> dict[str, Any]:
        hours = max(1, min(hours, 8760))
        since = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=hours)
        where, params = self._iap_telemetry_filters(
            user_id=user_id,
            product_id=product_id,
            environment=environment,
            since=since.isoformat(),
        )
        with self.database.connect() as db:
            total_events = db.execute(
                f"SELECT COUNT(*) AS count FROM iap_telemetry_events {where}",
                params,
            ).fetchone()["count"]
            by_event_type = db.execute(
                f"""
                SELECT event_type AS name, COUNT(*) AS count
                FROM iap_telemetry_events
                {where}
                GROUP BY event_type
                ORDER BY count DESC, event_type
                """,
                params,
            ).fetchall()
            by_product = db.execute(
                f"""
                SELECT product_id, event_type, status, COUNT(*) AS count
                FROM iap_telemetry_events
                {where}
                GROUP BY product_id, event_type, status
                ORDER BY count DESC, product_id, event_type, status
                """,
                params,
            ).fetchall()

        return {
            "window_hours": hours,
            "user_id": user_id,
            "product_id": product_id,
            "total_events": total_events,
            "by_event_type": [dict(row) for row in by_event_type],
            "by_product": [dict(row) for row in by_product],
            "latest_events": self.list_iap_telemetry_events(
                limit=10,
                user_id=user_id,
                product_id=product_id,
                environment=environment,
                since=since.isoformat(),
            ),
        }

    def list_iap_buying_attempts(
        self,
        limit: int = 100,
        user_id: str | None = None,
        product_id: str | None = None,
        status: str | None = None,
        environment: str | None = None,
        hours: int | None = None,
        include_restore: bool = True,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        event_types = list(IAP_BUYING_ATTEMPT_EVENT_TYPES)
        if include_restore:
            event_types.extend(IAP_RESTORE_ATTEMPT_EVENT_TYPES)

        conditions = [f"LOWER(event_type) IN ({self._placeholders(event_types)})"]
        params: list[Any] = event_types.copy()
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if product_id:
            conditions.append("product_id = ?")
            params.append(product_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if environment:
            conditions.append("environment = ?")
            params.append(environment)
        since = self._since_for_hours(hours)
        if since:
            conditions.append("created_at >= ?")
            params.append(since)

        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM iap_telemetry_events
                WHERE {" AND ".join(conditions)}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_iap_paying_users(
        self,
        limit: int = 100,
        user_id: str | None = None,
        product_id: str | None = None,
        environment: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        state_case, state_params = self._iap_state_case()
        success_predicate, success_params = self._iap_success_predicate("first")

        base_conditions = ["product_id IS NOT NULL", "product_id != ''"]
        base_params: list[Any] = []
        if user_id:
            base_conditions.append("user_id = ?")
            base_params.append(user_id)
        if product_id:
            base_conditions.append("product_id = ?")
            base_params.append(product_id)
        if environment:
            base_conditions.append("environment = ?")
            base_params.append(environment)

        first_success_filters = ""
        first_success_params: list[Any] = []
        if environment:
            first_success_filters = " AND first.environment = ?"
            first_success_params.append(environment)

        with self.database.connect() as db:
            rows = db.execute(
                f"""
                WITH state_events AS (
                    SELECT
                        *,
                        {state_case} AS entitlement_state
                    FROM iap_telemetry_events
                    WHERE {" AND ".join(base_conditions)}
                ),
                latest_state AS (
                    SELECT
                        *,
                        ROW_NUMBER() OVER (
                            PARTITION BY user_id, COALESCE(product_id, '')
                            ORDER BY created_at DESC, id DESC
                        ) AS row_num
                    FROM state_events
                    WHERE entitlement_state IN ('active', 'inactive')
                )
                SELECT
                    latest.user_id,
                    latest.product_id,
                    latest.product_type,
                    latest.transaction_id,
                    latest.original_transaction_id,
                    latest.offer_id,
                    latest.offer_type,
                    latest.storefront,
                    latest.currency_code,
                    latest.display_price,
                    latest.price,
                    latest.status,
                    latest.event_type,
                    latest.platform,
                    latest.environment,
                    latest.app_version,
                    COALESCE(
                        (
                            SELECT MIN(first.created_at)
                            FROM iap_telemetry_events first
                            WHERE first.user_id = latest.user_id
                                AND COALESCE(first.product_id, '') = COALESCE(latest.product_id, '')
                                AND {success_predicate}
                                {first_success_filters}
                        ),
                        latest.created_at
                    ) AS first_success_at,
                    latest.created_at AS latest_success_at
                FROM latest_state latest
                WHERE latest.row_num = 1
                    AND latest.entitlement_state = 'active'
                ORDER BY latest.created_at DESC, latest.id DESC
                LIMIT ?
                """,
                (
                    *state_params,
                    *base_params,
                    *success_params,
                    *first_success_params,
                    limit,
                ),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_iap_telemetry_outcomes(
        self,
        outcome: str = "all",
        hours: int = 24,
        user_id: str | None = None,
        product_id: str | None = None,
        environment: str | None = None,
    ) -> list[dict[str, Any]]:
        outcome = outcome if outcome in {"all", "success", "failure"} else "all"
        since = self._since_for_hours(hours)
        outcome_case, outcome_params = self._iap_outcome_case()

        conditions: list[str] = []
        params: list[Any] = []
        if outcome == "all":
            conditions.append("outcome IN ('success', 'failure')")
        else:
            conditions.append("outcome = ?")
            params.append(outcome)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if product_id:
            conditions.append("product_id = ?")
            params.append(product_id)
        if environment:
            conditions.append("environment = ?")
            params.append(environment)
        if since:
            conditions.append("created_at >= ?")
            params.append(since)

        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT
                    outcome,
                    product_id,
                    product_type,
                    event_type,
                    status,
                    reason,
                    MAX(message) AS sample_message,
                    COUNT(*) AS count,
                    MAX(created_at) AS latest_at
                FROM (
                    SELECT
                        *,
                        {outcome_case} AS outcome
                    FROM iap_telemetry_events
                )
                WHERE {" AND ".join(conditions)}
                GROUP BY outcome, product_id, product_type, event_type, status, reason
                ORDER BY latest_at DESC, count DESC, product_id, event_type, status, reason
                """,
                (*outcome_params, *params),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_device_telemetry(
        self,
        limit: int = 100,
        user_id: str | None = None,
        platform: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM user_devices
                {where}
                ORDER BY last_seen_at DESC, id DESC
                LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
            return [
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "platform": row["platform"],
                    "environment": row["environment"],
                    "has_apns_token": bool(row["apns_token"]),
                    "apns_token_tail": identifier_tail(row["apns_token"]),
                    "has_onesignal_subscription": bool(row["onesignal_subscription_id"]),
                    "onesignal_subscription_id_tail": identifier_tail(
                        row["onesignal_subscription_id"]
                    ),
                    "device_model": row["device_model"],
                    "device_os": row["device_os"],
                    "app_version": row["app_version"],
                    "created_at": row["created_at"],
                    "last_seen_at": row["last_seen_at"],
                }
                for row in rows
            ]

    def list_failure_telemetry(
        self,
        limit: int = 100,
        user_id: str | None = None,
        ticker: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        filters = []
        params: list[Any] = []
        if user_id:
            filters.append("user_id = ?")
            params.append(user_id)
        if ticker:
            filters.append("ticker = ?")
            params.append(normalize_ticker(ticker))
        where = f"AND {' AND '.join(filters)}" if filters else ""
        with self.database.connect() as db:
            rows = db.execute(
                f"""
                SELECT *
                FROM (
                    SELECT
                        'alert_event' AS source,
                        user_id,
                        alert_rule_id,
                        ticker,
                        reason,
                        message,
                        created_at
                    FROM alert_event_log
                    WHERE event_type IN ('failure', 'error')
                    {where}
                    UNION ALL
                    SELECT
                        'notification' AS source,
                        user_id,
                        alert_rule_id,
                        ticker,
                        status AS reason,
                        body AS message,
                        created_at
                    FROM notification_log
                    WHERE status NOT LIKE 'sent%'
                    {where}
                )
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (*params, *params, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def _favorite_row(
        self, db: sqlite3.Connection, user_id: str, ticker: str
    ) -> dict[str, Any]:
        row = db.execute(
            """
            SELECT f.created_at, c.*
            FROM favorites f
            JOIN companies c ON c.ticker = f.ticker
            WHERE f.user_id = ? AND f.ticker = ?
            """,
            (user_id, ticker),
        ).fetchone()
        return {
            "ticker": row["ticker"],
            "created_at": row["created_at"],
            "company": company_from_row(row),
        }

    def _ensure_company(self, db: sqlite3.Connection, ticker: str) -> None:
        db.execute(
            """
            INSERT INTO companies(ticker, name, asset_type)
            VALUES (?, ?, 'stock')
            ON CONFLICT(ticker) DO NOTHING
            """,
            (ticker, ticker),
        )

    def _ensure_notification_preferences(
        self, db: sqlite3.Connection, user_id: str, now: str
    ) -> None:
        db.execute(
            """
            INSERT INTO notification_preferences(user_id, ios_enabled, watchos_enabled, updated_at)
            VALUES (?, 1, 1, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, now),
        )

    def _iap_outcome_case(self, alias: str = "") -> tuple[str, list[Any]]:
        success_predicate, success_params = self._iap_success_predicate(alias)
        failure_predicate, failure_params = self._iap_failure_predicate(alias)
        return (
            f"""
            CASE
                WHEN {success_predicate} THEN 'success'
                WHEN {failure_predicate} THEN 'failure'
                ELSE 'other'
            END
            """,
            [*success_params, *failure_params],
        )

    def _iap_state_case(self, alias: str = "") -> tuple[str, list[Any]]:
        success_predicate, success_params = self._iap_success_predicate(alias)
        inactive_predicate, inactive_params = self._iap_inactive_predicate(alias)
        return (
            f"""
            CASE
                WHEN {success_predicate} THEN 'active'
                WHEN {inactive_predicate} THEN 'inactive'
                ELSE 'other'
            END
            """,
            [*success_params, *inactive_params],
        )

    def _iap_success_predicate(self, alias: str = "") -> tuple[str, list[Any]]:
        return self._iap_event_or_status_predicate(
            IAP_SUCCESS_EVENT_TYPES,
            IAP_SUCCESS_STATUSES,
            alias,
        )

    def _iap_failure_predicate(self, alias: str = "") -> tuple[str, list[Any]]:
        return self._iap_event_or_status_predicate(
            IAP_FAILURE_EVENT_TYPES,
            IAP_FAILURE_STATUSES,
            alias,
        )

    def _iap_inactive_predicate(self, alias: str = "") -> tuple[str, list[Any]]:
        return self._iap_event_or_status_predicate(
            IAP_INACTIVE_EVENT_TYPES,
            IAP_INACTIVE_STATUSES,
            alias,
        )

    def _iap_event_or_status_predicate(
        self,
        event_types: Sequence[str],
        statuses: Sequence[str],
        alias: str = "",
    ) -> tuple[str, list[Any]]:
        prefix = f"{alias}." if alias else ""
        return (
            f"""
            (
                LOWER(COALESCE({prefix}event_type, '')) IN ({self._placeholders(event_types)})
                OR LOWER(COALESCE({prefix}status, '')) IN ({self._placeholders(statuses)})
            )
            """,
            [*event_types, *statuses],
        )

    def _since_for_hours(self, hours: int | None) -> str | None:
        if hours is None:
            return None
        clamped_hours = max(1, min(hours, 8760))
        return (
            datetime.now(UTC).replace(microsecond=0) - timedelta(hours=clamped_hours)
        ).isoformat()

    def _placeholders(self, values: Sequence[object]) -> str:
        return ",".join("?" for _ in values)

    def _iap_telemetry_filters(
        self,
        user_id: str | None = None,
        product_id: str | None = None,
        event_type: str | None = None,
        status: str | None = None,
        environment: str | None = None,
        since: str | None = None,
    ) -> tuple[str, list[Any]]:
        conditions: list[str] = []
        params: list[Any] = []
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if product_id:
            conditions.append("product_id = ?")
            params.append(product_id)
        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if environment:
            conditions.append("environment = ?")
            params.append(environment)
        if since:
            conditions.append("created_at >= ?")
            params.append(since)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        return where, params

    def _preference_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "user_id": row["user_id"],
            "ios_enabled": bool(row["ios_enabled"]),
            "watchos_enabled": bool(row["watchos_enabled"]),
            "ios_registered": bool(row["ios_registered"]),
            "watchos_registered": bool(row["watchos_registered"]),
            "updated_at": row["updated_at"],
        }
