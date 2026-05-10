import os

from celery import Celery

broker_url = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/2")
result_backend = os.getenv("REDIS_URL", "redis://redis:6379/1")

celery_app = Celery("stockai_ml", broker=broker_url, backend=result_backend)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
)
