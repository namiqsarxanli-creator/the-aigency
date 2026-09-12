"""F2–F5 qoruyucuları: doğrulama, generasiya, yenidən yazma, versiyalar.

ƏSAS PRİNSİP (audit §05): məzmun sahəsinə heç vaxt yer tutucu və ya uydurma yazılmır.
Model tələbi ödəyə bilmirsə, material `NEEDS_INPUT` statusu ilə BOŞ qalır və səbəb görünür.
"""
import json

import pytest

from app import studio_ai
from app.content_studio import create_asset
from app.db_models import ContentAsset, ContentAssetVersion, Workspace
from app.studio_ai import StudioBrief, validate

GOOD = {
    "headline_options": ["Tikiş harada dayanır?", "Çanta niyə sürüşür?", "Bir tikiş, uzun ömür"],
    "caption": "Kətan çanta gün ərzində çiynindən sürüşürsə, problem çantada deyil — tikişin "
               "yerindədir. Bunu necə həll etdiyimizi şərhdə soruşun.",
    "hashtags": ["#kətan", "#əlişi"],
    "visual_direction": {"subject": "çanta tikişi", "lighting": "yumşaq gündüz işığı"},
    "slides": [],
    "needs_input": [],
    "confidence": "high",
}


@pytest.fixture
def workspace(db):
    workspace = Workspace(
        name="Kətan Studio", slug="gen-ws", brand_ai_consent=True,
        brand_products="kətan çantalar", brand_forbidden_phrases="ən ucuz\nzəmanətli qazanc",
    )
    db.add(workspace)
    db.commit()
    return workspace


def _mock_llm(monkeypatch, *responses):
    """`_call_llm` ardıcıl cavablar qaytarır. None = model əlçatan deyil."""
    calls = {"n": 0}

    def fake(messages, max_tokens=700, temperature=0.5, model_tier="mini", usage_ctx=None):
        calls["n"] += 1
        calls.setdefault("usage_ctx", usage_ctx)
        index = min(calls["n"] - 1, len(responses) - 1)
        payload = responses[index]
        return None if payload is None else json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr(studio_ai, "_call_llm", fake)
    return calls


# ── F2: doğrulama ────────────────────────────────────────────────────────────────

def test_field_label_in_copy_is_rejected():
    brief = StudioBrief()
    data = dict(GOOD, caption="Bu təklif. Auditoriya: kiçik biznes sahibləri üçün nəzərdə tutulub.")
    assert any("sahə etiketi" in p for p in validate(data, brief))


def test_instruction_text_is_rejected():
    brief = StudioBrief()
    data = dict(GOOD, headline_options=["Auditoriyanın əsas problemini göstərin"])
    assert any("təlimat" in p for p in validate(data, brief))


def test_forbidden_phrase_is_rejected():
    brief = StudioBrief(must_avoid=["ən ucuz"])
    data = dict(GOOD, caption="Bazarda ən ucuz qiymət bizdədir və keyfiyyət də yüksəkdir burada.")
    assert any("qadağan ifadə" in p for p in validate(data, brief))


def test_number_without_a_supporting_fact_is_flagged():
    brief = StudioBrief(facts=[])
    data = dict(GOOD, caption="Bizi 500 müştəri seçib və hamısı nəticədən razı qaldı, sizi də gözləyirik.")
    assert any("mənbəsiz rəqəm" in p for p in validate(data, brief))


def test_number_backed_by_a_fact_passes():
    brief = StudioBrief(facts=["12 ay zəmanət veririk"])
    data = dict(GOOD, caption="Hər çantaya 12 ay zəmanət veririk, çünki tikişinə inanırıq. "
                              "Şərhdə soruşun.")
    assert not any("mənbəsiz rəqəm" in p for p in validate(data, brief))


def test_carousel_needs_enough_slides():
    brief = StudioBrief(content_format="CAROUSEL")
    assert any("slayd" in p for p in validate(dict(GOOD, slides=[{"role": "hook"}]), brief))


def test_clean_copy_produces_no_problems():
    assert validate(GOOD, StudioBrief(facts=[])) == []


# ── F3: generasiya ───────────────────────────────────────────────────────────────

def test_generation_stores_options_and_caption(monkeypatch, db, workspace):
    _mock_llm(monkeypatch, GOOD)
    result = studio_ai.generate_draft(workspace, StudioBrief(facts=["12 ay zəmanət"]))
    assert result["ok"] is True
    assert len(result["headline_options"]) == 3
    assert "tikişin" in result["caption"]


def test_generation_passes_usage_context(monkeypatch, db, workspace):
    """Studio+ token panelində və günlük büdcədə görünməlidir."""
    calls = _mock_llm(monkeypatch, GOOD)
    studio_ai.generate_draft(workspace, StudioBrief())
    assert calls["usage_ctx"] == {"workspace_id": workspace.id, "feature": "studio"}


def test_bad_output_triggers_exactly_one_repair(monkeypatch, db, workspace):
    bad = dict(GOOD, caption="Auditoriya: hamı üçün nəzərdə tutulmuş universal bir təklifdir bu.")
    calls = _mock_llm(monkeypatch, bad, GOOD)
    result = studio_ai.generate_draft(workspace, StudioBrief())
    assert result["ok"] is True
    assert calls["n"] == 2, "düzəliş cəhdi bir dəfə olmalıdır"


def test_two_bad_answers_never_produce_content(monkeypatch, db, workspace):
    """ƏSAS QORUYUCU: model iki dəfə pozuntu versə, UYDURMA MƏZMUN YAZILMIR."""
    bad = dict(GOOD, caption="Auditoriya: hamı. Məqsəd: satış.")
    _mock_llm(monkeypatch, bad, bad)
    result = studio_ai.generate_draft(workspace, StudioBrief())
    assert result["ok"] is False
    assert result["caption"] == "" and result["headline_options"] == []
    assert result["needs_input"], "çatışmayan sahələr sadalanmalıdır"
    assert "keyfiyyət tələblərinə" in result["reason"]


def test_missing_model_is_reported_not_faked(monkeypatch, db, workspace):
    _mock_llm(monkeypatch, None)
    result = studio_ai.generate_draft(workspace, StudioBrief())
    assert result["ok"] is False and result["caption"] == ""
    assert "büdcə" in result["reason"] or "əlçatan" in result["reason"]


def test_brand_memory_needs_consent(db, workspace):
    brief = StudioBrief()
    assert "kətan çantalar" in studio_ai.studio_context(workspace, brief)
    workspace.brand_ai_consent = False
    db.commit()
    assert "kətan çantalar" not in studio_ai.studio_context(workspace, brief)


def test_context_forbids_numbers_when_no_facts_given(db, workspace):
    context = studio_ai.studio_context(workspace, StudioBrief(facts=[]))
    assert "QADAĞANDIR" in context


# ── F4/F5: səhifə, yenidən yazma, versiyalar ─────────────────────────────────────

def test_form_asks_for_input_not_output(registered_client):
    client = registered_client("gen1@test.az", "Gen Test")
    page = client.get("/content-studio")
    assert 'name="facts"' in page.text and 'name="goal"' in page.text and 'name="tone"' in page.text
    # Nəticə sahələri artıq əl ilə istənilmir.
    assert 'name="caption"' not in page.text


def test_created_asset_is_generated_and_keeps_its_brief(monkeypatch, registered_client, db):
    _mock_llm(monkeypatch, GOOD)
    client = registered_client("gen2@test.az", "Gen Test 2")
    client.post("/content-studio", data={
        "title": "Kətan launch", "format": "POST", "goal": "maraq",
        "subject": "kətan çantalar", "facts": "12 ay zəmanət", "tone": "isti", "cta": "Şərhdə soruşun",
    }, follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()
    assert asset.status == "DRAFT"
    assert asset.headline in GOOD["headline_options"]
    assert json.loads(asset.headline_options) == GOOD["headline_options"]
    assert StudioBrief.from_json(asset.brief_json).facts == ["12 ay zəmanət"]


def test_failed_generation_lands_in_needs_input(monkeypatch, registered_client, db):
    _mock_llm(monkeypatch, None)
    client = registered_client("gen3@test.az", "Gen Test 3")
    client.post("/content-studio", data={
        "title": "Modelsiz material", "format": "POST", "goal": "maraq", "facts": "",
    }, follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()
    assert asset.status == "NEEDS_INPUT"
    assert not asset.caption and not asset.headline

    page = client.get(f"/content-studio?id={asset.id}")
    assert "məlumat lazımdır" in page.text
    assert "uydurmur" in page.text


def test_regenerate_archives_the_previous_version(monkeypatch, registered_client, db):
    _mock_llm(monkeypatch, GOOD)
    client = registered_client("gen4@test.az", "Gen Test 4")
    client.post("/content-studio", data={
        "title": "Arxiv testi", "format": "POST", "goal": "maraq", "facts": "12 ay zəmanət",
    }, follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()
    first_caption = asset.caption

    second = dict(GOOD, caption="Tamam başqa bir caption mətni, ilkindən fərqlidir və uzundur.")
    _mock_llm(monkeypatch, second)
    client.post(f"/content-studio/{asset.id}/regenerate", data={"delta": "qisa"}, follow_redirects=True)
    db.refresh(asset)

    versions = db.query(ContentAssetVersion).filter(ContentAssetVersion.asset_id == asset.id).all()
    assert len(versions) == 1
    assert versions[0].caption == first_caption
    assert asset.caption != first_caption


def test_approved_asset_is_never_overwritten(monkeypatch, registered_client, db):
    _mock_llm(monkeypatch, GOOD)
    client = registered_client("gen5@test.az", "Gen Test 5")
    client.post("/content-studio", data={
        "title": "Təsdiq testi", "format": "POST", "goal": "maraq", "facts": "12 ay zəmanət",
    }, follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()
    client.post(f"/content-studio/{asset.id}/review", data={"decision": "APPROVED"}, follow_redirects=True)
    db.refresh(asset)
    approved_caption = asset.caption

    _mock_llm(monkeypatch, dict(GOOD, caption="Bu mətn heç vaxt yazılmamalıdır, çünki təsdiqlənib."))
    page = client.post(f"/content-studio/{asset.id}/regenerate", data={"delta": "qisa"}, follow_redirects=True)
    db.refresh(asset)
    assert asset.caption == approved_caption
    assert "təsdiqlənib" in page.text


def test_review_feedback_drives_the_rewrite(monkeypatch, registered_client, db):
    """SC-5: rəy artıq saxlanılıb unudulmur — təlimata çevrilir."""
    _mock_llm(monkeypatch, GOOD)
    client = registered_client("gen6@test.az", "Gen Test 6")
    client.post("/content-studio", data={
        "title": "Rəy testi", "format": "POST", "goal": "maraq", "facts": "12 ay zəmanət",
    }, follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()
    client.post(f"/content-studio/{asset.id}/review", data={
        "decision": "CHANGES_REQUESTED", "feedback": "Başlıq çox uzundur, qısalt",
    }, follow_redirects=True)

    seen = {}

    def fake(messages, max_tokens=700, temperature=0.5, model_tier="mini", usage_ctx=None):
        seen["text"] = messages[1]["content"]
        return json.dumps(GOOD, ensure_ascii=False)

    monkeypatch.setattr(studio_ai, "_call_llm", fake)
    client.post(f"/content-studio/{asset.id}/regenerate", data={}, follow_redirects=True)
    assert "Başlıq çox uzundur" in seen["text"], "rəy promptə ötürülmədi"


def test_headline_choice_must_come_from_the_options(monkeypatch, registered_client, db):
    _mock_llm(monkeypatch, GOOD)
    client = registered_client("gen7@test.az", "Gen Test 7")
    client.post("/content-studio", data={
        "title": "Seçim testi", "format": "POST", "goal": "maraq", "facts": "12 ay zəmanət",
    }, follow_redirects=True)
    asset = db.query(ContentAsset).order_by(ContentAsset.id.desc()).first()

    client.post(f"/content-studio/{asset.id}/headline",
                data={"headline": GOOD["headline_options"][2]}, follow_redirects=True)
    db.refresh(asset)
    assert asset.headline == GOOD["headline_options"][2]

    client.post(f"/content-studio/{asset.id}/headline",
                data={"headline": "kənardan gələn başlıq"}, follow_redirects=True)
    db.refresh(asset)
    assert asset.headline == GOOD["headline_options"][2], "siyahıda olmayan başlıq qəbul edildi"


def test_asset_without_a_brief_cannot_be_regenerated(registered_client, db):
    client = registered_client("gen8@test.az", "Gen Test 8")
    workspace = db.query(Workspace).filter(Workspace.name == "Gen Test 8").first()
    asset = create_asset(db, workspace, "Köhnə material", "POST", "Başlıq", "Mətn", "")

    page = client.post(f"/content-studio/{asset.id}/regenerate", data={"delta": "qisa"},
                       follow_redirects=True)
    db.refresh(asset)
    assert asset.caption == "Mətn"
    assert "brif saxlanmadan" in page.text
