"""Məqsəddən icraya gedən kampaniya generatoru — müddəti müştəri seçir.

NİYƏ FAZA ƏSASLI: plan təsadüfi postlar yığını deyil, inandırma qövsüdür — diqqət, dəyər,
etibar, təklif, yekun. Uzun kampaniya bu qövsü UZATMALIDIR, təkrarlamamalıdır: 7 günlük
şablonu dörd dəfə təkrarlasaq, müştəri dörd açılış və dörd bağlanış alır ki, bu da plan
yox, səhv kimi görünür. Ona görə günlər fazalar arasında NİSBƏTLƏ bölünür və sıra qorunur.

7 gün seçiləndə nəticə əvvəlki sabit planla eynidir — köhnə davranış ayrıca kod yolu deyil,
sadəcə bu modelin xüsusi halıdır.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.db_models import Campaign, CampaignDay, ContentAsset, Workspace

MIN_DURATION = 3    # bundan az gündə qövs (hook + dəyər + təklif) sığmır
MAX_DURATION = 90   # bir rübdən uzun plan real olaraq izlənmir
DEFAULT_DURATION = 7

# Hazır seçimlər — müştəri rəqəm yox, NİYYƏT seçir.
DURATION_PRESETS = [
    (7, "1 həftə", "Mesajı sınaqdan keçir"),
    (14, "2 həftə", "Sürət topla"),
    (30, "1 ay", "Tam launch"),
]

# (faza açarı, etiket, çəki) — çəkilər nisbəti müəyyən edir, cəmi 100 olmalıdır.
PHASES = [
    ("hook", "Diqqət", 15),
    ("value", "Dəyər", 30),
    ("trust", "Etibar", 25),
    ("offer", "Təklif", 20),
    ("close", "Yekun", 10),
]

# Hər faza üçün beat hovuzu: (format, bucaq, hook mətni, CTA).
# Gün sayı artdıqca hovuz dövr edir, amma eyni beat ardıcıl təkrarlanmır.
PHASE_BEATS = {
    "hook": [
        ("Reel", "Diqqət · əsas problem", "Bu nəticəyə çatmağınıza mane olan əsas səbəb nədir?", "Videonu sona qədər izləyin"),
        ("Story", "Diqqət · gündəlik reallıq", "Bu vəziyyət sizə də tanışdırmı?", "Cavabınızı yazın"),
        ("Post", "Diqqət · yanlış təsəvvür", "Ən çox təkrarlanan səhv fikri aydınlaşdıraq", "Fikrinizi bölüşün"),
    ],
    "value": [
        ("Carousel", "Dəyər · praktik bələdçi", "Bu məqsədə çatmaq üçün 3 konkret addım", "Yadda saxlayın və tətbiq edin"),
        ("Story", "Araşdırma · auditoriya səsi", "Sizin üçün ən çətin mərhələ hansıdır?", "Sorğuda cavab verin"),
        ("Reel", "Proses · pərdəarxası", "Nəticənin necə hazırlandığını 30 saniyədə görün", "Prosesi izləyin"),
        ("Post", "Dəyər · sadə izah", "Mürəkkəb görünən məsələni sadə dildə izah edirik", "Sualınızı yazın"),
    ],
    "trust": [
        ("Carousel", "Etibar · sübut və etiraz", "Ən çox verilən 3 sualın dürüst cavabı", "Sualınızı şərhdə yazın"),
        ("Post", "Etibar · real nəticə", "Əvvəl və sonra: konkret rəqəmlərlə", "Nəticəyə baxın"),
        ("Reel", "Etibar · müştəri təcrübəsi", "Bu işi bizimlə görənlər nə deyir?", "Rəyləri oxuyun"),
        ("Story", "Etibar · şəffaflıq", "Necə işlədiyimizi açıq göstəririk", "Suallarınızı verin"),
    ],
    "offer": [
        ("Post", "Təklif · aydın növbəti addım", "Sizin üçün uyğun həll necə görünür?", "Ətraflı məlumat üçün müraciət edin"),
        ("Carousel", "Təklif · paket müqayisəsi", "Hansı variant sizin ölçünüzə uyğundur?", "Uyğun olanı seçin"),
        ("Reel", "Təklif · başlamaq nə qədər asandır", "İlk addım cəmi bir mesajdır", "Bizə yazın"),
    ],
    "close": [
        ("Story", "Yekun · nəticə və dialoq", "Bu dövrdən hansı fikir sizin üçün faydalı oldu?", "Cavabınızı paylaşın"),
        ("Post", "Yekun · xülasə", "Bu müddətdə danışdığımız hər şey bir yerdə", "Saxlayın və paylaşın"),
    ],
}


# Platformanın QƏBUL ETDİYİ formatlar. Əvvəl format faza hovuzundan, platforma isə növbə
# ilə seçilirdi və ikisi HEÇ VAXT qarşılaşdırılmırdı — nəticədə TikTok gününə "Carousel"
# düşə bilirdi. Bu, TikTok-a xas deyil: LinkedIn-də "Story", YouTube-da "Post" da eyni
# şəkildə yanlış çıxırdı.
PLATFORM_FORMATS = {
    "instagram": ["Reel", "Story", "Post", "Carousel"],
    "tiktok": ["Reel"],                       # yalnız qısa video
    "youtube": ["Reel"],                      # Shorts
    "youtube shorts": ["Reel"],
    "facebook": ["Post", "Reel", "Story"],
    "linkedin": ["Post", "Carousel"],         # Story yoxdur
    "twitter": ["Post"],
    "x": ["Post"],
    "telegram": ["Post"],
    "pinterest": ["Post", "Carousel"],
}
DEFAULT_FORMATS = ["Post", "Reel"]
# Uyğunsuzluqda hansı formata keçmək: video-first platformada Carousel → Reel,
# Story dəstəkləməyəndə Story → Post.
_FALLBACK_ORDER = ["Reel", "Post", "Carousel", "Story"]


def formats_for(platform: str) -> list[str]:
    return PLATFORM_FORMATS.get((platform or "").strip().lower(), DEFAULT_FORMATS)


def fit_format(content_type: str, platform: str) -> str:
    """Faza beat-inin formatı platformaya uymursa, ən yaxın icazəli formata çevirir."""
    allowed = formats_for(platform)
    if content_type in allowed:
        return content_type
    for fallback in _FALLBACK_ORDER:
        if fallback in allowed:
            return fallback
    return allowed[0]


def assign_platform(content_type: str, channels: list[str], load: dict[str, int]) -> tuple[str, str]:
    """Kanalı və formatı birlikdə seçir. `load` yerində dəyişdirilir.

    NİYƏ NÖVBƏ İLƏ DEYİL: sadə növbə (gün nömrəsi % kanal sayı) kanal ACLIĞINA səbəb olur.
    Instagram bütün formatları qəbul etdiyi üçün növbədə ona düşən gün həmişə onda qalır,
    TikTok-a düşən Story/Carousel günü isə yenə Instagram-a keçir. Canlı ölçmə:
    Instagram+TikTok, 14 gün → TikTok 0 gün; 30 gün → TikTok cəmi 2 gün.

    Ona görə hər gün üçün formatı dəstəkləyən kanallardan ƏN AZ YÜKLƏNMİŞİ seçilir.
    Beləliklə TikTok bütün video günlərini alır və seçilmiş kanal boş qalmır.
    Heç bir kanal formatı dəstəkləmirsə, format ən az yüklənmiş kanala uyğunlaşdırılır.
    """
    if not channels:
        return "Instagram", content_type
    supporting = [c for c in channels if content_type in formats_for(c)]
    pool = supporting or channels
    # Bərabər yükdə sıra qorunur ki, nəticə determinist olsun.
    platform = min(pool, key=lambda c: (load.get(c, 0), channels.index(c)))
    load[platform] = load.get(platform, 0) + 1
    return platform, (content_type if supporting else fit_format(content_type, platform))


def normalize_duration(value) -> int:
    """İstifadəçidən gələn müddəti icazəli aralığa salır. Yanlış giriş defolta düşür."""
    try:
        days = int(str(value).strip())
    except (TypeError, ValueError):
        return DEFAULT_DURATION
    return max(MIN_DURATION, min(days, MAX_DURATION))


def phase_distribution(duration: int) -> list[tuple[str, str, int]]:
    """Günləri fazalar arasında nisbətlə bölür.

    Hər fazaya ƏN AZI bir gün düşür (qövsün heç bir hissəsi tamamilə itməsin), qalan günlər
    çəkiyə görə paylanır. Yuvarlaqlaşdırmadan yaranan fərq ən böyük çəkili fazaya verilir ki,
    cəm həmişə dəqiq `duration` olsun.
    """
    duration = normalize_duration(duration)
    counts = {key: 1 for key, _, _ in PHASES}
    remaining = duration - len(PHASES)

    if remaining > 0:
        total_weight = sum(weight for _, _, weight in PHASES)
        allocated = 0
        for key, _, weight in PHASES:
            share = remaining * weight // total_weight
            counts[key] += share
            allocated += share
        # Yuvarlaqlaşdırma qalığı — ən ağır fazaya (Dəyər) əlavə olunur.
        leftover = remaining - allocated
        if leftover:
            heaviest = max(PHASES, key=lambda item: item[2])[0]
            counts[heaviest] += leftover
    elif remaining < 0:
        # duration < faza sayı: qövsün sonundan başlayaraq fazaları çıxarırıq,
        # çünki hook və dəyər olmadan plan mənasızdır.
        for key, _, _ in reversed(PHASES):
            if remaining == 0:
                break
            counts[key] -= 1
            remaining += 1
    return [(key, label, counts[key]) for key, label, _ in PHASES if counts[key] > 0]


def build_day_plan(duration: int) -> list[tuple[str, str, str, str]]:
    """Müddətə uyğun gün-gün beat siyahısı qaytarır (format, bucaq, hook, CTA)."""
    plan = []
    for key, _, count in phase_distribution(duration):
        pool = PHASE_BEATS[key]
        for index in range(count):
            plan.append(pool[index % len(pool)])
    return plan


def create_campaign(
    db: Session,
    workspace: Workspace,
    name: str,
    objective: str,
    audience: str,
    channels: str,
    budget: str,
    start_date: date | None = None,
    duration_days: int = DEFAULT_DURATION,
) -> Campaign:
    duration = normalize_duration(duration_days)
    selected_channels = [item.strip() for item in channels.split(",") if item.strip()] or ["Instagram"]
    begins = start_date or date.today()
    campaign = Campaign(
        workspace_id=workspace.id,
        name=name.strip(), objective=objective.strip(), audience=audience.strip() or workspace.brand_audience,
        channels=", ".join(selected_channels), monthly_budget=budget.strip() or None,
        status="PLANNED", start_date=begins,
    )
    db.add(campaign)
    db.flush()
    # SC-1: BU SAHƏLƏR MƏTNDİR, METADATA DEYİL. Əvvəl bura kampaniyanın məqsədi,
    # auditoriyası və brend məhsulu etiketlə yapışdırılırdı ("... Məqsəd: ...",
    # "... · Auditoriya: ..."), sonra körpü onu birbaşa caption-a köçürürdü — müştəri
    # caption yerində baza sahələri görürdü. Həmin kontekst onsuz da `campaign.objective`
    # və `campaign.audience` sahələrindədir; günə təkrar yapışdırmağa ehtiyac yoxdur.
    load: dict[str, int] = {}
    for day_number, (content_type, angle, hook, cta) in enumerate(build_day_plan(duration), start=1):
        platform, content_type = assign_platform(content_type, selected_channels, load)
        db.add(CampaignDay(
            campaign_id=campaign.id, day_number=day_number, platform=platform,
            content_type=content_type, theme=angle, hook=hook, cta=cta,
            planned_date=begins + timedelta(days=day_number - 1),
        ))
    db.commit()
    db.refresh(campaign)
    return campaign


def resize_campaign(db: Session, campaign: Campaign, duration_days: int) -> dict:
    """Mövcud kampaniyanın müddətini dəyişir.

    QAYDALAR (bax spesifikasiya CD-3):
      * Uzatma — yeni günlər sonuna əlavə olunur, mövcud günlərə TOXUNULMUR.
      * Qısaltma — artıq günlər silinir, amma onlara bağlı hazır MATERİAL SİLİNMİR;
        yalnız əlaqəsi kəsilir və material Studio arxivində qalır.
    Nə baş verdiyini çağıran tərəfə dict kimi qaytarır ki, istifadəçiyə dəqiq say göstərilsin.
    """
    target = normalize_duration(duration_days)
    days = sorted(campaign.days, key=lambda d: d.day_number)
    current = len(days)
    begins = campaign.start_date or date.today()

    if target == current:
        return {"added": 0, "removed": 0, "detached": 0, "duration": current}

    if target > current:
        plan = build_day_plan(target)
        channels = [c.strip() for c in (campaign.channels or "Instagram").split(",") if c.strip()] or ["Instagram"]
        # Mövcud günlərin yükü nəzərə alınır — əks halda uzatma paylanmanı pozar.
        load: dict[str, int] = {}
        for day in days:
            load[day.platform] = load.get(day.platform, 0) + 1
        for day_number in range(current + 1, target + 1):
            content_type, angle, hook, cta = plan[day_number - 1]
            platform, content_type = assign_platform(content_type, channels, load)
            db.add(CampaignDay(
                campaign_id=campaign.id, day_number=day_number, platform=platform,
                content_type=content_type, theme=angle, hook=hook, cta=cta,
                planned_date=begins + timedelta(days=day_number - 1),
            ))
        db.commit(); db.refresh(campaign)
        return {"added": target - current, "removed": 0, "detached": 0, "duration": target}

    doomed = [d for d in days if d.day_number > target]
    detached = 0
    for day in doomed:
        detached += db.query(ContentAsset).filter(ContentAsset.campaign_day_id == day.id).update(
            {ContentAsset.campaign_day_id: None}, synchronize_session=False
        )
        db.delete(day)
    db.commit(); db.refresh(campaign)
    return {"added": 0, "removed": len(doomed), "detached": detached, "duration": target}


def resize_impact(db: Session, campaign: Campaign, duration_days: int) -> dict:
    """Qısaltmadan ƏVVƏL nə itəcəyini hesablayır — təsdiq dialoqu üçün, heç nə dəyişmir."""
    target = normalize_duration(duration_days)
    doomed = [d for d in campaign.days if d.day_number > target]
    with_material = 0
    if doomed:
        with_material = db.query(ContentAsset).filter(
            ContentAsset.campaign_day_id.in_([d.id for d in doomed])
        ).count()
    return {"target": target, "removed": len(doomed), "with_material": with_material}
