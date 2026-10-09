from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Transfer(Base):
    __tablename__ = "transfers"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transfers_amount_positive"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_transfers_status",
        ),
        UniqueConstraint(
            "owner_subject",
            "idempotency_key",
            name="uq_transfers_owner_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    owner_subject: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_account_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    destination_account_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_outbox_attempts_nonnegative"),
        Index("ix_outbox_events_published_at", "published_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    transfer_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("transfers.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(String(255))
