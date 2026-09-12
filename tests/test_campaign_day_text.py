"""F1 qoruyucuları (audit SC-1).

TARİXÇƏ: plan gününün mətn sahələrinə kampaniyanın məqsədi, auditoriyası və brend məhsulu
etiketlə yapışdırılırdı. Körpü sonra həmin sahələri birbaşa caption-a köçürürdü, ona görə
müştəri caption yerində "Dəyər · praktik bələdçi · kətan çantalar / ... · Auditoriya: 25-40 yaş"
kimi baza sahələri görürdü. Bu, mətn deyil — metadata idi.
"""
import re

from app.campaigns import create_campaign, resize_campaign
from app.db_models import Campaign, ContentAsset, Workspace

LEAK = re.compile(r"(Məqsəd:|Auditoriya:)")


def _workspace(db, slug="meta-ws"):
    workspace = Workspace(
        name="Kətan Studio", slug=slug,
        brand_products="kətan çantalar, əl işi tikiş",
        brand_audience="25-40 yaş qadınlar",
    )
    db.add(workspace)
    db.commit()
    return workspace


def _campaign(db, workspace, duration=7):
    return create_campaign(
        db, workspace, "Payız launch", "demo müraciətlərini artırmaq",
        "25-40 yaş qadınlar", "Instagram", "300 AZN", duration_days=duration,
    )


# ── Plan günləri təmizdir ────────────────────────────────────────────────────────

def test_day_fields_carry_no_field_labels(db):
    for day in _campaign(db, _workspace(db)).days:
        for field in (day.theme, day.hook, day.cta):
            assert not LEAK.search(field or ""), f"sahə etiketi sızıb: {field!r}"


def test_brand_product_is_not_pasted_into_the_theme(db):
    """`brand_products` xam CRM sahəsidir — istehsal etiketinin içində yeri yoxdur."""
    for day in _campaign(db, _workspace(db)).days:
        assert "kətan çantalar" not in (day.theme or "")
        # Faza bucağı iki hissəlidir: "Dəyər · praktik bələdçi".
        assert (day.theme or "").count("·") <= 1


def test_context_is_still_reachable_from_the_campaign(db):
    """Kontekst itmir — sadəcə düzgün yerdə saxlanılır."""
    campaign = _campaign(db, _workspace(db))
    assert campaign.objective == "demo müraciətlərini artırmaq"
    assert campaign.audience == "25-40 yaş qadınlar"


def test_created_and_resized_days_have_the_same_shape(db):
    """Əvvəl yaratma yapışdırırdı, uzatma isə yapışdırmırdı — iki fərqli format yaranırdı."""
    workspace = _workspace(db)
    campaign = _campaign(db, workspace, 7)
    resize_campaign(db, campaign, 14)
    days = sorted(campaign.days, key=lambda d: d.day_number)
    assert len(days) == 14
    for day in days:
        assert not LEAK.search(day.hook or "")
        assert (day.theme or "").count("·") <= 1


# ── Körpü caption-a metadata köçürmür ────────────────────────────────────────────

def test_bridge_caption_is_copy_not_metadata(registered_client, db):
    client = registered_client("meta1@test.az", "Meta Test")
    client.post("/campaigns", data={
        "name": "Körpü testi", "objective": "demo müraciətlərini artırmaq",
        "audience": "25-40 yaş qadınlar", "channels": "Instagram",
        "monthly_budget": "0", "duration": "7",
    }, follow_redirects=True)
    campaign = db.query(Campaign).filter(Campaign.name == "Körpü testi").first()
    day = min(campaign.days, key=lambda d: d.day_number)

    client.post(f"/campaigns/day/{day.id}/to-asset", follow_redirects=True)
    asset = db.query(ContentAsset).filter(ContentAsset.campaign_day_id == day.id).first()

    assert asset is not None
    assert not LEAK.search(asset.caption or ""), f"caption-a metadata düşüb: {asset.caption!r}"
    assert not LEAK.search(asset.headline or "")
    # İstehsal etiketi tamamilə itmir — yeri vizual brifdir, orada nişanlanır.
    assert asset.visual_brief and "Instagram" in asset.visual_brief


def test_bridge_caption_matches_the_days_cta(registered_client, db):
    client = registered_client("meta2@test.az", "Meta Test 2")
    client.post("/campaigns", data={
        "name": "CTA testi", "objective": "sifariş artırmaq", "audience": "hamı",
        "channels": "Instagram", "monthly_budget": "0", "duration": "7",
    }, follow_redirects=True)
    campaign = db.query(Campaign).filter(Campaign.name == "CTA testi").first()
    day = min(campaign.days, key=lambda d: d.day_number)

    client.post(f"/campaigns/day/{day.id}/to-asset", follow_redirects=True)
    asset = db.query(ContentAsset).filter(ContentAsset.campaign_day_id == day.id).first()
    assert asset.caption == day.cta
    assert asset.headline == day.hook


# ── #4: platforma və format bir-birinə uyğun olmalıdır ───────────────────────────
#
# Əvvəl format faza hovuzundan, platforma isə növbə ilə seçilirdi və ikisi heç vaxt
# qarşılaşdırılmırdı — TikTok gününə "Carousel" düşə bilirdi.

from app.campaigns import assign_platform, fit_format, formats_for


def test_tiktok_only_ever_gets_short_video(db):
    workspace = _workspace(db, "tiktok-ws")
    campaign = create_campaign(
        db, workspace, "TikTok launch", "demo müraciətlərini artırmaq",
        "hamı", "TikTok", "0", duration_days=30,
    )
    formats = {day.content_type for day in campaign.days}
    assert formats == {"Reel"}, f"TikTok üçün uyğunsuz format: {formats}"


def test_every_day_matches_its_platform(db):
    workspace = _workspace(db, "multi-ws")
    campaign = create_campaign(
        db, workspace, "Çoxkanallı", "demo müraciətlərini artırmaq",
        "hamı", "Instagram, TikTok, LinkedIn", "0", duration_days=40,
    )
    for day in campaign.days:
        assert day.content_type in formats_for(day.platform), \
            f"{day.platform} üçün {day.content_type} uyğun deyil (gün {day.day_number})"


def test_linkedin_never_gets_a_story(db):
    workspace = _workspace(db, "li-ws")
    campaign = create_campaign(
        db, workspace, "LinkedIn plan", "demo müraciətlərini artırmaq",
        "hamı", "LinkedIn", "0", duration_days=25,
    )
    assert "Story" not in {day.content_type for day in campaign.days}


def test_extension_keeps_platform_rules(db):
    workspace = _workspace(db, "ext-ws")
    campaign = create_campaign(
        db, workspace, "Uzanan", "demo müraciətlərini artırmaq",
        "hamı", "TikTok", "0", duration_days=7,
    )
    resize_campaign(db, campaign, 30)
    assert {day.content_type for day in campaign.days} == {"Reel"}


def test_multi_channel_still_spreads_the_load(db):
    """Uyğunlaşdırma bir kanalı boş qoymamalıdır."""
    workspace = _workspace(db, "spread-ws")
    campaign = create_campaign(
        db, workspace, "Paylanma", "demo müraciətlərini artırmaq",
        "hamı", "Instagram, TikTok, LinkedIn", "0", duration_days=30,
    )
    used = {day.platform for day in campaign.days}
    assert used == {"Instagram", "TikTok", "LinkedIn"}, f"kanal boş qaldı: {used}"


def test_unknown_platform_falls_back_safely(db):
    assert fit_format("Carousel", "Naməlum Şəbəkə") in ("Post", "Reel")
    assert assign_platform("Story", ["TikTok"], {}) == ("TikTok", "Reel")


def test_no_selected_channel_is_ever_starved(db):
    """Canlı sınaqda tapıldı: sadə növbə ilə Instagram+TikTok, 14 gün → TikTok 0 gün aldı.

    Instagram bütün formatları qəbul etdiyi üçün növbəni udurdu. İstifadəçi kanalı seçib,
    amma planda ondan bir dənə də gün yoxdursa, bu, səssiz uğursuzluqdur.
    """
    from app.campaigns import build_day_plan

    for channels in (["Instagram", "TikTok"], ["Instagram", "TikTok", "LinkedIn"],
                     ["TikTok", "LinkedIn"]):
        for duration in (14, 30):
            load = {}
            used = {assign_platform(ct, channels, load)[0] for ct, *_ in build_day_plan(duration)}
            assert used == set(channels),                 f"{channels} · {duration} gün — istifadə olunmayan kanal: {set(channels) - used}"


def test_tiktok_gets_a_real_share_of_the_video_days(db):
    """TikTok yalnız Reel qəbul edir, ona görə video günlərinin ƏSAS HİSSƏSİ ona düşməlidir.

    "Hamısı" tələb etmək düzgün deyil: yük bərabərləşdikdə növbəti Reel Instagram-a keçir,
    bu isə balansın işlədiyini göstərir, qüsur deyil. Vacib olan iki şeydir — TikTok Reel
    günlərinin çoxunu alır və HEÇ VAXT video olmayan gün almır.
    """
    from app.campaigns import build_day_plan

    plan = build_day_plan(30)
    reels = sum(1 for ct, *_ in plan if ct == "Reel")
    load = {}
    assigned = [assign_platform(ct, ["Instagram", "TikTok"], load) for ct, *_ in plan]
    tiktok = [fmt for platform, fmt in assigned if platform == "TikTok"]
    assert set(tiktok) == {"Reel"}, f"TikTok video olmayan gün aldı: {set(tiktok)}"
    assert len(tiktok) >= reels - 1, f"TikTok {reels} Reel günündən yalnız {len(tiktok)} aldı"


def test_extension_does_not_break_the_balance(db):
    workspace = _workspace(db, "bal-ws")
    campaign = create_campaign(db, workspace, "Balans", "demo müraciətlərini artırmaq",
                               "hamı", "Instagram, TikTok", "0", duration_days=14)
    resize_campaign(db, campaign, 30)
    used = {d.platform for d in campaign.days}
    assert used == {"Instagram", "TikTok"}, f"uzatmadan sonra kanal itdi: {used}"
