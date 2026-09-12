"""LUMÉA yol xəritəsi: brend uyğunluğu, terminologiya, palitra, şəkil, kampaniya qatı.

Nümunə məlumat canlı LUMÉA Brand Kit-indən götürülüb — süni deyil, real tərkib.
"""
import json

import pytest

from app import campaign_ai, studio_ai
from app.campaign_ai import enrich_campaign
from app.campaigns import create_campaign
from app.compliance import EMPTY_RULES, check_text, parse_glossary, rules_from_workspace
from app.content_studio import create_asset
from app.db_models import Campaign, ContentAsset, Workspace
from app.studio_ai import StudioBrief, _brand_fields, validate

PALETTE = "#F4EFE6 fil sümüyü, #D8C7AD isti bej, #3B2A22 tünd qəhvəyi, #B89A62 zəif qızılı"
PRODUCTS = ("Barrier Restore Serum: seramid, niasinamid və hialuron turşusu tərkibli baryer "
            "dəstək serumu. İlk 100 ön sifarişə 15% endirim və Bakı daxilində pulsuz çatdırılma.")


@pytest.fixture
def lumea(db):
    workspace = Workspace(
        name="LUMÉA Skin", slug="lumea", brand_ai_consent=True,
        brand_description="LUMÉA Skin — həssas dəri üçün elmi düşüncəli premium brend.",
        brand_products=PRODUCTS,
        brand_colors=PALETTE,
        brand_voice="Sakit, savadlı, şəffaf, minimal.",
        brand_forbidden_phrases="möcüzəvi nəticə\nzəmanətli nəticə\ndərhal müalicə",
        brand_glossary="baryer -> bariyer",
    )
    db.add(workspace)
    db.commit()
    return workspace


def _brief(workspace, **kw):
    return StudioBrief(**{**_brand_fields(workspace), **kw})


def _payload(**kw):
    base = {
        "headline_options": ["Bariyer nədir və niyə vacibdir?"],
        "caption": "Həssas dəri üçün sadə izah: bariyer nə edir, nə etmir. "
                   "Suallarınızı şərhdə soruşun.",
        "hashtags": [], "slides": [],
        "visual_direction": {"palette": "isti bej #D8C7AD, zəif qızılı #B89A62"},
        "needs_input": [], "confidence": "high",
    }
    base.update(kw)
    return base


# ── Terminologiya lüğəti (#9) ────────────────────────────────────────────────────

def test_glossary_parses_several_separators():
    assert parse_glossary("baryer -> bariyer\nseramid → seramid\nx: y\nzibil") == [
        ["baryer", "bariyer"], ["seramid", "seramid"], ["x", "y"],
    ]


def test_wrong_term_is_caught(lumea):
    """Model səhv yazmır, Brand Kit-dən köçürür — doğrulama onu tutmalıdır."""
    data = _payload(headline_options=["Dəri baryerini gücləndirən qulluq"])
    problems = validate(data, _brief(lumea))
    assert any("bariyer" in p for p in problems), problems


def test_correct_term_passes(lumea):
    assert validate(_payload(), _brief(lumea)) == []


# ── Sübutsuz iddialar (#9) ───────────────────────────────────────────────────────

def test_unverified_claim_is_caught(lumea):
    data = _payload(headline_options=["Dəri bariyerini bərpa edən formula"])
    assert any("sübutsuz iddia" in p for p in validate(data, _brief(lumea)))


def test_claim_backed_by_a_fact_passes(lumea):
    brief = _brief(lumea, facts=["Klinik testdə bariyeri bərpa edən nəticə qeydə alınıb"])
    data = _payload(headline_options=["Bariyeri bərpa edən qulluq"])
    assert not any("sübutsuz iddia" in p for p in validate(data, brief))


# ── Qadağan ifadələr (#10) ───────────────────────────────────────────────────────

def test_forbidden_phrase_variant_is_caught(lumea):
    """«möcüzəvi nəticə» siyahıdadır; «möcüzəvi effekt» də tutulmalıdır."""
    data = _payload(caption="Bu serum möcüzəvi effekt verir və dəri hamar olur, tam etibarlıdır.")
    assert any("qadağan ifadə" in p for p in validate(data, _brief(lumea)))


def test_compliance_layer_is_shared_with_agent_roles(lumea):
    """Eyni qaydalar agent layihələrinə də tətbiq olunur — əvvəl yalnız Studio+-da idi."""
    rules = rules_from_workspace(lumea)
    assert check_text("Dərhal müalicə təmin edirik.", rules)
    assert check_text("Bariyer haqqında sadə izah.", rules) == []


def test_empty_rules_never_block_anything():
    assert check_text("İstənilən mətn burada.", EMPTY_RULES) == []


# ── Palitra (#8) ─────────────────────────────────────────────────────────────────

def test_off_brand_colour_is_caught(lumea):
    data = _payload(visual_direction={"palette": "təmiz mavi və ağ fon", "subject": "serum"})
    problems = validate(data, _brief(lumea))
    assert any("mavi" in p for p in problems), problems


def test_off_brand_hex_is_caught(lumea):
    data = _payload(visual_direction={"palette": "vurğu #1E90FF"})
    assert any("#1e90ff" in p.lower() for p in validate(data, _brief(lumea)))


def test_brand_palette_passes(lumea):
    assert validate(_payload(), _brief(lumea)) == []


def test_palette_check_is_skipped_without_a_brand_palette(db):
    workspace = Workspace(name="Palitrasız", slug="nopal")
    db.add(workspace)
    db.commit()
    data = _payload(visual_direction={"palette": "mavi və ağ"})
    assert not any("palette" in p for p in validate(data, _brief(workspace)))


# ── Fakt mənbəyi (#5 / P1) ───────────────────────────────────────────────────────

def test_offer_numbers_from_the_brand_kit_are_not_treated_as_invented(lumea):
    """«15% endirim» Brand Kit-dədir — doğrulama onu uydurma saymamalıdır."""
    data = _payload(caption="İlk 100 ön sifarişə 15% endirim tətbiq olunur. "
                            "Şərhdə soruşun, ətraflı yazaq.")
    problems = validate(data, _brief(lumea))
    assert not any("mənbəsiz rəqəm" in p for p in problems), problems


def test_invented_number_is_still_caught(lumea):
    data = _payload(caption="Bizi 5000 müştəri seçib və hamısı razı qalıb, siz də qoşulun.")
    assert any("mənbəsiz rəqəm" in p for p in validate(data, _brief(lumea)))


# ── Razılıq qapısı ───────────────────────────────────────────────────────────────

def test_brand_data_stays_out_of_the_prompt_without_consent(db, lumea):
    lumea.brand_ai_consent = False
    db.commit()
    context = studio_ai.studio_context(lumea, _brief(lumea))
    assert "bariyer" not in context.lower()
    assert PALETTE not in context
    assert "15% endirim" not in context


def test_validation_still_works_without_consent(db, lumea):
    """Doğrulama LOKALDIR — heç nə göndərmir, ona görə razılıqdan asılı olmamalıdır."""
    lumea.brand_ai_consent = False
    db.commit()
    data = _payload(headline_options=["Dəri baryerini gücləndirən qulluq"])
    assert any("bariyer" in p for p in validate(data, _brief(lumea)))


def test_consent_puts_palette_and_glossary_into_the_prompt(lumea):
    context = studio_ai.studio_context(lumea, _brief(lumea))
    assert "bariyer" in context.lower()
    assert "#D8C7AD" in context


# ── Avtomatik şəkil (#7) ─────────────────────────────────────────────────────────

def test_generated_material_gets_an_image(monkeypatch, db, lumea):
    from app import content_studio

    monkeypatch.setattr(content_studio, "_clean", content_studio._clean)
    asset = create_asset(db, lumea, "Şəkil testi", "POST", "", "", "")
    content_studio.apply_result(db, asset, {
        "ok": True, "headline_options": ["Başlıq"], "caption": "Mətn", "hashtags": [],
        "visual_direction": {"subject": "serum şüşəsi", "palette": "isti bej"},
        "slides": [], "needs_input": [], "confidence": "high",
    })
    db.refresh(asset)
    assert asset.image_url, "şəkil ünvanı yazılmadı"
    assert asset.image_source in ("TestStock", "generated", "stock")


def test_material_without_visual_direction_has_no_image(db, lumea):
    from app import content_studio

    asset = create_asset(db, lumea, "Şəkilsiz", "POST", "", "", "")
    content_studio.apply_result(db, asset, {
        "ok": True, "headline_options": ["Başlıq"], "caption": "Mətn", "hashtags": [],
        "visual_direction": {}, "slides": [], "needs_input": [], "confidence": "high",
    })
    db.refresh(asset)
    assert not asset.image_url


# ── Kampaniya zənginləşdirməsi (#3) ──────────────────────────────────────────────

def _campaign(db, workspace, channels="Instagram", days=7):
    return create_campaign(db, workspace, "LUMÉA launch", "demo müraciətlərini artırmaq",
                           "həssas dəri sahibləri", channels, "0", duration_days=days)


def test_enrichment_replaces_template_text(monkeypatch, db, lumea):
    campaign = _campaign(db, lumea)
    before = {d.day_number: d.hook for d in campaign.days}

    def fake(messages, **kw):
        user = messages[1]["content"]
        numbers = [int(line.split("Gün ")[1].split(":")[0])
                   for line in user.splitlines() if line.startswith("- Gün ")]
        return json.dumps({"days": [
            {"day": n, "theme": f"Bariyer mövzusu {n}", "hook": f"Konkret açılış {n}",
             "cta": "Şərhdə soruşun"} for n in numbers
        ]}, ensure_ascii=False)

    monkeypatch.setattr(campaign_ai, "_call_llm", fake)
    result = enrich_campaign(db, lumea, campaign)
    assert result["updated"] == 7 and result["skipped"] == 0
    for day in campaign.days:
        assert day.hook != before[day.day_number]
        assert day.hook.startswith("Konkret açılış")


def test_enrichment_never_empties_the_plan_when_the_model_fails(monkeypatch, db, lumea):
    campaign = _campaign(db, lumea)
    before = {d.day_number: (d.theme, d.hook, d.cta) for d in campaign.days}

    monkeypatch.setattr(campaign_ai, "_call_llm", lambda messages, **kw: None)
    result = enrich_campaign(db, lumea, campaign)
    assert result["updated"] == 0
    for day in campaign.days:
        assert (day.theme, day.hook, day.cta) == before[day.day_number], "şablon mətni itdi"


def test_enrichment_rejects_non_compliant_days(monkeypatch, db, lumea):
    """Qadağan ifadə və ya sahə etiketi olan gün TƏTBİQ EDİLMİR — şablonda qalır."""
    campaign = _campaign(db, lumea)
    before = {d.day_number: d.hook for d in campaign.days}

    def fake(messages, **kw):
        user = messages[1]["content"]
        numbers = [int(line.split("Gün ")[1].split(":")[0])
                   for line in user.splitlines() if line.startswith("- Gün ")]
        out = []
        for index, n in enumerate(numbers):
            if index == 0:
                out.append({"day": n, "theme": "Mövzu", "hook": "Möcüzəvi nəticə vəd edirik",
                            "cta": "Yazın"})
            elif index == 1:
                out.append({"day": n, "theme": "Faza · etiket", "hook": "Auditoriya: hamı",
                            "cta": "Yazın"})
            else:
                out.append({"day": n, "theme": f"Təmiz mövzu {n}", "hook": f"Təmiz açılış {n}",
                            "cta": "Şərhdə soruşun"})
        return json.dumps({"days": out}, ensure_ascii=False)

    monkeypatch.setattr(campaign_ai, "_call_llm", fake)
    result = enrich_campaign(db, lumea, campaign)
    assert result["skipped"] >= 2, result
    rejected = [d for d in campaign.days if d.hook == before[d.day_number]]
    assert rejected, "pozuntulu gün tətbiq edildi"
    assert not any("Möcüzəvi" in (d.hook or "") for d in campaign.days)
    assert not any("Auditoriya:" in (d.hook or "") for d in campaign.days)


def test_enrichment_batches_by_phase_not_by_day(monkeypatch, db, lumea):
    """30 günlük plan 30 deyil, faza sayı qədər çağırış etməlidir."""
    campaign = _campaign(db, lumea, days=30)
    calls = {"n": 0}

    def fake(messages, **kw):
        calls["n"] += 1
        return None

    monkeypatch.setattr(campaign_ai, "_call_llm", fake)
    enrich_campaign(db, lumea, campaign)
    assert calls["n"] <= 8, f"çox çağırış: {calls['n']}"


# ── Avtomatik kampaniya qaralaması (#2) ──────────────────────────────────────────

def test_finished_project_creates_a_draft_campaign(db, lumea):
    from app.agency import _draft_campaign_for
    from app.db_models import AgentProject

    project = AgentProject(brief="LUMÉA Barrier Restore Serum üçün launch kampaniyası",
                           workspace_id=lumea.id, status="AWAITING_APPROVAL")
    db.add(project)
    db.commit()

    _draft_campaign_for(db, project)
    campaign = db.query(Campaign).filter(Campaign.source_project_id == project.id).first()
    assert campaign is not None
    assert campaign.status == "DRAFT", "qaralama birbaşa PLANNED olmamalıdır"
    assert campaign.days, "qaralamanın planı boşdur"


def test_draft_campaign_is_created_only_once(db, lumea):
    from app.agency import _draft_campaign_for
    from app.db_models import AgentProject

    project = AgentProject(brief="Təkrar test", workspace_id=lumea.id, status="AWAITING_APPROVAL")
    db.add(project)
    db.commit()

    _draft_campaign_for(db, project)
    _draft_campaign_for(db, project)
    assert db.query(Campaign).filter(Campaign.source_project_id == project.id).count() == 1


def test_draft_campaigns_stay_out_of_the_calendar(registered_client, db):
    """Qaralama təqvimi doldurmamalıdır — istifadəçi onu özü işə salır."""
    client = registered_client("draft1@test.az", "Draft WS")
    workspace = db.query(Workspace).filter(Workspace.name == "Draft WS").first()
    live = create_campaign(db, workspace, "CANLI PLAN", "demo müraciətlərini artırmaq",
                           "hamı", "Instagram", "0", duration_days=7)
    draft = create_campaign(db, workspace, "QARALAMA PLAN", "demo müraciətlərini artırmaq",
                            "hamı", "Instagram", "0", duration_days=7)
    draft.status = "DRAFT"
    db.commit()

    page = client.get("/calendar")
    assert "CANLI PLAN" in page.text or live.days[0].theme in page.text
    assert "QARALAMA PLAN" not in page.text


# ── Brand Kit təklif axını (#1) ──────────────────────────────────────────────────

def test_suggestions_are_never_applied_automatically(monkeypatch, db, lumea):
    """ƏSAS QORUYUCU: Brand Kit generasiyanın mənbəyidir — səssiz yazılmamalıdır."""
    from app import brand_sync
    from app.db_models import AgentProject, BrandKitSuggestion

    project = AgentProject(brief="Yeni auditoriya araşdırması", workspace_id=lumea.id,
                           status="AWAITING_APPROVAL")
    db.add(project)
    db.commit()
    before = lumea.brand_voice

    monkeypatch.setattr(brand_sync, "_call_llm", lambda messages, **kw: json.dumps({
        "suggestions": [{"field": "brand_voice", "suggested": "Daha isti və danışıq dilində ton.",
                         "rationale": "Layihədə bu ton işlədi."}]
    }, ensure_ascii=False))

    assert brand_sync.collect_suggestions(db, project) == 1
    db.refresh(lumea)
    assert lumea.brand_voice == before, "Brand Kit avtomatik dəyişdi!"
    assert db.query(BrandKitSuggestion).filter(
        BrandKitSuggestion.status == "PENDING").count() == 1


def test_accepting_a_suggestion_writes_it(db, lumea):
    from app.brand_sync import apply_suggestion
    from app.db_models import BrandKitSuggestion

    suggestion = BrandKitSuggestion(
        workspace_id=lumea.id, field="brand_voice", current_value=lumea.brand_voice,
        suggested_value="Daha isti və danışıq dilində ton.",
    )
    db.add(suggestion)
    db.commit()

    apply_suggestion(db, lumea, suggestion)
    db.refresh(lumea)
    assert lumea.brand_voice == "Daha isti və danışıq dilində ton."
    assert suggestion.status == "ACCEPTED"


def test_protected_fields_cannot_be_suggested(monkeypatch, db, lumea):
    """Rəng, loqo və qadağan ifadələr brendin sərt qərarlarıdır — təklif oluna bilməz."""
    from app import brand_sync
    from app.db_models import AgentProject

    project = AgentProject(brief="Test", workspace_id=lumea.id, status="AWAITING_APPROVAL")
    db.add(project)
    db.commit()
    monkeypatch.setattr(brand_sync, "_call_llm", lambda messages, **kw: json.dumps({
        "suggestions": [
            {"field": "brand_colors", "suggested": "#1E90FF mavi, #FFFFFF ağ"},
            {"field": "brand_forbidden_phrases", "suggested": "heç nə"},
        ]
    }, ensure_ascii=False))

    assert brand_sync.collect_suggestions(db, project) == 0
    db.refresh(lumea)
    assert lumea.brand_colors == PALETTE


def test_no_suggestions_without_consent(monkeypatch, db, lumea):
    """Təklif üçün brend məlumatı modelə göndərilir — bu, məhz razılığın əhatəsidir."""
    from app import brand_sync
    from app.db_models import AgentProject

    lumea.brand_ai_consent = False
    db.commit()
    project = AgentProject(brief="Test", workspace_id=lumea.id, status="AWAITING_APPROVAL")
    db.add(project)
    db.commit()

    called = {"n": 0}

    def fake(messages, **kw):
        called["n"] += 1
        return None

    monkeypatch.setattr(brand_sync, "_call_llm", fake)
    assert brand_sync.collect_suggestions(db, project) == 0
    assert called["n"] == 0, "razılıq yoxdur, amma model çağırıldı!"


# ── Qadağan siyahısının parsinqi — canlı Brand Kit-də tapıldı ────────────────────
#
# LUMÉA siyahını BİR SƏTİRDƏ vergüllə yazmışdı. Parser yalnız sətir sonuna görə bölürdü,
# ona görə bütün siyahı bir «ifadə» olurdu və nəticə hər iki istiqamətdə səhv çıxırdı.

REAL_LIST = ("Möcüzəvi nəticə, dərhal müalicə, zəmanətli nəticə, "
             "bütün dəri problemlərini həll edir, tibbi sübutsuz iddialar, aqressiv satış təzyiqi.")


def _rules_with(text, db):
    workspace = Workspace(name="Vergül testi", slug="comma", brand_forbidden_phrases=text)
    db.add(workspace)
    db.commit()
    return rules_from_workspace(workspace)


def test_comma_separated_list_becomes_separate_phrases(db):
    rules = _rules_with(REAL_LIST, db)
    assert len(rules.must_avoid) == 6, rules.must_avoid
    assert "Möcüzəvi nəticə" in rules.must_avoid


def test_banned_phrase_in_a_comma_list_is_caught(db):
    """Əvvəl bu TƏMİZ keçirdi — siyahı tək ifadə sayıldığı üçün."""
    rules = _rules_with(REAL_LIST, db)
    assert check_text("Bu serum möcüzəvi nəticə verir.", rules)
    assert check_text("Zəmanətli nəticə təklif edirik.", rules)


def test_ordinary_sentence_is_not_blocked_by_a_long_description(db):
    """Əvvəl «problemlərini» sözü olan hər cümlə bloklanırdı — ən uzun söz kimi seçilirdi."""
    rules = _rules_with(REAL_LIST, db)
    assert check_text("Həssas dərinin problemlərini sadə dildə izah edirik.", rules) == []
    assert check_text("Dəri tipləri haqqında sakit, savadlı izah.", rules) == []


def test_long_banned_description_still_matches_in_full(db):
    rules = _rules_with(REAL_LIST, db)
    assert any("bütün dəri problemlərini həll edir" in p
               for p in check_text("Bütün dəri problemlərini həll edir.", rules))


def test_short_phrase_still_matches_by_stem(db):
    """«möcüzəvi nəticə» siyahıdadırsa «möcüzəvi effekt» də tutulmalıdır."""
    rules = _rules_with(REAL_LIST, db)
    assert check_text("Bu serum möcüzəvi effekt verir.", rules)


def test_neutral_white_is_not_a_palette_violation(lumea):
    """Canlı sınaqda tapıldı: model açıq fil sümüyünü «yumşaq ağ» adlandırdı və düzgün
    çıxış NEEDS_INPUT-a düşdü. «ağ»/«qara» neytraldır — şikayətin mövzusu MAVİ idi."""
    data = _payload(visual_direction={"palette": "yumşaq ağ fon, isti bej #D8C7AD"})
    assert not any("palette" in p for p in validate(data, _brief(lumea)))


def test_blue_is_still_a_palette_violation(lumea):
    data = _payload(visual_direction={"palette": "təmiz mavi və ağ fon"})
    assert any("mavi" in p for p in validate(data, _brief(lumea)))


def test_confidence_is_high_when_brand_kit_supplies_the_facts(monkeypatch, db, lumea):
    """Faktın OLMASI vacibdir, haradan gəldiyi yox — əvvəl yalnız forma sahəsinə baxırdı."""
    from app import studio_ai as m

    monkeypatch.setattr(m, "_call_llm", lambda messages, **kw: json.dumps(_payload(), ensure_ascii=False))
    result = m.generate_draft(lumea, _brief(lumea))          # forma faktı YOXDUR
    assert result["ok"] and result["confidence"] == "high"


def test_confidence_is_low_without_any_facts(monkeypatch, db):
    from app import studio_ai as m

    workspace = Workspace(name="Faktsız", slug="nofacts", brand_ai_consent=True)
    db.add(workspace)
    db.commit()
    monkeypatch.setattr(m, "_call_llm", lambda messages, **kw: json.dumps(_payload(), ensure_ascii=False))
    result = m.generate_draft(workspace, StudioBrief(**_brand_fields(workspace)))
    assert result["confidence"] == "low"


# ── Veo günlük sərt limiti ───────────────────────────────────────────────────────
#
# Google-un büdcəsi yalnız XƏBƏRDARLIQ göndərir, kəsmir — ona görə kəsmə tətbiqin
# öz tərəfindədir. Bu testlər limitin həqiqətən kəsdiyini qoruyur.

def test_veo_is_off_by_default(db):
    from app import veo

    assert veo.enabled() is False
    assert veo.allowed(db) is False
    assert veo.start({"subject": "test"}) is None


def test_veo_stops_at_the_daily_limit(monkeypatch, db):
    from app import veo
    from app.core import settings

    monkeypatch.setattr(settings, "gemini_api_key", "x")
    monkeypatch.setattr(settings, "veo_enabled", True)
    monkeypatch.setattr(settings, "veo_daily_limit", 3)

    for i in range(3):
        assert veo.allowed(db) is True, f"{i}-cü videoda vaxtından əvvəl kəsdi"
        veo.record(db, workspace_id=1, asset_id=None)

    assert veo.allowed(db) is False, "limit dolub, amma kəsmədi"
    assert veo.budget(db)["left"] == 0


def test_veo_budget_reports_cost(monkeypatch, db):
    from app import veo
    from app.core import settings

    monkeypatch.setattr(settings, "veo_daily_limit", 10)
    monkeypatch.setattr(settings, "veo_cost_per_video", 0.40)
    veo.record(db, workspace_id=1, asset_id=None)
    b = veo.budget(db)
    assert b["used"] == 1 and b["spent"] == 0.40 and b["cap"] == 4.0


def test_zero_limit_blocks_everything(monkeypatch, db):
    from app import veo
    from app.core import settings

    monkeypatch.setattr(settings, "gemini_api_key", "x")
    monkeypatch.setattr(settings, "veo_enabled", True)
    monkeypatch.setattr(settings, "veo_daily_limit", 0)
    assert veo.allowed(db) is False
