from celery import Celery
from backend.core.config import settings

celery_app = Celery(
    "transaction_pipeline",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["backend.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "backend.workers.tasks.process_transaction_job": {"queue": "default"},
    },
    task_soft_time_limit=600,  # 10 minutes soft limit
    task_time_limit=900,       # 15 minutes hard limit
    broker_connection_retry_on_startup=True,
)
