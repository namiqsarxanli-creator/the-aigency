"""Təhvil paketi — çap-hazır hesabat və ZIP arxiv.

Xüsusi diqqət: Azərbaycan hərfləri (ə, ğ, ı, ş, ç, ö, ü) həm HTML-də, həm ZIP faylının
məzmununda düzgün kodlaşdırılmalıdır — köhnə kodlaşdırma səhvləri məhz burada üzə çıxır.
"""
import io
import zipfile

import pytest

from app.agency import advance_project, create_project
from app.export import build_zip, collect_bundle, render_report_html, zip_filename
from app.db_models import Campaign, CampaignDay, ContentAsset, Workspace


@pytest.fixture
def finished_project(db):
    project = create_project(db, "Eko-dostu qəhvə brendi üçün İSTİLİK kampaniyası")
    for _ in range(40):
        if advance_project(db, project) is None:
            break
    return project


def test_bundle_collects_all_department_outputs(db, finished_project):
    bundle = collect_bundle(db, finished_project)
    roles = {section["role"] for section in bundle["sections"]}
    assert {"strategist", "copywriter", "designer", "developer", "marketing", "analytics"} <= roles
    assert roles.isdisjoint({"legal", "finance"})


def test_report_html_is_self_contained(db, finished_project):
    html = render_report_html(collect_bundle(db, finished_project), "Test Şirkət")
    assert html.startswith("<!doctype html>")
    # Xarici asset olmamalıdır ki, fayl oflayn saxlanılanda da eyni görünsün.
    assert "<link" not in html and "<script src" not in html
    assert "window.print()" in html, "Çap düyməsi olmalıdır"


def test_report_preserves_azerbaijani_characters(db, finished_project):
    html = render_report_html(collect_bundle(db, finished_project), "Şirkət Ə")
    assert "Şirkət Ə" in html
    assert "İSTİLİK" in html, "Brifdəki hərflər olduğu kimi qalmalıdır"


def test_report_escapes_html_in_outputs(db, finished_project):
    """Agent çıxışı XAM HTML ola bilir (developer rolu belədir) — hesabatda İCRA olunmamalı,
    kod kimi GÖRÜNMƏLİDİR. Əks halda modelin yazdığı <script> hesabatı açan şəxsdə işləyərdi."""
    from app.db_models import AgentTask

    developer = db.query(AgentTask).filter(
        AgentTask.project_id == finished_project.id, AgentTask.role == "developer"
    ).first()
    developer.output = "<script>alert('xss')</script><p>Salam</p>"
    db.commit()

    html = render_report_html(collect_bundle(db, finished_project), "Test")
    assert "<script>alert('xss')</script>" not in html, "Skript xam şəkildə keçməməlidir!"
    assert "&lt;script&gt;" in html, "Kod escape edilib görünməlidir"


def test_zip_contains_expected_files(db, finished_project):
    archive = zipfile.ZipFile(io.BytesIO(build_zip(collect_bundle(db, finished_project))))
    assert archive.testzip() is None, "ZIP zədəli olmamalıdır"

    names = archive.namelist()
    assert "00-brif.txt" in names
    assert "OXU-MENI.txt" in names
    assert any(name.startswith("01-") for name in names)
    assert any("deliverable" in name for name in names)


def test_zip_contents_are_valid_utf8(db, finished_project):
    archive = zipfile.ZipFile(io.BytesIO(build_zip(collect_bundle(db, finished_project))))
    brief = archive.read("00-brif.txt").decode("utf-8")
    assert "İSTİLİK" in brief and "qəhvə" in brief


def test_zip_filename_is_filesystem_safe(db, finished_project):
    name = zip_filename(finished_project)
    assert name.endswith(".zip")
    # Azərbaycan hərfləri və boşluqlar fayl adında problem yaradır — transliterasiya olunmalıdır.
    assert all(char.isascii() for char in name), f"Fayl adı ASCII olmalıdır: {name}"
    assert " " not in name


def test_social_zip_excludes_developer_and_includes_actionable_calendar(db, finished_project):
    workspace = Workspace(name="ZIP Test", slug="zip-test")
    db.add(workspace)
    db.flush()
    finished_project.workspace_id = workspace.id
    finished_project.output_type = "social_post"
    campaign = Campaign(
        workspace_id=finished_project.workspace_id, name="7 günlük təqdimat",
        objective="Məhsulu tanıtmaq", channels="Instagram",
        source_project_id=finished_project.id,
    )
    db.add(campaign)
    db.flush()
    day = CampaignDay(
        campaign_id=campaign.id, day_number=1, platform="Instagram",
        content_type="REEL", theme="Məhsulun təqdimatı",
        hook="İlk 3 saniyədə nəticəni göstər", cta="DM yazın", status="PLANNED",
    )
    db.add(day)
    db.flush()
    db.add(ContentAsset(
        workspace_id=finished_project.workspace_id, campaign_day_id=day.id,
        title="Təqdimat Reeli", format="REEL", aspect_ratio="9:16",
        caption="Yeni məhsulumuzu kəşf edin", visual_brief="Yaxın plan məhsul videosu",
        status="DRAFT",
    ))
    db.commit()

    archive = zipfile.ZipFile(io.BytesIO(build_zip(collect_bundle(db, finished_project))))
    names = archive.namelist()
    assert not any("developer" in name for name in names)
    assert "02-7-gunluk-paylasim-plani.txt" in names
    assert "03-kontent-teqvimi.csv" in names
    assert "04-caption-ve-mesajlar.txt" in names
    assert "05-olcme-plani.txt" in names
    plan = archive.read("02-7-gunluk-paylasim-plani.txt").decode("utf-8")
    assert "Instagram" in plan and "REEL" in plan and "DM yazın" in plan
    calendar = archive.read("03-kontent-teqvimi.csv").decode("utf-8-sig")
    assert "Platforma" in calendar and "Məhsulun təqdimatı" in calendar


def test_export_requires_login(client):
    response = client.get("/agency/1/export/zip", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
