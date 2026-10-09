import logging
import hashlib
import json
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, status
from redis import Redis, RedisError
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import get_settings
from app.database import engine, get_db
from app.logging_config import configure_logging
from app.models import OutboxEvent, Transfer
from app.schemas import TransferCreate, TransferRead
from app.security import authenticated_subject

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


is_production = settings.app_env.lower() == "production"
app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> dict[str, str]:
    if not all((settings.oidc_issuer, settings.oidc_audience, settings.oidc_jwks_url)):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Identity provider is not configured",
        )
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        redis = Redis.from_url(settings.celery_broker_url, socket_timeout=2)
        try:
            redis.ping()
        finally:
            redis.close()
    except (SQLAlchemyError, RedisError, OSError, ValueError) as exc:
        logger.warning("Readiness check failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service dependencies are unavailable",
        ) from exc
    return {"status": "ready"}


@app.middleware("http")
async def add_request_context(request: Request, call_next) -> Response:
    request_id_header = request.headers.get("X-Request-ID")
    try:
        request_id = str(UUID(request_id_header)) if request_id_header else str(uuid4())
    except ValueError:
        request_id = str(uuid4())

    started_at = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    if is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    logger.info(
        "http_request request_id=%s method=%s path=%s status=%s duration_ms=%d",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        int((time.monotonic() - started_at) * 1000),
    )
    return response


def transfer_fingerprint(payload: TransferCreate) -> str:
    canonical = json.dumps(
        {
            "amount": format(payload.amount, ".2f"),
            "currency": payload.currency,
            "destination_account_id": payload.destination_account_id,
            "source_account_id": payload.source_account_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@app.post(
    "/transfers",
    response_model=TransferRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_transfer(
    payload: TransferCreate,
    db: Session = Depends(get_db),
    owner_subject: str = Depends(authenticated_subject),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Transfer:
    fingerprint = transfer_fingerprint(payload)
    if idempotency_key is not None:
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")
        idempotency_key = idempotency_key.strip()
        existing = db.scalar(
            select(Transfer).where(
                Transfer.owner_subject == owner_subject,
                Transfer.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key was already used with a different request",
                )
            return existing

    if payload.amount > Decimal(settings.max_transfer_amount) / Decimal(100):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Transfer amount exceeds the configured limit",
        )
    if payload.currency not in settings.supported_currencies:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Currency is not supported",
        )

    transfer = Transfer(
        owner_subject=owner_subject,
        source_account_id=payload.source_account_id,
        destination_account_id=payload.destination_account_id,
        amount=payload.amount,
        currency=payload.currency,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
    )
    try:
        db.add(transfer)
        db.flush()
        db.add(OutboxEvent(transfer_id=transfer.id, event_type="transfers.process"))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if idempotency_key is None:
            raise
        existing = db.scalar(
            select(Transfer).where(
                Transfer.owner_subject == owner_subject,
                Transfer.idempotency_key == idempotency_key,
            )
        )
        if existing is None:
            raise
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency-Key was already used with a different request",
            ) from exc
        return existing
    db.refresh(transfer)

    logger.info("Accepted simulated transfer transfer_id=%s", transfer.id)
    return transfer


@app.get("/transfers/{transfer_id}", response_model=TransferRead)
def get_transfer(
    transfer_id: str,
    db: Session = Depends(get_db),
    owner_subject: str = Depends(authenticated_subject),
) -> Transfer:
    transfer = db.scalar(
        select(Transfer).where(
            Transfer.id == transfer_id,
            Transfer.owner_subject == owner_subject,
        )
    )
    if transfer is None:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer
