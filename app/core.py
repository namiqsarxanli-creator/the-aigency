"""Mərkəzi konfiqurasiya: .env oxunur, tənzimləmələr bir yerdə saxlanılır."""
import os

from dotenv import load_dotenv

load_dotenv(override=True)


class Settings:
    # DİQQƏT: bu açar ÖDƏNİŞLİDİR və YALNIZ şəkil generasiyası üçün işlədilir
    # (`app/openai_images.py`). Mətn zəncirindən (`agency._providers`) qəsdən çıxarılıb —
    # əks halda hər LLM sorğusu bu ödənişli açarı yeyərdi. Mətn üçün Groq/Gemini kifayətdir.
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()
    openai_nano_model: str = os.getenv("OPENAI_NANO_MODEL", "gpt-5-nano").strip()
    openai_image_model: str = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1").strip()
    openai_image_size: str = os.getenv("OPENAI_IMAGE_SIZE", "1024x1024").strip()

    # Sora (OpenAI video) — Veo kimi ödənişlidir və pulsuz tarifi yoxdur (bax `app/sora.py`).
    openai_video_model: str = os.getenv("OPENAI_VIDEO_MODEL", "sora-2").strip()
    openai_video_size: str = os.getenv("OPENAI_VIDEO_SIZE", "1280x720").strip()
    openai_video_seconds: str = os.getenv("OPENAI_VIDEO_SECONDS", "8").strip()

    # Hər üçü OpenAI-uyğun /chat/completions formatı təqdim edir — eyni kodla çağırıla bilir.
    groq_api_key: str = os.getenv("GROQ_API_KEY", "").strip()
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip()

    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    # VEO ÖDƏNİŞLİDİR və pulsuz tarifi yoxdur — defolt SÖNÜLÜ. Açmadan sorğu getmir.
    veo_enabled: bool = os.getenv("VEO_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    veo_model: str = os.getenv("VEO_MODEL", "veo-3.1-lite-generate-preview").strip()
    # SƏRT GÜNLÜK LİMİT. Google-un büdcəsi yalnız XƏBƏRDARLIQ göndərir, kəsmir —
    # ona görə kəsmə tətbiqin öz tərəfindədir. Limit dolanda video sorğusu getmir.
    veo_daily_limit: int = int(os.getenv("VEO_DAILY_LIMIT", "10") or 10)
    # Bir videonun təxmini qiyməti (8 san · lite · 720p). Yalnız hesabat üçündür.
    veo_cost_per_video: float = float(os.getenv("VEO_COST_PER_VIDEO", "0.40") or 0.40)

    hf_api_key: str = os.getenv("HF_API_KEY", "").strip()
    hf_model: str = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct").strip()

    # OpenRouter — bir açarla onlarla pulsuz model (model adı ":free" ilə bitməlidir, əks halda
    # ödənişli tarifə düşür). Pulsuz limit: ~20 sorğu/dəq və gündə 50 sorğu (kredit almasanız).
    # DİQQƏT: pulsuz model siyahısı TEZ-TEZ DƏYİŞİR (Meta rotasiya edir) — bir model bir gün
    # işləyib sabah 404/429 verə bilər, ona görə ehtiyat rolunda saxlanılır.
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "").strip()
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free").strip()

    # Cerebras — çox sürətli, amma İYUL 2026-DAN kart tələb edir (bir dəfəlik $5 trial krediti,
    # 30 gündə bitir). Əvvəllər tam pulsuz idi. Açar boşdursa sadəcə keçilir.
    cerebras_api_key: str = os.getenv("CEREBRAS_API_KEY", "").strip()
    cerebras_model: str = os.getenv("CEREBRAS_MODEL", "llama-3.3-70b").strip()

    # Vizual mənbələr — sırayla sınanır: Pexels -> Unsplash -> Pixabay -> (AI) -> Commons.
    # Üçü də pulsuzdur və kart tələb etmir; açarı olmayanlar sadəcə keçilir.
    pexels_api_key: str = os.getenv("PEXELS_API_KEY", "").strip()
    unsplash_access_key: str = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
    pixabay_api_key: str = os.getenv("PIXABAY_API_KEY", "").strip()
    allow_ai_image_fallback: bool = os.getenv("ALLOW_AI_IMAGE_FALLBACK", "false").lower() == "true"

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./agency.db").strip()
    redis_url: str = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
    worker_mode: str = os.getenv("WORKER_MODE", "embedded").strip().lower()
    environment: str = os.getenv("APP_ENV", "development").strip().lower()
    cookie_secure: bool = os.getenv("COOKIE_SECURE", "auto").strip().lower() in {"1", "true", "yes"}
    db_pool_size: int = int(os.getenv("DB_POOL_SIZE", "10"))
    db_max_overflow: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))

    # Boş qalsa qorumasız işləyir (lokal demo) — dolarsa, mutasiya edən endpoint-lər
    # `X-API-Key` başlığında bunu tələb edir. Ngrok ilə internetə açıldıqda vacibdir.
    agency_api_key: str = os.getenv("AGENCY_API_KEY", "").strip()

    # Müştəriyə göndərilən "/s/{share_token}" linkinin əvvəlinə əlavə olunur. Lokal test üçün
    # defolt kifayətdir, amma müştəri linki AÇSIN deyə bu, backend-in özünün İCTİMAİ (ngrok və s.)
    # ünvanı olmalıdır — n8n-in daxili host.docker.internal ÜNVANI YARAMAZ, çünki o yalnız Docker
    # konteynerləri arasında işləyir, xarici brauzerdən əlçatan deyil.
    # DİQQƏT: Instagram paylaşımı üçün də bu VACİBDİR — Meta şəkli bu URL-dən özü yükləyir.
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8800").strip().rstrip("/")

    # YALNIZ media (Instagram şəkli) üçün ictimai ünvan — autentifikasiyadan AYRIDIR.
    # Niyə ayrı: `public_base_url` https olanda sessiya çərəzi `Secure` işarələnir
    # (bax auth.set_session_cookie) və tətbiqə `http://127.0.0.1:8800` ilə girmək mümkün
    # olmur. Instagram üçün isə ictimai HTTPS ünvan şərtdir. Bu sahə ikisini uzlaşdırır:
    # tətbiq lokal qalır, Meta isə tuneldən şəkli yükləyir.
    # Boş qalsa `public_base_url`-ə düşür.
    public_media_base_url: str = (
        os.getenv("PUBLIC_MEDIA_BASE_URL", "").strip().rstrip("/")
        or os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8800").strip().rstrip("/")
    )

    # Instagram Graph API (rəsmi, Meta app + Facebook developer hesabı tələb edir). Boş qalsa
    # deaktivdir. Yalnız BUFFER_API_KEY də boşdursa istifadə olunur (bax aşağı).
    instagram_access_token: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()
    instagram_user_id: str = os.getenv("INSTAGRAM_USER_ID", "").strip()
    instagram_api_version: str = os.getenv("INSTAGRAM_API_VERSION", "v23.0").strip()
    # İki fərqli giriş üsulu var və TOKENLƏRİ BİR-BİRİNİ ƏVƏZ ETMİR:
    #   graph.instagram.com  -> "Instagram login" (Facebook Page tələb etmir) — bizim quraşdırma
    #   graph.facebook.com   -> "Facebook login" (Page + instagram_business_account tələb edir)
    instagram_api_host: str = os.getenv("INSTAGRAM_API_HOST", "https://graph.instagram.com").strip().rstrip("/")

    # TikTok Content Posting API. developers.tiktok.com-da app yaradıb "Content Posting API"
    # məhsulunu əlavə edin, "video.publish" scope-unu aktivləşdirin. Hər workspace öz hesabını
    # OAuth ilə qoşur (bax `app/tiktok.py`, `/tiktok/connect`) — burada YALNIZ app-ın öz
    # kimliyi (client key/secret) saxlanılır, istifadəçi tokenləri workspace-də saxlanılır.
    # App audit keçməyibsə TikTok yalnız "SELF_ONLY" (şəxsi) paylaşıma icazə verir — açıq
    # (public) paylaşım üçün TikTok-a audit sorğusu göndərmək lazımdır.
    tiktok_client_key: str = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
    tiktok_client_secret: str = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
    tiktok_redirect_uri: str = os.getenv("TIKTOK_REDIRECT_URI", "").strip()

    # Buffer (buffer.com) — Meta app/Facebook developer hesabı TƏLƏB ETMİR, Instagram-ı birbaşa
    # (IG login ilə) qoşmaq kifayətdir. Settings → API → "Create Personal API Key". Buffer bunu
    # varsa MƏHZ ONU istifadə edir (Meta-dan asılılığı olmadığı üçün üstünlük verilir).
    buffer_api_key: str = os.getenv("BUFFER_API_KEY", "").strip()
    # İxtiyari — boş qalsa qoşulu kanallar arasından "instagram" servisli olanı avtomatik tapır.
    buffer_channel_id: str = os.getenv("BUFFER_CHANNEL_ID", "").strip()

    # Web dashboard-dan yaradılan briflərin chat_id-si olmur. Bunu doldursanız (öz Telegram
    # chat ID-niz, @userinfobot-dan öyrənilir), web-dən yaradılan layihələr də hazır olanda
    # sizə Telegram bildirişi göndərir. Boş qalsa, yalnız Telegram /brief ilə yaradılanlar bildirilir.
    default_telegram_chat_id: str = os.getenv("DEFAULT_TELEGRAM_CHAT_ID", "").strip()

    # Lokal n8n-in daxili ünvanı (məs. http://127.0.0.1:5678). Doldurulsa, bu tətbiq
    # `/webhook*` istəklərini n8n-ə ötürür — belədə pulsuz ngrok-un TƏK statik domeni həm
    # Twilio zənglərinə (bu tətbiq), həm də n8n-in Telegram webhook-una xidmət edir.
    # Bax: app/n8n_proxy.py. Buludda n8n olmadığı üçün orada BOŞ qalmalıdır.
    n8n_internal_url: str = os.getenv("N8N_INTERNAL_URL", "").strip()

    # Təsdiqlənmiş satış emailləri üçün SMTP. Boş qaldıqda növbə işləyir, amma heç nə göndərmir.
    smtp_host: str = os.getenv("SMTP_HOST", "").strip()
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_username: str = os.getenv("SMTP_USERNAME", "").strip()
    smtp_password: str = os.getenv("SMTP_PASSWORD", "").strip()
    smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "").strip()
    smtp_use_tls: bool = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
    # Xarici əməliyyatlar ayrı açarlardır: sosial paylaşımı açmaq email göndərişini açmır.
    # EXTERNAL_ACTIONS_ENABLED köhnə quraşdırmalar üçün yalnız sosial paylaşım fallback-ıdır.
    external_actions_enabled: bool = os.getenv("EXTERNAL_ACTIONS_ENABLED", "false").lower() == "true"
    social_publish_enabled: bool = os.getenv("SOCIAL_PUBLISH_ENABLED", "false").lower() == "true"
    email_delivery_enabled: bool = os.getenv("EMAIL_DELIVERY_ENABLED", "false").lower() == "true"

    # --- Əlaqə məlumatları (saytda göstərilir) -----------------------------------------
    # Boş qalsa saytda HEÇ NƏ göstərilmir — yarımçıq/uydurma nömrə göstərməkdənsə gizlətmək
    # daha düzgündür. Nömrəni beynəlxalq formatda yazın: +994 XX XXX XX XX
    contact_phone: str = os.getenv("CONTACT_PHONE", "").strip()
    contact_email: str = os.getenv("CONTACT_EMAIL", "").strip()
    # Zəng qəbul saatları (məs. "B.e–Cümə, 09:00–18:00"). Boş qalsa göstərilmir.
    contact_hours: str = os.getenv("CONTACT_HOURS", "").strip()

    # --- Saytdakı səsli AI agenti -------------------------------------------------------
    # Nitq TANIMA brauzerin öz Web Speech API-si ilə pulsuz olur — server üçün açar lazım deyil.
    # Aşağıdakılar yalnız SƏSLƏNDİRMƏ üçündür və İXTİYARİDİR: boş qalsa brauzerin öz səsi
    # işlədilir (o da pulsuzdur, sadəcə bəzi cihazlarda Azərbaycanca səs olmaya bilər).
    # Azure F0 (pulsuz) tarifi: ayda 0.5M simvol — bu istifadə üçün bol-bol kifayətdir.
    azure_speech_key: str = os.getenv("AZURE_SPEECH_KEY", "").strip()
    azure_speech_region: str = os.getenv("AZURE_SPEECH_REGION", "").strip()
    # az-AZ-BanuNeural (qadın) və ya az-AZ-BabekNeural (kişi)
    azure_speech_voice: str = os.getenv("AZURE_SPEECH_VOICE", "az-AZ-BanuNeural").strip()
    # Səsli agenti tamamilə söndürmək üçün "false"
    voice_agent_enabled: bool = os.getenv("VOICE_AGENT_ENABLED", "true").lower() == "true"

    # --- Təqdimat zəngi: "bir klik" ilə real telefona AI zəngi (Control Room-da düymə) --------
    # Twilio Console > Account Info. Boş qalsa düymə "konfiqurasiya olunmayıb" göstərir.
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    twilio_from_number: str = os.getenv("TWILIO_FROM_NUMBER", "").strip()
    # Realtime səs modeli — mətn zəncirindən ayrı, çünki səsli danışıq üçün xüsusi modeldir.
    # `openai_api_key`-i (yuxarıda, şəkil üçün ayrılmış) bilərəkdən paylaşır: bu da açıq
    # istifadəçi əməli ilə tetiklənən, təsadüfən yanmayan bir funksiyadır.
    openai_realtime_model: str = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime").strip()
    openai_realtime_voice: str = os.getenv("OPENAI_REALTIME_VOICE", "marin").strip()
    # Soz novbesinin tesbiti: semantic (tovsiye olunur, telefon xettinde daha dogru isleyir) | server
    voice_call_vad_mode: str = os.getenv("VOICE_CALL_VAD_MODE", "semantic").strip()
    voice_call_vad_eagerness: str = os.getenv("VOICE_CALL_VAD_EAGERNESS", "low").strip()
    # Twilio-nun <Stream>-inin qosulacagi wss:// unvani (ngrok domeni, protokolsuz).
    # QESDEN `public_base_url`-e geri dusmur: o defolt olaraq "127.0.0.1:8800"-dur ve
    # Twilio-nun bulud serverlerinden HEC ELCATAN DEYIL — sukutla oradan goturulseydi
    # duyme "aktivdir" gorunerdi, amma zeng qosulub AI-siz qalardi (yerli test tapintisi).
    voice_call_public_domain: str = os.getenv("VOICE_CALL_PUBLIC_DOMAIN", "").strip()
    # Zəng işarəsi HƏMİŞƏ bu nömrəyə zəng edir (təqdim edənin öz telefonu) — forma/nömrə
    # yazma yoxdur, düymə bu tək məqsəd üçündür.
    demo_call_phone_number: str = os.getenv("DEMO_CALL_PHONE_NUMBER", "").strip()


settings = Settings()


def contact_phone_href() -> str:
    """`tel:` linki üçün nömrəni normallaşdırır (boşluq/defis/mötərizə silinir)."""
    raw = settings.contact_phone
    if not raw:
        return ""
    return "tel:" + "".join(ch for ch in raw if ch.isdigit() or ch == "+")


def validate_production_settings() -> list[str]:
    """İstehsalda təhlükəli default-ları səssiz qəbul etmir."""
    if settings.environment != "production":
        return []
    errors = []
    if not settings.database_url.startswith("postgresql"):
        errors.append("DATABASE_URL PostgreSQL olmalıdır")
    if settings.worker_mode != "celery":
        errors.append("WORKER_MODE=celery olmalıdır")
    if not settings.agency_api_key or len(settings.agency_api_key) < 32:
        errors.append("AGENCY_API_KEY ən az 32 simvol olmalıdır")
    if not settings.public_base_url.startswith("https://"):
        errors.append("PUBLIC_BASE_URL HTTPS olmalıdır")
    return errors


# Uzaq şəkil yükləyərkən göndərilən kimlik. Wikimedia (upload.wikimedia.org) User-Agent
# olmayan sorğuları 403 ilə rədd edir — bu, onların açıq siyasətidir. `stock_photos` axtarış
# sorğusunda UA göndərirdi, amma tapılan şəkli YÜKLƏYƏN proksi göndərmirdi: nəticədə
# Wikimedia-dan seçilmiş hər şəkil əbədi 502 verirdi (canlı sınaqda təsdiqləndi).
HTTP_USER_AGENT = "TheAgency/1.0 (+https://the-agency.local; creative workspace)"
