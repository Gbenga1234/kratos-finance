import logging

from app.celery_app import celery_app
from app.database import SessionLocal
from app.logging_config import configure_logging
from app.config import get_settings
from app.models import Transfer

logger = logging.getLogger(__name__)
configure_logging(get_settings().log_level)


@celery_app.task(name="transfers.process")
def process_transfer(transfer_id: str) -> str:
    with SessionLocal() as db:
        transfer = db.get(Transfer, transfer_id)
        if transfer is None:
            logger.error("Transfer task references missing transfer_id=%s", transfer_id)
            return "missing"
        if transfer.status != "pending":
            logger.info(
                "Skipping transfer_id=%s with status=%s",
                transfer_id,
                transfer.status,
            )
            return transfer.status

        transfer.status = "processing"
        db.commit()

        # This starter records a simulated outcome; no funds are moved.
        transfer.status = "completed"
        db.commit()

    logger.info("Simulated transfer completed transfer_id=%s", transfer_id)
    return "completed"
