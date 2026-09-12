"""Təqvim → Studiya uyğunsuzluğunun qoruyucuları (spesifikasiya §4, RC-1…RC-4).

TARİXÇƏ: təqvimdə bir kampaniya göstərilirdi, materiala keçəndə tamam başqası açılırdı və
heç bir xəbərdarlıq olmurdu. Səbəb bir deyil, dörd idi: adlarda kampaniya kimliyi yox idi,
yan siyahı yalnız adı göstərirdi, tapılmayan id səssizcə ƏN SON materialla əvəz olunurdu,
yetim materiallar isə mənbəsini tamamilə itirirdi.
"""
from app.campaigns import create_campaign
from app.db_models import Campaign, ContentAsset, Workspace


def _make_campaign(client, db, name, duration="7"):
    client.post("/campaigns", data={
        "name": name, "objective": "demo müraciətlərini artırmaq",
        "audience": "hamı", "channels": "Instagram", "monthly_budget": "0",
        "duration": duration,
    }, follow_redirects=True)
    return db.query(Campaign).filter(Campaign.name == name).first()


def _first_day(campaign):
    return min(campaign.days, key=lambda d: d.day_number)


# ── RC-3: səssiz əvəzləmə ────────────────────────────────────────────────────────

def test_unknown_asset_id_never_shows_a_different_asset(registered_client, db):
    """ƏSAS QORUYUCU: mövcud olmayan id sorğulananda başqa material AÇILMAMALIDIR."""
    client = registered_client("studio1@test.az", "Studio Test")
    campaign = _make_campaign(client, db, "Mövcud kampaniya")
    client.post(f"/campaigns/day/{_first_day(campaign).id}/to-asset", follow_redirects=True)
    real = db.query(ContentAsset).first()
    assert real is not None

    page = client.get("/content-studio?id=999999")
    assert page.status_code == 200
    assert "tapılmadı" in page.text
    # Yan siyahı bütün materialları sadalayır (naviqasiyadır) — ona görə adın orada olması
    # normaldır. Vacib olan: DETAL sahəsində heç bir material AÇILMAMALIDIR.
    assert 'class="visual-area"' not in page.text, "tapılmayan id başqa materialı açdı!"
    assert real.headline not in page.text or not real.headline


def test_asset_from_another_workspace_is_refused_not_substituted(registered_client, db):
    owner = registered_client("studio2@test.az", "Owner WS")
    campaign = _make_campaign(owner, db, "Sahibin kampaniyası")
    owner.post(f"/campaigns/day/{_first_day(campaign).id}/to-asset", follow_redirects=True)
    foreign = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()

    other = registered_client("studio3@test.az", "Other WS")
    page = other.get(f"/content-studio?id={foreign.id}")
    assert page.status_code == 200
    assert "tapılmadı" in page.text
    assert foreign.title not in page.text, "başqa workspace-in materialı sızdı!"


def test_no_id_still_opens_the_newest_asset(registered_client, db):
    """id verilmədikdə ən sonuncunu açmaq düzgündür — bu, əvəzləmə deyil."""
    client = registered_client("studio4@test.az", "Studio Test 4")
    campaign = _make_campaign(client, db, "Adi kampaniya")
    client.post(f"/campaigns/day/{_first_day(campaign).id}/to-asset", follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()

    page = client.get("/content-studio")
    assert page.status_code == 200
    assert "tapılmadı" not in page.text
    assert asset.title in page.text


# ── RC-1 / RC-2: kimlik ──────────────────────────────────────────────────────────

def test_two_campaigns_never_produce_identical_titles(registered_client, db):
    """Əvvəl hər kampaniyanın 1-ci günü eyni "Gün 1 · Reel" adını alırdı."""
    client = registered_client("studio5@test.az", "Studio Test 5")
    first = _make_campaign(client, db, "Yaz kampaniyası")
    second = _make_campaign(client, db, "Payız kampaniyası")

    for campaign in (first, second):
        client.post(f"/campaigns/day/{_first_day(campaign).id}/to-asset", follow_redirects=True)

    titles = [a.title for a in db.query(ContentAsset).all()]
    assert len(titles) == len(set(titles)), f"eyni adlı material yarandı: {titles}"
    assert any("Yaz kampaniyası" in t for t in titles)
    assert any("Payız kampaniyası" in t for t in titles)


def test_sidebar_shows_campaign_and_day_for_each_asset(registered_client, db):
    client = registered_client("studio6@test.az", "Studio Test 6")
    campaign = _make_campaign(client, db, "Kontekst testi")
    client.post(f"/campaigns/day/{_first_day(campaign).id}/to-asset", follow_redirects=True)

    page = client.get("/content-studio")
    assert "Kontekst testi" in page.text
    assert "Gün 1" in page.text


# ── RC-4: yetim materialın mənbəyi ───────────────────────────────────────────────

def test_orphaned_asset_states_its_broken_source(registered_client, db):
    """Plan günü silinəndə material qalır; mənbə bloku gizlənməməli, izah etməlidir."""
    client = registered_client("studio7@test.az", "Studio Test 7")
    workspace = db.query(Workspace).filter(Workspace.name == "Studio Test 7").first()
    campaign = create_campaign(db, workspace, "Qısalacaq", "məqsəd mətni burada",
                               "hamı", "Instagram", "0", duration_days=20)
    last = max(campaign.days, key=lambda d: d.day_number)
    client.post(f"/campaigns/day/{last.id}/to-asset", follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()

    client.post(f"/campaigns/{campaign.id}/duration",
                data={"duration": "7", "confirm": "1"}, follow_redirects=True)
    db.refresh(asset)
    assert asset.campaign_day_id is None

    page = client.get(f"/content-studio?id={asset.id}")
    assert page.status_code == 200
    assert "plan günü silinib" in page.text.lower()


# ── Körpü davranışı ──────────────────────────────────────────────────────────────

def test_converting_twice_opens_the_same_asset(registered_client, db):
    client = registered_client("studio8@test.az", "Studio Test 8")
    campaign = _make_campaign(client, db, "İdempotent test")
    day = _first_day(campaign)

    client.post(f"/campaigns/day/{day.id}/to-asset", follow_redirects=True)
    client.post(f"/campaigns/day/{day.id}/to-asset", follow_redirects=True)

    count = db.query(ContentAsset).filter(ContentAsset.campaign_day_id == day.id).count()
    assert count == 1, "təkrar basılanda dublikat yarandı"
