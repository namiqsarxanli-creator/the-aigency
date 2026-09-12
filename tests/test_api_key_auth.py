"""Avtomasiya marşrutlarının API açarı ilə qorunması.

TARİXÇƏ: `AGENCY_API_KEY` boş qaldıqda `/agency/pending-approval`, `/agency/{id}/image` və
`/mark-notified` marşrutları TAMAMİLƏ autentifikasiyasız idi və BÜTÜN workspace-lərin gözləyən
layihələrini (brif, Telegram chat ID, şəkil linki) qaytarırdı — canlı sınaqda ayrı hesabdan
başqa workspace-in layihəsi oxundu. Bu testlər açar qoyulduqda həmin qapıların bağlandığını
və düzgün açarla n8n-in hələ də işlədiyini yoxlayır.
"""
import pytest

from app.core import settings
from app.db_models import AgentProject, Workspace

KEY = "test-agency-key-12345"
# HTTP başlıqları yalnız ASCII qəbul edir — Azərbaycan hərfləri burada işləmir.
WRONG_KEY = "wrong-key"


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(settings, "agency_api_key", KEY)
    return KEY


@pytest.fixture
def legacy_workspace(db):
    """`workspace_scope` açarla gələn avtomasiyanı "legacy" workspace-ə bağlayır — o olmasa 503."""
    workspace = Workspace(name="The Agency", slug="legacy")
    db.add(workspace)
    db.commit()
    return workspace


@pytest.fixture
def pending_project(db, legacy_workspace):
    """Telegram bildirişi gözləyən layihə (pending-approval yalnız chat_id-si olanları qaytarır)."""
    workspace = legacy_workspace
    project = AgentProject(
        brief="Məxfi brif — başqa workspace", status="AWAITING_APPROVAL",
        telegram_chat_id="123456", notified=False, workspace_id=workspace.id,
        share_token="test-token-abc", deliverable_image_url="https://example.test/x.jpg",
    )
    db.add(project)
    db.commit()
    return project


def test_pending_approval_requires_key(client, api_key, pending_project):
    assert client.get("/agency/pending-approval").status_code == 401
    assert client.get("/agency/pending-approval", headers={"X-API-Key": WRONG_KEY}).status_code == 401

    ok = client.get("/agency/pending-approval", headers={"X-API-Key": KEY})
    assert ok.status_code == 200
    assert ok.json()["id"] == pending_project.id


def test_mark_notified_requires_key(client, api_key, pending_project):
    path = f"/agency/{pending_project.id}/mark-notified"
    assert client.post(path).status_code == 401
    assert client.post(path, headers={"X-API-Key": KEY}).status_code == 200


def test_image_endpoint_requires_key(client, api_key, pending_project):
    """ID əsaslı şəkil ünvanı sadalana bilər — açarsız bağlı olmalıdır."""
    assert client.get(f"/agency/{pending_project.id}/image").status_code == 401


def test_public_image_uses_unguessable_token(client, api_key, pending_project, monkeypatch):
    """Instagram/Meta başlıq göndərə bilmir, ona görə token əsaslı ünvan AÇIQ qalmalıdır —
    amma yalnız düzgün token ilə."""
    import app.api as api_module

    monkeypatch.setitem(api_module._image_cache, pending_project.id, b"\xff\xd8fake-jpeg")

    ok = client.get(f"/s/{pending_project.share_token}/image")
    assert ok.status_code == 200
    assert ok.content == b"\xff\xd8fake-jpeg"

    assert client.get("/s/tamam-yanlis-token/image").status_code == 404


def test_brief_creation_requires_key_without_session(client, api_key, legacy_workspace):
    """Sessiyasız brif yaratmaq yalnız düzgün açarla mümkün olmalıdır (LLM kvotası qorunur)."""
    assert client.post("/agency/brief", json={"brief": "İcazəsiz brif"}).status_code == 401
    assert client.post(
        "/agency/brief", json={"brief": "İcazəli brif"}, headers={"X-API-Key": KEY},
    ).status_code == 200


def test_empty_key_keeps_local_demo_open(client, monkeypatch, pending_project):
    """Açar BOŞ olanda köhnə (lokal demo) davranış qalır — bu, qəsdən belədir, amma
    məhz buna görə .env-də açarın doldurulması tövsiyə olunur."""
    monkeypatch.setattr(settings, "agency_api_key", "")
    assert client.get("/agency/pending-approval").status_code == 200
