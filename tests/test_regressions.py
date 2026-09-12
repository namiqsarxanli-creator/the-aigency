"""Canlı serverdə tapılmış qüsurların qoruyucuları.

Bu testlər tapılma üsuluna görə qruplanıb: hər biri işləyən tətbiqdə real sorğu ilə
təsdiqlənmiş, sonra kodda bağlanmış bir davranışdır.
"""
from app.db_models import Campaign, ContentAsset, Workspace


def _make_campaign(client, name, duration="7"):
    return client.post("/campaigns", data={
        "name": name, "objective": "demo müraciətlərini artırmaq", "audience": "hamı",
        "channels": "Instagram", "monthly_budget": "0", "duration": duration,
    }, follow_redirects=True)


# ── CAMP-1: kampaniya səhifəsində səssiz əvəzləmə ────────────────────────────────
#
# Studio-dakı RC-3-ün eynisi, amma nəticəsi ağırdır: müddət formasının `action`-ı
# `selected_campaign.id`-yə bağlıdır. Səhifə başqa kampaniyanı açanda «Tətbiq et»
# düyməsi SƏHV kampaniyanın günlərini silirdi.

def test_unknown_campaign_id_never_opens_a_different_campaign(registered_client, db):
    client = registered_client("camp-reg1@test.az", "Camp Reg")
    _make_campaign(client, "BİRİNCİ")
    _make_campaign(client, "İKİNCİ")

    page = client.get("/campaigns?id=999999")
    assert page.status_code == 200
    assert "tapılmadı" in page.text
    assert "İKİNCİ</h2>" not in page.text, "tapılmayan id başqa kampaniyanı açdı!"


def test_unknown_campaign_id_exposes_no_destructive_form(registered_client, db):
    """ƏSAS QORUYUCU: gün silən forma heç bir kampaniyaya bağlanmamalıdır."""
    client = registered_client("camp-reg2@test.az", "Camp Reg 2")
    _make_campaign(client, "TƏK PLAN", duration="30")
    campaign = db.query(Campaign).filter(Campaign.name == "TƏK PLAN").first()

    page = client.get("/campaigns?id=999999")
    assert f'action="/campaigns/{campaign.id}/duration"' not in page.text
    assert "/duration" not in page.text, "səhifədə hələ də dağıdıcı forma var"
    # Plan toxunulmamış qalır.
    db.refresh(campaign)
    assert len(campaign.days) == 30


def test_campaign_from_another_workspace_is_refused_not_substituted(registered_client, db):
    owner = registered_client("camp-reg3@test.az", "Owner WS")
    _make_campaign(owner, "SAHİBİN PLANI")
    foreign = db.query(Campaign).filter(Campaign.name == "SAHİBİN PLANI").first()

    other = registered_client("camp-reg4@test.az", "Other WS")
    _make_campaign(other, "ÖZ PLANIM")
    page = other.get(f"/campaigns?id={foreign.id}")
    assert "tapılmadı" in page.text
    assert "SAHİBİN PLANI" not in page.text, "başqa workspace-in kampaniyası sızdı!"
    assert "ÖZ PLANIM</h2>" not in page.text, "səssizcə öz kampaniyası ilə əvəzləndi"


def test_no_id_still_opens_the_newest_campaign(registered_client, db):
    """id verilmədikdə ən sonuncunu açmaq düzgündür — bu, əvəzləmə deyil."""
    client = registered_client("camp-reg5@test.az", "Camp Reg 5")
    _make_campaign(client, "KÖHNƏ")
    _make_campaign(client, "ƏN YENİ")

    page = client.get("/campaigns")
    assert "tapılmadı" not in page.text
    assert "ƏN YENİ" in page.text


# ── STUDIO-1: naməlum format 500 verirdi ─────────────────────────────────────────

def test_unsupported_format_does_not_crash(registered_client, db):
    """`create_asset` naməlum formatda ValueError atırdı və marşrut onu tutmurdu."""
    client = registered_client("fmt1@test.az", "Format Test")
    response = client.post("/content-studio", data={
        "title": "Zibil format", "format": "XYZ", "goal": "maraq", "facts": "",
    }, follow_redirects=True)
    assert response.status_code == 200, "naməlum format səhifəni çökdürdü"

    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()
    assert asset.format == "POST", "naməlum format təhlükəsiz dəyərə düşməlidir"


def test_empty_and_lowercase_formats_are_accepted(registered_client, db):
    client = registered_client("fmt2@test.az", "Format Test 2")
    for value, expected in (("", "POST"), ("story", "STORY"), ("Carousel", "CAROUSEL")):
        client.post("/content-studio", data={
            "title": f"Format {value or 'bos'}", "format": value, "goal": "maraq", "facts": "",
        }, follow_redirects=True)
        asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()
        assert asset.format == expected, f"{value!r} -> {asset.format}, gözlənilən {expected}"


# ── Çarpaz-workspace dağıdıcı əməliyyatlar (canlı sınaqda təmiz çıxdı) ───────────

def test_intruder_cannot_shrink_someone_elses_campaign(registered_client, db):
    owner = registered_client("xt1@test.az", "XT Owner")
    _make_campaign(owner, "QORUNAN PLAN", duration="30")
    campaign = db.query(Campaign).filter(Campaign.name == "QORUNAN PLAN").first()

    intruder = registered_client("xt2@test.az", "XT Intruder")
    intruder.post(f"/campaigns/{campaign.id}/duration",
                  data={"duration": "3", "confirm": "1"}, follow_redirects=True)
    db.refresh(campaign)
    assert len(campaign.days) == 30, "yad istifadəçi planı qısaltdı!"


def test_intruder_cannot_convert_someone_elses_day(registered_client, db):
    owner = registered_client("xt3@test.az", "XT Owner 3")
    _make_campaign(owner, "GÜN PLANI")
    campaign = db.query(Campaign).filter(Campaign.name == "GÜN PLANI").first()
    day = min(campaign.days, key=lambda d: d.day_number)

    intruder = registered_client("xt4@test.az", "XT Intruder 4")
    intruder.post(f"/campaigns/day/{day.id}/to-asset", follow_redirects=True)

    stolen = db.query(Workspace).filter(Workspace.name == "XT Intruder 4").first()
    assert db.query(ContentAsset).filter(ContentAsset.workspace_id == stolen.id).count() == 0


# ── IMG-1: Wikimedia şəkilləri əbədi 502 verirdi ─────────────────────────────────
#
# `stock_photos` Wikimedia-da AXTARARKƏN User-Agent göndərirdi, amma tapılan şəkli
# YÜKLƏYƏN proksi göndərmirdi. Wikimedia UA-sız sorğunu 403 ilə rədd edir, ona görə
# Wikimedia-dan seçilmiş hər şəkil `/agency/{id}/image` ünvanında 502 verirdi.
# Canlı sınaq: UA-sız 403 (126 bayt) · UA ilə 200 (51806 bayt).

def test_image_download_identifies_itself(monkeypatch):
    from app import api
    from app.core import HTTP_USER_AGENT

    seen = {}

    class _Resp:
        status_code = 200
        content = b"jpeg-baytlari"

        def raise_for_status(self):
            return None

    def fake_get(url, timeout=None, headers=None):
        seen["headers"] = headers or {}
        return _Resp()

    monkeypatch.setattr(api.requests, "get", fake_get)
    api._image_cache.clear()
    project = type("P", (), {"id": 987654, "deliverable_image_url": "https://upload.wikimedia.org/x.jpg"})()

    assert api._image_bytes(project) == b"jpeg-baytlari"
    assert seen["headers"].get("User-Agent") == HTTP_USER_AGENT, "UA göndərilmir — Wikimedia 403 verəcək"
    api._image_cache.clear()


def test_failed_image_download_is_not_cached(monkeypatch):
    """Uğursuzluq keşlənsə, mənbə düzələndən sonra da şəkil əbədi sınıq qalardı."""
    import requests as requests_module
    from fastapi import HTTPException

    from app import api

    def fake_get(url, timeout=None, headers=None):
        raise requests_module.RequestException("403")

    monkeypatch.setattr(api.requests, "get", fake_get)
    api._image_cache.clear()
    project = type("P", (), {"id": 987655, "deliverable_image_url": "https://upload.wikimedia.org/y.jpg"})()

    try:
        api._image_bytes(project)
        raise AssertionError("502 gözlənilirdi")
    except HTTPException as exc:
        assert exc.status_code == 502
    assert 987655 not in api._image_cache, "uğursuzluq keşlənib!"
