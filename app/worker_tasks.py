"""Celery tərəfindən icra edilən qısa, təkrar çağırıla bilən factory tick-ləri."""
import secrets
from contextlib import contextmanager

from redis import Redis
from app.agency import TERMINAL_STATUSES, advance_project
from app.celery_app import celery_app
from app.database import SessionLocal
from app.db_models import AgentProject
from app.factory import is_enabled, recover_stale_jobs
from app.night_shift import enqueue_due_night_shifts, process_one_factory_job
from app.outbound import process_outbox
from app.core import settings
from app.scheduler import publish_due_scheduled_content
from app.social_tracking import sync_due_asset_social_metrics, sync_due_social_metrics


@contextmanager
def _tick_lock(name: str, ttl: int = 300):
    """Beat üst-üstə tick göndərsə yalnız bir worker-i içəri buraxır."""
    client = Redis.from_url(settings.redis_url)
    key, token = f"agency:lock:{name}", secrets.token_hex(16)
    acquired = bool(client.set(key, token, nx=True, ex=ttl))
    try:
        yield acquired
    finally:
        if acquired:
            client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                1, key, token,
            )


@celery_app.task(name="app.worker_tasks.factory_tick", autoretry_for=(Exception,),
                 retry_backoff=True, retry_kwargs={"max_retries": 3})
def factory_tick() -> dict:
    with _tick_lock("factory") as acquired:
        if not acquired:
            return {"skipped": "previous_tick_running"}
        db = SessionLocal()
        try:
            return {"recovered": recover_stale_jobs(db), "enqueued": enqueue_due_night_shifts(db),
                    "jobs": process_one_factory_job(db), "outbound": process_outbox(db),
                    "social_metrics": sync_due_social_metrics(db),
                    "asset_social_metrics": sync_due_asset_social_metrics(db),
                    "scheduled_content": publish_due_scheduled_content(db)}
        finally:
            db.close()


@celery_app.task(name="app.worker_tasks.project_tick", autoretry_for=(Exception,),
                 retry_backoff=True, retry_kwargs={"max_retries": 2})
def project_tick() -> dict:
    with _tick_lock("projects", ttl=900) as acquired:
        if not acquired:
            return {"skipped": "previous_tick_running"}
        db = SessionLocal()
        advanced = 0
        try:
            project_ids = [row[0] for row in db.query(AgentProject.id).filter(
                AgentProject.status.notin_(list(TERMINAL_STATUSES))).all()]
            for project_id in project_ids:
                project = db.get(AgentProject, project_id)
                if not project or (project.workspace_id and not is_enabled(db, project.workspace_id, "agents_enabled")):
                    continue
                if advance_project(db, project):
                    advanced += 1
            return {"advanced": advanced}
        finally:
            db.close()
