"""F0 qoruyucuları (audit SC-2, SC-3).

TARİXÇƏ: `slides_json`-a kopiraytere ünvanlanmış təlimat yazılırdı, şablon isə onu heç
oxumurdu — hər carousel 2, 3 və 4-cü slaydda materialın adını təkrarlayırdı. Vizual brif də
şəklin yerində 36px kursivlə göstərilirdi, yəni daxili istehsal təlimatı nəticə kimi görünürdü.
"""
import json

from app.content_studio import build_slides, create_asset, parse_slides
from app.db_models import ContentAsset, Workspace


def _workspace(db, slug="slides-ws"):
    workspace = Workspace(name="Slides WS", slug=slug)
    db.add(workspace)
    db.commit()
    return workspace


# ── SC-2: yer tutucu təlimat məzmun kimi saxlanılmır ─────────────────────────────

def test_new_carousel_never_stores_instruction_text(db):
    asset = create_asset(
        db, _workspace(db), "Yaz kolleksiyası", "CAROUSEL",
        headline="Kətan çanta niyə uzun qalır?", caption="", visual_brief="",
    )
    stored = json.dumps(json.loads(asset.slides_json), ensure_ascii=False)
    for instruction in ("göstərin", "izah edin", "təqdim edin", "əlavə edin"):
        assert instruction not in stored, f"yer tutucu təlimat saxlanılıb: {instruction}"


def test_only_the_known_slide_is_filled(db):
    asset = create_asset(
        db, _workspace(db), "Test", "CAROUSEL",
        headline="Açılış cümləsi", caption="", visual_brief="",
    )
    slides = parse_slides(asset)
    assert slides[0]["headline"] == "Açılış cümləsi"
    assert slides[0]["empty"] is False
    # Qalanları uydurulmur — boş qalır.
    assert all(s["empty"] for s in slides[1:]), "bilmədiyimiz slayd doldurulub"


def test_legacy_placeholder_slides_are_filtered_out(db):
    """Köhnə materiallar bazada təlimat mətni saxlayır — ekrana çıxmamalıdır."""
    workspace = _workspace(db)
    asset = ContentAsset(
        workspace_id=workspace.id, title="Köhnə carousel", format="CAROUSEL",
        aspect_ratio="4:5", headline="Real başlıq", status="DRAFT",
        slides_json=json.dumps([
            {"slide": 1, "role": "hook", "text": "Real başlıq"},
            {"slide": 2, "role": "problem", "text": "Auditoriyanın əsas problemini göstərin"},
            {"slide": 3, "role": "insight", "text": "Əsas faydalı fikri izah edin"},
        ], ensure_ascii=False),
    )
    db.add(asset)
    db.commit()

    slides = parse_slides(asset)
    assert slides[0]["headline"] == "Real başlıq"
    assert slides[1]["empty"] is True and slides[2]["empty"] is True


def test_broken_slides_json_does_not_crash(db):
    workspace = _workspace(db)
    asset = ContentAsset(
        workspace_id=workspace.id, title="Sınıq", format="CAROUSEL", aspect_ratio="4:5",
        headline="Başlıq", status="DRAFT", slides_json="{bu json deyil",
    )
    db.add(asset)
    db.commit()
    slides = parse_slides(asset)
    assert len(slides) == 5 and slides[0]["headline"] == "Başlıq"


def test_non_carousel_has_no_slides(db):
    asset = create_asset(db, _workspace(db), "Sadə post", "POST", "Başlıq", "", "")
    assert asset.slides_json is None
    assert parse_slides(asset) == []


# ── SC-2: şablon slides_json-u oxuyur ────────────────────────────────────────────

def test_carousel_preview_does_not_repeat_the_title(monkeypatch, registered_client, db):
    """Əvvəl 2, 3 və 4-cü slayd eyni sətri — materialın adını — göstərirdi."""
    from app import studio_ai

    payload = {
        "headline_options": ["Tikiş harada dayanır?"],
        "caption": "Kətan çanta çiynindən sürüşürsə, problem tikişin yerindədir. Şərhdə soruşun.",
        "hashtags": [], "visual_direction": {},
        "slides": [
            {"role": "hook", "headline": "Tikiş harada dayanır?", "body": "Birinci slayd."},
            {"role": "problem", "headline": "Sürüşmə", "body": "İkinci slayd."},
            {"role": "solution", "headline": "İkiqat tikiş", "body": "Üçüncü slayd."},
            {"role": "cta", "headline": "Şərhdə soruşun", "body": "Dördüncü slayd."},
        ],
        "needs_input": [], "confidence": "high",
    }
    monkeypatch.setattr(studio_ai, "_call_llm",
                        lambda messages, **kw: json.dumps(payload, ensure_ascii=False))

    client = registered_client("slides1@test.az", "Slides Test")
    client.post("/content-studio", data={
        "title": "Kətan çanta launch", "format": "CAROUSEL", "goal": "maraq",
        "subject": "kətan çantalar", "facts": "", "tone": "neytral", "cta": "Şərhdə soruşun",
    }, follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()

    page = client.get(f"/content-studio?id={asset.id}")
    assert page.status_code == 200
    assert "Kətan çanta launch · əsas fikir" not in page.text, "köhnə təkrar hələ də var"
    assert "Tikiş harada dayanır?" in page.text
    assert "İkinci slayd." in page.text, "slides_json ekrana çıxmır"


def test_carousel_without_a_model_shows_empty_slides(registered_client, db):
    """Model əlçatan olmayanda uydurma yazılmır — slaydlar açıq şəkildə boş qalır."""
    client = registered_client("slides1b@test.az", "Slides Test 1b")
    client.post("/content-studio", data={
        "title": "Modelsiz carousel", "format": "CAROUSEL", "goal": "maraq", "facts": "",
    }, follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()

    page = client.get(f"/content-studio?id={asset.id}")
    assert "Bu slaydın mətni hələ yazılmayıb." in page.text
    assert "Modelsiz carousel · əsas fikir" not in page.text


# ── SC-3: brif kreativin yerində durmur ──────────────────────────────────────────

def test_visual_brief_is_labelled_not_presented_as_the_creative(registered_client, db):
    client = registered_client("slides2@test.az", "Slides Test 2")
    workspace = db.query(Workspace).filter(Workspace.name == "Slides Test 2").first()
    asset = create_asset(db, workspace, "Reel testi", "REEL", "Başlıq", "",
                         "Instagram · REEL — Dəyər · praktik bələdçi")

    page = client.get(f"/content-studio?id={asset.id}")
    assert "Vizual brif — şəkil hələ yoxdur" in page.text, "brif etiketsiz göstərilir"


def test_missing_visual_brief_states_it(registered_client, db):
    client = registered_client("slides3@test.az", "Slides Test 3")
    workspace = db.query(Workspace).filter(Workspace.name == "Slides Test 3").first()
    asset = create_asset(db, workspace, "Brifsiz post", "POST", "Başlıq", "", "")

    page = client.get(f"/content-studio?id={asset.id}")
    assert "Vizual istiqamət yazılmayıb." in page.text
    assert "Brifsiz post" not in page.text.split('class="visual-area"')[1][:400]
