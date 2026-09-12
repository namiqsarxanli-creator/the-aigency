"""Instagram paylaşımı — workspace-ə bağlı, əlavə ödənişli paket.

TARİXÇƏ (KRİTİK): əvvəl `instagram.py`-nin bütün funksiyaları birbaşa qlobal
`settings.instagram_access_token` oxuyurdu. Yəni İSTƏNİLƏN müştəri workspace-indən "Paylaş"
düyməsinə basıldıqda kontent tətbiq SAHİBİNİN Instagram hesabına — real, ictimai hesaba —
dərc olunurdu. İndi hesab workspace-ə bağlıdır və qlobala fallback QƏSDƏN YOXDUR.
"""
import pytest

from app import instagram
from app.core import settings
from app.db_models import AgentProject, Workspace


@pytest.fixture
def workspace(db):
    ws = Workspace(name="Müştəri MMC", slug="musteri")
    db.add(ws)
    db.commit()
    return ws


def test_account_is_none_when_not_connected(workspace):
    assert instagram.account_for(workspace) is None


def test_account_is_none_when_addon_disabled(db, workspace):
    """Token olsa BELƏ paket söndürülübsə paylaşım olmamalıdır."""
    workspace.instagram_access_token = "tok"
    workspace.instagram_user_id = "123"
    workspace.instagram_addon_enabled = False
    db.commit()
    assert instagram.account_for(workspace) is None


def test_account_returned_when_connected(db, workspace):
    workspace.instagram_access_token = "tok"
    workspace.instagram_user_id = "123"
    workspace.instagram_addon_enabled = True
    db.commit()
    account = instagram.account_for(workspace)
    assert account is not None
    assert (account.access_token, account.user_id) == ("tok", "123")


def test_no_fallback_to_global_env(db, workspace, monkeypatch):
    """ƏSAS QORUYUCU: qlobal .env hesabı doldurulsa belə, qoşulmamış workspace üçün
    hesab qaytarılmamalıdır — əks halda köhnə çarpaz-kirayəçi bugu geri qayıdar."""
    monkeypatch.setattr(settings, "instagram_access_token", "SAHIBIN-TOKENI")
    monkeypatch.setattr(settings, "instagram_user_id", "999")
    assert instagram.account_for(workspace) is None


def test_guard_rejects_unconnected_account():
    with pytest.raises(instagram.InstagramError, match="əlavə paket"):
        instagram._guard(instagram.IgAccount("", ""), "https://example.test/a.jpg")


def test_publish_blocked_with_402_when_not_connected(registered_client, db, monkeypatch):
    """UI düyməni gizlətsə də API birbaşa çağırıla bilər — server də bloklamalıdır."""
    monkeypatch.setattr(settings, "external_actions_enabled", True)
    client = registered_client("ig@test.az", "IG MMC")
    project_id = client.post("/agency/brief", json={"brief": "Instagram postu hazırla"}).json()["id"]

    project = db.query(AgentProject).filter(AgentProject.id == project_id).first()
    project.output_type = "social_post"
    project.status = "AWAITING_APPROVAL"
    project.deliverable_html = "Post mətni"
    project.deliverable_image_url = "https://example.test/a.jpg"
    db.commit()

    response = client.post(f"/agency/{project_id}/publish-instagram")
    assert response.status_code == 402
    assert "əlavə paket" in response.json()["detail"]


def test_project_detail_reports_instagram_unavailable(registered_client, db):
    """UI bu bayrağa görə düymə yerinə paket təklifi göstərir."""
    client = registered_client("ig2@test.az", "IG2 MMC")
    project_id = client.post("/agency/brief", json={"brief": "Instagram postu"}).json()["id"]
    assert client.get(f"/agency/{project_id}").json()["instagram_available"] is False


def test_project_detail_reports_instagram_available_when_connected(registered_client, db):
    client = registered_client("ig3@test.az", "IG3 MMC")
    project_id = client.post("/agency/brief", json={"brief": "Instagram postu"}).json()["id"]

    workspace = db.query(Workspace).filter(Workspace.name == "IG3 MMC").first()
    workspace.instagram_access_token = "tok"
    workspace.instagram_user_id = "123"
    workspace.instagram_addon_enabled = True
    db.commit()

    assert client.get(f"/agency/{project_id}").json()["instagram_available"] is True


def test_pricing_page_explains_the_addon(client):
    response = client.get("/pricing")
    assert response.status_code == 200
    assert "Instagram" in response.text
