"""Durable night-shift scheduler and lead-production worker."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.db_models import (
    FactoryJob, LeadAudit, NightShiftPlan, NightShiftReport, SalesActivity, SalesLead,
)
from app.factory import get_control, log_action
from app.lead_finder import discover_businesses
from app.sales_intelligence import audit_lead, create_outreach_sequence

BAKU = ZoneInfo("Asia/Baku")


def next_run_utc(hour_baku: int, now: datetime | None = None) -> datetime:
    local_now = (now or datetime.now(timezone.utc)).astimezone(BAKU)
    target = local_now.replace(hour=hour_baku, minute=0, second=0, microsecond=0)
    if target <= local_now:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc).replace(tzinfo=None)


def enqueue_due_night_shifts(db) -> int:
    now = datetime.utcnow()
    plans = db.query(NightShiftPlan).filter(NightShiftPlan.next_run_at <= now).all()
    added = 0
    for plan in plans:
        control = get_control(db, plan.workspace_id)
        if not (control.factory_enabled and control.lead_discovery_enabled):
            continue
        existing = db.query(FactoryJob).filter(
            FactoryJob.workspace_id == plan.workspace_id,
            FactoryJob.job_type == "NIGHT_LEAD_DISCOVERY",
            FactoryJob.status.in_(["PENDING", "RUNNING", "RETRY"]),
        ).first()
        if not existing:
            db.add(FactoryJob(
                workspace_id=plan.workspace_id, job_type="NIGHT_LEAD_DISCOVERY",
                payload_json=json.dumps({"plan_id": plan.id}), priority=50, run_after=now,
            ))
            added += 1
        plan.next_run_at = next_run_utc(plan.run_hour_baku)
    if plans: db.commit()
    return added


def enqueue_now(db, plan: NightShiftPlan) -> FactoryJob:
    job = FactoryJob(
        workspace_id=plan.workspace_id, job_type="NIGHT_LEAD_DISCOVERY",
        payload_json=json.dumps({"plan_id": plan.id}), priority=10, run_after=datetime.utcnow(),
    )
    db.add(job); db.commit(); db.refresh(job); return job


def _execute_lead_job(db, job: FactoryJob) -> None:
    payload = json.loads(job.payload_json or "{}")
    plan = db.get(NightShiftPlan, payload.get("plan_id"))
    if not plan or plan.workspace_id != job.workspace_id:
        raise ValueError("Night shift plan tapılmadı")
    found = discover_businesses(plan.city, plan.category, plan.daily_lead_target)
    added_leads = []
    for item in found:
        exists = db.query(SalesLead).filter(
            SalesLead.workspace_id == plan.workspace_id,
            SalesLead.source_external_id == item.source_external_id,
        ).first()
        if exists: continue
        lead = SalesLead(
            workspace_id=plan.workspace_id, company_name=item.company_name, category=item.category,
            city=item.city, address=item.address, website=item.website, phone=item.phone,
            email=item.email, source="OpenStreetMap", source_external_id=item.source_external_id,
            source_url=item.source_url, score=item.score, status="NEW",
            outreach_message=item.outreach_message,
        )
        db.add(lead); db.flush(); added_leads.append(lead)
    db.commit()
    audited = drafts = 0
    for lead in sorted(added_leads, key=lambda x: x.score, reverse=True)[:5]:
        audit = audit_lead(db, lead); audited += int(bool(audit))
        if lead.score >= 70 and not db.query(SalesActivity).filter(SalesActivity.lead_id == lead.id).first():
            create_outreach_sequence(db, plan.workspace_id, lead); drafts += 3
    report = NightShiftReport(
        workspace_id=plan.workspace_id, job_id=job.id, discovered=len(found), added=len(added_leads),
        audited=audited, outreach_drafts=drafts,
        summary=f"{plan.city} · {plan.category}: {len(found)} tapıldı, {len(added_leads)} yeni lead, {audited} audit, {drafts} mesaj draftı.",
    )
    db.add(report); plan.last_run_at = datetime.utcnow(); db.commit()
    log_action(db, plan.workspace_id, "night-worker", "NIGHT_SHIFT_COMPLETED", "FactoryJob", str(job.id), report.summary)


def process_one_factory_job(db) -> int:
    now = datetime.utcnow()
    job = db.query(FactoryJob).filter(
        FactoryJob.status.in_(["PENDING", "RETRY"]), FactoryJob.run_after <= now,
    ).order_by(FactoryJob.priority, FactoryJob.id).first()
    if not job: return 0
    control = get_control(db, job.workspace_id)
    if not (control.factory_enabled and control.lead_discovery_enabled): return 0
    job.status = "RUNNING"; job.locked_at = now; job.attempts += 1; db.commit()
    try:
        if job.job_type == "NIGHT_LEAD_DISCOVERY":
            _execute_lead_job(db, job)
        else:
            raise ValueError(f"Naməlum job növü: {job.job_type}")
        job.status = "COMPLETED"; job.completed_at = datetime.utcnow(); job.locked_at = None; db.commit()
    except Exception as exc:
        db.rollback(); job = db.get(FactoryJob, job.id)
        job.status = "RETRY" if job.attempts < job.max_attempts else "FAILED"
        job.run_after = datetime.utcnow() + timedelta(minutes=5 * job.attempts)
        job.locked_at = None; job.last_error = str(exc)[:2000]; db.commit()
    return 1
