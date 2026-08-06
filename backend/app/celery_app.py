 
from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "lab_orchestrator",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks.deploy", "app.tasks.cleanup", "app.tasks.monitor"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "cleanup-expired-stands": {
        "task": "app.tasks.cleanup.cleanup_expired_stands",
        "schedule": 60.0,
        "options": {"queue": "celery"}
    }
}