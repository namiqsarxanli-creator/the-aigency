"""SQLAlchemy engine/session qurulumu."""
import logging
import re

from sqlalchemy import event, inspect, text
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core import settings

is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_options = {"connect_args": connect_args, "pool_pre_ping": True}
if not is_sqlite:
    engine_options.update(pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
                          pool_recycle=1800)
engine = create_engine(settings.database_url, **engine_options)
logger = logging.getLogger(__name__)

if is_sqlite:
    # Defolt SQLite jurnal rejimi ("delete") konkurent yazma/oxumada "database is locked" və ya
    # "bad parameter or other API misuse" xətalarına meyillidir — arxa fon planlayıcısı (hər 6san)
    # + API sorğuları + paralel dəstək departamenti batch-i (ThreadPoolExecutor) eyni anda DB-yə
    # toxunanda bu üzə çıxdı (canlı testdə tapıldı). WAL rejimi oxucuları yazıcını bloklamır —
    # standart və etibarlı həlldir. `busy_timeout` konfliktdə xəta atmaq əvəzinə qısa gözləyir.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def initialize_database() -> None:
    """Yeni cədvəlləri yaradır və köhnə demo DB-ni workspace sxeminə təhlükəsiz keçirir."""
    # Import burada edilir ki, bütün modellər Base metadata-ya qeyd olunsun və circular import olmasın.
    from app import db_models

    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    project_columns = {column["name"] for column in inspector.get_columns("agent_projects")}
    if "workspace_id" not in project_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_projects ADD COLUMN workspace_id INTEGER"))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_agent_projects_workspace_id "
                "ON agent_projects (workspace_id)"
            ))

    workspace_columns = {column["name"] for column in inspect(engine).get_columns("workspaces")}
    timestamp_type = "DATETIME" if is_sqlite else "TIMESTAMP"
    workspace_migrations = {
        "brand_description": "TEXT", "brand_audience": "TEXT", "brand_voice": "TEXT",
        "brand_colors": "VARCHAR(300)", "brand_fonts": "VARCHAR(300)",
        "brand_products": "TEXT", "brand_forbidden_phrases": "TEXT",
        "brand_logo_url": "VARCHAR(500)", "brand_ai_consent": "BOOLEAN NOT NULL DEFAULT 0",
        "brand_updated_at": timestamp_type,
        "instagram_access_token": "TEXT", "instagram_user_id": "VARCHAR(60)",
        "instagram_addon_enabled": "BOOLEAN NOT NULL DEFAULT 0",
        "brand_glossary": "TEXT",
        "tiktok_access_token": "TEXT", "tiktok_refresh_token": "TEXT",
        "tiktok_open_id": "VARCHAR(80)", "tiktok_token_expires_at": timestamp_type,
        "tiktok_addon_enabled": "BOOLEAN NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        for column_name, column_type in workspace_migrations.items():
            if column_name not in workspace_columns:
                connection.execute(text(
                    f"ALTER TABLE workspaces ADD COLUMN {column_name} {column_type}"
                ))

    inspector = inspect(engine)
    if "campaigns" in inspector.get_table_names():
        campaign_columns = {column["name"] for column in inspector.get_columns("campaigns")}
        day_columns = {column["name"] for column in inspector.get_columns("campaign_days")}
        with engine.begin() as connection:
            if "source_project_id" not in campaign_columns:
                connection.execute(text("ALTER TABLE campaigns ADD COLUMN source_project_id INTEGER"))
            if "start_date" not in campaign_columns:
                connection.execute(text("ALTER TABLE campaigns ADD COLUMN start_date DATE"))
            if "planned_date" not in day_columns:
                connection.execute(text("ALTER TABLE campaign_days ADD COLUMN planned_date DATE"))
                connection.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_campaign_days_planned_date ON campaign_days (planned_date)"
                ))

    if "content_assets" in inspector.get_table_names():
        asset_columns = {column["name"] for column in inspector.get_columns("content_assets")}
        asset_migrations = {
            "headline_options": "TEXT", "hashtags": "TEXT", "needs_input": "TEXT",
            "confidence": "VARCHAR(10)", "brief_json": "TEXT",
            "image_url": "VARCHAR(1000)", "image_source": "VARCHAR(60)",
            "video_url": "VARCHAR(1000)", "video_operation": "VARCHAR(300)",
            "instagram_published": "BOOLEAN NOT NULL DEFAULT 0",
            "instagram_post_id": "VARCHAR(60)", "instagram_permalink": "VARCHAR(300)",
            "tiktok_published": "BOOLEAN NOT NULL DEFAULT 0", "tiktok_post_id": "VARCHAR(120)",
            "scheduled_at": timestamp_type, "scheduled_platforms": "VARCHAR(60)",
            "schedule_error": "TEXT",
        }
        with engine.begin() as connection:
            for column_name, column_type in asset_migrations.items():
                if column_name not in asset_columns:
                    connection.execute(text(
                        f"ALTER TABLE content_assets ADD COLUMN {column_name} {column_type}"
                    ))

    if "lead_audits" in inspector.get_table_names():
        audit_columns = {column["name"] for column in inspector.get_columns("lead_audits")}
        if "details_json" not in audit_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE lead_audits ADD COLUMN details_json TEXT"))

    if "sales_proposals" in inspector.get_table_names():
        proposal_columns = {column["name"] for column in inspector.get_columns("sales_proposals")}
        if "language" not in proposal_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE sales_proposals ADD COLUMN language VARCHAR(5) NOT NULL DEFAULT 'AZ'"))

    if "asset_social_trackers" in inspector.get_table_names():
        # `asset_id` əvvəl tək başına UNIQUE idi (bir asset = bir izləyici) — TikTok dəstəyi ilə
        # eyni Reel-in HƏM Instagram-a, HƏM TikTok-a paylaşılması lazım oldu, ona görə məhdudiyyət
        # (asset_id, platform) cütünə keçirilir. SQLite inline UNIQUE-i ALTER TABLE ilə silə
        # bilmədiyi üçün cədvəl yenidən qurulur (canlıda cəmi bir neçə sətir var, risksizdir).
        existing_uniques = {
            tuple(sorted(uc.get("column_names") or []))
            for uc in inspector.get_unique_constraints("asset_social_trackers")
        }
        if ("asset_id", "platform") not in existing_uniques and "asset_social_trackers_old" not in inspector.get_table_names():
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE asset_social_trackers RENAME TO asset_social_trackers_old"))
            db_models.AssetSocialTracker.__table__.create(bind=engine)
        # AYRICA tranzaksiyada: server canlı SQLite faylını açıq saxlayanda DROP TABLE müvəqqəti
        # "database is locked" verə bilər — eyni tranzaksiyada olsaydı bu, artıq uğurlu INSERT-i
        # də geri qaytarardı (canlıda məhz belə oldu, sonra əl ilə düzəldildi).
        if "asset_social_trackers_old" in inspect(engine).get_table_names():
            with engine.begin() as connection:
                connection.execute(text(
                    "INSERT OR IGNORE INTO asset_social_trackers (id, workspace_id, asset_id, campaign_id, platform, "
                    "content_type, external_post_id, permalink, status, last_synced_at, next_sync_at, "
                    "last_error, created_at) "
                    "SELECT id, workspace_id, asset_id, campaign_id, platform, content_type, external_post_id, "
                    "permalink, status, last_synced_at, next_sync_at, last_error, created_at "
                    "FROM asset_social_trackers_old"
                ))
            with engine.begin() as connection:
                connection.execute(text("DROP TABLE asset_social_trackers_old"))

    if "share_token" not in project_columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE agent_projects ADD COLUMN share_token VARCHAR(48)"))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_projects_share_token "
                "ON agent_projects (share_token)"
            ))

    db = SessionLocal()
    try:
        # Köhnə layihələrin ictimai linki hələ ardıcıl ID-yə bağlı idi — hər birinə təxmin
        # edilməyən token veririk ki, sadalama ilə oxunmasınlar.
        from app.agency import new_share_token

        for project in db.query(db_models.AgentProject).filter(
            db_models.AgentProject.share_token.is_(None)
        ).all():
            project.share_token = new_share_token()
        db.commit()

        # Köhnə material adları yalnız "Gün 1 · Reel" formasındadır — kampaniya kimliyi
        # olmadığı üçün eyni workspace-də bir neçə material eyni adı daşıyır və istifadəçi
        # onları bir-birindən ayıra bilmir. Bağlı olduğu kampaniyanın adını əvvələ əlavə
        # edirik. Yetim materiallara (plan günü silinib) toxunmuruq — onlar üçün mənbə yoxdur.
        for asset in db.query(db_models.ContentAsset).filter(
            db_models.ContentAsset.campaign_day_id.isnot(None),
            db_models.ContentAsset.title.like("Gün %"),
        ).all():
            day = db.get(db_models.CampaignDay, asset.campaign_day_id)
            if day:
                campaign = db.get(db_models.Campaign, day.campaign_id)
                if campaign:
                    asset.title = f"{campaign.name} · {asset.title}"[:180]
        db.commit()

        # SC-1 backfill: köhnə plan günlərinin `theme` sahəsi "{faza} · {bucaq}: {məhsul}"
        # formatındadır — sondakı hissə `brand_products` xam CRM sahəsinin ilk sətridir.
        # Körpü isə caption-u `theme + cta` kimi qururdu, ona görə müştəri caption yerində
        # "Problem və həll: Kətan köynəklər, payız paltarları, əl işi aksesuarl..." görürdü.
        # Plan günləri YALNIZ generatordan gəlir (mətn redaktə marşrutu yoxdur) və generasiya
        # edilmiş bucaqların heç birində iki nöqtə yoxdur — ona görə kəsmək təhlükəsizdir.
        cleaned_days = cleaned_assets = 0
        for day in db.query(db_models.CampaignDay).all():
            old_theme = day.theme or ""
            theme = old_theme.rsplit(": ", 1)[0].strip() if ": " in old_theme else old_theme
            hook = re.sub(r"\s*Məqsəd:.*$", "", day.hook or "", flags=re.S).strip()
            cta = re.sub(r"\s*·\s*Auditoriya:.*$", "", day.cta or "", flags=re.S).strip()

            # Günə bağlı DRAFT materiallar eyni yapışdırmanı daşıyır. Yalnız caption-u həqiqətən
            # KÖHNƏ theme ilə başlayanlara toxunuruq — istifadəçinin öz mətni olduğu kimi qalır.
            # Təsdiqlənmiş və dəyişiklik gözləyən materiallara ümumiyyətlə toxunmuruq.
            if old_theme:
                for asset in db.query(db_models.ContentAsset).filter(
                    db_models.ContentAsset.campaign_day_id == day.id,
                    db_models.ContentAsset.status == "DRAFT",
                ).all():
                    if (asset.caption or "").startswith(old_theme):
                        asset.headline, asset.caption = hook, cta
                        cleaned_assets += 1

            if (theme, hook, cta) != (day.theme, day.hook, day.cta):
                day.theme, day.hook, day.cta = theme, hook, cta
                cleaned_days += 1
        db.commit()
        if cleaned_days or cleaned_assets:
            logger.info("SC-1 backfill: %s plan günü, %s draft material təmizləndi",
                        cleaned_days, cleaned_assets)

        # Platforma-format uyğunsuzluğu (audit #4): köhnə planlarda format platformadan
        # asılı olmadan seçilirdi, ona görə TikTok gününə "Carousel" düşə bilirdi.
        # YALNIZ hələ işlənməmiş (PLANNED) günlərə toxunuruq — təsdiqlənmiş və ya
        # materiala çevrilmiş günü dəyişmək istifadəçinin işini pozardı.
        from app.campaigns import fit_format

        fixed_formats = 0
        for day in db.query(db_models.CampaignDay).filter(
            db_models.CampaignDay.status == "PLANNED"
        ).all():
            corrected = fit_format(day.content_type or "", day.platform or "")
            if corrected != day.content_type:
                day.content_type = corrected
                fixed_formats += 1
        db.commit()
        if fixed_formats:
            logger.info("Platforma-format uyğunlaşdırması: %s plan günü düzəldildi", fixed_formats)

        legacy_workspace = db.query(db_models.Workspace).filter(db_models.Workspace.slug == "legacy").first()
        if not legacy_workspace:
            legacy_workspace = db_models.Workspace(name="The Aigency", slug="legacy")
            db.add(legacy_workspace)
            db.flush()
        db.query(db_models.AgentProject).filter(
            db_models.AgentProject.workspace_id.is_(None)
        ).update({db_models.AgentProject.workspace_id: legacy_workspace.id}, synchronize_session=False)
        db.commit()

        # Instagram hesabı əvvəllər QLOBAL .env-də idi — yəni hər workspace-in "Paylaş" düyməsi
        # tətbiq sahibinin hesabına dərc edirdi. İndi hesab workspace-ə bağlıdır. Köhnə qlobal
        # açarı BİR DƏFƏ sahibin (legacy) workspace-inə köçürürük ki, onun mövcud quraşdırması
        # işləməyə davam etsin; qalan bütün workspace-lər isə düzgün şəkildə bağlı qalır.
        if (
            settings.instagram_access_token
            and settings.instagram_user_id
            and not legacy_workspace.instagram_access_token
        ):
            legacy_workspace.instagram_access_token = settings.instagram_access_token
            legacy_workspace.instagram_user_id = settings.instagram_user_id
            legacy_workspace.instagram_addon_enabled = True
            db.commit()
    finally:
        db.close()
