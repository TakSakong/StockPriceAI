from celery import Celery

from ..core.config import settings

celery_app = Celery(
    "stockai_ml",
    broker=settings.celery_broker_url,
    backend=settings.redis_url,
    include=["app.workers.scan_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    result_expires=settings.celery_result_expires,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "warmup-sp500-cache-every-hour": {
            "task": "scan_tasks.warmup_cache_task",
            "schedule": 3600.0,  # 1 hour
        },
    },
)
