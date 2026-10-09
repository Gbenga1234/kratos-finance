import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.config import get_settings


def test_migration_preserves_legacy_sqlite_transfer_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE transfers (
                id VARCHAR(36) PRIMARY KEY,
                source_account_id VARCHAR(100) NOT NULL,
                destination_account_id VARCHAR(100) NOT NULL,
                amount NUMERIC(18, 2) NOT NULL,
                currency VARCHAR(3) NOT NULL,
                status VARCHAR(20) NOT NULL,
                idempotency_key VARCHAR(128) UNIQUE,
                failure_reason VARCHAR(255),
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            CREATE INDEX ix_transfers_source_account_id
                ON transfers (source_account_id);
            CREATE INDEX ix_transfers_destination_account_id
                ON transfers (destination_account_id);
            CREATE INDEX ix_transfers_status ON transfers (status);
            INSERT INTO transfers VALUES (
                'legacy-id', 'old-source', 'old-destination', 2.50, 'USD', 'completed',
                'old-key', NULL, '2026-01-01 00:00:00', '2026-01-01 00:00:00'
            );
            """
        )

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")
    get_settings.cache_clear()
    try:
        repository_root = Path(__file__).resolve().parents[1]
        config = Config(str(repository_root / "alembic.ini"))
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{database_path}")
    try:
        columns = {column["name"] for column in inspect(engine).get_columns("transfers")}
        assert {"owner_subject", "request_fingerprint"} <= columns
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT owner_subject, request_fingerprint, amount "
                    "FROM transfers WHERE id = 'legacy-id'"
                )
            ).one()
        assert row.owner_subject == "legacy-unowned"
        assert row.request_fingerprint == "0" * 64
        assert row.amount == 2.5
    finally:
        engine.dispose()
