from app.campaigns import (
    DEFAULT_DURATION, MAX_DURATION, MIN_DURATION, build_day_plan, create_campaign,
    normalize_duration, phase_distribution, resize_campaign, resize_impact,
)
from app.db_models import ContentAsset, Workspace


def _workspace(db, slug="test-agency"):
    workspace = Workspace(
        name="Test Agency", slug=slug, brand_description="AI marketinq studiyası",
        brand_audience="kiçik biznes sahibləri",
    )
    db.add(workspace)
    db.commit()
    return workspace


def _campaign(db, workspace, duration=DEFAULT_DURATION, name="Pilot"):
    return create_campaign(
        db, workspace, name, "demo müraciətlərini artırmaq",
        "marketinq rəhbərləri", "Instagram", "300 AZN", duration_days=duration,
    )


# ── Müddət modeli ────────────────────────────────────────────────────────────────

def test_seven_days_remains_the_default_shape(db):
    """Köhnə davranış qorunmalıdır: 7 gün seçiləndə plan əvvəlki kimi olur."""
    campaign = _campaign(db, _workspace(db))
    assert len(campaign.days) == 7
    assert [day.day_number for day in campaign.days] == list(range(1, 8))
    # SC-1-dən sonra məqsəd ARTIQ hook-a yapışdırılmır — o, `campaign.objective`-dədir.
    assert campaign.objective == "demo müraciətlərini artırmaq"
    assert all("Məqsəd:" not in day.hook for day in campaign.days)


def test_duration_is_honoured_exactly(db):
    workspace = _workspace(db)
    for duration in (3, 14, 30, 45):
        campaign = _campaign(db, workspace, duration, name=f"K{duration}")
        assert len(campaign.days) == duration
        assert [d.day_number for d in campaign.days] == list(range(1, duration + 1))


def test_duration_is_clamped_to_allowed_range(db):
    assert normalize_duration(1) == MIN_DURATION
    assert normalize_duration(500) == MAX_DURATION
    assert normalize_duration("abc") == DEFAULT_DURATION
    assert normalize_duration(None) == DEFAULT_DURATION
    assert normalize_duration("21") == 21


def test_phase_split_always_sums_to_duration(db):
    """Yuvarlaqlaşdırma səhvi olsa plan gün sayı istənilənlə uyğun gəlməzdi."""
    for duration in range(MIN_DURATION, 61):
        total = sum(count for _, _, count in phase_distribution(duration))
        assert total == duration, f"{duration} gün üçün cəm {total}"


def test_arc_order_is_preserved_not_repeated(db):
    """Uzun kampaniya qövsü UZATMALIDIR, təkrarlamamalı — yəni bir açılış, bir bağlanış."""
    plan = build_day_plan(30)
    angles = [angle for _, angle, _, _ in plan]
    assert angles[0].startswith("Diqqət"), "plan diqqət fazası ilə başlamalıdır"
    assert angles[-1].startswith("Yekun"), "plan yekun fazası ilə bitməlidir"
    # Yekun yalnız sonda olmalıdır; ortada görünsə qövs təkrarlanıb deməkdir.
    assert not any(a.startswith("Yekun") for a in angles[:-3])


def test_no_two_consecutive_days_share_a_beat(db):
    for duration in (14, 30, 60):
        angles = [angle for _, angle, _, _ in build_day_plan(duration)]
        repeats = [i for i in range(1, len(angles)) if angles[i] == angles[i - 1]]
        assert not repeats, f"{duration} gündə ardıcıl təkrar: {repeats}"


def test_planned_dates_follow_start_date(db):
    campaign = _campaign(db, _workspace(db), 10)
    days = sorted(campaign.days, key=lambda d: d.day_number)
    assert (days[-1].planned_date - days[0].planned_date).days == 9


# ── Müddətin dəyişdirilməsi (CD-3) ───────────────────────────────────────────────

def test_extending_keeps_existing_days_untouched(db):
    workspace = _workspace(db)
    campaign = _campaign(db, workspace, 7)
    original = {d.day_number: d.theme for d in campaign.days}

    result = resize_campaign(db, campaign, 21)
    assert result["added"] == 14 and result["removed"] == 0
    assert len(campaign.days) == 21
    for day in campaign.days:
        if day.day_number in original:
            assert day.theme == original[day.day_number], "mövcud gün yenidən yazılıb"


def test_shortening_detaches_material_but_never_deletes_it(db):
    workspace = _workspace(db)
    campaign = _campaign(db, workspace, 20)
    last_day = max(campaign.days, key=lambda d: d.day_number)
    asset = ContentAsset(
        workspace_id=workspace.id, campaign_day_id=last_day.id, title="Hazır material",
        format="POST", aspect_ratio="4:5", status="DRAFT",
    )
    db.add(asset)
    db.commit()
    asset_id = asset.id

    result = resize_campaign(db, campaign, 7)
    assert result["removed"] == 13
    assert result["detached"] == 1
    survivor = db.query(ContentAsset).filter(ContentAsset.id == asset_id).first()
    assert survivor is not None, "material silinməməli idi"
    assert survivor.campaign_day_id is None, "yalnız əlaqə kəsilməlidir"


def test_resize_impact_reports_before_changing_anything(db):
    workspace = _workspace(db)
    campaign = _campaign(db, workspace, 30)
    impact = resize_impact(db, campaign, 7)
    assert impact["removed"] == 23
    assert len(campaign.days) == 30, "hesablama planı dəyişməməlidir"


def test_resize_to_same_duration_is_a_no_op(db):
    campaign = _campaign(db, _workspace(db), 12)
    result = resize_campaign(db, campaign, 12)
    assert result == {"added": 0, "removed": 0, "detached": 0, "duration": 12}


# ── Səhifə (CD-1, CD-4) ──────────────────────────────────────────────────────────

def test_creation_form_offers_duration_choices(registered_client):
    client = registered_client("campaign@test.az", "Campaign Test")
    page = client.get("/campaigns")
    assert page.status_code == 200
    assert 'name="duration"' in page.text
    assert 'name="duration_custom"' in page.text
    assert 'name="start_date"' in page.text


def test_custom_duration_creates_that_many_days(registered_client):
    client = registered_client("campaign2@test.az", "Campaign Test 2")
    response = client.post("/campaigns", data={
        "name": "Aylıq launch", "objective": "demo müraciətlərini artırmaq",
        "audience": "marketinq rəhbərləri", "channels": "Instagram",
        "monthly_budget": "300 AZN", "duration": "custom", "duration_custom": "30",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert response.text.count('class="day"') == 30


def test_preset_duration_creates_that_many_days(registered_client):
    client = registered_client("campaign3@test.az", "Campaign Test 3")
    response = client.post("/campaigns", data={
        "name": "İki həftəlik", "objective": "demo müraciətlərini artırmaq",
        "audience": "marketinq rəhbərləri", "channels": "Instagram",
        "monthly_budget": "300 AZN", "duration": "14",
    }, follow_redirects=True)
    assert response.text.count('class="day"') == 14


def test_shortening_via_page_requires_confirmation(registered_client, db):
    """Qısaltma dağıdıcıdır — təsdiqsiz heç bir gün silinməməlidir."""
    from app.db_models import Campaign

    client = registered_client("campaign4@test.az", "Campaign Test 4")
    client.post("/campaigns", data={
        "name": "Uzun plan", "objective": "demo müraciətlərini artırmaq",
        "audience": "hamı", "channels": "Instagram", "monthly_budget": "0",
        "duration": "custom", "duration_custom": "30",
    }, follow_redirects=True)
    campaign = db.query(Campaign).filter(Campaign.name == "Uzun plan").first()

    first = client.post(f"/campaigns/{campaign.id}/duration", data={"duration": "7"})
    assert first.status_code == 200
    assert "silinəcək" in first.text
    db.refresh(campaign)
    assert len(campaign.days) == 30, "təsdiqsiz gün silinib!"

    client.post(f"/campaigns/{campaign.id}/duration",
                data={"duration": "7", "confirm": "1"}, follow_redirects=True)
    db.refresh(campaign)
    assert len(campaign.days) == 7


def test_extending_via_page_needs_no_confirmation(registered_client, db):
    from app.db_models import Campaign

    client = registered_client("campaign5@test.az", "Campaign Test 5")
    client.post("/campaigns", data={
        "name": "Qısa plan", "objective": "demo müraciətlərini artırmaq",
        "audience": "hamı", "channels": "Instagram", "monthly_budget": "0", "duration": "7",
    }, follow_redirects=True)
    campaign = db.query(Campaign).filter(Campaign.name == "Qısa plan").first()

    client.post(f"/campaigns/{campaign.id}/duration",
                data={"duration": "14"}, follow_redirects=True)
    db.refresh(campaign)
    assert len(campaign.days) == 14


def test_header_links_are_functional(registered_client):
    client = registered_client("campaign6@test.az", "Campaign Test 6")
    home = client.get("/")
    assert home.status_code == 200
    assert 'href="/#studio"' in home.text
    assert 'href="/#briefRoom"' in home.text
