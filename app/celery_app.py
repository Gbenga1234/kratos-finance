from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "kratos_finance",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_default_queue="default",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    worker_hijack_root_logger=False,
    timezone="UTC",
    beat_schedule={
        "dispatch-transfer-outbox": {
            "task": "outbox.dispatch",
            "schedule": 5.0,
        },
    },
)
