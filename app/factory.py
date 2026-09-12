"""Durable control-plane primitives for the lights-out factory."""
from datetime import datetime, timedelta

from app.db_models import FactoryAuditLog, FactoryControl, FactoryJob


def get_control(db, workspace_id: int) -> FactoryControl:
    control = db.query(FactoryControl).filter(FactoryControl.workspace_id == workspace_id).first()
    if not control:
        control = FactoryControl(workspace_id=workspace_id)
        db.add(control); db.commit(); db.refresh(control)
    return control


def is_enabled(db, workspace_id: int, capability: str) -> bool:
    control = get_control(db, workspace_id)
    return bool(control.factory_enabled and getattr(control, capability, False))


def log_action(db, workspace_id: int, actor: str, action: str, target_type: str = "", target_id: str = "", detail: str = ""):
    db.add(FactoryAuditLog(
        workspace_id=workspace_id, actor=actor[:120], action=action[:100],
        target_type=target_type[:80] or None, target_id=str(target_id)[:80] or None,
        detail=detail[:3000] or None,
    ))
    db.commit()


def recover_stale_jobs(db, minutes: int = 15) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    jobs = db.query(FactoryJob).filter(
        FactoryJob.status == "RUNNING", FactoryJob.locked_at < cutoff
    ).all()
    for job in jobs:
        job.status = "RETRY" if job.attempts < job.max_attempts else "FAILED"
        job.locked_at = None
        job.last_error = "Worker dayandığı üçün iş avtomatik bərpa edildi."
    if jobs: db.commit()
    return len(jobs)
