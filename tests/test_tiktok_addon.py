"""TikTok paylaşımı — Instagram-a bənzər workspace-ə bağlı əlavə paket, amma OAuth ilə qoşulur.

Burada Meta ilə eyni tapıntı qorunur: qlobal fallback QƏSDƏN yoxdur, hər workspace yalnız
ÖZÜ qoşduğu hesaba paylaşa bilər (bax `test_instagram_addon.py`-dəki tarixçə qeydi)."""
import pytest

from app import tiktok
from app.db_models import Workspace


@pytest.fixture
def workspace(db):
    ws = Workspace(name="Müştəri MMC", slug="musteri-tt")
    db.add(ws)
    db.commit()
    return ws


def test_account_is_none_when_not_connected(workspace):
    assert tiktok.account_for(workspace) is None


def test_account_is_none_when_addon_disabled(db, workspace):
    workspace.tiktok_access_token = "tok"
    workspace.tiktok_refresh_token = "ref"
    workspace.tiktok_open_id = "abc"
    workspace.tiktok_addon_enabled = False
    db.commit()
    assert tiktok.account_for(workspace) is None


def test_account_returned_when_connected(db, workspace):
    workspace.tiktok_access_token = "tok"
    workspace.tiktok_refresh_token = "ref"
    workspace.tiktok_open_id = "abc"
    workspace.tiktok_addon_enabled = True
    db.commit()
    account = tiktok.account_for(workspace)
    assert account is not None
    assert (account.access_token, account.refresh_token, account.open_id) == ("tok", "ref", "abc")


def test_no_fallback_to_global_app_credentials(db, workspace, monkeypatch):
    """Qlobal TikTok app açarları (client key/secret) doldurulsa belə, bunlar app kimliyidir —
    heç bir workspace-in ƏVƏZİNƏ istifadəçi tokeni deyil, ona görə qoşulmamış workspace None
    qaytarmalıdır."""
    from app.core import settings

    monkeypatch.setattr(settings, "tiktok_client_key", "APP-KEY")
    monkeypatch.setattr(settings, "tiktok_client_secret", "APP-SECRET")
    assert tiktok.account_for(workspace) is None


def test_publish_rejects_unconnected_account():
    with pytest.raises(tiktok.TikTokError, match="qoşulmayıb"):
        tiktok.publish_video(tiktok.TikTokAccount("", "", ""), "https://example.test/a.mp4", "caption")


def test_publish_rejects_local_url(db, workspace):
    workspace.tiktok_access_token = "tok"
    workspace.tiktok_refresh_token = "ref"
    workspace.tiktok_open_id = "abc"
    workspace.tiktok_addon_enabled = True
    db.commit()
    account = tiktok.account_for(workspace)
    with pytest.raises(tiktok.TikTokError, match="lokaldır"):
        tiktok.publish_video(account, "http://127.0.0.1:8800/media/a.mp4", "caption")


def test_connect_redirects_to_login_when_disabled_and_configured(client, monkeypatch):
    """App konfiqurasiya edilməyibsə `/tiktok/connect` Brand Kit-ə xəbərlə qaytarmalıdır,
    login olmuş istifadəçi kontekstində."""
    from app.core import settings

    monkeypatch.setattr(settings, "tiktok_client_key", "")
    response = client.get("/tiktok/connect", follow_redirects=False)
    assert response.status_code in (303, 307)
