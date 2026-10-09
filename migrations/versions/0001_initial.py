"""Create transfer and transactional outbox tables.

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def create_transfers_table() -> None:
    op.create_table(
        "transfers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_subject", sa.String(length=255), nullable=False),
        sa.Column("source_account_id", sa.String(length=100), nullable=False),
        sa.Column("destination_account_id", sa.String(length=100), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_transfers_amount_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_transfers_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_subject",
            "idempotency_key",
            name="uq_transfers_owner_idempotency",
        ),
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    migrated_sqlite = False
    if "transfers" not in tables:
        create_transfers_table()
    elif op.get_bind().dialect.name == "sqlite":
        migrated_sqlite = True
        old_indexes = [
            index["name"]
            for index in inspector.get_indexes("transfers")
            if index["name"]
        ]
        op.rename_table("transfers", "transfers_legacy")
        create_transfers_table()
        op.execute(
            sa.text(
                "INSERT INTO transfers "
                "(id, owner_subject, source_account_id, destination_account_id, amount, "
                "currency, status, idempotency_key, request_fingerprint, failure_reason, "
                "created_at, updated_at) "
                "SELECT id, 'legacy-unowned', source_account_id, destination_account_id, "
                "amount, currency, status, idempotency_key, "
                "'0000000000000000000000000000000000000000000000000000000000000000', "
                "failure_reason, created_at, updated_at FROM transfers_legacy"
            )
        )
        for index_name in old_indexes:
            op.drop_index(index_name, table_name="transfers_legacy")
        op.drop_table("transfers_legacy")
    else:
        for constraint in inspector.get_unique_constraints("transfers"):
            if constraint["column_names"] == ["idempotency_key"] and constraint["name"]:
                op.drop_constraint(constraint["name"], "transfers", type_="unique")
        op.add_column(
            "transfers",
            sa.Column("owner_subject", sa.String(length=255), nullable=True),
        )
        op.add_column(
            "transfers",
            sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
        )
        op.execute(
            "UPDATE transfers SET owner_subject = 'legacy-unowned', "
            "request_fingerprint = "
            "'0000000000000000000000000000000000000000000000000000000000000000'"
        )
        op.alter_column("transfers", "owner_subject", nullable=False)
        op.alter_column("transfers", "request_fingerprint", nullable=False)
        op.create_check_constraint(
            "ck_transfers_amount_positive",
            "transfers",
            "amount > 0",
        )
        op.create_check_constraint(
            "ck_transfers_status",
            "transfers",
            "status IN ('pending', 'processing', 'completed', 'failed')",
        )
        op.create_unique_constraint(
            "uq_transfers_owner_idempotency",
            "transfers",
            ["owner_subject", "idempotency_key"],
        )

    existing_indexes = (
        set()
        if migrated_sqlite
        else {index["name"] for index in inspector.get_indexes("transfers")}
    )
    for index_name, columns in (
        ("ix_transfers_owner_subject", ["owner_subject"]),
        ("ix_transfers_source_account_id", ["source_account_id"]),
        ("ix_transfers_destination_account_id", ["destination_account_id"]),
        ("ix_transfers_status", ["status"]),
    ):
        if index_name not in existing_indexes:
            op.create_index(index_name, "transfers", columns)

    if "outbox_events" not in tables:
        op.create_table(
            "outbox_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("transfer_id", sa.String(length=36), nullable=False),
            sa.Column("event_type", sa.String(length=100), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("attempts", sa.Integer(), nullable=False),
            sa.Column("last_error", sa.String(length=255), nullable=True),
            sa.CheckConstraint("attempts >= 0", name="ck_outbox_attempts_nonnegative"),
            sa.ForeignKeyConstraint(
                ["transfer_id"],
                ["transfers.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("transfer_id"),
        )
    if "ix_outbox_events_published_at" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("outbox_events")
    }:
        op.create_index("ix_outbox_events_published_at", "outbox_events", ["published_at"])


def downgrade() -> None:
    raise RuntimeError("Transfer history is append-only; use a forward migration to roll back")
