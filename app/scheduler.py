"""Arxa fonda işləyən avtonom dövrə: aktiv layihələri kimsə düyməyə basmasa belə özü irəlilədir.
Bu, /agency/brief ilə (məs. Telegram-dan) yaradılan layihələrin heç bir manual /run çağırışı
olmadan da başa çatmasını təmin edir — sistem həqiqətən özbaşına işləyən bir "şirkət"dir."""
import asyncio
import logging
from datetime import datetime

from app.agency import TERMINAL_STATUSES, advance_project
from app.database import SessionLocal
from app.db_models import ContentAsset, AgentProject
from app.locks import get_lock
from app.ws import manager
from app.outbound import process_outbox
from app.factory import is_enabled, recover_stale_jobs
from app.night_shift import enqueue_due_night_shifts, process_one_factory_job
from app.social_tracking import sync_due_asset_social_metrics, sync_due_social_metrics

logger = logging.getLogger(__name__)

TICK_SECONDS = 6


def publish_due_scheduled_content(db) -> int:
    """Müştərinin əvvəlcədən planlaşdırdığı ("15 sentyabr 10:00-da paylaş") materialları
    vaxtı çatanda avtomatik dərc edir — bax `/content-studio/{id}/schedule` (Bakı yerli vaxtı
    UTC-yə çevrilib saxlanılır, ona görə burada `datetime.utcnow()` ilə birbaşa müqayisə düzgündür).

    BİRDƏFƏLİK tetiklənmə: hər platform üçün TƏK cəhd edilir, sonra `scheduled_at` HƏR NƏTİCƏDƏ
    (uğurlu və ya uğursuz) təmizlənir — sonsuz təkrar cəhd YOXDUR. Uğursuzluq `schedule_error`-da
    saxlanılır ki, istifadəçi Content Studio-da görüb əl ilə "İndi paylaş" ilə təkrar cəhd edə bilsin."""
    from app.web import publish_asset_to_instagram, publish_asset_to_tiktok

    now = datetime.utcnow()
    due = db.query(ContentAsset).filter(
        ContentAsset.scheduled_at.isnot(None), ContentAsset.scheduled_at <= now,
    ).all()
    published = 0
    for asset in due:
        workspace = asset.workspace
        platforms = [p for p in (asset.scheduled_platforms or "").split(",") if p]
        errors = []
        for platform in platforms:
            try:
                if platform == "instagram" and not asset.instagram_published:
                    notice = publish_asset_to_instagram(db, workspace, asset)
                    if notice != "ig_published":
                        errors.append(f"Instagram: {notice}")
                    else:
                        published += 1
                elif platform == "tiktok" and not asset.tiktok_published:
                    notice = publish_asset_to_tiktok(db, workspace, asset)
                    if notice != "tt_published":
                        errors.append(f"TikTok: {notice}")
                    else:
                        published += 1
            except Exception:
                logger.exception(
                    "Planlaşdırılmış paylaşım xətası (asset #%s, platform %s)", asset.id, platform
                )
                errors.append(f"{platform}: gözlənilməz xəta")
        asset.scheduled_at = None
        asset.scheduled_platforms = None
        asset.schedule_error = "; ".join(errors) if errors else None
        db.commit()
    return published


async def agency_loop() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        db = SessionLocal()
        try:
            recover_stale_jobs(db)
            enqueue_due_night_shifts(db)
            try:
                await asyncio.to_thread(process_one_factory_job, db)
            except Exception:
                logger.exception("Factory job işlənərkən xəta baş verdi")
            try:
                await asyncio.to_thread(process_outbox, db)
            except Exception:
                logger.exception("Email növbəsi işlənərkən xəta baş verdi")
            try:
                await asyncio.to_thread(sync_due_social_metrics, db)
            except Exception:
                logger.exception("Sosial media metrikləri sinxronlaşdırılarkən xəta baş verdi")
            try:
                await asyncio.to_thread(sync_due_asset_social_metrics, db)
            except Exception:
                logger.exception("Content Studio sosial metrikləri sinxronlaşdırılarkən xəta baş verdi")
            try:
                await asyncio.to_thread(publish_due_scheduled_content, db)
            except Exception:
                logger.exception("Planlaşdırılmış paylaşımlar işlənərkən xəta baş verdi")
            active_projects = (
                db.query(AgentProject)
                .filter(AgentProject.status.notin_(list(TERMINAL_STATUSES)))
                .all()
            )
            for project in active_projects:
                if project.workspace_id and not is_enabled(db, project.workspace_id, "agents_enabled"):
                    continue
                lock = get_lock(project.id)
                if lock.locked():
                    # Manual /run bu layihəni artıq işlədir — eyni anda toxunmuruq
                    # (əks halda hər rol üçün təkrarlanan tapşırıqlar yaranar).
                    continue
                async with lock:
                    try:
                        event = await asyncio.to_thread(advance_project, db, project)
                    except Exception:
                        logger.exception("Layihə #%s irəlilədilərkən xəta baş verdi", project.id)
                        continue
                if event:
                    await manager.broadcast(event)
        finally:
            db.close()
