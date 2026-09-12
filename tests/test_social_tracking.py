from datetime import datetime, timedelta

from app import social_tracking
from app.db_models import AgentProject, Campaign, CampaignMetric, SocialPostTracker, Workspace


def test_social_tracker_upserts_daily_instagram_snapshot(db, monkeypatch):
    workspace = Workspace(name="Ölçmə", slug="olcme", instagram_access_token="tok",
                          instagram_user_id="123", instagram_addon_enabled=True)
    db.add(workspace); db.flush()
    campaign = Campaign(workspace_id=workspace.id, name="7 günlük plan", objective="Test", status="ACTIVE")
    db.add(campaign); db.flush()
    project = AgentProject(workspace_id=workspace.id, brief="Post", status="DELIVERED",
                           output_type="social_post", instagram_published=True)
    db.add(project); db.flush()
    tracker = SocialPostTracker(workspace_id=workspace.id, project_id=project.id,
                                campaign_id=campaign.id, external_post_id="ig-1",
                                status="ACTIVE", next_sync_at=datetime.utcnow() - timedelta(minutes=1))
    db.add(tracker); db.commit()

    monkeypatch.setattr(social_tracking, "fetch_instagram_metrics", lambda *_: {
        "reach": 120, "views": 180, "likes": 15, "comments": 3, "saved": 4, "shares": 2,
    })

    assert social_tracking.sync_due_social_metrics(db) == 1
    metric = db.query(CampaignMetric).one()
    assert (metric.reach, metric.impressions, metric.engagements) == (120, 180, 24)
    assert tracker.last_synced_at is not None
    assert tracker.last_error is None


def test_metric_map_accepts_graph_api_values():
    assert social_tracking._metric_map([
        {"name": "reach", "values": [{"value": 42}]},
        {"name": "shares", "values": [{"value": {"story": 2, "feed": 3}}]},
    ]) == {"reach": 42, "shares": 5}
