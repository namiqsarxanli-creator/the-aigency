"""HTML səhifələri (dashboard + müştəriyə göndərilən ictimai nəticə linki)."""
import logging
import re
import secrets
from pathlib import Path

from urllib.parse import parse_qs, urlencode
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.analytics import build_analytics
from app.usage_report import build_usage_report
from app.export import build_zip, collect_bundle, render_report_html, zip_filename
from app.db_models import AgentProject, AssetReview, AssetSocialTracker, BrandKitSuggestion, Campaign, CampaignDay, CampaignMetric, ContentAsset, FactoryAuditLog, FactoryJob, LeadAudit, MeetingBrief, NightShiftPlan, NightShiftReport, OutboundDelivery, PitchMeeting, SalesActivity, SalesLead, SalesProposal, SocialPostTracker
from app.factory import get_control, log_action
from app.night_shift import BAKU, enqueue_now, next_run_utc
from app.outbound import smtp_ready, external_delivery_enabled
from app.core import contact_phone_href, settings
from app.lead_finder import CATEGORY_TAGS, OUTREACH_LANGUAGES, discover_businesses
from app.sales_intelligence import audit_lead, create_meeting_brief, create_outreach_sequence, create_proposal
from app.brand_sync import SUGGESTABLE, apply_suggestion
from app.campaign_ai import enrich_campaign
from app.campaigns import (
    DURATION_PRESETS, MAX_DURATION, MIN_DURATION, create_campaign,
    normalize_duration, phase_distribution, resize_campaign, resize_impact,
)
from app.content_studio import (
    apply_result, archive_version, create_asset, format_for_campaign_type, json_list, parse_slides,
)
from app.studio_ai import (
    DELTAS, GOALS, TONES, StudioBrief, brief_from_campaign_day, brief_from_form, generate_draft,
)
from app.auth import (
    SESSION_COOKIE, authenticate, clear_session_cookie, context_from_request,
    create_session, is_platform_owner, register_user, revoke_session, set_session_cookie,
)

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")
logger = logging.getLogger(__name__)

_CITY_TRANSLIT = str.maketrans({
    "ə": "e", "Ə": "e", "ğ": "g", "Ğ": "g", "ı": "i", "I": "i", "İ": "i",
    "ö": "o", "Ö": "o", "ü": "u", "Ü": "u", "ç": "c", "Ç": "c", "ş": "s", "Ş": "s",
})


def _normalize_city(text: str) -> str:
    """Şəhər axtarışı üçün: kiçik hərf + Azərbaycan/Türk hərflərini ASCII-yə salır ki,
    istifadəçinin yazdığı "baki" saxlanılan "Bakı, Azərbaycan" daxilində tapılsın."""
    return text.lower().translate(_CITY_TRANSLIT)


# Brand Kit-də şrift seçimi — sərbəst mətn əvəzinə kuratorlu siyahı, hər biri nümunə ilə
# göstərilir (bax templates/brand_kit.html). Google Fonts-da mövcud, geniş yayılmış cütlər.
FONT_OPTIONS = [
    "Playfair Display", "Instrument Serif", "Cormorant Garamond", "DM Serif Display",
    "Cinzel", "Lora", "Inter", "Poppins", "Manrope", "Work Sans", "Space Grotesk",
    "Outfit", "DM Sans", "Sora",
]

# Şriftlərlə eyni məntiq: sərbəst mətn (əl ilə HEX yazmaq) əvəzinə kuratorlu palitra siyahısı —
# hər biri hazır 3 rənglə (vurğu, tünd, açıq) gəlir (bax templates/brand_kit.html).
COLOR_PALETTES = [
    ("Qızılı & Tünd", ["#D4B978", "#17110D", "#F2EEE6"]),
    ("Sakit Pastel", ["#E8B4B8", "#F7E7CE", "#3A3335"]),
    ("Cəsarətli Neon", ["#00E5A0", "#0B0B0F", "#FF3B6E"]),
    ("Torpaq Tonları", ["#B08968", "#3D2B1F", "#EDE0D4"]),
    ("Mono Boz", ["#2B2B2B", "#8C8C8C", "#F4F4F4"]),
    ("Okean Mavisi", ["#0F5C8C", "#022B3A", "#E1F1FA"]),
    ("Meşə Yaşılı", ["#2F5233", "#1B2E1D", "#E7EFE2"]),
    ("İsti Terrakota", ["#C1633C", "#3B2216", "#F5E6D3"]),
    ("Korporativ Lacivərd", ["#1F3A93", "#0A0F2C", "#F0F3FA"]),
    ("Çəhrayı Romantik", ["#D98CA0", "#4A2532", "#FBEFF1"]),
    ("Minimal Ağ-Qara", ["#111111", "#666666", "#FFFFFF"]),
    ("Bənövşəyi Kreativ", ["#7C3AED", "#1E1033", "#F1E9FF"]),
]

# Əlaqə məlumatları HƏR səhifədə lazımdır (footer). Qlobal kimi qeyd edirik ki, hər route-a
# ayrıca ötürməyi unutmaq mümkün olmasın — unutsaq footer səssizcə boş qalardı.
templates.env.globals["contact_phone"] = settings.contact_phone
templates.env.globals["contact_phone_href"] = contact_phone_href()
templates.env.globals["contact_email"] = settings.contact_email
templates.env.globals["contact_hours"] = settings.contact_hours
templates.env.globals["voice_agent_enabled"] = settings.voice_agent_enabled


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "agency.html", {
        "active_page": "agency", "current_user": context.user,
        "current_workspace": context.workspace, "membership": context.membership,
    })


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    # DİQQƏT: əvvəllər artıq giriş edilmişsə birbaşa "/"-ə yönləndirilirdi — bu, istifadəçinin
    # BAŞQA hesabla daxil olmasını qeyri-mümkün edirdi (formu heç görə bilmirdi, əvvəlcə
    # çıxış etməli idi). POST /login onsuz da yeni sessiya yaradıb köhnə çərəzi əvəz edir,
    # ona görə forma həmişə açıq qalmalıdır (canlı istifadəçi tapıntısı).
    return templates.TemplateResponse(request, "auth_synapsex.html", {"mode": "login", "error": None})


@router.post("/login")
async def login_submit(request: Request, db: Session = Depends(get_db)):
    form = parse_qs((await request.body()).decode("utf-8"))
    email = (form.get("email") or [""])[0]
    password = (form.get("password") or [""])[0]
    context = authenticate(db, email, password)
    if not context:
        return templates.TemplateResponse(
            request, "auth_synapsex.html", {"mode": "login", "error": "Email və ya şifrə yanlışdır."},
            status_code=400,
        )
    raw_token = create_session(db, context)
    response = RedirectResponse("/", status_code=303)
    set_session_cookie(response, raw_token)
    return response


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    if context_from_request(request, db):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "auth_synapsex.html", {"mode": "register", "error": None})


@router.post("/register")
async def register_submit(request: Request, db: Session = Depends(get_db)):
    form = parse_qs((await request.body()).decode("utf-8"))
    full_name = (form.get("full_name") or [""])[0].strip()
    company_name = (form.get("company_name") or [""])[0].strip()
    email = (form.get("email") or [""])[0].strip()
    password = (form.get("password") or [""])[0]
    if len(full_name) < 2 or len(company_name) < 2 or len(email) < 5 or len(password) < 8:
        return templates.TemplateResponse(
            request, "auth_synapsex.html",
            {"mode": "register", "error": "Bütün sahələri düzgün doldurun; şifrə ən az 8 simvol olsun."},
            status_code=400,
        )
    try:
        context = register_user(db, email, full_name, company_name, password)
    except ValueError as exc:
        return templates.TemplateResponse(
            request, "auth_synapsex.html", {"mode": "register", "error": str(exc)}, status_code=400,
        )
    raw_token = create_session(db, context)
    response = RedirectResponse("/", status_code=303)
    set_session_cookie(response, raw_token)
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    revoke_session(db, request.cookies.get(SESSION_COOKIE))
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response


def _parsed_fonts(raw: str | None) -> tuple[str, str]:
    """`brand_fonts` "Başlıq, Mətn" formatında saxlanılır — seçicini əvvəlcədən doldurmaq üçün ayırır."""
    parts = [p.strip() for p in (raw or "").split(",") if p.strip()]
    heading = parts[0] if parts else FONT_OPTIONS[0]
    body = parts[1] if len(parts) > 1 else FONT_OPTIONS[6]
    return heading, body


def _palette_options(raw: str | None) -> tuple[list[dict], str]:
    """`brand_colors` "#HEX, #HEX, #HEX" formatında saxlanılır. Kuratorlu palitra seçicisini
    əvvəlcədən doldurur — saxlanılan dəyər siyahıdakı palitralardan biri ilə üst-üstə düşmürsə
    (məs. köhnə əl ilə yazılmış rənglər), onu "Hazırkı seçim" kimi başa əlavə edirik ki, səhifə
    açılanda istifadəçinin mövcud rəngləri səssizcə dəyişdirilməsin."""
    hexes = [h.upper() for h in re.findall(r"#[0-9a-fA-F]{6}", raw or "")]
    options = [{"name": name, "value": ", ".join(colors)} for name, colors in COLOR_PALETTES]
    if not hexes:
        return options, options[0]["value"]
    stored_value = ", ".join(hexes)
    if any(opt["value"].upper() == stored_value.upper() for opt in options):
        return options, next(opt["value"] for opt in options if opt["value"].upper() == stored_value.upper())
    options = [{"name": "Hazırkı seçim", "value": stored_value}] + options
    return options, stored_value


@router.get("/brand-kit", response_class=HTMLResponse)
def brand_kit_page(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    heading_font, body_font = _parsed_fonts(context.workspace.brand_fonts)
    color_options, color_selected = _palette_options(context.workspace.brand_colors)
    from app import tiktok
    return templates.TemplateResponse(request, "brand_kit.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "saved": request.query_params.get("saved") == "1",
        "error": None,
        "suggestions": db.query(BrandKitSuggestion).filter(
            BrandKitSuggestion.workspace_id == context.workspace.id,
            BrandKitSuggestion.status == "PENDING",
        ).order_by(BrandKitSuggestion.id.desc()).all(),
        "suggestable": SUGGESTABLE,
        "font_options": FONT_OPTIONS, "heading_font": heading_font, "body_font": body_font,
        "color_options": color_options, "color_selected": color_selected,
        "tiktok_app_configured": tiktok.app_configured(),
        "tiktok_connected": bool(tiktok.account_for(context.workspace)),
        "tiktok_notice": request.query_params.get("tiktok"),
    })


@router.post("/brand-kit")
async def brand_kit_save(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    value = lambda key, limit: ((form.get(key) or [""])[0].strip())[:limit]
    logo_url = value("brand_logo_url", 500)
    if logo_url and not logo_url.lower().startswith(("http://", "https://")):
        heading_font, body_font = _parsed_fonts(value("brand_fonts", 300))
        color_options, color_selected = _palette_options(value("brand_colors", 300))
        from app import tiktok
        return templates.TemplateResponse(request, "brand_kit.html", {
            "current_user": context.user, "current_workspace": context.workspace,
            "membership": context.membership, "saved": False,
            "error": "Loqo ünvanı http:// və ya https:// ilə başlamalıdır.",
            "suggestions": [], "suggestable": SUGGESTABLE,
            "font_options": FONT_OPTIONS, "heading_font": heading_font, "body_font": body_font,
            "color_options": color_options, "color_selected": color_selected,
            "tiktok_app_configured": tiktok.app_configured(),
            "tiktok_connected": bool(tiktok.account_for(context.workspace)),
            "tiktok_notice": None,
        }, status_code=400)
    workspace = context.workspace
    # Workspace adı əvvəl YALNIZ qeydiyyatda yazılırdı və dəyişdirmək üçün interfeys yox idi —
    # səhv ad qalırsa yeganə yol bazaya müdaxilə idi (canlı sistemdə "Kətan" belə qalmışdı).
    new_name = value("workspace_name", 120)
    if len(new_name) >= 2:
        workspace.name = new_name
    workspace.brand_description = value("brand_description", 3000)
    workspace.brand_audience = value("brand_audience", 3000)
    workspace.brand_voice = value("brand_voice", 1500)
    workspace.brand_colors = value("brand_colors", 300)
    workspace.brand_fonts = value("brand_fonts", 300)
    workspace.brand_products = value("brand_products", 4000)
    workspace.brand_forbidden_phrases = value("brand_forbidden_phrases", 2000)
    workspace.brand_glossary = value("brand_glossary", 2000)
    workspace.brand_logo_url = logo_url or None
    workspace.brand_ai_consent = (form.get("brand_ai_consent") or [""])[0] == "on"
    workspace.brand_updated_at = datetime.utcnow()
    db.commit()
    return RedirectResponse("/brand-kit?saved=1", status_code=303)


_TIKTOK_STATE_COOKIE = "tiktok_oauth_state"


@router.get("/tiktok/connect")
def tiktok_connect(request: Request, db: Session = Depends(get_db)):
    """İstifadəçini TikTok icazə səhifəsinə göndərir. Geri qayıdanda `/tiktok/callback`
    eyni brauzer sessiyasından workspace-i tapır (bax `context_from_request`)."""
    from app import tiktok

    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not tiktok.app_configured():
        return RedirectResponse("/brand-kit?tiktok=app_not_configured", status_code=303)

    state = secrets.token_urlsafe(24)
    response = RedirectResponse(tiktok.authorize_url(state), status_code=303)
    # CSRF qorunması: callback-də bu çərəzin dəyəri `state` parametri ilə müqayisə olunur.
    response.set_cookie(_TIKTOK_STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax")
    return response


@router.get("/tiktok/callback")
def tiktok_callback(request: Request, db: Session = Depends(get_db)):
    from app import tiktok

    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)

    error = request.query_params.get("error")
    if error:
        return RedirectResponse("/brand-kit?tiktok=denied", status_code=303)

    state = request.query_params.get("state") or ""
    if not state or state != request.cookies.get(_TIKTOK_STATE_COOKIE):
        return RedirectResponse("/brand-kit?tiktok=state_mismatch", status_code=303)

    code = request.query_params.get("code")
    if not code:
        return RedirectResponse("/brand-kit?tiktok=no_code", status_code=303)

    try:
        data = tiktok.exchange_code(code)
    except tiktok.TikTokError as exc:
        logger.warning("TikTok OAuth uğursuz oldu (workspace %s): %s", context.workspace.id, exc)
        return RedirectResponse("/brand-kit?tiktok=exchange_failed", status_code=303)

    workspace = context.workspace
    workspace.tiktok_access_token = data["access_token"]
    workspace.tiktok_refresh_token = data.get("refresh_token")
    workspace.tiktok_open_id = data.get("open_id")
    workspace.tiktok_token_expires_at = datetime.utcnow() + timedelta(seconds=int(data.get("expires_in", 0) or 0))
    workspace.tiktok_addon_enabled = True
    db.commit()

    response = RedirectResponse("/brand-kit?tiktok=connected", status_code=303)
    response.delete_cookie(_TIKTOK_STATE_COOKIE)
    return response


@router.post("/tiktok/disconnect")
def tiktok_disconnect(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    workspace = context.workspace
    workspace.tiktok_access_token = None
    workspace.tiktok_refresh_token = None
    workspace.tiktok_open_id = None
    workspace.tiktok_token_expires_at = None
    workspace.tiktok_addon_enabled = False
    db.commit()
    return RedirectResponse("/brand-kit?tiktok=disconnected", status_code=303)


@router.get("/campaigns", response_class=HTMLResponse)
def campaigns_page(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    campaigns = db.query(Campaign).filter(Campaign.workspace_id == context.workspace.id).order_by(Campaign.id.desc()).all()
    selected_id = request.query_params.get("id")
    selected, campaign_missing = None, False
    if selected_id:
        # KONKRET kampaniya istənilib. Tapılmasa ƏVƏZİNƏ BAŞQASINI GÖSTƏRMİRİK.
        # Əvvəl `selected = campaigns[0]` edilirdi və bu, Studio-dakı RC-3-dən də təhlükəli idi:
        # səhifədəki müddət formasının `action`-ı `selected_campaign.id`-yə bağlıdır, yəni
        # silinmiş kampaniyaya köhnə linkdən girən istifadəçi BAŞQA kampaniyanı görür və
        # «Tətbiq et» basanda onun günlərini silir. Canlı sınaqda təsdiqləndi.
        if selected_id.isdigit():
            selected = db.query(Campaign).filter(
                Campaign.id == int(selected_id), Campaign.workspace_id == context.workspace.id
            ).first()
        campaign_missing = selected is None
    elif campaigns:
        # Ünvanda id yoxdursa ən sonuncunu açmaq düzgündür — bu, əvəzləmə deyil.
        selected = campaigns[0]
    return templates.TemplateResponse(request, "campaigns.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "campaigns": campaigns, "selected_campaign": selected,
        "duration_presets": DURATION_PRESETS, "min_duration": MIN_DURATION,
        "max_duration": MAX_DURATION, "today": date.today(),
        "phase_preview": phase_distribution(len(selected.days)) if selected and selected.days else [],
        "resize_notice": request.query_params.get("resized"),
        "campaign_missing": campaign_missing,
        "error": None,
    })


@router.post("/campaigns/{campaign_id}/duration")
async def campaign_resize(campaign_id: int, request: Request, db: Session = Depends(get_db)):
    """Mövcud kampaniyanın müddətini dəyişir (CD-3).

    Qısaltma DAĞIDICIDIR, ona görə iki addımlıdır: `confirm` göndərilməyibsə nə itəcəyini
    hesablayıb təsdiq üçün geri qaytarır. Uzatma itki yaratmadığı üçün dərhal tətbiq olunur."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    campaign = db.query(Campaign).filter(
        Campaign.id == campaign_id, Campaign.workspace_id == context.workspace.id
    ).first()
    if not campaign:
        return RedirectResponse("/campaigns", status_code=303)

    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    raw = (form.get("duration") or [""])[0]
    if raw == "custom":
        raw = (form.get("duration_custom") or [""])[0]
    target = normalize_duration(raw)
    confirmed = (form.get("confirm") or [""])[0] == "1"

    impact = resize_impact(db, campaign, target)
    if impact["removed"] and not confirmed:
        # Təsdiq mərhələsi: heç nə dəyişmir, istifadəçiyə DƏQİQ say göstərilir.
        campaigns = db.query(Campaign).filter(Campaign.workspace_id == context.workspace.id).order_by(Campaign.id.desc()).all()
        return templates.TemplateResponse(request, "campaigns.html", {
            "current_user": context.user, "current_workspace": context.workspace,
            "membership": context.membership, "campaigns": campaigns, "selected_campaign": campaign,
            "duration_presets": DURATION_PRESETS, "min_duration": MIN_DURATION,
            "max_duration": MAX_DURATION, "today": date.today(),
            "phase_preview": phase_distribution(len(campaign.days)) if campaign.days else [],
            "pending_resize": impact, "resize_notice": None, "error": None,
        })

    result = resize_campaign(db, campaign, target)
    notice = urlencode({"resized": f"{result['added']}-{result['removed']}-{result['detached']}"})
    return RedirectResponse(f"/campaigns?id={campaign.id}&{notice}", status_code=303)


@router.post("/campaigns")
async def campaign_create(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    get_value = lambda key, limit: ((form.get(key) or [""])[0].strip())[:limit]
    name, objective = get_value("name", 160), get_value("objective", 2000)
    if len(name) < 3 or len(objective) < 10:
        campaigns = db.query(Campaign).filter(Campaign.workspace_id == context.workspace.id).all()
        return templates.TemplateResponse(request, "campaigns.html", {
            "current_user": context.user, "current_workspace": context.workspace,
            "membership": context.membership, "campaigns": campaigns, "selected_campaign": None,
            "error": "Kampaniya adı və ən az 10 simvolluq məqsəd yazın.",
        }, status_code=400)
    # Müddət: "custom" seçilibsə ayrı sahədən oxunur. `normalize_duration` icazəli
    # aralığa (3-90) salır, ona görə yanlış giriş xəta yox, defolt verir.
    raw_duration = get_value("duration_custom", 5) if get_value("duration", 10) == "custom" else get_value("duration", 10)
    campaign = create_campaign(
        db, context.workspace, name, objective, get_value("audience", 2000),
        get_value("channels", 300), get_value("monthly_budget", 80),
        date.fromisoformat(get_value("start_date", 10)) if get_value("start_date", 10) else date.today(),
        duration_days=normalize_duration(raw_duration),
    )
    # Plan quruluşu determinist yığıldı; indi gün mətnləri brendə uyğunlaşdırılır (audit #3).
    # Uğursuz olsa şablon mətni qalır — plan heç vaxt boş və ya yarımçıq olmur.
    enrich_campaign(db, context.workspace, campaign)
    return RedirectResponse(f"/campaigns?id={campaign.id}", status_code=303)


@router.get("/calendar", response_class=HTMLResponse)
def content_calendar(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    items = (
        db.query(CampaignDay).join(Campaign)
        .filter(Campaign.workspace_id == context.workspace.id, Campaign.status != "DRAFT")
        .order_by(CampaignDay.planned_date, CampaignDay.day_number).all()
    )
    return templates.TemplateResponse(request, "calendar.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "items": items, "today": date.today(),
    })


@router.post("/calendar/{day_id}/status")
async def calendar_status(day_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    status = ((form.get("status") or [""])[0]).upper()
    if status not in {"PLANNED", "IN_REVIEW", "APPROVED", "PUBLISHED"}:
        return RedirectResponse("/calendar", status_code=303)
    item = db.query(CampaignDay).join(Campaign).filter(
        CampaignDay.id == day_id, Campaign.workspace_id == context.workspace.id
    ).first()
    if item:
        item.status = status
        db.commit()
    return RedirectResponse("/calendar", status_code=303)


@router.post("/campaigns/day/{day_id}/to-asset")
def campaign_day_to_asset(day_id: int, request: Request, db: Session = Depends(get_db)):
    """KÖRPÜ: kampaniya planındakı bir günü Content Studio-da hazır draft-a çevirir.
    Gün üçün artıq material yaradılıbsa təkrar yaratmır, mövcudunu açır (idempotent) — belə
    olanda düyməyə iki dəfə basmaq dublikat yaratmır."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    day = db.query(CampaignDay).join(Campaign).filter(
        CampaignDay.id == day_id, Campaign.workspace_id == context.workspace.id
    ).first()
    if not day:
        return RedirectResponse("/calendar", status_code=303)

    existing = db.query(ContentAsset).filter(
        ContentAsset.campaign_day_id == day.id,
        ContentAsset.workspace_id == context.workspace.id,
    ).first()
    if existing:
        return RedirectResponse(f"/content-studio?id={existing.id}", status_code=303)

    # Ada kampaniya adı əlavə olunur: əks halda hər kampaniyanın 1-ci günü eyni
    # "Gün 1 · Reel" adını alır və yan siyahıda bir-birindən seçilmir (RC-1).
    asset = create_asset(
        db, context.workspace,
        title=f"{day.campaign.name} · Gün {day.day_number} · {day.content_type}"[:180],
        content_format=format_for_campaign_type(day.content_type),
        # SC-1: caption-a `theme` YAZILMIR — o, istehsal etiketidir ("Dəyər · praktik
        # bələdçi"), müştərinin oxuyacağı mətn deyil. Etiketin yeri vizual brifdir və
        # orada F0-dan sonra açıq şəkildə brif kimi nişanlanır.
        headline=day.hook or "",
        caption=day.cta or "",
        visual_brief=f"{day.platform} · {day.content_type} — {day.theme}",
        campaign_day_id=day.id,
    )
    # Brif saxlanılır ki, Studio+-da «Yenidən yaz» eyni girişlə işləsin. Generasiya
    # burada işlədilmir — təqvimdən keçid ani olmalıdır, model çağırışı isə deyil.
    asset.brief_json = brief_from_campaign_day(day, context.workspace).to_json()
    db.commit()
    # Gün artıq istehsala keçdi: planlaşdırılmışdan baxış mərhələsinə qaldırılır ki, təqvimdə
    # hansı günlərin üzərində real iş getdiyi görünsün.
    if day.status == "PLANNED":
        day.status = "IN_REVIEW"
        db.commit()
    return RedirectResponse(f"/content-studio?id={asset.id}", status_code=303)


@router.get("/content-studio", response_class=HTMLResponse)
def content_studio_page(request: Request, db: Session = Depends(get_db)):
    from app import instagram, tiktok

    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    assets = db.query(ContentAsset).filter(ContentAsset.workspace_id == context.workspace.id).order_by(ContentAsset.id.desc()).all()
    selected_id = request.query_params.get("id")
    selected, missing = None, False
    if selected_id:
        # KONKRET material istənilib. Tapılmasa ƏVƏZİNƏ BAŞQASINI GÖSTƏRMİRİK.
        # Əvvəl `selected = assets[0]` edilirdi: silinmiş və ya başqa workspace-ə aid id
        # sorğulananda səhifə ən son materialı eyni görünüşdə, heç bir xəbərdarlıq olmadan
        # açırdı — istifadəçi yanlış materialı redaktə edib təsdiqləyə bilirdi.
        if selected_id.isdigit():
            selected = db.query(ContentAsset).filter(
                ContentAsset.id == int(selected_id), ContentAsset.workspace_id == context.workspace.id
            ).first()
        missing = selected is None
    elif assets:
        # Ünvanda id yoxdursa ən son materialı açmaq düzgündür — bu, əvəzləmə deyil.
        selected = assets[0]

    # Gündən-günə keçid: material bir kampaniya gününə bağlıdırsa, siyahıya qayıtmadan
    # əvvəlki/növbəti günə keçmək üçün. `/campaigns/day/{id}/to-asset` idempotentdir —
    # material artıq varsa açır, yoxdursa yaradır, ona görə hədəf gündə hələ material
    # olmasa da düymə işləyir.
    prev_day, next_day = None, None
    if selected and selected.campaign_day:
        siblings = (
            db.query(CampaignDay)
            .filter(CampaignDay.campaign_id == selected.campaign_day.campaign_id)
            .order_by(CampaignDay.day_number)
            .all()
        )
        idx = next((i for i, d in enumerate(siblings) if d.id == selected.campaign_day.id), None)
        if idx is not None:
            if idx > 0:
                prev_day = siblings[idx - 1]
            if idx < len(siblings) - 1:
                next_day = siblings[idx + 1]

    scheduled_at_baku = None
    if selected and selected.scheduled_at:
        scheduled_at_baku = selected.scheduled_at.replace(tzinfo=timezone.utc).astimezone(BAKU)

    return templates.TemplateResponse(request, "content_studio.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "assets": assets, "selected_asset": selected,
        "asset_missing": missing, "error": None, "slides": parse_slides(selected),
        "goals": GOALS, "tones": TONES, "deltas": DELTAS,
        "headline_options": json_list(selected.headline_options) if selected else [],
        "hashtags": json_list(selected.hashtags) if selected else [],
        "needs_input": json_list(selected.needs_input) if selected else [],
        "notice": request.query_params.get("notice"),
        "instagram_available": instagram.account_for(context.workspace) is not None,
        "tiktok_available": tiktok.account_for(context.workspace) is not None,
        "social_publish_enabled": settings.social_publish_enabled or settings.external_actions_enabled,
        "prev_day": prev_day, "next_day": next_day,
        "scheduled_at_baku": scheduled_at_baku,
    })


@router.post("/content-studio")
async def content_studio_create(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    value = lambda key, limit: ((form.get(key) or [""])[0].strip())[:limit]
    title = value("title", 180)
    if len(title) < 3:
        return RedirectResponse("/content-studio", status_code=303)

    # BƏLƏDÇİLİ BRİF (audit F4): istifadəçidən nəticə deyil, GİRİŞ istənilir. Başlıq və
    # caption artıq əl ilə yazılmır — onları generasiya qatı yazır və doğrulamadan keçirir.
    brief = brief_from_form(form, context.workspace)
    asset = create_asset(
        db, context.workspace, title, brief.content_format,
        headline="", caption="", visual_brief="",
    )
    asset.brief_json = brief.to_json()
    db.commit()
    apply_result(db, asset, generate_draft(context.workspace, brief))
    return RedirectResponse(f"/content-studio?id={asset.id}", status_code=303)


@router.post("/content-studio/generate-reel")
async def content_studio_generate_reel(request: Request, db: Session = Depends(get_db)):
    """Müştəri sərbəst konsept yazır, sistem başlıq/caption/hashtag YAZIR və Sora ilə
    video ÇƏKİR (audit tələbi: "konsepti yazıb reel yarat"). Sinxrondur — Sora bir neçə
    dəqiqə çəkə bilər, ona görə bu sorğu həmin müddət gözləyir."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    concept = ((form.get("concept") or [""])[0].strip())[:600]
    if len(concept) < 10:
        return RedirectResponse("/content-studio?notice=reel_concept_short", status_code=303)

    asset = create_asset(
        db, context.workspace, title=concept[:180], content_format="REEL",
        headline="", caption="", visual_brief=concept,
    )
    brief = brief_from_form(
        {"format": ["REEL"], "subject": [concept], "facts": [concept], "goal": ["maraq"], "tone": ["neytral"]},
        context.workspace,
    )
    asset.brief_json = brief.to_json()
    db.commit()
    apply_result(db, asset, generate_draft(context.workspace, brief))
    return RedirectResponse(f"/content-studio?id={asset.id}", status_code=303)


@router.post("/content-studio/{asset_id}/regenerate")
async def content_asset_regenerate(asset_id: int, request: Request, db: Session = Depends(get_db)):
    """Yenidən yazma: delta düyməsi, sərbəst təlimat, ya da rəy (audit F5).

    Təsdiqlənmiş materialın üstünə YAZILMIR — əvvəl köhnə nüsxə arxivlənir, uğursuzluqda
    material `NEEDS_INPUT` olur, amma arxiv qalır.
    """
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    asset = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.workspace_id == context.workspace.id
    ).first()
    if not asset:
        return RedirectResponse("/content-studio", status_code=303)
    if asset.status == "APPROVED":
        return RedirectResponse(
            f"/content-studio?id={asset.id}&notice=approved", status_code=303
        )

    brief = StudioBrief.from_json(asset.brief_json)
    if brief is None:
        return RedirectResponse(f"/content-studio?id={asset.id}&notice=nobrief", status_code=303)

    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    delta = ((form.get("delta") or [""])[0]).strip()
    note = ((form.get("instruction") or [""])[0].strip())[:500]
    instruction = DELTAS[delta][1] if delta in DELTAS else note
    if not instruction and asset.reviews:
        # Rəy artıq ölü sahə deyil — son "dəyişiklik tələb et" qeydi təlimata çevrilir (SC-5).
        latest = asset.reviews[0]
        if latest.decision == "CHANGES_REQUESTED" and latest.feedback:
            instruction = latest.feedback[:500]

    archive_version(db, asset, delta or (instruction[:60] if instruction else "yenidən yaz"))
    apply_result(db, asset, generate_draft(context.workspace, brief, instruction))
    return RedirectResponse(f"/content-studio?id={asset.id}", status_code=303)


@router.post("/content-studio/{asset_id}/headline")
async def content_asset_pick_headline(asset_id: int, request: Request, db: Session = Depends(get_db)):
    """Üç variantdan birini seçmək. Seçilməyənlər saxlanılır."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    asset = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.workspace_id == context.workspace.id
    ).first()
    if not asset:
        return RedirectResponse("/content-studio", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    choice = ((form.get("headline") or [""])[0].strip())[:240]
    if choice and choice in json_list(asset.headline_options):
        asset.headline = choice
        db.commit()
    return RedirectResponse(f"/content-studio?id={asset.id}", status_code=303)


@router.post("/content-studio/{asset_id}/review")
async def content_asset_review(asset_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    asset = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.workspace_id == context.workspace.id
    ).first()
    if not asset:
        return RedirectResponse("/content-studio", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    decision = ((form.get("decision") or [""])[0]).upper()
    feedback = ((form.get("feedback") or [""])[0].strip())[:2000]
    if decision not in {"APPROVED", "CHANGES_REQUESTED"}:
        return RedirectResponse(f"/content-studio?id={asset.id}", status_code=303)
    asset.status = decision
    db.add(AssetReview(
        asset_id=asset.id, user_id=context.user.id, decision=decision, feedback=feedback or None
    ))
    # KÖRPÜNÜN DÖVRƏSİ: material kampaniya gününə bağlıdırsa, qərar təqvimə də əks olunur —
    # beləliklə təqvimdə hansı günün həqiqətən hazır olduğu əl ilə yeniləmədən görünür.
    if asset.campaign_day_id:
        day = db.get(CampaignDay, asset.campaign_day_id)
        if day and day.status != "PUBLISHED":
            day.status = "APPROVED" if decision == "APPROVED" else "IN_REVIEW"
    db.commit()

    # DİQQƏT: əvvəllər «Dəyişiklik tələb et» yalnız rəyi YAZIRDI — material dəyişmirdi, istifadəçi
    # ayrıca aşağıda «Yenidən yaz» düyməsini də basmalı idi. Bu, gizli iki addımlı axın idi və
    # istifadəçi təcrübəsində "heç nə olmur" kimi görünürdü (canlı istifadəçi rəyi ilə tapıldı).
    # İndi rəy YAZILAN KİMİ dərhal həmin təlimatla yenidən yaradılır — bir kliklə nəticə görünür.
    if decision == "CHANGES_REQUESTED" and feedback:
        brief = StudioBrief.from_json(asset.brief_json)
        if brief is not None:
            archive_version(db, asset, feedback[:60])
            apply_result(db, asset, generate_draft(context.workspace, brief, feedback))
    return RedirectResponse(f"/content-studio?id={asset.id}", status_code=303)


def _nonnegative_int(value: str | None) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _money_to_cents(value: str | None) -> int:
    try:
        return max(0, int(Decimal(value or "0") * 100))
    except (InvalidOperation, TypeError, ValueError):
        return 0


@router.get("/analytics", response_class=HTMLResponse)
def analytics_page(request: Request, campaign: str | None = None, db: Session = Depends(get_db)):
    # DIQQET: `campaign` QESDEN `str`-dir, `int` DEYIL. Filtr formasindaki "Bütün kampaniyalar"
    # secimi `value=""` gonderir (`?campaign=`), FastAPI ise bos setri int-e cevire bilmeyib
    # 422 JSON xetasi qaytarirdi — istifadeci sehife evezine xam xeta gorurdu (canli tapinti).
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    campaign_id = _nonnegative_int(campaign) or None
    campaigns = db.query(Campaign).filter(
        Campaign.workspace_id == context.workspace.id
    ).order_by(Campaign.created_at.desc()).all()
    selected = next((item for item in campaigns if item.id == campaign_id), None) if campaign_id else None
    report = build_analytics(db, context.workspace.id, selected.id if selected else None)
    trackers = db.query(SocialPostTracker).filter(SocialPostTracker.workspace_id == context.workspace.id).order_by(SocialPostTracker.id.desc()).all()
    return templates.TemplateResponse(request, "analytics.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "campaigns": campaigns,
        "selected_campaign": selected, "report": report, "today": date.today(), "social_trackers": trackers,
    })


@router.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request, db: Session = Depends(get_db)):
    """Paketlər səhifəsi — Instagram avtomatik dərci əlavə paket kimi izah olunur."""
    context = context_from_request(request, db)
    return templates.TemplateResponse(request, "pricing.html", {
        "current_user": context.user if context else None,
        "current_workspace": context.workspace if context else None,
        "membership": context.membership if context else None,
    })


@router.get("/tiktok5cCbIiCfBuge07T8bg1bdd4cTbKnP1U0.txt", response_class=PlainTextResponse)
def tiktok_domain_verification_v1():
    """TikTok "URL prefix" mülkiyyət təsdiqi (bax `/tiktok/connect` sənədləşməsi) — bu fayl
    TIKTOK_REDIRECT_URI-nin bizim nəzarətimizdə olan domendə olduğunu sübut edir. TikTok
    Developer Portal-da yaradılıb, məzmunu SABİTDİR (özbaşına dəyişməyin). Quick tunnel domeni
    hər dəfə dəyişəndə TikTok YENİ fayl adı verir — köhnə marşrutlar KEÇMİŞ domenlərlə əlaqəli
    olduğu üçün silinmir, sadəcə yenisi əlavə olunur."""
    return "tiktok-developers-site-verification=5cCbIiCfBuge07T8bg1bdd4cTbKnP1U0"


@router.get("/tiktok0lw4kExy7ZG0zEuQDKrNFI91tSQSIRia.txt", response_class=PlainTextResponse)
def tiktok_domain_verification_v2():
    """Eyni məqsəd (bax yuxarıdakı funksiya) — tunel domeni full-elephant-handles-third-ə
    dəyişəndə TikTok tərəfindən yaradılan ikinci təsdiq faylı."""
    return "tiktok-developers-site-verification=0lw4kExy7ZG0zEuQDKrNFI91tSQSIRia"


@router.get("/tiktokURz7Ieyp4zvur3nDF0tN1Czqjttghrqe.txt", response_class=PlainTextResponse)
def tiktok_domain_verification_v3():
    """Eyni məqsəd (bax yuxarıdakı v1/v2) — bu, TikTok-un "Sandbox" hədəfi üçün AYRICA istədiyi
    təsdiq faylıdır (Production və hər Sandbox-un URL mülkiyyəti TikTok tərəfindən ayrı-ayrı
    izlənilir, biri digərini əvəz etmir)."""
    return "tiktok-developers-site-verification=URz7Ieyp4zvur3nDF0tN1Czqjttghrqe"


@router.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    """Statik ictimai səhifə — TikTok/Meta kimi platformalar app qeydiyyatında real
    Terms of Service linki tələb edir (bax `/tiktok/connect` sənədləşməsi)."""
    return templates.TemplateResponse(request, "legal_static.html", {
        "current_user": None, "current_workspace": None, "membership": None,
        "page_title": "İstifadə şərtləri", "updated": date.today().strftime("%d.%m.%Y"),
        "body_html": (
            "<p>The Aigency tətbiqindən istifadə etməklə aşağıdakı şərtləri qəbul edirsiniz:</p>"
            "<ul>"
            "<li>Xidmət müştərilərə AI ilə marketinq materialı hazırlamaq və sosial media hesablarına "
            "(Instagram, TikTok və s.) paylaşmaq imkanı verir.</li>"
            "<li>Sosial media hesabınızı qoşmaqla, yalnız SİZİN təsdiqlədiyiniz materialın həmin "
            "hesaba dərc olunmasına icazə verirsiniz.</li>"
            "<li>Hesabınızı istənilən vaxt Brand Kit bölməsindən ayıra (disconnect) bilərsiniz.</li>"
            "<li>Xidmət \"olduğu kimi\" təqdim olunur, fasiləsiz işləmə zəmanəti verilmir.</li>"
            "</ul>"
        ),
    })


@router.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    return templates.TemplateResponse(request, "legal_static.html", {
        "current_user": None, "current_workspace": None, "membership": None,
        "page_title": "Məxfilik siyasəti", "updated": date.today().strftime("%d.%m.%Y"),
        "body_html": (
            "<p>Bu səhifə The Aigency-nin topladığı məlumatları izah edir:</p>"
            "<ul>"
            "<li>Hesab məlumatları (ad, email) — daxil olma və workspace idarəetməsi üçün.</li>"
            "<li>Sosial media platforması (Instagram/TikTok) qoşulanda saxlanılan access/refresh "
            "tokenlər — YALNIZ sizin adınızdan, sizin təsdiqlədiyiniz materialı dərc etmək üçün "
            "istifadə olunur, üçüncü tərəflə paylaşılmır.</li>"
            "<li>Məlumatlarınızı silmək istəsəniz bizimlə əlaqə saxlayın.</li>"
            "</ul>"
        ),
    })


@router.get("/usage", response_class=HTMLResponse)
def usage_page(request: Request, days: int = 30, db: Session = Depends(get_db)):
    """LLM token/xərc paneli — hansı departament və provayder nə qədər sərf edir."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context):
        return RedirectResponse("/", status_code=303)
    days = days if days in (1, 7, 30, 90) else 30
    report = build_usage_report(db, context.workspace.id, days=days)
    return templates.TemplateResponse(request, "usage.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "report": report, "days": days,
    })


@router.post("/analytics/metrics")
async def analytics_add_metric(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    value = lambda key: (form.get(key) or [""])[0]
    campaign_id = _nonnegative_int(value("campaign_id")) or None
    if campaign_id and not db.query(Campaign).filter(
        Campaign.id == campaign_id, Campaign.workspace_id == context.workspace.id
    ).first():
        campaign_id = None
    try:
        recorded_date = datetime.strptime(value("recorded_date"), "%Y-%m-%d").date()
    except ValueError:
        recorded_date = date.today()
    db.add(CampaignMetric(
        workspace_id=context.workspace.id, campaign_id=campaign_id, recorded_date=recorded_date,
        platform=(value("platform").strip()[:80] or "Digər"),
        content_type=(value("content_type").strip()[:80] or None),
        impressions=_nonnegative_int(value("impressions")), reach=_nonnegative_int(value("reach")),
        engagements=_nonnegative_int(value("engagements")), clicks=_nonnegative_int(value("clicks")),
        leads=_nonnegative_int(value("leads")), sales=_nonnegative_int(value("sales")),
        spend_cents=_money_to_cents(value("spend")), revenue_cents=_money_to_cents(value("revenue")),
    ))
    db.commit()
    suffix = f"?campaign={campaign_id}" if campaign_id else ""
    return RedirectResponse(f"/analytics{suffix}", status_code=303)


SALES_STATUSES = {"NEW", "RESEARCH", "READY", "CONTACTED", "REPLIED", "MEETING", "WON", "LOST"}


@router.get("/sales", response_class=HTMLResponse)
def sales_page(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    active_category = (request.query_params.get("category") or "").strip()
    if active_category not in CATEGORY_TAGS:
        active_category = ""
    search_city = (request.query_params.get("city") or "").strip()
    query = db.query(SalesLead).filter(SalesLead.workspace_id == context.workspace.id)
    # Axtarış CRM bazasına yeni lead-lər əlavə edir, amma nəticə ekranı yalnız həmin
    # axtarışın sahəsini göstərməlidir. Köhnə lead-lər bazada qalır və "Hamısını göstər"
    # ilə yenidən görünür.
    # DİQQƏT: əvvəllər yalnız kateqoriyaya görə süzülürdü, ŞƏHƏRƏ görə YOX — nəticədə başqa
    # şəhərdən (məs. Bakı) daha yüksək xallı köhnə lead axtarılan şəhərin (İstanbul) öz
    # nəticələrindən ÖNDƏ görünürdü (canlı istifadəçi tapıntısı). `SalesLead.city` axtarışdan
    # gələn "Şəhər, Ölkə" formatını saxlayır, ona görə substring uyğunluğu kifayətdir.
    if active_category:
        query = query.filter(SalesLead.category == active_category)
    leads = query.order_by(SalesLead.score.desc(), SalesLead.created_at.desc()).all()
    if search_city:
        # SQL LIKE/ILIKE ASCII-əsaslıdır: "baki" (nöqtəsiz i) "Bakı" (Azərbaycan ı) daxilində
        # TAPILMIR, çünki bunlar fərqli simvollardır — SQL-də uyğunluq axtarsaq bütün nəticələr
        # itirdi (canlı istifadəçi tapıntısı). Python-da normallaşdırıb müqayisə edirik.
        needle = _normalize_city(search_city)
        leads = [lead for lead in leads if needle in _normalize_city(lead.city or "")]
    counts = {status: sum(1 for lead in leads if lead.status == status) for status in SALES_STATUSES}
    return templates.TemplateResponse(request, "sales.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "leads": leads, "counts": counts,
        "categories": CATEGORY_TAGS.keys(), "error": request.query_params.get("error"),
        "found": request.query_params.get("found"),
        "active_category": active_category,
        "search_city": search_city,
        "search_country": (request.query_params.get("country") or "").strip(),
        "search_language": (request.query_params.get("language") or "az").strip(),
        "outreach_languages": OUTREACH_LANGUAGES,
    })


@router.post("/sales/discover")
async def sales_discover(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    value = lambda key: ((form.get(key) or [""])[0].strip())
    city = value("city")[:120]
    country = value("country")[:120]
    category = value("category") if value("category") in CATEGORY_TAGS else "retail"
    language = value("language") if value("language") in OUTREACH_LANGUAGES else "az"
    if len(city) < 2:
        return RedirectResponse("/sales?error=Şəhər+adını+yazın", status_code=303)
    try:
        found = discover_businesses(city, category, limit=25, country=country, language=language)
    except Exception:
        return RedirectResponse("/sales?error=Açıq+biznes+mənbəsi+hazırda+cavab+vermir", status_code=303)
    added = 0
    for item in found:
        exists = db.query(SalesLead).filter(
            SalesLead.workspace_id == context.workspace.id,
            SalesLead.source_external_id == item.source_external_id,
        ).first()
        if exists:
            continue
        db.add(SalesLead(
            workspace_id=context.workspace.id, company_name=item.company_name,
            category=item.category, city=item.city, address=item.address,
            website=item.website, phone=item.phone, email=item.email,
            source="OpenStreetMap", source_external_id=item.source_external_id,
            source_url=item.source_url, score=item.score, status="NEW",
            outreach_message=item.outreach_message,
        ))
        added += 1
    db.commit()
    query = urlencode({"found": added, "category": category, "city": city, "country": country, "language": language})
    return RedirectResponse(f"/sales?{query}", status_code=303)


@router.post("/sales/{lead_id}/status")
async def sales_lead_status(lead_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    status = ((form.get("status") or [""])[0]).upper()
    lead = db.query(SalesLead).filter(
        SalesLead.id == lead_id, SalesLead.workspace_id == context.workspace.id
    ).first()
    if lead and status in SALES_STATUSES:
        lead.status = status
        db.commit()
    return RedirectResponse("/sales", status_code=303)


@router.get("/sales/{lead_id}", response_class=HTMLResponse)
def sales_lead_detail(lead_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    lead = db.query(SalesLead).filter(SalesLead.id == lead_id, SalesLead.workspace_id == context.workspace.id).first()
    if not lead:
        return RedirectResponse("/sales", status_code=303)
    audit = db.query(LeadAudit).filter(LeadAudit.lead_id == lead.id).order_by(LeadAudit.id.desc()).first()
    proposal = db.query(SalesProposal).filter(
        SalesProposal.lead_id == lead.id, SalesProposal.workspace_id == context.workspace.id
    ).order_by(SalesProposal.id.desc()).first()
    activities = db.query(SalesActivity).filter(
        SalesActivity.lead_id == lead.id, SalesActivity.workspace_id == context.workspace.id
    ).order_by(SalesActivity.id).all()
    meeting = db.query(MeetingBrief).filter(
        MeetingBrief.lead_id == lead.id, MeetingBrief.workspace_id == context.workspace.id
    ).order_by(MeetingBrief.id.desc()).first()
    import json
    audit_details = json.loads(audit.details_json or "{}") if audit else {}
    return templates.TemplateResponse(request, "sales_lead.html", {
        "current_user": context.user, "current_workspace": context.workspace, "membership": context.membership,
        "lead": lead, "audit": audit, "proposal": proposal, "activities": activities, "meeting": meeting,
        "smtp_ready": smtp_ready(), "external_delivery_enabled": external_delivery_enabled(),
        "strengths": json.loads(audit.strengths_json or "[]") if audit else [],
        "issues": json.loads(audit.issues_json or "[]") if audit else [],
        "opportunities": json.loads(audit.opportunities_json or "[]") if audit else [],
        "questions": json.loads(meeting.questions_json or "[]") if meeting else [],
        "objections": json.loads(meeting.objections_json or "[]") if meeting else [],
        "audit_sections": audit_details.get("sections", []),
        "audit_evidence": audit_details.get("evidence", {}),
        "audit_priorities": audit_details.get("priorities", []),
        "audit_action_plan": audit_details.get("action_plan", []),
    })


@router.post("/sales/{lead_id}/audit")
def sales_lead_audit(lead_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    lead = db.query(SalesLead).filter(SalesLead.id == lead_id, SalesLead.workspace_id == context.workspace.id).first()
    if lead:
        audit_lead(db, lead)
    return RedirectResponse(f"/sales/{lead_id}", status_code=303)


@router.post("/sales/{lead_id}/proposal")
async def sales_lead_proposal(lead_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    language = "EN" if ((form.get("language") or ["AZ"])[0]).upper() == "EN" else "AZ"
    lead = db.query(SalesLead).filter(SalesLead.id == lead_id, SalesLead.workspace_id == context.workspace.id).first()
    if lead:
        audit = db.query(LeadAudit).filter(LeadAudit.lead_id == lead.id).order_by(LeadAudit.id.desc()).first()
        create_proposal(db, context.workspace.id, lead, audit, language=language)
    return RedirectResponse(f"/sales/{lead_id}", status_code=303)


@router.post("/sales/{lead_id}/outreach")
def sales_lead_outreach(lead_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    lead = db.query(SalesLead).filter(SalesLead.id == lead_id, SalesLead.workspace_id == context.workspace.id).first()
    if lead:
        db.query(SalesActivity).filter(SalesActivity.lead_id == lead.id, SalesActivity.workspace_id == context.workspace.id).delete()
        create_outreach_sequence(db, context.workspace.id, lead)
    return RedirectResponse(f"/sales/{lead_id}#outreach", status_code=303)


@router.post("/sales/{lead_id}/meeting")
def sales_lead_meeting(lead_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    lead = db.query(SalesLead).filter(SalesLead.id == lead_id, SalesLead.workspace_id == context.workspace.id).first()
    if lead: create_meeting_brief(db, context.workspace.id, lead)
    return RedirectResponse(f"/sales/{lead_id}#outreach", status_code=303)


@router.post("/sales/activity/{activity_id}/approve")
def approve_sales_activity(activity_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    activity = db.query(SalesActivity).filter(
        SalesActivity.id == activity_id, SalesActivity.workspace_id == context.workspace.id
    ).first()
    if activity:
        lead = db.query(SalesLead).filter(SalesLead.id == activity.lead_id, SalesLead.workspace_id == context.workspace.id).first()
        exists = db.query(OutboundDelivery).filter(OutboundDelivery.activity_id == activity.id).first()
        if lead and lead.email and not exists:
            db.add(OutboundDelivery(
                workspace_id=context.workspace.id, lead_id=lead.id, activity_id=activity.id,
                recipient=lead.email, status="QUEUED", scheduled_at=activity.due_at or datetime.utcnow(),
            ))
            activity.status = "APPROVED"; db.commit()
    return RedirectResponse(f"/sales/{activity.lead_id if activity else ''}", status_code=303)


def _pitch_meeting_rows(db: Session) -> list[dict]:
    """Demo zeng agentinin teyin etdiyi gorusler — Control Room-da canli gostermek ucun.

    `scheduled_at` bazada Baki yerli vaxtdan UTC-ye cevrilmis saxlanilir (bax
    `app/voice_pitch.py::_book_slot`) — burada eksinə cevrilib teqdimat ucun oxunakli
    Azerbaycanca formata salinir."""
    from app.voice_pitch import BAKU, az_datetime

    now_utc = datetime.utcnow()
    rows = db.query(PitchMeeting).order_by(PitchMeeting.scheduled_at.desc()).limit(20).all()
    return [{
        "vaxt": az_datetime(m.scheduled_at.replace(tzinfo=timezone.utc).astimezone(BAKU)),
        "gelecek": m.scheduled_at >= now_utc,
        "qeyd_edildi": m.created_at,
    } for m in rows]


def _night_lead_rows(db: Session, workspace_id: int, limit: int = 12) -> list[dict]:
    """Control Room-un "Səhər hesabatları" paneli üçün — gecə növbəsinin tapdığı bizneslər.

    NİYƏ LAZIMDIR: hesabat sətri yalnız RƏQƏM deyirdi ("15 tapıldı, 0 yeni lead"), amma
    təqdimat zamanı biznesin ADI lazımdır və ondan birbaşa audit/təklif/outreach səhifəsinə
    keçmək istənilir. Hər sətir `/sales/{id}`-ə bağlanır.

    `NightShiftReport`-un lead-lərlə birbaşa əlaqəsi YOXDUR (yalnız saylar saxlanılır), ona
    görə ən son əlavə olunan lead-lər göstərilir — gecə növbəsi də məhz onları yaradır.
    """
    leads = (
        db.query(SalesLead)
        .filter(SalesLead.workspace_id == workspace_id)
        .order_by(SalesLead.created_at.desc(), SalesLead.id.desc())
        .limit(limit)
        .all()
    )
    ids = [lead.id for lead in leads]
    audited: set[int] = set()
    drafted: set[int] = set()
    if ids:
        audited = {r[0] for r in db.query(LeadAudit.lead_id).filter(LeadAudit.lead_id.in_(ids)).distinct()}
        drafted = {r[0] for r in db.query(SalesActivity.lead_id).filter(SalesActivity.lead_id.in_(ids)).distinct()}
    return [{
        "id": lead.id,
        "ad": lead.company_name,
        "kateqoriya": (lead.category or "").replace("_", " "),
        "sehir": lead.city or "",
        "bal": lead.score,
        "status": lead.status,
        "audit_var": lead.id in audited,
        "outreach_var": lead.id in drafted,
    } for lead in leads]


def _lead_stats(db: Session, workspace_id: int) -> dict:
    total = db.query(SalesLead).filter(SalesLead.workspace_id == workspace_id).count()
    audited = (
        db.query(LeadAudit.lead_id)
        .join(SalesLead, SalesLead.id == LeadAudit.lead_id)
        .filter(SalesLead.workspace_id == workspace_id)
        .distinct().count()
    )
    drafts = db.query(SalesActivity).filter(SalesActivity.workspace_id == workspace_id).count()
    return {"total": total, "audited": audited, "drafts": drafts}


def _availability_grid(db: Session, days: int = 6) -> list[dict]:
    """Növbəti bir neçə iş günü üçün boş/dolu saat cədvəli — hansı vaxtın dolu olduğunu
    teqdimatda GÖZLƏ görmək üçün (bax `app/voice_pitch.py` üçün eyni iş saatları qaydası)."""
    from app.voice_pitch import BAKU, BUSINESS_HOURS, az_date

    now_baku = datetime.now(BAKU)
    booked_utc = {row.scheduled_at for row in db.query(PitchMeeting.scheduled_at).all()}

    grid = []
    offset = 0
    while len(grid) < days and offset < 30:
        day = (now_baku + timedelta(days=offset)).date()
        offset += 1
        if day.weekday() >= 5:
            continue
        cells = []
        for hour in BUSINESS_HOURS:
            local_dt = datetime(day.year, day.month, day.day, hour, tzinfo=BAKU)
            if local_dt < now_baku:
                continue
            taken = local_dt.astimezone(timezone.utc).replace(tzinfo=None) in booked_utc
            cells.append({"saat": f"{hour:02d}:00", "dolu": taken})
        if cells:
            grid.append({"gun": az_date(day), "saatlar": cells})
    return grid


@router.get("/control-room", response_class=HTMLResponse)
def control_room(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context):
        return RedirectResponse("/", status_code=303)
    wid = context.workspace.id
    control = get_control(db, wid)
    jobs = db.query(FactoryJob).filter(FactoryJob.workspace_id == wid).order_by(FactoryJob.id.desc()).limit(30).all()
    logs = db.query(FactoryAuditLog).filter(FactoryAuditLog.workspace_id == wid).order_by(FactoryAuditLog.id.desc()).limit(40).all()
    projects = db.query(AgentProject).filter(AgentProject.workspace_id == wid).all()
    deliveries = db.query(OutboundDelivery).filter(OutboundDelivery.workspace_id == wid).all()
    night_plan = db.query(NightShiftPlan).filter(NightShiftPlan.workspace_id == wid).first()
    night_reports = db.query(NightShiftReport).filter(NightShiftReport.workspace_id == wid).order_by(NightShiftReport.id.desc()).limit(10).all()
    pitch_meetings = _pitch_meeting_rows(db)
    availability_grid = _availability_grid(db)
    night_leads = _night_lead_rows(db, wid)
    lead_stats = _lead_stats(db, wid)
    ai_report = build_usage_report(db, wid, days=1)
    stats = {
        "active": sum(p.status not in {"AWAITING_APPROVAL", "DELIVERED", "REJECTED"} for p in projects),
        "approval": sum(p.status == "AWAITING_APPROVAL" for p in projects),
        "queued": sum(j.status in {"PENDING", "RETRY"} for j in jobs),
        "failed": sum(j.status == "FAILED" for j in jobs),
        "outbox": sum(d.status == "QUEUED" for d in deliveries),
        "sent": sum(d.status == "SENT" for d in deliveries),
    }
    return templates.TemplateResponse(request, "control_room.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "control": control, "jobs": jobs, "logs": logs, "stats": stats,
        "night_plan": night_plan, "night_reports": night_reports, "categories": CATEGORY_TAGS.keys(),
        "ai_report": ai_report, "pitch_meetings": pitch_meetings, "availability_grid": availability_grid,
        "night_leads": night_leads, "lead_stats": lead_stats,
        "social_publish_enabled": settings.social_publish_enabled or settings.external_actions_enabled,
        "email_delivery_enabled": settings.email_delivery_enabled,
    })


@router.get("/approvals", response_class=HTMLResponse)
def approvals_page(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    projects = db.query(AgentProject).filter(
        AgentProject.workspace_id == context.workspace.id,
        AgentProject.status == "AWAITING_APPROVAL",
    ).order_by(AgentProject.created_at.asc()).all()
    now = datetime.utcnow()
    rows = [{
        "project": project,
        "age_hours": max(0, int((now - project.created_at).total_seconds() // 3600)) if project.created_at else 0,
        "preview": (project.deliverable_html or "")[:260],
    } for project in projects]
    return templates.TemplateResponse(request, "approvals.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership, "approval_rows": rows,
    })


@router.post("/approvals/{project_id}/approve")
def approval_accept(project_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    project = db.query(AgentProject).filter(
        AgentProject.id == project_id, AgentProject.workspace_id == context.workspace.id
    ).first()
    if project and project.status == "AWAITING_APPROVAL":
        project.status = "DELIVERED"; db.commit()
        log_action(db, context.workspace.id, context.user.email, "PROJECT_APPROVED", "AgentProject", str(project.id), "Daxili təsdiq; xarici göndəriş edilmədi.")
    return RedirectResponse("/approvals", status_code=303)


@router.post("/approvals/{project_id}/reject")
async def approval_reject(project_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    reason = ((form.get("reason") or ["Yenidən işlənməlidir."])[0].strip() or "Yenidən işlənməlidir.")[:500]
    project = db.query(AgentProject).filter(
        AgentProject.id == project_id, AgentProject.workspace_id == context.workspace.id
    ).first()
    if project and project.status == "AWAITING_APPROVAL":
        project.status = "REJECTED"; project.retry_feedback = reason; db.commit()
        log_action(db, context.workspace.id, context.user.email, "PROJECT_REJECTED", "AgentProject", str(project.id), reason)
    return RedirectResponse("/approvals", status_code=303)


@router.post("/control-room/settings")
async def control_room_settings(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    control = get_control(db, context.workspace.id)
    control.factory_enabled = "factory_enabled" in form
    control.agents_enabled = "agents_enabled" in form
    control.outbound_enabled = "outbound_enabled" in form
    control.lead_discovery_enabled = "lead_discovery_enabled" in form
    control.daily_email_limit = min(100, max(0, _nonnegative_int((form.get("daily_email_limit") or ["10"])[0])))
    control.daily_api_budget_cents = min(100000, max(0, _nonnegative_int((form.get("daily_api_budget_cents") or ["100"])[0])))
    db.commit()
    log_action(db, context.workspace.id, context.user.email, "FACTORY_SETTINGS_UPDATED", detail=f"factory={control.factory_enabled}, agents={control.agents_enabled}, outbound={control.outbound_enabled}")
    return RedirectResponse("/control-room", status_code=303)


@router.post("/control-room/emergency-stop")
def control_room_emergency_stop(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    control = get_control(db, context.workspace.id)
    control.factory_enabled = control.agents_enabled = control.outbound_enabled = control.lead_discovery_enabled = False
    db.commit()
    log_action(db, context.workspace.id, context.user.email, "EMERGENCY_STOP", detail="Bütün avtomatik fəaliyyətlər dayandırıldı.")
    return RedirectResponse("/control-room", status_code=303)


def _owned_project_or_none(db: Session, project_id: int, workspace_id: int) -> AgentProject | None:
    return (
        db.query(AgentProject)
        .filter(AgentProject.id == project_id, AgentProject.workspace_id == workspace_id)
        .first()
    )


@router.get("/agency/{project_id}/export/report", response_class=HTMLResponse)
def export_report(project_id: int, request: Request, db: Session = Depends(get_db)):
    """Çap-hazır hesabat — brauzerin "PDF kimi saxla" funksiyası ilə PDF olur."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    project = _owned_project_or_none(db, project_id, context.workspace.id)
    if not project:
        return HTMLResponse("<h1>Layihə tapılmadı</h1>", status_code=404)
    bundle = collect_bundle(db, project)
    return HTMLResponse(render_report_html(bundle, context.workspace.name))


@router.get("/agency/{project_id}/export/zip")
def export_zip(project_id: int, request: Request, db: Session = Depends(get_db)):
    """Bütün departament materialları + son məhsul — ZIP arxiv kimi."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    project = _owned_project_or_none(db, project_id, context.workspace.id)
    if not project:
        return HTMLResponse("<h1>Layihə tapılmadı</h1>", status_code=404)
    bundle = collect_bundle(db, project)
    return Response(
        content=build_zip(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename(project)}"'},
    )


@router.post("/control-room/night-shift")
async def control_room_night_shift(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    value = lambda key, default="": ((form.get(key) or [default])[0].strip())
    category = value("category", "restaurant")
    if category not in CATEGORY_TAGS: category = "restaurant"
    hour = min(23, _nonnegative_int(value("run_hour_baku", "2")))
    target = min(50, max(1, _nonnegative_int(value("daily_lead_target", "15"))))
    plan = db.query(NightShiftPlan).filter(NightShiftPlan.workspace_id == context.workspace.id).first()
    if not plan:
        plan = NightShiftPlan(workspace_id=context.workspace.id); db.add(plan)
    plan.city = value("city", "Baku, Azerbaijan")[:120] or "Baku, Azerbaijan"
    plan.category = category; plan.daily_lead_target = target; plan.run_hour_baku = hour
    plan.next_run_at = next_run_utc(hour); db.commit(); db.refresh(plan)
    log_action(db, context.workspace.id, context.user.email, "NIGHT_SHIFT_PLAN_UPDATED", "NightShiftPlan", str(plan.id), f"{plan.city} · {category} · {target} lead · {hour}:00")
    return RedirectResponse("/control-room", status_code=303)


@router.post("/control-room/night-shift/run-now")
def control_room_night_shift_now(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context: return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context): return RedirectResponse("/", status_code=303)
    plan = db.query(NightShiftPlan).filter(NightShiftPlan.workspace_id == context.workspace.id).first()
    control = get_control(db, context.workspace.id)
    if plan:
        control.factory_enabled = True; control.lead_discovery_enabled = True; db.commit()
        job = enqueue_now(db, plan)
        log_action(db, context.workspace.id, context.user.email, "NIGHT_SHIFT_ENQUEUED", "FactoryJob", str(job.id), "Manual sınaq növbəyə əlavə edildi.")
    return RedirectResponse("/control-room", status_code=303)


@router.get("/s/{share_token}", response_class=HTMLResponse)
def customer_view(share_token: str, request: Request, db: Session = Depends(get_db)):
    """Müştəriyə göndərilən İCTİMAİ, autentifikasiyasız link. Qəsdən auth-dan kənardır (müştəri
    hesab açmır), amma ünvanda layihə ID-si YOX, təxmin edilə bilməyən `share_token` var — əks
    halda /agency/1/view, /agency/2/view … deyə sadalamaqla bütün workspace-lərin hazır nəticələri
    oxuna bilərdi."""
    project = (
        db.query(AgentProject).filter(AgentProject.share_token == share_token).first()
        if share_token else None
    )
    if not project or project.status not in ("AWAITING_APPROVAL", "DELIVERED"):
        return templates.TemplateResponse(
            request, "customer_view.html",
            {"not_ready": True, "project": None}, status_code=404,
        )
    if project.output_type == "landing_page":
        # deliverable_html artıq tam, tək-fayllı HTML sənədidir (<!doctype>-dan başlayır) —
        # birbaşa xam HTML kimi qaytarırıq ki, Developer-in yazdığı səhifə olduğu kimi görünsün.
        return HTMLResponse(content=project.deliverable_html or "<p>Hazır deyil.</p>")
    return templates.TemplateResponse(
        request, "customer_view.html", {"not_ready": False, "project": project},
    )


@router.post("/brand-kit/suggestions/{suggestion_id}/{action}")
def brand_kit_suggestion(suggestion_id: int, action: str, request: Request, db: Session = Depends(get_db)):
    """Brand Kit təklifini qəbul edir və ya rədd edir (audit #1).

    Yazma YALNIZ buradan olur — layihə axını Brand Kit-ə heç vaxt birbaşa toxunmur.
    """
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    suggestion = db.query(BrandKitSuggestion).filter(
        BrandKitSuggestion.id == suggestion_id,
        BrandKitSuggestion.workspace_id == context.workspace.id,
    ).first()
    if suggestion and suggestion.status == "PENDING":
        if action == "accept":
            apply_suggestion(db, context.workspace, suggestion)
        elif action == "dismiss":
            suggestion.status = "DISMISSED"
            db.commit()
    return RedirectResponse("/brand-kit", status_code=303)


@router.post("/content-studio/{asset_id}/video")
def content_asset_collect_video(asset_id: int, request: Request, db: Session = Depends(get_db)):
    """Veo əməliyyatını yoxlayır: hazırdırsa videonu endirir.

    Video 1–2 dəqiqə çəkir, ona görə generasiya sorğusunda gözlənilmir — istifadəçi
    hazır olanda bu düymə ilə yığır.
    """
    from app import veo

    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    asset = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.workspace_id == context.workspace.id
    ).first()
    if not asset or not asset.video_operation:
        return RedirectResponse("/content-studio", status_code=303)
    url = veo.collect(asset.video_operation)
    if url:
        asset.video_url = url[:1000]
        asset.video_operation = None
        db.commit()
        return RedirectResponse(f"/content-studio?id={asset.id}", status_code=303)
    return RedirectResponse(f"/content-studio?id={asset.id}&notice=video_pending", status_code=303)


def _asset_public_media_url(url: str | None) -> str | None:
    """`video_url`/`image_url` yerli `public_base_url` ilə saxlanılır (baxış üçün kifayətdir),
    amma Meta faylı ÖZÜ ictimai ünvandan yükləyir — ona görə paylaşımda `public_media_base_url`-ə
    keçirilir (eyni yanaşma `api._instagram_image_url`-də AgentProject üçün var)."""
    if not url:
        return None
    if url.startswith(settings.public_base_url):
        return settings.public_media_base_url + url[len(settings.public_base_url):]
    return url if url.startswith("https://") else None


def publish_asset_to_instagram(db: Session, workspace, asset: ContentAsset) -> str:
    """Instagram-a dərc etmənin bütün qərar məntiqi burada cəmlənib — HTTP düyməsi (dərhal)
    və `app.scheduler`-dəki planlaşdırılmış tetikləyici (gecikmiş) ikisi də bunu çağırır.
    Qaytarılan koda görə çağıran tərəf UI bildirişi (`content_studio.html`-dəki `notice`) və ya
    planlaşdırma xətasını (`asset.schedule_error`) formalaşdırır — DB mutasiyaları YALNIZ
    "ig_published" nəticəsində baş verir."""
    from app import instagram

    # POST/CAROUSEL şəkillə, REEL/STORY video ilə paylaşılır. Carousel API-də çoxlu media
    # konteyneri (uşaq elementlər) tələb edir — hələ dəstəklənmir, ona görə burada YOXDUR.
    is_photo = asset.format == "POST" and bool(asset.image_url)
    is_video = asset.format in ("REEL", "STORY") and bool(asset.video_url)

    if not (settings.social_publish_enabled or settings.external_actions_enabled):
        return "ig_disabled"
    if not (is_photo or is_video):
        return "ig_no_video"
    if asset.status != "APPROVED":
        return "ig_not_approved"
    if asset.instagram_published:
        return "ig_already"

    account = instagram.account_for(workspace)
    if not account:
        return "ig_not_connected"

    public_url = _asset_public_media_url(asset.image_url if is_photo else asset.video_url)
    if not public_url:
        return "ig_no_public_url"

    try:
        if is_photo:
            result = instagram.publish_photo(account, public_url, asset.caption or "")
        elif asset.format == "STORY":
            result = instagram.publish_story(account, public_url, is_video=True)
        else:
            result = instagram.publish_reel(account, public_url, asset.caption or "")
    except instagram.InstagramError as exc:
        logger.warning("Instagram paylaşımı uğursuz oldu (asset %s): %s", asset.id, exc)
        asset.schedule_error = f"Instagram: {exc}"[:1000]
        return "ig_failed"

    asset.instagram_published = True
    asset.instagram_post_id = (result.get("id") or "")[:60] or None
    asset.instagram_permalink = (result.get("permalink") or "")[:300] or None
    campaign_id = None
    if asset.campaign_day_id:
        day = db.get(CampaignDay, asset.campaign_day_id)
        if day:
            day.status = "PUBLISHED"
            campaign_id = day.campaign_id

    # Analitika YALNIZ bu izləyicidən (sinxronizasiya job-u ilə) doldurulur — bunsuz paylaşım
    # izsiz qalır və "Kampaniyalar"dan dərc edilən Reel-in nəticəsi Analitikada görünmür.
    # DİQQƏT: platform ilə filtrlənir — TikTok dəstəyi əlavə olunandan bəri eyni asset üçün
    # birdən çox tracker sətri ola bilər (bax db_models.py-dəki (asset_id, platform) UNIQUE).
    tracker = db.query(AssetSocialTracker).filter(
        AssetSocialTracker.asset_id == asset.id, AssetSocialTracker.platform == "Instagram"
    ).first()
    if not tracker:
        tracker = AssetSocialTracker(workspace_id=workspace.id, asset_id=asset.id, platform="Instagram")
        db.add(tracker)
    tracker.campaign_id = campaign_id
    tracker.content_type = asset.format
    tracker.external_post_id = result.get("id")
    tracker.permalink = result.get("permalink")
    tracker.status = "ACTIVE"
    tracker.next_sync_at = datetime.utcnow()

    db.commit()
    return "ig_published"


@router.post("/content-studio/{asset_id}/publish-instagram")
def content_asset_publish_instagram(asset_id: int, request: Request, db: Session = Depends(get_db)):
    """Təsdiqlənmiş Reel/Story materialını Instagram-a dərc edir (rəsmi Graph API).
    GERİ ALINMAYAN ictimai əməldir — yalnız bu düymə açıq basılanda baş verir."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    asset = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.workspace_id == context.workspace.id
    ).first()
    if not asset:
        return RedirectResponse("/content-studio", status_code=303)
    notice = publish_asset_to_instagram(db, context.workspace, asset)
    if asset.schedule_error:
        db.commit()
    return RedirectResponse(f"/content-studio?id={asset.id}&notice={notice}", status_code=303)


def publish_asset_to_tiktok(db: Session, workspace, asset: ContentAsset) -> str:
    """`publish_asset_to_instagram`-ın TikTok qardaşı — bax onun docstring-i. HTTP düyməsi
    (dərhal) və `app.scheduler`-dəki planlaşdırılmış tetikləyici (gecikmiş) ikisi də çağırır."""
    from app import tiktok

    # TikTok yalnız video qəbul edir — POST/CAROUSEL formatı üçün paylaşım düyməsi yoxdur.
    is_video = asset.format in ("REEL", "STORY") and bool(asset.video_url)

    if not (settings.social_publish_enabled or settings.external_actions_enabled):
        return "tt_disabled"
    if not is_video:
        return "tt_no_video"
    if asset.status != "APPROVED":
        return "tt_not_approved"
    if asset.tiktok_published:
        return "tt_already"

    account = tiktok.ensure_fresh(workspace)
    if not account:
        return "tt_not_connected"
    db.commit()

    public_url = _asset_public_media_url(asset.video_url)
    if not public_url:
        return "tt_no_public_url"

    try:
        result = tiktok.publish_video(account, public_url, asset.caption or "")
    except tiktok.TikTokError as exc:
        logger.warning("TikTok paylaşımı uğursuz oldu (asset %s): %s", asset.id, exc)
        asset.schedule_error = f"TikTok: {exc}"[:1000]
        db.commit()
        return "tt_failed"

    asset.tiktok_published = True
    asset.tiktok_post_id = (result.get("id") or "")[:120] or None
    campaign_id = None
    if asset.campaign_day_id:
        day = db.get(CampaignDay, asset.campaign_day_id)
        if day:
            campaign_id = day.campaign_id
            if day.status != "PUBLISHED":
                day.status = "PUBLISHED"

    # `AssetSocialTracker`-ın `asset_id` unikallığı artıq (asset_id, platform) cütünə keçirilib
    # (bax db_models.py) — eyni Reel həm Instagram-a, həm TikTok-a paylaşılanda hər ikisi üçün
    # ayrı sətir yarana bilir. video_id YALNIZ PUBLIC_TO_EVERYONE paylaşımlarda dolur (SELF_ONLY-də
    # TikTok bunu qaytarmır) — sync job `sync_due_asset_social_metrics`-də bunu yoxlayır.
    tracker = db.query(AssetSocialTracker).filter(
        AssetSocialTracker.asset_id == asset.id, AssetSocialTracker.platform == "TikTok"
    ).first()
    if not tracker:
        tracker = AssetSocialTracker(workspace_id=workspace.id, asset_id=asset.id, platform="TikTok")
        db.add(tracker)
    has_video_id = bool(result.get("video_id"))
    tracker.campaign_id = campaign_id
    tracker.content_type = asset.format
    tracker.external_post_id = result.get("video_id") or result.get("publish_id")
    # `video_id` yoxdursa (adətən SELF_ONLY paylaşım) statistika sorğusu mümkün deyil — tracker
    # "READY" saxlanılır (sync job yalnız "ACTIVE" statuslu sətirləri götürür), beləliklə boş
    # nəticəyə görə təkrar-təkrar xəta yazılmır.
    tracker.status = "ACTIVE" if has_video_id else "READY"
    tracker.next_sync_at = datetime.utcnow() if has_video_id else None
    tracker.last_error = None if has_video_id else (
        "TikTok video ID-si qaytarılmadı (adətən SELF_ONLY paylaşımlarda baş verir) — "
        "statistika sinxronizasiyası mümkün deyil."
    )

    # Analitikada dərhal görünsün deyə ilk snapshot burada yazılır (sync job YALNIZ "ACTIVE"
    # tracker-ləri götürür, "READY" olanları heç vaxt sinxronlaşdırmır) — video_id varsa real
    # statistika ilə, yoxdursa sıfır bazası ilə ("dərc olundu, hələ ölçü yoxdur").
    stats = {"views": 0, "likes": 0, "comments": 0, "shares": 0}
    if has_video_id:
        try:
            stats = tiktok.fetch_video_stats(account, result["video_id"])
            tracker.last_synced_at = datetime.utcnow()
        except tiktok.TikTokError as exc:
            logger.info("TikTok ilkin statistika alınmadı (asset %s): %s", asset.id, exc)
    label = f"TikTok {asset.format} #{asset.id}"
    metric = CampaignMetric(
        workspace_id=workspace.id, campaign_id=campaign_id, recorded_date=date.today(),
        platform="TikTok", content_type=label,
        reach=stats["views"], impressions=stats["views"],
        engagements=stats["likes"] + stats["comments"] + stats["shares"],
    )
    db.add(metric)
    asset.schedule_error = None

    db.commit()
    return "tt_published"


@router.post("/content-studio/{asset_id}/publish-tiktok")
def content_asset_publish_tiktok(asset_id: int, request: Request, db: Session = Depends(get_db)):
    """Təsdiqlənmiş Reel materialını TikTok-a dərc edir (rəsmi Content Posting API).
    GERİ ALINMAYAN ictimai əməldir — yalnız bu düymə açıq basılanda baş verir."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    asset = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.workspace_id == context.workspace.id
    ).first()
    if not asset:
        return RedirectResponse("/content-studio", status_code=303)
    notice = publish_asset_to_tiktok(db, context.workspace, asset)
    return RedirectResponse(f"/content-studio?id={asset.id}&notice={notice}", status_code=303)


SCHEDULABLE_PLATFORMS = ("instagram", "tiktok")


def _platform_schedulable(platform: str, workspace, asset: ContentAsset) -> bool:
    """Manual "İndi paylaş" düymələrindəki eyni uyğunluq yoxlaması (bax `content_studio.html`-
    dəki `ig_ready`/`tt_ready`) — planlaşdırma anında yox, İNDİ yoxlanılır ki, istifadəçi heç vaxt
    uğursuz olacaq bir plan qurmasın (məs. hesab qoşulmayıb və ya format uyğun deyil)."""
    if platform == "instagram":
        from app import instagram
        is_photo = asset.format == "POST" and bool(asset.image_url)
        is_video = asset.format in ("REEL", "STORY") and bool(asset.video_url)
        return (is_photo or is_video) and instagram.account_for(workspace) is not None
    if platform == "tiktok":
        from app import tiktok
        is_video = asset.format in ("REEL", "STORY") and bool(asset.video_url)
        return is_video and tiktok.account_for(workspace) is not None
    return False


@router.post("/content-studio/{asset_id}/schedule")
async def content_asset_schedule(asset_id: int, request: Request, db: Session = Depends(get_db)):
    """Materialı gələcək tarix/saata (Bakı vaxtı ilə) planlaşdırır — `app.scheduler`-dəki fon
    dövrü həmin an çatanda `publish_asset_to_instagram`/`publish_asset_to_tiktok`-u avtomatik
    çağırır. Manual "İndi paylaş" düymələri ilə YANAŞI mövcuddur, onları əvəz etmir."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    asset = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.workspace_id == context.workspace.id
    ).first()
    if not asset:
        return RedirectResponse("/content-studio", status_code=303)
    notice_url = f"/content-studio?id={asset.id}&notice="
    if asset.status != "APPROVED":
        return RedirectResponse(notice_url + "sched_not_approved", status_code=303)

    form = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
    platforms = [p for p in (form.get("platforms") or []) if p in SCHEDULABLE_PLATFORMS]
    raw_dt = (form.get("scheduled_at") or [""])[0].strip()
    if not platforms or not raw_dt:
        return RedirectResponse(notice_url + "sched_invalid", status_code=303)
    if not all(_platform_schedulable(p, context.workspace, asset) for p in platforms):
        return RedirectResponse(notice_url + "sched_platform_unavailable", status_code=303)
    try:
        local_naive = datetime.strptime(raw_dt, "%Y-%m-%dT%H:%M")
    except ValueError:
        return RedirectResponse(notice_url + "sched_invalid", status_code=303)
    # `datetime-local` sahəsi istifadəçinin BROWSER-inin yerli saatını verir — bu tətbiqdə hamı
    # Bakıdan işlədiyi üçün Bakı yerli vaxtı kimi qəbul edib UTC-yə çeviririk (bax `app.night_shift`
    # -dəki eyni nümunə).
    scheduled_at = local_naive.replace(tzinfo=BAKU).astimezone(timezone.utc).replace(tzinfo=None)
    if scheduled_at <= datetime.utcnow():
        return RedirectResponse(notice_url + "sched_past", status_code=303)

    asset.scheduled_at = scheduled_at
    asset.scheduled_platforms = ",".join(platforms)
    asset.schedule_error = None
    db.commit()
    return RedirectResponse(notice_url + "sched_set", status_code=303)


@router.post("/content-studio/{asset_id}/schedule/cancel")
def content_asset_schedule_cancel(asset_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    asset = db.query(ContentAsset).filter(
        ContentAsset.id == asset_id, ContentAsset.workspace_id == context.workspace.id
    ).first()
    if asset:
        asset.scheduled_at = None
        asset.scheduled_platforms = None
        asset.schedule_error = None
        db.commit()
    return RedirectResponse(f"/content-studio?id={asset_id}&notice=sched_cancelled", status_code=303)
