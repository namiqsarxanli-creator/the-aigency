"""Post, Story və Carousel üçün strukturlaşdırılmış istehsal draftları.

F0 (audit SC-2): əvvəl `slides_json`-a kopiraytere ünvanlanmış TƏLİMAT yazılırdı
("Auditoriyanın əsas problemini göstərin") və o, məzmun kimi saxlanılırdı. Üstəlik şablon
`slides_json`-u ümumiyyətlə oxumurdu — carousel önizləməsi materialın adını üç dəfə təkrarlayırdı.

İndi qayda budur: MƏZMUN SAHƏSİNƏ YER TUTUCU YAZILMIR. Doldura bilmədiyimiz slayd boş qalır və
şablon onu açıq şəkildə "mətn yoxdur" kimi göstərir. Dürüst boşluq saxta məzmundan yaxşıdır.
"""
import json
import logging
import re

from sqlalchemy.orm import Session

from app.db_models import ContentAsset, Workspace

logger = logging.getLogger(__name__)

RATIOS = {"POST": "4:5", "STORY": "9:16", "CAROUSEL": "4:5", "REEL": "9:16"}

# Kampaniya generatoru (`campaigns.CONTENT_ROTATION`) bu adlarla gün tipi yazır — studiya
# formatına çevirmək üçün xəritə. Naməlum tip gəlsə POST-a düşür.
CAMPAIGN_TYPE_TO_FORMAT = {"REEL": "REEL", "STORY": "STORY", "CAROUSEL": "CAROUSEL", "POST": "POST"}

# Carousel skeleti — hər slaydın ROLU var, mətni isə yalnız həqiqətən varsa doldurulur.
SLIDE_ROLES = [
    ("hook", "Açılış"),
    ("problem", "Problem"),
    ("insight", "Əsas fikir"),
    ("solution", "Həll"),
    ("cta", "Çağırış"),
]
ROLE_LABELS = dict(SLIDE_ROLES)

# Köhnə materiallarda saxlanılmış təlimat mətnini məzmun kimi göstərməmək üçün.
# DİQQƏT — «yazın» və «seçin» BURADA YOXDUR. Onlar Azərbaycan dilində ən adi
# çağırışlardır («Şərhdə yazın», «Uyğun olanı seçin») və siyahıya salınanda hər
# düzgün CTA yer tutucu kimi rədd olunurdu. Yalnız MƏZMUN SLOTUNA ünvanlanmış
# təlimat feilləri qalır.
_INSTRUCTION_RE = re.compile(
    r"(göstərin|izah edin|təqdim edin|əlavə edin|buraya yazın)\s*[.!…]?$", re.IGNORECASE
)

# Köhnə skeletdə bir yer tutucu təlimat şəklində deyil, sadəcə kateqoriya adı idi — nümunə
# üzrə tutulmur, ona görə hərfi siyahı lazımdır.
_LEGACY_PLACEHOLDERS = {
    "növbəti addıma çağırış",
    "auditoriyanın əsas problemini göstərin",
    "əsas faydalı fikri izah edin",
}


def format_for_campaign_type(content_type: str) -> str:
    return CAMPAIGN_TYPE_TO_FORMAT.get((content_type or "").strip().upper(), "POST")


def _clean(value) -> str | None:
    """Yer tutucu təlimatı məzmun saymır — belə mətn boşluq kimi qaytarılır."""
    text = (value or "").strip()
    if not text or _INSTRUCTION_RE.search(text) or text.lower() in _LEGACY_PLACEHOLDERS:
        return None
    return text


def build_slides(headline: str | None) -> str:
    """Carousel skeleti. YALNIZ bildiyimizi yazırıq — qalan slaydlar boş qalır."""
    opening = _clean(headline)
    return json.dumps(
        [
            {"role": role, "headline": opening if role == "hook" else None, "body": None}
            for role, _ in SLIDE_ROLES
        ],
        ensure_ascii=False,
    )


def parse_slides(asset: ContentAsset | None) -> list[dict]:
    """`slides_json`-u şablonun oxuya biləcəyi formaya salır.

    İki sxemi də başa düşür: köhnə {"slide", "role", "text"} və yeni
    {"role", "headline", "body"}. Köhnə yer tutucu təlimatlar süzülür (SC-2).
    """
    if asset is None or (asset.format or "").upper() != "CAROUSEL":
        return []
    try:
        raw = json.loads(asset.slides_json or "[]")
    except (json.JSONDecodeError, TypeError):
        raw = []
    if not isinstance(raw, list) or not raw:
        raw = json.loads(build_slides(asset.headline or asset.title))

    slides = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        role = (item.get("role") or "").strip().lower()
        headline = _clean(item.get("headline") or item.get("text"))
        body = _clean(item.get("body"))
        slides.append({
            "number": index,
            "role": role,
            "label": ROLE_LABELS.get(role, role.title() or "Slayd"),
            "headline": headline,
            "body": body,
            "empty": not (headline or body),
        })
    return slides


def create_asset(
    db: Session, workspace: Workspace, title: str, content_format: str,
    headline: str, caption: str, visual_brief: str, campaign_day_id: int | None = None,
) -> ContentAsset:
    content_format = content_format.upper()
    if content_format not in RATIOS:
        raise ValueError("Dəstəklənməyən format")
    slides = build_slides(headline or title) if content_format == "CAROUSEL" else None
    asset = ContentAsset(
        workspace_id=workspace.id, title=title.strip(), format=content_format,
        aspect_ratio=RATIOS[content_format], headline=headline.strip(), caption=caption.strip(),
        visual_brief=visual_brief.strip(), slides_json=slides, status="DRAFT",
        campaign_day_id=campaign_day_id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


# ---------------------------------------------------------------------------
# Generasiya nəticəsinin saxlanması (audit F3/F5)
# ---------------------------------------------------------------------------

def archive_version(db: Session, asset: ContentAsset, reason: str) -> None:
    """Yenidən yazmadan ƏVVƏLKİ nüsxəni saxlayır ki, heç nə itməsin."""
    from app.db_models import ContentAssetVersion

    if not (asset.headline or asset.caption or asset.slides_json):
        return
    db.add(ContentAssetVersion(
        asset_id=asset.id, headline=asset.headline, caption=asset.caption,
        visual_brief=asset.visual_brief, slides_json=asset.slides_json, reason=reason[:120],
    ))


def _attach_image(db: Session, asset: ContentAsset, direction: dict) -> None:
    """Vizual istiqamətdən şəkil seçir (audit #7).

    Yeni provayder (DALL·E/Midjourney) LAZIM DEYİL — zəncir artıq `agency.py`-də var, sadəcə
    Studio+ onu heç vaxt çağırmırdı. Əvvəl real foto axtarılır, tapılmasa generasiya edilir.

    Yalnız ÜNVAN saxlanılır: şəkil yükləməsi generasiya sorğusunu bloklamamalıdır. Baytlar
    tələb anında mövcud proksi (`api._image_bytes`) ilə gəlir. Şəkil tapılmasa material
    yenə də etibarlıdır — vizual brif qalır, sadəcə şəkil olmur.
    """
    from app import openai_images, sora, stock_photos, veo
    from app.agency import _pollinations_url

    # MODUL üzərindən çağırılır, adı dəyərlə import edilmir: `from ... import name`
    # bağlamanı dondurur və testdəki patch işləmir — bu tələ bu kod bazasında artıq
    # iki dəfə həqiqi şəbəkə sorğusuna səbəb olub.

    # Palitra brifdən götürülür (Brand Kit dəyəri), modelin öz təsvirindən yox — şəkil
    # generatoruna DƏQİQ HEX vermək lazımdır.
    from app.studio_ai import StudioBrief

    brief = StudioBrief.from_json(asset.brief_json)
    palette = (brief.palette if brief else "") or ""

    terms = " ".join(
        str(direction.get(key)).strip()
        for key in ("subject", "composition", "palette")
        if isinstance(direction.get(key), str) and direction.get(key).strip()
    )[:300]
    if not terms:
        return

    # Video ƏVVƏLCƏ başladılır: uzunmüddətli əməliyyatdır və şəkil uğurlu olanda funksiya
    # erkən `return` edir — aşağıda qalsaydı Reel-lər heç vaxt video almazdı.
    # Ödənişlidir, ona görə `VEO_ENABLED` olmadan heç nə etmir.
    if (asset.format or "").upper() in veo.VERTICAL_FORMATS and veo.allowed(db):
        try:
            operation = veo.start(direction, palette)
            if operation:
                asset.video_operation = operation[:300]
                # Sorğu GETDİ — cəhd də pula yazılır, ona görə sayğac artır.
                veo.record(db, asset.workspace_id, asset.id)
        except Exception:  # noqa: BLE001 — video materialı bloklamamalıdır
            logger.warning("Veo başladıla bilmədi", exc_info=True)
    elif (asset.format or "").upper() in veo.VERTICAL_FORMATS and veo.enabled():
        logger.info("Veo günlük limiti dolub — video başladılmadı (material %s)", asset.id)
    elif (asset.format or "").upper() in veo.VERTICAL_FORMATS and sora.configured():
        # Veo AÇIQ DEYİL (billing/limit) — Sora eyni OpenAI açarı ilə işləyir və ehtiyat
        # kimi işə düşür. SİNXRONDUR (bir neçə dəqiqə çəkə bilər) — Veo-nun start/collect
        # ayrılığı yoxdur, çünki bu funksiya artıq sinxron çağırılır (bax `apply_result`).
        try:
            video_url = sora.generate(direction, palette)
            if video_url:
                asset.video_url = video_url[:1000]
        except Exception:  # noqa: BLE001 — video materialı bloklamamalıdır
            logger.warning("Sora video generasiyası uğursuz oldu", exc_info=True)

    # 1) OpenAI (gpt-image-1) — brend palitrasını prompta yaza bildiyimiz yeganə addım, ona
    # görə birinci. Ödənişlidir, amma ən sadiq nəticəni verir.
    try:
        url = openai_images.generate(direction, palette)
    except Exception:  # noqa: BLE001 — şəkil materialı bloklamamalıdır
        logger.warning("OpenAI şəkil çağırışı çökdü", exc_info=True)
        url = None
    if url:
        asset.image_url, asset.image_source = url[:1000], "openai"
        return


    # 2) Real stok foto, 3) Pollinations — köhnə ehtiyat zənciri olduğu kimi qalır.
    try:
        photo = stock_photos.find_stock_photo(terms, include_commons=False)
    except Exception:  # noqa: BLE001
        logger.warning("Stok foto axtarışı uğursuz oldu, generasiyaya keçilir", exc_info=True)
        photo = None
    if photo:
        asset.image_url, asset.image_source = photo.url[:1000], (photo.source or "stock")[:60]
    else:
        asset.image_url, asset.image_source = _pollinations_url(terms)[:1000], "generated"


def apply_result(db: Session, asset: ContentAsset, result: dict) -> ContentAsset:
    """Generasiya nəticəsini materiala yazır.

    `ok=False` olduqda MƏZMUN SAHƏLƏRİ BOŞ QALIR və status `NEEDS_INPUT` olur — uydurma
    mətn yazılmır (audit §05).
    """
    from app.studio_ai import visual_direction_text

    asset.needs_input = json.dumps(result.get("needs_input") or [], ensure_ascii=False)
    asset.confidence = (result.get("confidence") or "low")[:10]

    if not result.get("ok"):
        asset.status = "NEEDS_INPUT"
        db.commit()
        db.refresh(asset)
        return asset

    options = result.get("headline_options") or []
    asset.headline_options = json.dumps(options, ensure_ascii=False)
    if options:
        asset.headline = options[0][:240]
    asset.caption = (result.get("caption") or "")[:4000]
    asset.hashtags = json.dumps(result.get("hashtags") or [], ensure_ascii=False)
    direction = result.get("visual_direction") or {}
    brief_text = visual_direction_text(direction)
    if brief_text:
        asset.visual_brief = brief_text[:2000]
    _attach_image(db, asset, direction)
    slides = result.get("slides") or []
    if slides and (asset.format or "").upper() == "CAROUSEL":
        asset.slides_json = json.dumps(
            [
                {"role": (s.get("role") or "").strip().lower(),
                 "headline": _clean(s.get("headline")),
                 "body": _clean(s.get("body"))}
                for s in slides
            ],
            ensure_ascii=False,
        )
    asset.status = "DRAFT"
    db.commit()
    db.refresh(asset)
    return asset


def json_list(raw: str | None) -> list:
    try:
        value = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return value if isinstance(value, list) else []
