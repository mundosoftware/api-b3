import sqlite3
from typing import Any

from src.config import Settings, get_settings
from src.database import Database, normalize_ticker, utc_now_iso
from src.models import AlertRuleCreateRequest, AlertRuleOut, AlertRuleUpdateRequest


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


class Repository:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.database = Database(self.settings)

    def upsert_user(
        self, user_id: str, display_name: str | None = None, timezone: str | None = None
    ) -> dict[str, Any]:
        now = utc_now_iso()
        user_timezone = timezone or self.settings.default_timezone
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO users(user_id, display_name, timezone, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    display_name = COALESCE(excluded.display_name, users.display_name),
                    timezone = COALESCE(excluded.timezone, users.timezone),
                    updated_at = excluded.updated_at
                """,
                (user_id, display_name, user_timezone, now, now),
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
        normalized = normalize_ticker(ticker)
        now = utc_now_iso()
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO companies(ticker, name, asset_type, logo, last_price, daily_change_percent, updated_at)
                VALUES (?, ?, 'stock', ?, ?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name = COALESCE(excluded.name, companies.name),
                    logo = COALESCE(excluded.logo, companies.logo),
                    last_price = excluded.last_price,
                    daily_change_percent = excluded.daily_change_percent,
                    updated_at = excluded.updated_at
                """,
                (normalized, name or normalized, logo, last_price, daily_change_percent, now),
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
        self.upsert_user(user_id, timezone=request.timezone)
        ticker = normalize_ticker(request.ticker)
        now = utc_now_iso()
        weekdays = ",".join(str(day) for day in request.weekdays)
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
                    request.timezone or self.settings.default_timezone,
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

    def mark_alert_checked(
        self,
        alert_id: int,
        price: float,
        percent_change: float | None,
        baseline_price: float | None = None,
        triggered: bool = False,
    ) -> None:
        now = utc_now_iso()
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
        apns_token: str,
        environment: str,
        onesignal_subscription_id: str | None,
    ) -> None:
        self.upsert_user(user_id)
        now = utc_now_iso()
        with self.database.connect() as db:
            db.execute(
                """
                INSERT INTO user_devices(
                    user_id, platform, apns_token, onesignal_subscription_id,
                    environment, created_at, last_seen_at
                )
                VALUES (?, 'watchos', ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, platform, apns_token) DO UPDATE SET
                    onesignal_subscription_id = COALESCE(
                        excluded.onesignal_subscription_id,
                        user_devices.onesignal_subscription_id
                    ),
                    environment = excluded.environment,
                    last_seen_at = excluded.last_seen_at
                """,
                (user_id, apns_token, onesignal_subscription_id, environment, now, now),
            )

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
