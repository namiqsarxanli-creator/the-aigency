from datetime import date

from app.analytics import build_analytics
from app.db_models import CampaignMetric, Workspace


def test_zero_reach_snapshot_does_not_break_analytics(db):
    workspace = Workspace(name="Analitika", slug="analitika")
    db.add(workspace)
    db.flush()
    db.add(CampaignMetric(
        workspace_id=workspace.id,
        recorded_date=date.today(),
        platform="Instagram",
        content_type="Instagram Post #1",
        impressions=0,
        reach=0,
        engagements=0,
    ))
    db.commit()

    report = build_analytics(db, workspace.id)

    assert report["has_data"] is True
    assert report["totals"]["reach"] == 0
    assert report["trend"][0]["height"] == 8


def test_analytics_page_accepts_empty_campaign_filter(registered_client):
    """Filtr formasindaki "Bütün kampaniyalar" secimi `?campaign=` (bos deyer) gonderir —
    evvel FastAPI bunu int-e cevire bilmeyib 422 JSON xetasi qaytarirdi (canli tapinti)."""
    client = registered_client("analytics@test.az", "Analitika MMC")

    response = client.get("/analytics?campaign=")

    assert response.status_code == 200
    assert "Kampaniya analitikası" in response.text


def test_analytics_page_accepts_valid_campaign_filter(registered_client):
    client = registered_client("analytics2@test.az", "Analitika MMC2")

    assert client.get("/analytics?campaign=999").status_code == 200
    assert client.get("/analytics").status_code == 200
