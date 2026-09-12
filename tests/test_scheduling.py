"""Planlaşdırılmış avtomatik paylaşım — /content-studio/{id}/schedule (Bakı yerli vaxtı) və
arxa fon tetiklənməsi (`app.scheduler.publish_due_scheduled_content`)."""
from datetime import datetime, timedelta, timezone

import pytest

from app import instagram
from app.db_models import ContentAsset, Workspace
from app.night_shift import BAKU
from app.scheduler import publish_due_scheduled_content


def _future_local_str(hours=2):
    future = datetime.now(BAKU) + timedelta(hours=hours)
    return future.strftime("%Y-%m-%dT%H:%M")


def _reel(workspace_id, **overrides):
    defaults = dict(
        workspace_id=workspace_id, title="Test Reel", format="REEL", aspect_ratio="9:16",
        caption="Test caption", status="APPROVED", video_url="https://example.test/v.mp4",
    )
    defaults.update(overrides)
    return ContentAsset(**defaults)


def test_schedule_rejects_unavailable_platform(registered_client, db):
    client = registered_client("sched1@test.az", "Schedule MMC1")
    ws = db.query(Workspace).filter(Workspace.name == "Schedule MMC1").first()
    asset = _reel(ws.id)
    db.add(asset); db.commit()

    response = client.post(f"/content-studio/{asset.id}/schedule", data={
        "scheduled_at": _future_local_str(), "platforms": "instagram",
    }, follow_redirects=False)

    assert response.status_code == 303
    assert "sched_platform_unavailable" in response.headers["location"]
    db.refresh(asset)
    assert asset.scheduled_at is None


def test_schedule_converts_baku_local_time_to_utc(registered_client, db):
    client = registered_client("sched2@test.az", "Schedule MMC2")
    ws = db.query(Workspace).filter(Workspace.name == "Schedule MMC2").first()
    ws.instagram_access_token = "tok"; ws.instagram_user_id = "1"; ws.instagram_addon_enabled = True
    db.commit()
    asset = _reel(ws.id)
    db.add(asset); db.commit()

    local_str = _future_local_str(3)
    response = client.post(f"/content-studio/{asset.id}/schedule", data={
        "scheduled_at": local_str, "platforms": "instagram",
    }, follow_redirects=False)

    assert response.status_code == 303
    assert "sched_set" in response.headers["location"]
    db.refresh(asset)
    assert asset.scheduled_platforms == "instagram"
    expected_utc = (
        datetime.strptime(local_str, "%Y-%m-%dT%H:%M")
        .replace(tzinfo=BAKU).astimezone(timezone.utc).replace(tzinfo=None)
    )
    assert abs((asset.scheduled_at - expected_utc).total_seconds()) < 2


def test_schedule_rejects_past_datetime(registered_client, db):
    client = registered_client("sched3@test.az", "Schedule MMC3")
    ws = db.query(Workspace).filter(Workspace.name == "Schedule MMC3").first()
    ws.instagram_access_token = "tok"; ws.instagram_user_id = "1"; ws.instagram_addon_enabled = True
    db.commit()
    asset = _reel(ws.id)
    db.add(asset); db.commit()

    past = (datetime.now(BAKU) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    response = client.post(f"/content-studio/{asset.id}/schedule", data={
        "scheduled_at": past, "platforms": "instagram",
    }, follow_redirects=False)

    assert "sched_past" in response.headers["location"]


def test_schedule_cancel_clears_fields(registered_client, db):
    client = registered_client("sched4@test.az", "Schedule MMC4")
    ws = db.query(Workspace).filter(Workspace.name == "Schedule MMC4").first()
    ws.instagram_access_token = "tok"; ws.instagram_user_id = "1"; ws.instagram_addon_enabled = True
    db.commit()
    asset = _reel(ws.id)
    db.add(asset); db.commit()

    client.post(f"/content-studio/{asset.id}/schedule", data={
        "scheduled_at": _future_local_str(), "platforms": "instagram",
    })
    db.refresh(asset)
    assert asset.scheduled_at is not None

    client.post(f"/content-studio/{asset.id}/schedule/cancel")
    db.refresh(asset)
    assert asset.scheduled_at is None
    assert asset.scheduled_platforms is None


def test_publish_due_scheduled_content_publishes_and_clears(db, monkeypatch):
    from app.core import settings

    ws = Workspace(
        name="Auto MMC", slug="auto-mmc", instagram_access_token="tok",
        instagram_user_id="1", instagram_addon_enabled=True,
    )
    db.add(ws); db.commit()
    asset = _reel(ws.id, scheduled_at=datetime.utcnow() - timedelta(minutes=1), scheduled_platforms="instagram")
    db.add(asset); db.commit()

    monkeypatch.setattr(settings, "social_publish_enabled", True)
    monkeypatch.setattr(
        instagram, "publish_reel",
        lambda account, url, caption: {"id": "123", "permalink": "https://instagram.test/p/1"},
    )

    published = publish_due_scheduled_content(db)

    assert published == 1
    db.refresh(asset)
    assert asset.instagram_published is True
    assert asset.instagram_post_id == "123"
    assert asset.scheduled_at is None
    assert asset.scheduled_platforms is None
    assert asset.schedule_error is None


def test_publish_due_scheduled_content_records_error_without_retry_loop(db, monkeypatch):
    """Uğursuz cəhddən sonra `scheduled_at` YENƏ DƏ təmizlənməlidir — sonsuz təkrar cəhd yoxdur,
    xəta yalnız `schedule_error`-da görünür (istifadəçi əl ilə təkrar cəhd edə bilər)."""
    from app import instagram as instagram_module
    from app.core import settings

    ws = Workspace(
        name="Fail MMC", slug="fail-mmc", instagram_access_token="tok",
        instagram_user_id="1", instagram_addon_enabled=True,
    )
    db.add(ws); db.commit()
    asset = _reel(ws.id, scheduled_at=datetime.utcnow() - timedelta(minutes=1), scheduled_platforms="instagram")
    db.add(asset); db.commit()

    monkeypatch.setattr(settings, "social_publish_enabled", True)

    def _boom(account, url, caption):
        raise instagram_module.InstagramError("test şəbəkə xətası")

    monkeypatch.setattr(instagram_module, "publish_reel", _boom)

    published = publish_due_scheduled_content(db)

    assert published == 0
    db.refresh(asset)
    assert asset.instagram_published is False
    assert asset.scheduled_at is None
    assert asset.scheduled_platforms is None
    assert asset.schedule_error
