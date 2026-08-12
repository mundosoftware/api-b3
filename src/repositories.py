import sqlite3
from collections.abc import Sequence
from typing import Any

from src.config import Settings, get_settings
from src.database import Database, normalize_ticker, utc_now_iso
from src.models import (
    AlertRuleCreateRequest,
    AlertRuleOut,
    AlertRuleUpdateRequest,
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

    def _preference_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "user_id": row["user_id"],
            "ios_enabled": bool(row["ios_enabled"]),
            "watchos_enabled": bool(row["watchos_enabled"]),
            "ios_registered": bool(row["ios_registered"]),
            "watchos_registered": bool(row["watchos_registered"]),
            "updated_at": row["updated_at"],
        }
