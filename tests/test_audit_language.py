"""Audit və təklif mətnləri MÜŞTƏRİNİN başa düşdüyü dildə olmalıdır.

TARİXÇƏ: audit nəticələri "P1 · Meta description yoxdur; axtarış snippet-i idarə edilmir",
"P2 · LocalBusiness schema-nı əlaqələndirin", "Gün 1 · GA4/Tag Manager ... QA edin" kimi
mətnlərlə doluydu. Bu hesabat restoran və ya mağaza sahibinə göstərilir — o adam nə "P1",
nə "meta description", nə də "GA4" bilir. Nəticədə təklif "texniki sənəd" təsiri bağışlayır
və satmır. Bu testlər həmin terminlərin geri qayıtmasının qarşısını alır.
"""
import json

import pytest

from app import sales_intelligence
from app.db_models import LeadAudit, SalesLead, Workspace

# Müştəriyə GÖSTƏRİLƏN mətndə olmamalı terminlər. Bunlar HTML-i skan edən regex-lərdə
# sərbəst işlənə bilər — test yalnız istifadəçiyə çatan sətirləri yoxlayır.
JARGON = [
    "P1 ", "P2 ", "P3 ", "KRİTİK",
    "CTA", "SEO title", "meta description", "Meta description",
    "canonical", "viewport", "snippet", "schema",
    "GA4", "Tag Manager", "Meta Pixel", "conversion event",
    "workflow", "pilot", "alt mətni", "Open Graph", "testimonial",
    "case study", "lead formu", "QA edin", "indeksləmə", "HTML həcmi",
]


@pytest.fixture
def lead(db):
    workspace = Workspace(name="Test MMC", slug="test-mmc")
    db.add(workspace)
    db.flush()
    item = SalesLead(
        workspace_id=workspace.id, company_name="Kafe Nur", website=None,
        city="Bakı", phone=None, email=None, source_external_id="test-lead-1",
    )
    db.add(item)
    db.commit()
    return item


def _all_customer_text(audit: LeadAudit) -> str:
    """Auditin müştəriyə göstərilən BÜTÜN mətnini bir yerə yığır."""
    details = json.loads(audit.details_json or "{}")
    parts = [audit.summary]
    for key in ("strengths_json", "issues_json", "opportunities_json"):
        parts.extend(json.loads(getattr(audit, key) or "[]"))
    parts.extend(details.get("action_plan", []))
    parts.extend(details.get("priorities", []))
    for section in details.get("sections", []):
        parts.append(section.get("name", ""))
        parts.extend(section.get("findings", []))
    return "\n".join(parts)


def test_audit_text_has_no_jargon(db, lead):
    """Saytı olmayan lead — offline işləyir, şəbəkəyə çıxmır."""
    audit = sales_intelligence.audit_lead(db, lead)
    text = _all_customer_text(audit)
    found = [term for term in JARGON if term in text]
    assert not found, f"Müştəri mətnində jarqon qaldı: {found}"


def test_priority_labels_are_plain_words(db, lead):
    audit = sales_intelligence.audit_lead(db, lead)
    text = _all_customer_text(audit)
    # Ən azı bir tapıntı sadə prioritet etiketi daşımalıdır.
    assert any(label in text for label in ("Təcili", "Vacib", "Faydalı"))


def test_findings_explain_business_impact(db, lead):
    """Tapıntı yalnız "nə səhvdir" deyil, "bu sizə nəyə başa gəlir" də deməlidir —
    əks halda müştəri niyə pul xərcləməli olduğunu anlamır."""
    audit = sales_intelligence.audit_lead(db, lead)
    issues = json.loads(audit.issues_json or "[]")
    assert issues, "Saytı olmayan lead üçün ən azı bir problem gözlənilir"
    impact_words = ("müştəri", "sifariş", "itki", "itir", "tapa bilmir", "pul", "rəqib")
    assert any(any(word in issue.lower() for word in impact_words) for issue in issues)


def test_section_names_are_plain(db, lead):
    audit = sales_intelligence.audit_lead(db, lead)
    names = {s["name"] for s in json.loads(audit.details_json)["sections"]}
    # Köhnə, texniki adlar qayıtmamalıdır.
    assert "Konversiya yolu" not in names
    assert "SEO və tapılma" not in names
    assert "Əlçatanlıq və paylaşım" not in names
    assert "Google-da tapılma" in names


def test_action_plan_is_written_for_the_customer(db, lead):
    audit = sales_intelligence.audit_lead(db, lead)
    plan = json.loads(audit.details_json)["action_plan"]
    assert len(plan) == 7
    joined = " ".join(plan)
    assert "GA4" not in joined and "canonical" not in joined and "QA" not in joined
    assert "1-ci gün" in joined


def test_proposal_az_is_plain(db, lead):
    audit = sales_intelligence.audit_lead(db, lead)
    proposal = sales_intelligence.create_proposal(db, lead.workspace_id, lead, audit, "AZ")
    text = f"{proposal.problem} {proposal.solution}"
    found = [term for term in JARGON if term in text]
    assert not found, f"Təklif mətnində jarqon qaldı: {found}"


def test_proposal_en_translates_section_names(db, lead):
    """QORUYUCU: `create_proposal`-dakı tərcümə cədvəlinin açarları `audit_lead`-dəki bölmə
    adları ilə eyni olmalıdır. Bölmə adlarını dəyişəndə bu cədvəl köhnəlirdi və ingiliscə
    təklifə Azərbaycanca ad düşürdü — səssiz bug idi."""
    audit = sales_intelligence.audit_lead(db, lead)
    proposal = sales_intelligence.create_proposal(db, lead.workspace_id, lead, audit, "EN")
    # Ən zəif 3 bölmənin adı tərcümə olunmalıdır; azərbaycanca ad sızmamalıdır.
    for az_name in json.loads(audit.details_json)["sections"]:
        assert az_name["name"] not in proposal.problem, (
            f"Tərcümə cədvəlində {az_name['name']!r} açarı yoxdur — ingiliscə təklifə AZ ad düşdü"
        )


def test_meeting_brief_has_no_jargon(db, lead):
    brief = sales_intelligence.create_meeting_brief(db, lead.workspace_id, lead)
    text = " ".join(json.loads(brief.objections_json)) + " " + (brief.agenda or "")
    found = [term for term in JARGON if term in text]
    assert not found, f"Görüş brifində jarqon qaldı: {found}"
