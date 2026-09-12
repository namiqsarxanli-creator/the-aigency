"""Instagram/TikTok insight-larını kampaniya analitikasına təhlükəsiz snapshot kimi yazır."""
from datetime import date, datetime, timedelta
import requests
from app.core import settings
from app.db_models import AssetSocialTracker, CampaignMetric, SocialPostTracker
from app.instagram import account_for
from app import tiktok as tiktok_module


def _metric_map(items):
    result = {}
    for item in items:
        values = item.get("values") or []
        raw = values[-1].get("value", 0) if values else item.get("value", 0)
        if isinstance(raw, dict): raw = sum(v for v in raw.values() if isinstance(v, (int, float)))
        result[item.get("name", "")] = int(raw or 0)
    return result


def fetch_instagram_metrics(account, post_id):
    base = f"{settings.instagram_api_host}/{settings.instagram_api_version}/{post_id}"
    basic = requests.get(base, params={"fields":"like_count,comments_count","access_token":account.access_token}, timeout=30)
    basic.raise_for_status(); payload = basic.json()
    metrics = {"likes":int(payload.get("like_count") or 0), "comments":int(payload.get("comments_count") or 0)}
    for group in ("reach,saved,shares,total_interactions,views", "reach,saved,total_interactions"):
        response = requests.get(f"{base}/insights", params={"metric":group,"access_token":account.access_token}, timeout=30)
        if response.ok: metrics.update(_metric_map(response.json().get("data") or [])); break
    return metrics


def sync_due_social_metrics(db, limit=10):
    now = datetime.utcnow()
    trackers = db.query(SocialPostTracker).filter(SocialPostTracker.status=="ACTIVE",
        SocialPostTracker.external_post_id.isnot(None),
        (SocialPostTracker.next_sync_at.is_(None)) | (SocialPostTracker.next_sync_at<=now)).limit(limit).all()
    synced = 0
    for tracker in trackers:
        account = account_for(tracker.workspace)
        if not account:
            tracker.last_error="Instagram hesabı qoşulmayıb"; tracker.next_sync_at=now+timedelta(hours=6); continue
        try:
            data=fetch_instagram_metrics(account,tracker.external_post_id); label=f"Instagram Post #{tracker.project_id}"
            snapshot=db.query(CampaignMetric).filter(CampaignMetric.workspace_id==tracker.workspace_id,
                CampaignMetric.campaign_id==tracker.campaign_id,CampaignMetric.recorded_date==date.today(),
                CampaignMetric.content_type==label).first()
            if not snapshot:
                snapshot=CampaignMetric(workspace_id=tracker.workspace_id,campaign_id=tracker.campaign_id,
                    recorded_date=date.today(),platform="Instagram",content_type=label); db.add(snapshot)
            snapshot.reach=data.get("reach",0); snapshot.impressions=data.get("views",data.get("reach",0))
            snapshot.engagements=data.get("total_interactions",0) or sum(data.get(k,0) for k in ("likes","comments","saved","shares"))
            # İlk 48 saat postun ən sürətli hərəkət etdiyi dövrdür: demo və canlı idarəetmə üçün
            # 5 dəqiqəlik ritm, daha köhnə postlar üçün API kvotasını qoruyan saatlıq ritm.
            is_fresh = bool(tracker.created_at and now - tracker.created_at <= timedelta(days=2))
            tracker.last_synced_at=now
            tracker.next_sync_at=now + (timedelta(minutes=5) if is_fresh else timedelta(hours=1))
            tracker.last_error=None; synced+=1
        except Exception as exc:
            tracker.last_error=str(exc)[:1000]; tracker.next_sync_at=now+timedelta(hours=3)
    if trackers: db.commit()
    return synced


def _fetch_tiktok_metrics(account, video_id):
    data = tiktok_module.fetch_video_stats(account, video_id)
    return {
        "reach": data["views"], "views": data["views"],
        "total_interactions": data["likes"] + data["comments"] + data["shares"],
    }


def sync_due_asset_social_metrics(db, limit=10):
    """`sync_due_social_metrics`-in Content Studio qardaşı — `AssetSocialTracker` üçün.
    Kampaniyalardan (Content Studio) paylaşılan Reel/Story-ni Analitikaya qoşur. Platformaya görə
    (Instagram/TikTok) fərqli hesab+metrika mənbəyinə müraciət edir."""
    now = datetime.utcnow()
    trackers = db.query(AssetSocialTracker).filter(AssetSocialTracker.status=="ACTIVE",
        AssetSocialTracker.external_post_id.isnot(None),
        (AssetSocialTracker.next_sync_at.is_(None)) | (AssetSocialTracker.next_sync_at<=now)).limit(limit).all()
    synced = 0
    for tracker in trackers:
        is_tiktok = tracker.platform == "TikTok"
        account = tiktok_module.account_for(tracker.workspace) if is_tiktok else account_for(tracker.workspace)
        if not account:
            tracker.last_error = f"{tracker.platform} hesabı qoşulmayıb"
            tracker.next_sync_at = now + timedelta(hours=6)
            continue
        try:
            data = (_fetch_tiktok_metrics(account, tracker.external_post_id) if is_tiktok
                    else fetch_instagram_metrics(account, tracker.external_post_id))
            label=f"{tracker.platform} {tracker.content_type or 'Post'} #{tracker.asset_id}"
            snapshot=db.query(CampaignMetric).filter(CampaignMetric.workspace_id==tracker.workspace_id,
                CampaignMetric.campaign_id==tracker.campaign_id,CampaignMetric.recorded_date==date.today(),
                CampaignMetric.content_type==label).first()
            if not snapshot:
                snapshot=CampaignMetric(workspace_id=tracker.workspace_id,campaign_id=tracker.campaign_id,
                    recorded_date=date.today(),platform=tracker.platform,content_type=label); db.add(snapshot)
            snapshot.reach=data.get("reach",0); snapshot.impressions=data.get("views",data.get("reach",0))
            snapshot.engagements=data.get("total_interactions",0) or sum(data.get(k,0) for k in ("likes","comments","saved","shares"))
            is_fresh = bool(tracker.created_at and now - tracker.created_at <= timedelta(days=2))
            tracker.last_synced_at=now
            tracker.next_sync_at=now + (timedelta(minutes=5) if is_fresh else timedelta(hours=1))
            tracker.last_error=None; synced+=1
        except Exception as exc:
            tracker.last_error=str(exc)[:1000]; tracker.next_sync_at=now+timedelta(hours=3)
    if trackers: db.commit()
    return synced
