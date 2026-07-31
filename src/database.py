import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from src.config import Settings, get_settings
from src.lists import bdrs, etfs, fiis, stocks


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def normalize_ticker(ticker: str) -> str:
    normalized = "".join(ch for ch in ticker.upper().strip() if ch.isalnum())
    if not normalized:
        raise ValueError("ticker is required")
    if len(normalized) > 12:
        raise ValueError("ticker is too long")
    return normalized


def ticker_catalog() -> list[dict[str, str]]:
    entries: dict[str, dict[str, str]] = {}
    for symbol in stocks:
        ticker = normalize_ticker(symbol)
        entries[ticker] = {"ticker": ticker, "name": ticker, "asset_type": "stock"}
    for symbol in fiis:
        ticker = normalize_ticker(symbol)
        entries[ticker] = {"ticker": ticker, "name": ticker, "asset_type": "fii"}
    for symbol in etfs:
        ticker = normalize_ticker(symbol)
        entries[ticker] = {"ticker": ticker, "name": ticker, "asset_type": "etf"}
    for symbol in bdrs:
        ticker = normalize_ticker(symbol)
        entries[ticker] = {"ticker": ticker, "name": ticker, "asset_type": "bdr"}
    return sorted(entries.values(), key=lambda row: row["ticker"])


class Database:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.path = Path(self.settings.database_path)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            yield db
            db.commit()
        finally:
            db.close()


def init_db(settings: Settings | None = None) -> None:
    database = Database(settings)
    with database.connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS companies (
                ticker TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                logo TEXT,
                last_price REAL,
                daily_change_percent REAL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                display_name TEXT,
                timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS user_devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                platform TEXT NOT NULL,
                apns_token TEXT,
                onesignal_subscription_id TEXT,
                environment TEXT NOT NULL DEFAULT 'production',
                created_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                UNIQUE(user_id, platform, apns_token)
            );

            CREATE TABLE IF NOT EXISTS favorites (
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                ticker TEXT NOT NULL REFERENCES companies(ticker) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                PRIMARY KEY(user_id, ticker)
            );

            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                ticker TEXT NOT NULL REFERENCES companies(ticker) ON DELETE CASCADE,
                enabled INTEGER NOT NULL DEFAULT 1,
                metric TEXT NOT NULL CHECK(metric IN ('price', 'percent')),
                operator TEXT NOT NULL CHECK(operator IN ('gte', 'lte')),
                threshold REAL NOT NULL,
                baseline_price REAL,
                weekdays TEXT NOT NULL DEFAULT '1,2,3,4,5',
                start_time TEXT NOT NULL DEFAULT '10:00',
                end_time TEXT NOT NULL DEFAULT '18:00',
                timezone TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
                frequency_minutes INTEGER NOT NULL DEFAULT 15,
                cooldown_minutes INTEGER NOT NULL DEFAULT 60,
                last_checked_at TEXT,
                last_triggered_at TEXT,
                last_price REAL,
                last_percent_change REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_alert_rules_due
                ON alert_rules(enabled, ticker, last_checked_at);

            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                alert_rule_id INTEGER REFERENCES alert_rules(id) ON DELETE SET NULL,
                ticker TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                onesignal_notification_id TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        now = utc_now_iso()
        for company in ticker_catalog():
            db.execute(
                """
                INSERT INTO companies(ticker, name, asset_type)
                VALUES (?, ?, ?)
                ON CONFLICT(ticker) DO UPDATE SET
                    name = excluded.name,
                    asset_type = excluded.asset_type
                """,
                (company["ticker"], company["name"], company["asset_type"]),
            )
        db.execute("UPDATE users SET updated_at = COALESCE(updated_at, ?)", (now,))
