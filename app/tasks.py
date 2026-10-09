import logging
from datetime import datetime, timezone

from kombu.exceptions import OperationalError
from sqlalchemy import select, update

from app.celery_app import celery_app
from app.config import get_settings
from app.database import SessionLocal
from app.logging_config import configure_logging
from app.models import OutboxEvent, Transfer

logger = logging.getLogger(__name__)
configure_logging(get_settings().log_level)


@celery_app.task(
    name="outbox.dispatch",
    bind=True,
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def dispatch_outbox(self) -> int:
    published = 0
    with SessionLocal() as db:
        events = db.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(100)
            .with_for_update(skip_locked=True)
        ).all()

        for event in events:
            try:
                celery_app.send_task(
                    event.event_type,
                    args=[event.transfer_id],
                    queue="default",
                )
            except OperationalError as exc:
                event.attempts += 1
                event.last_error = type(exc).__name__
                db.commit()
                logger.error(
                    "Unable to publish outbox_event_id=%s error_type=%s",
                    event.id,
                    type(exc).__name__,
                )
                raise
            event.attempts += 1
            event.last_error = None
            event.published_at = datetime.now(timezone.utc)
            published += 1
        db.commit()

    return published


@celery_app.task(name="transfers.process")
def process_transfer(transfer_id: str) -> str:
    with SessionLocal() as db:
        result = db.execute(
            update(Transfer)
            .where(Transfer.id == transfer_id, Transfer.status == "pending")
            .values(
                status="completed",
                updated_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount:
            db.commit()
            logger.info("Simulated transfer completed transfer_id=%s", transfer_id)
            return "completed"

        transfer = db.get(Transfer, transfer_id)
        if transfer is None:
            logger.error("Transfer task references missing transfer_id=%s", transfer_id)
            return "missing"
        logger.info(
            "Skipping transfer_id=%s with status=%s",
            transfer_id,
            transfer.status,
        )
        return transfer.status
