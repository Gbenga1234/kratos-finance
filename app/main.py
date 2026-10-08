import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, status
from kombu.exceptions import OperationalError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models
from app.celery_app import celery_app
from app.config import get_settings
from app.database import Base, engine, get_db
from app.logging_config import configure_logging
from app.models import Transfer
from app.schemas import TransferCreate, TransferRead

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/transfers",
    response_model=TransferRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_transfer(
    payload: TransferCreate,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Transfer:
    if idempotency_key is not None:
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
        existing = db.scalar(
            select(Transfer).where(Transfer.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing

    transfer = Transfer(
        source_account_id=payload.source_account_id,
        destination_account_id=payload.destination_account_id,
        amount=payload.amount,
        currency=payload.currency,
        idempotency_key=idempotency_key,
    )
    db.add(transfer)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if idempotency_key is None:
            raise
        existing = db.scalar(
            select(Transfer).where(Transfer.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return existing
    db.refresh(transfer)

    try:
        celery_app.send_task("transfers.process", args=[transfer.id], queue="default")
    except OperationalError as exc:
        transfer.status = "failed"
        transfer.failure_reason = "Transfer could not be queued"
        db.commit()
        logger.exception("Unable to queue transfer_id=%s", transfer.id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Transfer processing is temporarily unavailable",
        ) from exc

    logger.info("Accepted transfer_id=%s", transfer.id)
    return transfer


@app.get("/transfers/{transfer_id}", response_model=TransferRead)
def get_transfer(transfer_id: str, db: Session = Depends(get_db)) -> Transfer:
    transfer = db.get(Transfer, transfer_id)
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer
