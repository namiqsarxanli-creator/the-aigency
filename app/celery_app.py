"""İstehsal worker-i: Redis broker, Celery beat və dayanıqlı periodik işlər."""
from celery import Celery

from app.core import settings

celery_app = Celery("the_agency", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json", result_serializer="json", accept_content=["json"],
    timezone="UTC", enable_utc=True, task_acks_late=True,
    task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "factory-queue-every-10-seconds": {"task": "app.worker_tasks.factory_tick", "schedule": 10.0},
        "agent-projects-every-6-seconds": {"task": "app.worker_tasks.project_tick", "schedule": 6.0},
    },
    imports=("app.worker_tasks",),
)
