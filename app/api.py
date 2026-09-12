"""JSON API — layihə yaratmaq, addım-addım işlətmək, izləmək, təsdiqləmək."""
import asyncio
import logging
import time
from datetime import datetime
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.orm import Session

from app.agency import (
    REGENERABLE_STATUSES, TERMINAL_STATUSES, advance_project, create_project, regenerate_task,
    start_retry,
)
from app.core import HTTP_USER_AGENT, settings
from app.database import get_db
from app.factory import is_enabled
from app.db_models import AgentProject, AgentTask, AgentTaskVersion, SocialPostTracker, Workspace
from app import instagram
from app.locks import get_lock
from app.models import (
    BriefRequest, InstagramPublishResult, PendingProjectOut, ProjectDetail, ProjectOut,
    RegenerateRequest, RejectRequest, RejectResult, RunResult, TaskVersionsResult, UsageReport,
)
from app.usage_report import build_usage_report
from app.ws import manager
from app.auth import workspace_scope

router = APIRouter()
logger = logging.getLogger(__name__)

# Deliverable şəkillərinin bayt keşi (layihə id -> şəkil baytları). Telegram sendPhoto-nun
# pollinations URL-ini birbaşa yükləməsi etibarsızdır (şəkil generasiyası 10-30s çəkir, Telegram-ın
# ~5s timeout-unu keçir). Bunun əvəzinə n8n şəkli backend-in bu keşindən host.docker.internal
# üzərindən ANINDA alır, backend isə pollinations-dan bir dəfə (səxavətli timeout ilə) yükləyir.
_image_cache: dict[int, bytes] = {}
# Keş prosesin ömrü boyu yaddaşda qalır — limitsiz olsa uzun işləyən serverdə hər layihənin şəkli
# (~25-200KB) yığılıb yaddaşı doldurar. Ən köhnə girişlər sıradan çıxarılır (sadə FIFO).
_IMAGE_CACHE_MAX_ITEMS = 64

MAX_STEPS_PER_RUN = 40
# advance_project addımları arasında kiçik gecikmə — CEO+4 rol+QA+revision-lar bir neçə saniyə
# ərzində 8-14 ardıcıl LLM sorğusu göndərir, bu "partlayış" bəzən provayderləri anlıq rate-limitə
# salır (QA-nın avtomatik təsdiqlə fallback vermə halları buradan yaranır). Kiçik gecikmə bunu azaldır.
STEP_DELAY_SECONDS = 0.05


def _get_project_or_404(db: Session, project_id: int, workspace_id: int | None = None) -> AgentProject:
    query = db.query(AgentProject).filter(AgentProject.id == project_id)
    if workspace_id is not None:
        query = query.filter(AgentProject.workspace_id == workspace_id)
    project = query.first()
    if not project:
        raise HTTPException(status_code=404, detail="Layihə tapılmadı")
    return project


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """AGENCY_API_KEY .env-də boşdursa qorumasız (lokal demo) — dolarsa `X-API-Key` başlığı
    dəqiq uyğun gəlməlidir. Ngrok ilə internetə açıq olan quraşdırmalarda vacibdir, çünki
    onsuz istənilən kəs sizin adınızdan layihə yaradıb LLM kvotanızı istifadə edə bilər."""
    if not settings.agency_api_key:
        return
    if x_api_key != settings.agency_api_key:
        raise HTTPException(status_code=401, detail="Yanlış ya da yoxdur X-API-Key")


@router.post("/agency/brief", response_model=ProjectOut)
def create_brief(payload: BriefRequest, workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db)):
    # Telegram-dan gələn brifdə chat_id olur; web-dən gələndə boş olur — belə halda .env-dəki
    # DEFAULT_TELEGRAM_CHAT_ID varsa onu istifadə edirik ki, web layihələri də sizə bildirilsin.
    chat_id = payload.telegram_chat_id or (settings.default_telegram_chat_id or None)
    project = create_project(db, payload.brief, telegram_chat_id=chat_id, workspace_id=workspace_id)
    return project


@router.get("/agency/projects", response_model=list[ProjectOut])
def list_projects(workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db)):
    return db.query(AgentProject).filter(AgentProject.workspace_id == workspace_id).order_by(AgentProject.id.desc()).limit(50).all()


@router.get("/agency/pending-approval", response_model=PendingProjectOut, dependencies=[Depends(require_api_key)])
def pending_approval(db: Session = Depends(get_db)):
    """Telegram/n8n bildiriş axını üçün: bildirilməli NÖVBƏTİ layihəni (tək obyekt) qaytarır.
    Qeyd: bu route `/agency/{project_id}`-dən ƏVVƏL qeydiyyatdan keçməlidir, yoxsa FastAPI
    'pending-approval' sətrini project_id kimi parse etməyə çalışıb 422 qaytarır.

    NİYƏ MASSİV YOX, TƏK OBYEKT: n8n HTTP node massivi bəzən ayrı item-lərə bölmür (bütöv
    massivi tək item kimi ötürür) — belə halda downstream IF node-da `{{ $json.id }}` boş
    sətir (`''`) olur və "number gözlənilirdi" xətası atır, Telegram node-u da `brief`,
    `telegram_chat_id`-ni oxuya bilmir. Tək obyekt qaytarsaq, `$json.id`, `$json.brief`,
    `$json.telegram_chat_id` birbaşa doldurulur və bu qeyri-müəyyənlik tamamilə aradan qalxır.
    Bir neçə layihə gözləyirsə, hər dəqiqəlik icra növbəti birini götürür (mark-notified sırayla).

    YALNIZ `telegram_chat_id`-si olanlar: web dashboard-dan yaradılanların chat_id-si yoxdur
    (DEFAULT_TELEGRAM_CHAT_ID qoyulmayıbsa), onlara Telegram bildirişi göndərmək mümkün deyil.

    Heç nə gözləmirsə 204 (No Content) qaytarılır ki, n8n axını sadəcə heç nə etmədən dayansın
    (boş obyekt qaytarsaq, IF node yenə `''` üstündə xəta verərdi)."""
    project = (
        db.query(AgentProject)
        .filter(
            AgentProject.status == "AWAITING_APPROVAL",
            AgentProject.notified.is_(False),
            AgentProject.telegram_chat_id.isnot(None),
        )
        .order_by(AgentProject.id)
        .first()
    )
    if not project:
        return Response(status_code=204)
    return PendingProjectOut(
        id=project.id,
        brief=project.brief,
        output_type=project.output_type,
        deliverable_html=project.deliverable_html,
        deliverable_image_url=project.deliverable_image_url,
        telegram_chat_id=project.telegram_chat_id,
        # Token əsaslıdır — n8n bu sahəni olduğu kimi oxuduğu üçün workflow-da dəyişiklik lazım deyil.
        view_url=f"{settings.public_base_url}/s/{project.share_token}",
    )


@router.get("/agency/usage", response_model=UsageReport)
def usage_report(
    days: int = 30, workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db),
):
    """LLM token istifadəsi: hansı provayder/rol nə qədər sərf edir, uğursuzluqlar nədən olur.
    Qeyd: `/agency/{project_id}`-dən ƏVVƏL qeydiyyatdan keçməlidir, yoxsa 'usage' sətri
    project_id kimi parse edilib 422 qaytarar (pending-approval ilə eyni səbəb)."""
    return build_usage_report(db, workspace_id, days=max(1, min(days, 365)))


@router.get("/agency/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id, workspace_id)
    detail = ProjectDetail.model_validate(project, from_attributes=True)
    # UI "Paylaş" düyməsini yalnız hesab HƏQİQƏTƏN qoşulubsa göstərsin deyə.
    detail.instagram_available = instagram.account_for(db.get(Workspace, workspace_id)) is not None
    return detail


@router.post("/agency/{project_id}/run", response_model=RunResult)
async def run_project(project_id: int, workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db)):
    """Layihəni terminal vəziyyətə (ya da addım limitinə) çatana qədər addım-addım irəlilədir.
    Hər addımdan sonra nəticə dərhal WebSocket-lə yayımlanır — beləliklə dashboard-da
    agentlərin işi CANLI axır, sadəcə sonda bir dəfə görünmür.

    `get_lock(project_id)` altında işləyir ki, arxa fon avtonom dövrəsi (scheduler.agency_loop)
    eyni layihəni EYNI ANDA irəlilətməyib təkrarlanan tapşırıqlar yaratmasın."""
    project = _get_project_or_404(db, project_id, workspace_id)
    if not is_enabled(db, workspace_id, "agents_enabled"):
        raise HTTPException(status_code=423, detail="AI agentləri Control Room-dan dayandırılıb.")

    steps = 0
    async with get_lock(project_id):
        while steps < MAX_STEPS_PER_RUN:
            db.refresh(project)
            if project.status in TERMINAL_STATUSES:
                break
            event = await asyncio.to_thread(advance_project, db, project)
            if event is None:
                break
            await manager.broadcast(event)
            steps += 1
            await asyncio.sleep(STEP_DELAY_SECONDS)

    db.refresh(project)
    return RunResult(status=project.status, steps=steps)


def _get_task_or_404(db: Session, project: AgentProject, task_id: int) -> AgentTask:
    task = (
        db.query(AgentTask)
        .filter(AgentTask.id == task_id, AgentTask.project_id == project.id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Tapşırıq tapılmadı")
    return task


@router.post("/agency/{project_id}/task/{task_id}/regenerate", response_model=ProjectDetail)
async def regenerate_single_task(
    project_id: int, task_id: int, payload: RegenerateRequest | None = None,
    workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db),
):
    """TƏK bir departamentin çıxışını yenidən yazdırır — bütün layihəni təkrar işlətmədən.

    Köhnə variant arxivlənir (`/versions` ilə baxıla bilər), ona görə bu əməl geri alına biləndir.
    `get_lock` altında işləyir ki, arxa fon dövrəsi eyni anda həmin layihəyə toxunmasın."""
    project = _get_project_or_404(db, project_id, workspace_id)
    if project.status not in REGENERABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Layihə hələ işləyir (status: {project.status}) — bitməsini gözləyin.",
        )
    task = _get_task_or_404(db, project, task_id)
    instruction = (payload.instruction if payload else None) or None

    async with get_lock(project_id):
        event = await asyncio.to_thread(regenerate_task, db, project, task, instruction)
    await manager.broadcast(event)
    db.refresh(project)
    return project


@router.get("/agency/{project_id}/task/{task_id}/versions", response_model=TaskVersionsResult)
def get_task_versions(
    project_id: int, task_id: int,
    workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db),
):
    """Bir tapşırığın arxivlənmiş köhnə variantları (ən yenisi əvvəldə)."""
    project = _get_project_or_404(db, project_id, workspace_id)
    task = _get_task_or_404(db, project, task_id)
    versions = (
        db.query(AgentTaskVersion)
        .filter(AgentTaskVersion.task_id == task.id)
        .order_by(AgentTaskVersion.version_no.desc())
        .all()
    )
    return TaskVersionsResult(
        task_id=task.id, role=task.role, title=task.title,
        current_output=task.output, versions=versions,
    )


@router.post("/agency/{project_id}/approve", response_model=ProjectOut)
async def approve_project(project_id: int, workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db)):
    project = _get_project_or_404(db, project_id, workspace_id)
    if project.status != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail=f"Layihə təsdiq gözləmir (status: {project.status})")
    project.status = "DELIVERED"
    db.commit()
    await manager.broadcast({
        "type": "agent_event", "project_id": project.id, "workspace_id": project.workspace_id, "project_status": project.status,
        "from_role": "human", "to_role": None, "kind": "decision", "content": "Müştəri təsdiqlədi ✅ Layihə TƏHVİL VERİLDİ.",
    })
    return project


@router.post("/agency/{project_id}/reject", response_model=RejectResult)
async def reject_project(project_id: int, payload: RejectRequest | None = None, workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db)):
    """Rədd edir. Səbəb (`reason`) verilibsə, komanda NİYƏ bəyənilmədiyini bilsin deyə eyni brif
    və rədd səbəbi ilə AVTOMATİK YENİ LAYİHƏ başladılır (bax: `agency.start_retry`) — beləliklə
    təkrar cəhd korrun eyni səhvi kor-koranə təkrarlamır."""
    project = _get_project_or_404(db, project_id, workspace_id)
    if project.status != "AWAITING_APPROVAL":
        raise HTTPException(status_code=400, detail=f"Layihə təsdiq gözləmir (status: {project.status})")
    reason = (payload.reason if payload else None) or None
    project.status = "REJECTED"
    project.reject_feedback = reason
    db.commit()
    await manager.broadcast({
        "type": "agent_event", "project_id": project.id, "workspace_id": project.workspace_id, "project_status": project.status,
        "from_role": "human", "to_role": None, "kind": "decision",
        "content": f"Müştəri rədd etdi ❌.{' Səbəb: ' + reason if reason else ''}",
    })

    retry_id = None
    if reason:
        retry_project, retry_event = start_retry(db, project, reason)
        retry_id = retry_project.id
        await manager.broadcast(retry_event)

    return RejectResult(id=project.id, brief=project.brief, status=project.status, created_at=project.created_at, retry_project_id=retry_id)


@router.post("/agency/{project_id}/mark-notified", response_model=ProjectOut, dependencies=[Depends(require_api_key)])
def mark_notified(project_id: int, db: Session = Depends(get_db)):
    """n8n Telegram bildirişini uğurla göndərdikdən sonra çağırır ki, təkrar bildiriş getməsin."""
    project = _get_project_or_404(db, project_id)
    project.notified = True
    db.commit()
    return project


@router.get("/agency/{project_id}/instagram-payload", dependencies=[Depends(require_api_key)])
def instagram_payload(project_id: int, db: Session = Depends(get_db)):
    """n8n üçün hazır paylaşım məlumatı: `{publish, image_url, caption, reason}`.

    NİYƏ BU ENDPOINT VAR: paylaşımı n8n edir (bax PROJECT_STATE.md, 59), amma şəkil
    ünvanının seçilməsi qeyri-triviallıqdır — proksi/mənbə seçimi, keş qıran parametr,
    Meta-nın yükləyə bildiyi host siyahısı. Bu məntiqi n8n-də TƏKRARLAMAMAQ üçün qərarı
    burada veririk, n8n isə sadəcə hazır `image_url`-i ötürür. Beləliklə düzəliş bir yerdə
    edilir.

    `publish=false` olanda `reason` səbəbi izah edir — n8n onu Telegram-a yazır.
    """
    project = _get_project_or_404(db, project_id)
    if project.output_type != "social_post":
        return {"publish": False, "reason": f"Layihə növü '{project.output_type}' — Instagram postu deyil."}
    if project.instagram_published:
        return {"publish": False, "reason": "Bu layihə artıq Instagram-a paylaşılıb."}
    if not instagram.is_configured():
        return {"publish": False, "reason": "Instagram konfiqurasiya olunmayıb (.env)."}

    image_url = _instagram_image_url(project)
    if not image_url:
        return {"publish": False, "reason": (
            "Şəkil ünvanı Meta üçün əlçatan deyil: PUBLIC_MEDIA_BASE_URL lokaldır və mənbə "
            "şəkli də yüklənə bilən host-da deyil."
        )}
    return {
        "publish": True,
        "project_id": project.id,
        "image_url": image_url,
        "caption": project.deliverable_html or "",
    }


@router.post("/agency/{project_id}/mark-instagram-published", dependencies=[Depends(require_api_key)])
def mark_instagram_published(project_id: int, post_id: str = "", permalink: str = "", db: Session = Depends(get_db)):
    """n8n paylaşımı bitirdikdən sonra nəticəni bazaya yazır (təkrar paylaşımı bloklayır)."""
    project = _get_project_or_404(db, project_id)
    project.instagram_published = True
    project.instagram_post_id = post_id or None
    project.instagram_permalink = permalink or None
    if project.status == "AWAITING_APPROVAL":
        project.status = "DELIVERED"
    db.commit()
    return {"ok": True, "project_id": project.id, "permalink": project.instagram_permalink}


@router.post("/agency/{project_id}/publish-instagram", response_model=InstagramPublishResult)
async def publish_instagram(project_id: int, workspace_id: int = Depends(workspace_scope), db: Session = Depends(get_db)):
    """Təsdiqlənmiş `social_post` layihəsini Instagram-a dərc edir (rəsmi Graph API).
    Bu, GERİ ALINMAYAN ictimai əməldir — yalnız açıq istifadəçi əməli ilə (bu endpoint çağırılanda)
    baş verir. Şəkil `public_base_url/s/{share_token}/image`-dən Meta tərəfindən yüklənir, ona görə
    həmin ünvan İCTİMAİ olmalıdır. Uğurda layihə DELIVERED işarələnir və təkrar paylaşım bloklanır."""
    if not (settings.social_publish_enabled or settings.external_actions_enabled):
        raise HTTPException(status_code=409, detail="Təhlükəsiz demo rejimi aktivdir; xarici paylaşım bloklanıb.")
    project = _get_project_or_404(db, project_id, workspace_id)
    if project.output_type != "social_post":
        raise HTTPException(status_code=400, detail="Yalnız Instagram postu (social_post) layihələri paylaşıla bilər.")
    if project.status not in ("AWAITING_APPROVAL", "DELIVERED"):
        raise HTTPException(status_code=400, detail=f"Layihə paylaşıma hazır deyil (status: {project.status}).")
    if project.instagram_published:
        raise HTTPException(status_code=400, detail="Bu layihə artıq Instagram-a paylaşılıb.")

    # Hesab MƏHZ bu workspace-in olmalıdır. Əvvəl qlobal .env hesabı istifadə olunurdu —
    # yəni istənilən müştərinin paylaşımı tətbiq sahibinin hesabına gedirdi.
    account = instagram.account_for(db.get(Workspace, workspace_id))
    if account is None:
        raise HTTPException(
            status_code=402,   # Payment Required — bu, əlavə ödənişli paketdir
            detail=(
                "Instagram avtomatik paylaşım bu workspace üçün aktiv deyil. "
                "Bu, əlavə paketdir — hesabınızı qoşduqdan sonra işə düşür."
            ),
        )

    image_url = _instagram_image_url(project)
    if not image_url:
        return InstagramPublishResult(ok=False, detail=(
            "Şəkli Instagram-a çatdırmaq mümkün deyil: PUBLIC_BASE_URL lokaldır və layihənin "
            "mənbə şəkli də Meta-nın yükləyə bildiyi ünvanda deyil. Port 8800-ü tunellə açıb "
            "PUBLIC_BASE_URL-i yeniləyin."
        ))
    caption = project.deliverable_html or ""
    try:
        result = await asyncio.to_thread(instagram.publish_photo, account, image_url, caption)
    except instagram.InstagramError as exc:
        logger.warning("Instagram paylaşımı uğursuz (layihə %s): %s", project.id, exc)
        return InstagramPublishResult(ok=False, detail=str(exc))

    project.instagram_published = True
    project.instagram_post_id = result.get("id")
    project.instagram_permalink = result.get("permalink")
    tracker = db.query(SocialPostTracker).filter(SocialPostTracker.project_id == project.id).first()
    if not tracker:
        tracker = SocialPostTracker(workspace_id=project.workspace_id, project_id=project.id)
        db.add(tracker)
    tracker.external_post_id = result.get("id")
    tracker.permalink = result.get("permalink")
    tracker.status = "ACTIVE"
    tracker.next_sync_at = datetime.utcnow()
    if project.status == "AWAITING_APPROVAL":
        project.status = "DELIVERED"  # paylaşım təsdiq deməkdir
    db.commit()
    await manager.broadcast({
        "type": "agent_event", "project_id": project.id, "workspace_id": project.workspace_id, "project_status": project.status,
        "from_role": "human", "to_role": None, "kind": "decision",
        "content": f"📸 Instagram-a paylaşıldı." + (f" {result['permalink']}" if result.get("permalink") else ""),
    })
    return InstagramPublishResult(ok=True, post_id=result.get("id"), permalink=result.get("permalink"))


# Meta şəkli ÖZÜ yükləyir, ona görə mənbə host bunu bloklamamalıdır. Aşağıdakılar real
# sınaqdan keçib (bax PROJECT_STATE.md, 51-ci maddə). Wikimedia və pollinations İŞLƏMİR:
# birincisi Meta-nın yükləyicisini bloklayır, ikincisi şəkli sorğu anında generasiya etdiyi
# üçün çox yavaşdır. Onlar üçün backend proksisi (yəni ictimai PUBLIC_BASE_URL) şərtdir.
_META_FETCHABLE_HOSTS = ("images.pexels.com", "images.unsplash.com", "cdn.pixabay.com")


def _instagram_image_url(project: AgentProject) -> str | None:
    """Instagram-a veriləcək şəkil ünvanını seçir.

    1) PUBLIC_BASE_URL ictimaidirsə — backend proksisi (ən etibarlısı: şəkil keşlənir,
       mənbənin yavaşlığından/əlçatmazlığından asılı deyil).
    2) Deyilsə — mənbə URL-i birbaşa, amma yalnız Meta-nın yükləyə bildiyi host-lardan.
    3) Heç biri yoxdursa — None (çağıran tərəf istifadəçiyə izahlı xəta qaytarır).
    """
    base = settings.public_media_base_url
    if not base.startswith(("http://127.0.0.1", "http://localhost")):
        # Token əsaslı ictimai ünvan: Meta başlıq göndərə bilmir, ona görə bu ünvan açarsız
        # olmalıdır — amma ardıcıl ID ilə sadalana bilməməlidir.
        #
        # `?v=<vaxt>` KEŞ QIRANDIR və VACİBDİR: Meta uğursuz yükləməni URL üzrə keşləyir.
        # Bir dəfə alınmasa (məs. mənbə o an boş qaytarıb), həmin ünvan məzmun düzələndən
        # sonra da rədd olunur — həm də məlumatsız `code: 1` xətası ilə. Hər cəhddə fərqli
        # `v` veririk ki, təkrar cəhd təmiz başlasın. Bax PROJECT_STATE.md, 58-ci maddə.
        return f"{base}/s/{project.share_token}/image?v={int(time.time())}"

    source = (project.deliverable_image_url or "").strip()
    if source.startswith("https://") and urlparse(source).netloc in _META_FETCHABLE_HOSTS:
        logger.info("Instagram: PUBLIC_BASE_URL lokaldır, mənbə URL birbaşa istifadə olunur (layihə %s)", project.id)
        return source
    return None


def _image_bytes(project: AgentProject) -> bytes:
    """Deliverable şəklini keşdən qaytarır, yoxdursa mənbədən bir dəfə yükləyir.
    İlk sorğuda pollinations-dan yüklənib keşlənir, sonrakılar keşdən dərhal gəlir. Beləliklə
    n8n → Telegram şəkil göndərişi etibarlı olur (yavaş, ictimai pollinations URL-inə asılı deyil)."""
    if project.id in _image_cache:
        return _image_cache[project.id]
    url = project.deliverable_image_url
    if not url:
        raise HTTPException(status_code=404, detail="Bu layihənin şəkli yoxdur")
    try:
        resp = requests.get(url, timeout=60, headers={"User-Agent": HTTP_USER_AGENT})
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Şəkil yüklənə bilmədi (layihə %s): %s", project.id, exc)
        raise HTTPException(status_code=502, detail="Şəkil mənbədən yüklənə bilmədi") from exc

    # BOŞ CAVABI KEŞLƏMƏ. Bəzi mənbələr (məs. pollinations `enhance=true` ilə) uğursuzluğu
    # 200 + boş gövdə kimi qaytarır — `raise_for_status()` bunu tutmur. Keşlənsə, həmin
    # layihənin şəkli əbədi 0 bayt qalır və səbəb görünməz olur (real yaşanıb).
    if not resp.content:
        logger.warning("Şəkil mənbəsi BOŞ cavab qaytardı (layihə %s): %s", project.id, url[:120])
        raise HTTPException(status_code=502, detail="Şəkil mənbəsi boş cavab qaytardı")

    while len(_image_cache) >= _IMAGE_CACHE_MAX_ITEMS:
        _image_cache.pop(next(iter(_image_cache)))
    _image_cache[project.id] = resp.content
    return resp.content


@router.api_route("/s/{share_token}/image", methods=["GET", "HEAD"])
def project_image_public(share_token: str, db: Session = Depends(get_db)):
    """Şəklin İCTİMAİ (autentifikasiyasız) ünvanı — QƏSDƏN belədir.

    Instagram/Meta media konteyneri yaradanda şəkli ÖZÜ yükləyir və heç bir başlıq (header)
    göndərə bilmir, yəni API açarı ilə qorunan ünvan onun üçün yararsızdır. Buna görə ünvanda
    ardıcıl layihə ID-si YOX, təxmin edilə bilməyən `share_token` var — `/s/{token}` səhifəsi
    ilə eyni model. Beləliklə şəkil xarici xidmətlər üçün əlçatan qalır, amma
    /agency/1/image, /agency/2/image … deyə sadalamaqla bütün workspace-lərin şəkillərini
    HEAD DƏ DƏSTƏKLƏNİR (FastAPI `@router.get` bunu avtomatik etmir): Meta media konteyneri
    yaratmazdan əvvəl HEAD sorğusu atır və 405 alanda ümumi `code: 1` xətası qaytarır —
    səbəbi göstərmir, ona görə tapmaq çətindir. Bax PROJECT_STATE.md, 57-ci maddə."""
    project = (
        db.query(AgentProject).filter(AgentProject.share_token == share_token).first()
        if share_token else None
    )
    if not project:
        raise HTTPException(status_code=404, detail="Layihə tapılmadı")
    return Response(content=_image_bytes(project), media_type="image/jpeg")


@router.get("/agency/{project_id}/image", dependencies=[Depends(require_api_key)])
def project_image(project_id: int, db: Session = Depends(get_db)):
    """ID əsaslı daxili ünvan — yalnız API açarı ilə (n8n kimi server-server istifadəçilər üçün).
    Açarsız ictimai giriş lazımdırsa `/s/{share_token}/image` istifadə edilməlidir."""
    return Response(content=_image_bytes(_get_project_or_404(db, project_id)), media_type="image/jpeg")


@router.get("/health")
def health(db: Session = Depends(get_db)):
    from sqlalchemy import text
    from app.core import settings

    db.execute(text("SELECT 1"))
    components = {"database": "ok", "worker_mode": settings.worker_mode}
    if settings.worker_mode == "celery":
        try:
            from redis import Redis
            components["redis"] = "ok" if Redis.from_url(settings.redis_url).ping() else "error"
        except Exception:
            components["redis"] = "error"
    return {"status": "ok" if components.get("redis") != "error" else "degraded",
            "components": components}
