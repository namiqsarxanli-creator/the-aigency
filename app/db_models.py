"""ORM cədvəlləri: bir 'layihə' (AgentProject), onun tapşırıqları (AgentTask)
və agentlərarası canlı söhbət lenti (AgentMessage)."""
from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(120), nullable=False)
    password_hash = Column(String(500), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=func.now())

    memberships = relationship("WorkspaceMember", back_populates="user", cascade="all, delete-orphan")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(120), nullable=False, unique=True, index=True)
    brand_description = Column(Text, nullable=True)
    brand_audience = Column(Text, nullable=True)
    brand_voice = Column(Text, nullable=True)
    brand_colors = Column(String(300), nullable=True)
    brand_fonts = Column(String(300), nullable=True)
    brand_products = Column(Text, nullable=True)
    brand_forbidden_phrases = Column(Text, nullable=True)
    # Terminologiya: "səhv → düzgün" cütləri, hər sətirdə biri. Həm prompta düşür,
    # həm də doğrulamada yoxlanılır — brend lüğəti bir yerdə saxlanılır.
    brand_glossary = Column(Text, nullable=True)
    brand_logo_url = Column(String(500), nullable=True)
    brand_ai_consent = Column(Boolean, nullable=False, default=False)
    brand_updated_at = Column(DateTime, nullable=True)
    # --- Instagram avtomatik paylaşım (ƏLAVƏ ÖDƏNİŞLİ PAKET) ---------------------------
    # Bunlar QƏSDƏN workspace səviyyəsindədir. Əvvəl hesab məlumatı yalnız qlobal .env-də
    # (`settings.instagram_access_token`) saxlanılırdı — yəni İSTƏNİLƏN müştərinin "Paylaş"
    # düyməsi kontenti tətbiq SAHİBİNİN Instagram hesabına dərc edirdi. Hər workspace yalnız
    # ÖZ hesabına paylaşa bilməlidir.
    instagram_access_token = Column(Text, nullable=True)
    instagram_user_id = Column(String(60), nullable=True)
    # Paket alınıb-alınmadığı. Token olsa belə paket söndürülübsə paylaşım bloklanır.
    instagram_addon_enabled = Column(Boolean, nullable=False, default=False)
    # --- TikTok Content Posting API ---------------------------------------------------
    # Instagram-dan fərqli olaraq bu, workspace sahibinin özünün OAuth ilə qoşduğu hesabdır
    # (bax `/tiktok/connect`) — statik .env tokeni YOXDUR, çünki TikTok hər istifadəçi üçün
    # ayrı access/refresh token tələb edir və onlar vaxtaşırı yenilənməlidir.
    tiktok_access_token = Column(Text, nullable=True)
    tiktok_refresh_token = Column(Text, nullable=True)
    tiktok_open_id = Column(String(80), nullable=True)
    tiktok_token_expires_at = Column(DateTime, nullable=True)
    tiktok_addon_enabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.now())

    members = relationship("WorkspaceMember", back_populates="workspace", cascade="all, delete-orphan")
    projects = relationship("AgentProject", back_populates="workspace")


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),)

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(30), nullable=False, default="owner")
    created_at = Column(DateTime, default=func.now())

    workspace = relationship("Workspace", back_populates="members")
    user = relationship("User", back_populates="memberships")


class UserSession(Base):
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())

    user = relationship("User", back_populates="sessions")
    workspace = relationship("Workspace")


class VeoUsage(Base):
    """Başladılan hər video üçün bir sətir — SƏRT günlük limitin sayğacı.

    NİYƏ AYRI CƏDVƏL: materialdan saymaq etibarsızdır (yenidən yazma eyni materialı
    təkrar işlədir, silinən material sayğacı geri salır). Xərc sayğacı silinməməlidir.
    """

    __tablename__ = "veo_usage"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, nullable=True, index=True)
    asset_id = Column(Integer, nullable=True)
    model = Column(String(80), nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)


class BrandKitSuggestion(Base):
    """Layihə nəticəsindən çıxan Brand Kit təklifi (audit #1).

    NİYƏ AVTOMATİK YAZILMIR: Brand Kit brendin həqiqət mənbəyidir. AI çıxışının ora səssizcə
    yazılması onu vaxtla korlayar — model bir dəfə səhv ton seçər, həmin ton yeni norma olar
    və sonrakı bütün generasiya ondan qidalanar. Ona görə təklif olaraq gözləyir, qərar
    istifadəçinindir.
    """

    __tablename__ = "brand_kit_suggestions"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    source_project_id = Column(Integer, ForeignKey("agent_projects.id"), nullable=True)
    field = Column(String(60), nullable=False)          # brand_audience / brand_voice / ...
    current_value = Column(Text, nullable=True)
    suggested_value = Column(Text, nullable=False)
    rationale = Column(String(400), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")   # PENDING/ACCEPTED/DISMISSED
    created_at = Column(DateTime, default=func.now())

    workspace = relationship("Workspace")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    name = Column(String(160), nullable=False)
    objective = Column(Text, nullable=False)
    audience = Column(Text, nullable=True)
    channels = Column(String(300), nullable=False, default="Instagram")
    # Sütun adı KÖHNƏDİR: kampaniyalar əvvəl 30 günlük idi, indi 7 günlükdür və interfeys
    # bunu "Həftəlik büdcə" kimi soruşur. Ad tarixi səbəbdən "monthly" qalıb (dəyişmək
    # miqrasiya tələb edir və heç bir davranışa təsir etmir) — məzmun HƏFTƏLİK büdcədir.
    # Sərbəst mətndir (məs. "300 AZN"), hesablamada istifadə olunmur.
    monthly_budget = Column(String(80), nullable=True)
    start_date = Column(Date, nullable=True)
    # Avtomatik qaralama hansı layihədən gəldiyini bilməlidir — əks halda layihə hər
    # işə salınanda yeni qaralama yaranar.
    source_project_id = Column(Integer, ForeignKey("agent_projects.id"), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="DRAFT")
    created_at = Column(DateTime, default=func.now())

    workspace = relationship("Workspace")
    days = relationship("CampaignDay", back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignDay.day_number")


# Avtomatik qaralama hansı layihədən gəldiyini bilməlidir — əks halda hər işə salınmada
# yenisi yaranar.
class CampaignDay(Base):
    __tablename__ = "campaign_days"
    __table_args__ = (UniqueConstraint("campaign_id", "day_number", name="uq_campaign_day"),)

    id = Column(Integer, primary_key=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    day_number = Column(Integer, nullable=False)
    platform = Column(String(80), nullable=False)
    content_type = Column(String(80), nullable=False)
    theme = Column(String(240), nullable=False)
    hook = Column(String(500), nullable=True)
    cta = Column(String(300), nullable=True)
    status = Column(String(30), nullable=False, default="PLANNED")
    planned_date = Column(Date, nullable=True, index=True)

    campaign = relationship("Campaign", back_populates="days")


class ContentAsset(Base):
    __tablename__ = "content_assets"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    campaign_day_id = Column(Integer, ForeignKey("campaign_days.id"), nullable=True, index=True)
    title = Column(String(180), nullable=False)
    format = Column(String(30), nullable=False)  # POST / STORY / CAROUSEL
    aspect_ratio = Column(String(20), nullable=False)
    headline = Column(String(240), nullable=True)
    caption = Column(Text, nullable=True)
    visual_brief = Column(Text, nullable=True)
    slides_json = Column(Text, nullable=True)
    # DRAFT / NEEDS_INPUT / APPROVED / CHANGES_REQUESTED
    status = Column(String(30), nullable=False, default="DRAFT")
    # Generasiya çıxışının strukturlu hissələri (JSON). Boş qalması normaldır — köhnə
    # materiallar və əl ilə yaradılanlar bu sahələri doldurmur.
    headline_options = Column(Text, nullable=True)
    hashtags = Column(Text, nullable=True)
    # Model doldura bilmədiyi sahələr — UYDURULMUR, burada sadalanır (audit §05).
    needs_input = Column(Text, nullable=True)
    confidence = Column(String(10), nullable=True)
    # Yenidən yazma üçün orijinal brif saxlanılır ki, eyni girişlə təkrar işlədilə bilsin.
    brief_json = Column(Text, nullable=True)
    # Vizual istiqamətdən avtomatik seçilmiş/generasiya edilmiş şəkil. Yalnız ÜNVAN
    # saxlanılır — baytlar tələb anında mövcud proksi ilə yüklənir.
    image_url = Column(String(1000), nullable=True)
    image_source = Column(String(60), nullable=True)
    # Video uzunmüddətli əməliyyatdır: əvvəl `operation` saxlanılır, hazır olanda `video_url`.
    video_url = Column(String(1000), nullable=True)
    video_operation = Column(String(300), nullable=True)
    instagram_published = Column(Boolean, nullable=False, default=False)
    instagram_post_id = Column(String(60), nullable=True)
    instagram_permalink = Column(String(300), nullable=True)
    tiktok_published = Column(Boolean, nullable=False, default=False)
    tiktok_post_id = Column(String(120), nullable=True)
    # Planlaşdırılmış avtomatik dərc: müştəri bugün materialı hazırlayıb təsdiqləyir, amma
    # dərci gələcək bir tarixə/saata (Bakı vaxtı ilə, UTC-yə çevrilib saxlanılır) təyin edir.
    # `app.scheduler.publish_due_scheduled_content` hər tick-də bunu yoxlayır.
    scheduled_at = Column(DateTime, nullable=True, index=True)
    scheduled_platforms = Column(String(60), nullable=True)  # "instagram,tiktok"
    schedule_error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    workspace = relationship("Workspace")
    campaign_day = relationship("CampaignDay")
    reviews = relationship("AssetReview", back_populates="asset", cascade="all, delete-orphan", order_by="AssetReview.id.desc()")
    versions = relationship("ContentAssetVersion", back_populates="asset", cascade="all, delete-orphan", order_by="ContentAssetVersion.id.desc()")


class ContentAssetVersion(Base):
    """Yenidən yazmadan ƏVVƏLKİ nüsxə (audit F5).

    `AgentTaskVersion` ilə eyni məntiq: köhnə çıxış arxivlənir, yenidən yazma uğursuz olsa
    geri qaytarıla bilir. Təsdiqlənmiş məzmunun üstünə heç vaxt yazılmır.
    """

    __tablename__ = "content_asset_versions"

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("content_assets.id"), nullable=False, index=True)
    headline = Column(String(240), nullable=True)
    caption = Column(Text, nullable=True)
    visual_brief = Column(Text, nullable=True)
    slides_json = Column(Text, nullable=True)
    reason = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=func.now())

    asset = relationship("ContentAsset", back_populates="versions")


class AssetReview(Base):
    __tablename__ = "asset_reviews"

    id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("content_assets.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    decision = Column(String(30), nullable=False)  # APPROVED / CHANGES_REQUESTED
    feedback = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    asset = relationship("ContentAsset", back_populates="reviews")
    user = relationship("User")


class CampaignMetric(Base):
    __tablename__ = "campaign_metrics"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)
    recorded_date = Column(Date, nullable=False, index=True)
    platform = Column(String(80), nullable=False, default="Digər")
    content_type = Column(String(80), nullable=True)
    impressions = Column(Integer, nullable=False, default=0)
    reach = Column(Integer, nullable=False, default=0)
    engagements = Column(Integer, nullable=False, default=0)
    clicks = Column(Integer, nullable=False, default=0)
    leads = Column(Integer, nullable=False, default=0)
    sales = Column(Integer, nullable=False, default=0)
    spend_cents = Column(Integer, nullable=False, default=0)
    revenue_cents = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=func.now())

    workspace = relationship("Workspace")
    campaign = relationship("Campaign")


class SocialPostTracker(Base):
    """Dərc edilmiş sosial postu kampaniya və insight snapshot-ları ilə bağlayır."""
    __tablename__ = "social_post_trackers"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("agent_projects.id"), nullable=False, unique=True, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)
    platform = Column(String(30), nullable=False, default="Instagram")
    external_post_id = Column(String(120), nullable=True, unique=True, index=True)
    permalink = Column(String(700), nullable=True)
    status = Column(String(30), nullable=False, default="READY", index=True)
    last_synced_at = Column(DateTime, nullable=True)
    next_sync_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    workspace = relationship("Workspace")
    project = relationship("AgentProject")
    campaign = relationship("Campaign")


class AssetSocialTracker(Base):
    """`SocialPostTracker`-in Content Studio qardaşı: kampaniyalardan (`ContentAsset`, Reel/Story)
    paylaşılan postları izləyir. AYRICA CƏDVƏLDİR (SocialPostTracker-i genişləndirmək əvəzinə) —
    orada `project_id` NOT NULL-dur və mövcud SQLite cədvəlini bu məhdudiyyəti aradan qaldırmaq
    üçün yenidən qurmaq lazım gələrdi. Yeni cədvəl `Base.metadata.create_all` ilə avtomatik
    yaranır, risksizdir.

    NİYƏ LAZIMDIR: `/content-studio/{id}/publish-instagram` paylaşımdan sonra heç bir iz
    qoymurdu — Analitika bölməsi yalnız `CampaignMetric`-dən oxuyur, o da yalnız bu izləyicidən
    (sinxronizasiya job-u ilə) doldurulur. İzsiz paylaşım = Analitikada nəticə YOXDUR (canlı
    istifadəçi tapıntısı — kampaniyadan paylaşılan Reel-in nəticəsi görünmürdü)."""
    __tablename__ = "asset_social_trackers"
    # DİQQƏT: `asset_id` tək başına UNIQUE İDİ (bir asset = bir izləyici) — TikTok dəstəyi
    # əlavə olunanda bu, eyni Reel-i HƏM Instagram-a, HƏM TikTok-a paylaşmağı əngəllədi (ikinci
    # tracker sətri IntegrityError verirdi). İndi məhdudiyyət (asset_id, platform) cütünə keçib.
    __table_args__ = (UniqueConstraint("asset_id", "platform", name="uq_asset_social_tracker_asset_platform"),)
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    asset_id = Column(Integer, ForeignKey("content_assets.id"), nullable=False, index=True)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=True, index=True)
    platform = Column(String(30), nullable=False, default="Instagram")
    content_type = Column(String(30), nullable=True)  # REEL / STORY
    external_post_id = Column(String(120), nullable=True, unique=True, index=True)
    permalink = Column(String(700), nullable=True)
    status = Column(String(30), nullable=False, default="READY", index=True)
    last_synced_at = Column(DateTime, nullable=True)
    next_sync_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    workspace = relationship("Workspace")
    asset = relationship("ContentAsset")
    campaign = relationship("Campaign")


class SalesLead(Base):
    __tablename__ = "sales_leads"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source_external_id", name="uq_workspace_sales_lead_source"),
    )

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    company_name = Column(String(200), nullable=False)
    category = Column(String(100), nullable=True)
    city = Column(String(120), nullable=True)
    address = Column(String(500), nullable=True)
    website = Column(String(500), nullable=True)
    phone = Column(String(120), nullable=True)
    email = Column(String(255), nullable=True)
    source = Column(String(80), nullable=False, default="OpenStreetMap")
    source_external_id = Column(String(120), nullable=False)
    source_url = Column(String(500), nullable=True)
    score = Column(Integer, nullable=False, default=0)
    status = Column(String(30), nullable=False, default="NEW", index=True)
    notes = Column(Text, nullable=True)
    outreach_message = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())

    workspace = relationship("Workspace")


class LeadAudit(Base):
    __tablename__ = "lead_audits"
    id = Column(Integer, primary_key=True)
    lead_id = Column(Integer, ForeignKey("sales_leads.id"), nullable=False, index=True)
    score = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=False)
    strengths_json = Column(Text, nullable=True)
    issues_json = Column(Text, nullable=True)
    opportunities_json = Column(Text, nullable=True)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    lead = relationship("SalesLead")


class SalesProposal(Base):
    __tablename__ = "sales_proposals"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("sales_leads.id"), nullable=False, index=True)
    language = Column(String(5), nullable=False, default="AZ")
    problem = Column(Text, nullable=False)
    solution = Column(Text, nullable=False)
    starter_price_cents = Column(Integer, nullable=False, default=29900)
    growth_price_cents = Column(Integer, nullable=False, default=59900)
    premium_price_cents = Column(Integer, nullable=False, default=99900)
    status = Column(String(30), nullable=False, default="DRAFT")
    payment_status = Column(String(30), nullable=False, default="UNPAID")
    created_at = Column(DateTime, nullable=False, default=func.now())
    lead = relationship("SalesLead")
    workspace = relationship("Workspace")


class SalesActivity(Base):
    __tablename__ = "sales_activities"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("sales_leads.id"), nullable=False, index=True)
    activity_type = Column(String(40), nullable=False)
    subject = Column(String(240), nullable=True)
    content = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="DRAFT")
    due_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    lead = relationship("SalesLead")


class OutboundDelivery(Base):
    __tablename__ = "outbound_deliveries"
    __table_args__ = (UniqueConstraint("activity_id", name="uq_outbound_activity"),)
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("sales_leads.id"), nullable=False, index=True)
    activity_id = Column(Integer, ForeignKey("sales_activities.id"), nullable=False)
    channel = Column(String(30), nullable=False, default="EMAIL")
    recipient = Column(String(255), nullable=False)
    status = Column(String(30), nullable=False, default="QUEUED", index=True)
    scheduled_at = Column(DateTime, nullable=False)
    sent_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    lead = relationship("SalesLead")
    activity = relationship("SalesActivity")


class FactoryControl(Base):
    __tablename__ = "factory_controls"
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_factory_control_workspace"),)
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    factory_enabled = Column(Boolean, nullable=False, default=True)
    agents_enabled = Column(Boolean, nullable=False, default=True)
    outbound_enabled = Column(Boolean, nullable=False, default=False)
    lead_discovery_enabled = Column(Boolean, nullable=False, default=False)
    daily_email_limit = Column(Integer, nullable=False, default=10)
    daily_api_budget_cents = Column(Integer, nullable=False, default=100)
    updated_at = Column(DateTime, nullable=False, default=func.now(), onupdate=func.now())
    workspace = relationship("Workspace")


class FactoryJob(Base):
    __tablename__ = "factory_jobs"
    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    job_type = Column(String(60), nullable=False, index=True)
    payload_json = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="PENDING", index=True)
    priority = Column(Integer, nullable=False, default=100)
    run_after = Column(DateTime, nullable=False, default=func.now(), index=True)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    locked_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    workspace = relationship("Workspace")


class FactoryAuditLog(Base):
    __tablename__ = "factory_audit_logs"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    actor = Column(String(120), nullable=False)
    action = Column(String(100), nullable=False, index=True)
    target_type = Column(String(80), nullable=True)
    target_id = Column(String(80), nullable=True)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    workspace = relationship("Workspace")


class NightShiftPlan(Base):
    __tablename__ = "night_shift_plans"
    __table_args__ = (UniqueConstraint("workspace_id", name="uq_night_shift_workspace"),)
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    city = Column(String(120), nullable=False, default="Baku, Azerbaijan")
    category = Column(String(80), nullable=False, default="restaurant")
    daily_lead_target = Column(Integer, nullable=False, default=15)
    run_hour_baku = Column(Integer, nullable=False, default=2)
    next_run_at = Column(DateTime, nullable=True, index=True)
    last_run_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=func.now())
    workspace = relationship("Workspace")


class NightShiftReport(Base):
    __tablename__ = "night_shift_reports"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    job_id = Column(Integer, ForeignKey("factory_jobs.id"), nullable=True)
    discovered = Column(Integer, nullable=False, default=0)
    added = Column(Integer, nullable=False, default=0)
    audited = Column(Integer, nullable=False, default=0)
    outreach_drafts = Column(Integer, nullable=False, default=0)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now(), index=True)
    workspace = relationship("Workspace")


class MeetingBrief(Base):
    __tablename__ = "meeting_briefs"
    id = Column(Integer, primary_key=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    lead_id = Column(Integer, ForeignKey("sales_leads.id"), nullable=False, index=True)
    questions_json = Column(Text, nullable=False)
    objections_json = Column(Text, nullable=False)
    agenda = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=func.now())
    lead = relationship("SalesLead")


class AgentProject(Base):
    __tablename__ = "agent_projects"

    id = Column(Integer, primary_key=True, index=True)
    # Müştəriyə göndərilən ictimai linkin təxmin edilə bilməyən açarı. Layihə ID-si ardıcıl
    # olduğu üçün /agency/1/view, /agency/2/view … deyə sadalamaqla BAŞQA workspace-lərin hazır
    # nəticələrini oxumaq mümkün idi; token bunun qarşısını alır (link yalnız onu bilənlərə açıqdır).
    share_token = Column(String(48), nullable=True, unique=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    brief = Column(Text, nullable=False)
    # BRIEF -> PLANNING(implicit) -> IN_PROGRESS -> AWAITING_APPROVAL -> DELIVERED | REJECTED
    status = Column(String(30), nullable=False, default="BRIEF")
    # CEO brifə görə təyin edir: "landing_page" (sayt) və ya "social_post" (Instagram/sosial
    # media postu) — Developer-in nə yazacağını (HTML kod, yoxsa paylaşıma hazır mətn) müəyyən edir.
    output_type = Column(String(30), nullable=False, default="landing_page")
    deliverable_html = Column(Text, nullable=True)
    deliverable_image_url = Column(String(500), nullable=True)
    # Satış departamentinin çıxışı: soyuq email + DM skripti + satış piti + kampaniya təklifi
    # (yaradıcı deliverable-dan ayrıca mətn sahəsi).
    sales_kit = Column(Text, nullable=True)
    # Instagram-a dərc olunubmu (təkrar paylaşımın qarşısını almaq üçün) + dərc olunan media ID/link
    instagram_published = Column(Boolean, nullable=False, default=False)
    instagram_post_id = Column(String(60), nullable=True)
    instagram_permalink = Column(String(300), nullable=True)
    # Telegram/n8n bildirişi artıq göndərilib mi (təkrar bildiriş göndərməmək üçün)
    notified = Column(Boolean, nullable=False, default=False)
    # Brif Telegram-dan yaradılıbsa, hansı çata bildiriş göndəriləcəyini bilmək üçün saxlanılır
    telegram_chat_id = Column(String(50), nullable=True)
    # Bu layihə RƏDD ediləndə (rejectdə) qeyd olunan səbəb — qeydiyyat üçün saxlanılır.
    reject_feedback = Column(Text, nullable=True)
    # Bu layihə əvvəlki RƏDD edilmiş layihənin avtomatik təkrar-cəhdidirsə, səbəb bura köçürülür
    # ki, CEO/komanda planlaşdırarkən NİYƏ bəyənilmədiyini bilib ona uyğun düzəliş etsin.
    retry_feedback = Column(Text, nullable=True)
    retry_of_id = Column(Integer, ForeignKey("agent_projects.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())

    workspace = relationship("Workspace", back_populates="projects")

    tasks = relationship(
        "AgentTask", back_populates="project", cascade="all, delete-orphan", order_by="AgentTask.order_index"
    )
    messages = relationship(
        "AgentMessage", back_populates="project", cascade="all, delete-orphan", order_by="AgentMessage.id"
    )


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("agent_projects.id"), nullable=False)
    role = Column(String(50), nullable=False)  # strategist / copywriter / designer / developer
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="TODO")  # TODO / DOING / REVIEW / DONE
    output = Column(Text, nullable=True)
    revision_count = Column(Integer, nullable=False, default=0)
    order_index = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=func.now())

    project = relationship("AgentProject", back_populates="tasks")
    versions = relationship(
        "AgentTaskVersion", back_populates="task", cascade="all, delete-orphan",
        order_by="AgentTaskVersion.version_no.desc()",
    )


class AgentTaskVersion(Base):
    """Bir tapşırığın KÖHNƏ çıxışının arxivi.

    `AgentTask.output` tək sütundur — yenidən yazdırdıqda köhnə mətn həmişəlik itirdi. Burada
    hər yenidən yazmadan ƏVVƏLKİ variant saxlanılır ki, istifadəçi variantları müqayisə edib
    lazım gələrsə köhnəyə qayıda bilsin. `version_no` 1-dən başlayır (ilk, orijinal çıxış)."""
    __tablename__ = "agent_task_versions"
    __table_args__ = (UniqueConstraint("task_id", "version_no", name="uq_task_version"),)

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("agent_tasks.id"), nullable=False, index=True)
    version_no = Column(Integer, nullable=False)
    output = Column(Text, nullable=True)
    # İstifadəçinin bu versiyanı yaradarkən verdiyi əlavə göstəriş (varsa) — "niyə dəyişdi" izi.
    instruction = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now())

    task = relationship("AgentTask", back_populates="versions")


class LlmUsage(Base):
    """Hər LLM sorğusunun token/uğur qeydi — hansı provayder və rol nə qədər sərf edir.

    Pulsuz provayder kvotaları daim dolduğu üçün bu görünürlük olmadan "hansı rol limiti yeyir"
    sualına yalnız təxminlə cavab vermək olurdu. Sorğu uğursuz olsa da (rate limit, 402) qeyd
    edilir — `ok=False` ilə — çünki uğursuzluq statistikası da provayder seçimi üçün vacibdir."""
    __tablename__ = "llm_usage"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    project_id = Column(Integer, ForeignKey("agent_projects.id"), nullable=True, index=True)
    role = Column(String(50), nullable=True, index=True)
    provider = Column(String(50), nullable=False, index=True)
    model = Column(String(120), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    total_tokens = Column(Integer, nullable=False, default=0)
    latency_ms = Column(Integer, nullable=False, default=0)
    ok = Column(Boolean, nullable=False, default=True)
    # Uğursuzluq səbəbi: "rate_limit" / "payment" / "server" / "network" / "parse"
    error_kind = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)


class VoiceCall(Base):
    """Saytdakı səsli agentə edilən bir "zəng" (danışıq sessiyası).

    Niyə saxlanılır: agentin əsas işi yönləndirməkdir — kimin zəng etdiyi, nə istədiyi və
    hansı nəticəyə gəldiyi qeyd olunmasa, "əlaqə məlumatını yazıb insana ötürsün" ssenarisi
    mənasız olardı. `session_id` brauzer tərəfində yaradılır və bir söhbətə aiddir."""
    __tablename__ = "voice_calls"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), nullable=False, unique=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=True, index=True)
    caller_name = Column(String(120), nullable=True)
    caller_phone = Column(String(40), nullable=True)
    # none / create_brief / capture_lead / handoff
    outcome = Column(String(30), nullable=False, default="none")
    turns = Column(Integer, nullable=False, default=0)
    transcript = Column(Text, nullable=True)
    created_project_id = Column(Integer, ForeignKey("agent_projects.id"), nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)

    workspace = relationship("Workspace")


class DemoCall(Base):
    """Təqdimat zamanı "bir klik" ilə edilən AI satış zəngi (Control Room düyməsi).

    Real bir lead-ə deyil, istənilən nömrəyə (adətən təqdim edənin öz telefonuna) gedir —
    məqsəd CRM yazısı deyil, canlı nümayişdir. Buna görə `SalesLead`-dən ayrı, sadə cədvəl."""
    __tablename__ = "demo_calls"

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = Column(Integer, ForeignKey("workspaces.id"), nullable=False, index=True)
    # Twilio TwiML-i zeng sorgusunun icinde qebul edir, amma media-stream websocket-i
    # sorgunu autentifikasiya ede bilmir - bu token o baglantini bu zenge baglayir.
    call_token = Column(String(48), nullable=False, unique=True, index=True)
    phone_number = Column(String(40), nullable=False)
    call_sid = Column(String(60), nullable=True)
    status = Column(String(20), nullable=False, default="initiated")
    transcript = Column(Text, nullable=True)
    created_at = Column(DateTime, default=func.now(), index=True)

    workspace = relationship("Workspace")


class PitchMeeting(Base):
    """Teqdimat zenginin ("gorus_teyin_et" funksiyasi) tesdiqlediyi demo gorusleri.

    Novbe cedveli budur: yeni gorus teyin edilende bu cedvel yoxlanilir — eyni saat
    doludursa, agent basqa bos vaxt teklif edir (bax `app/voice_pitch.py`)."""
    __tablename__ = "pitch_meetings"

    id = Column(Integer, primary_key=True, index=True)
    demo_call_id = Column(Integer, ForeignKey("demo_calls.id"), nullable=True, index=True)
    # Baki yerli vaxtdan UTC-ye cevrilmis, novbe toqqusmasi bunun uzerinden yoxlanilir.
    scheduled_at = Column(DateTime, nullable=False, index=True)
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=func.now())

    demo_call = relationship("DemoCall")


class AgentMessage(Base):
    __tablename__ = "agent_messages"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("agent_projects.id"), nullable=False)
    from_role = Column(String(50), nullable=False)
    to_role = Column(String(50), nullable=True)  # null = bütün komandaya (broadcast)
    kind = Column(String(20), nullable=False, default="chat")  # chat / handoff / critique / decision
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=func.now())

    project = relationship("AgentProject", back_populates="messages")
