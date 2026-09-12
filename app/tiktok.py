"""TikTok Content Posting API ilə paylaşım (rəsmi yol).

Instagram-dan fərqli iki nöqtə:

1. **Hesab başına OAuth.** Meta-da bir workspace bir dəfə statik access token yapışdırır;
   TikTok-da hər istifadəçi öz hesabını `/tiktok/connect` → TikTok icazə səhifəsi →
   `/tiktok/callback` axını ilə qoşmalıdır (bax `app/web.py`). Access token qısaömürlüdür
   (24 saat) və `refresh_token` ilə yenilənir — bunu hər paylaşımdan əvvəl yoxlayırıq.

2. **Audit tələbi.** App "audited" olmayana qədər TikTok yalnız `SELF_ONLY` (paylaşımı yalnız
   hesab sahibi görür) privacy səviyyəsinə icazə verir — açıq (`PUBLIC_TO_EVERYONE`) paylaşım
   TikTok-un app review-undan keçdikdən sonra açılır. Ona görə paylaşımdan əvvəl
   `/v2/post/publish/creator_info/query/` çağırılıb hesabın İCAZƏ VERDİYİ privacy
   seçimlərindən biri istifadə olunur — özbaşına dəyər göndərmək API-ni rədd etdirir.

Axın: video init (PULL_FROM_URL) -> `publish_id` -> status sorğusu FINISHED olana qədər.
"""
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import requests

from app.core import settings

logger = logging.getLogger(__name__)

API_BASE = "https://open.tiktokapis.com"
AUTH_BASE = "https://www.tiktok.com"
REQUEST_TIMEOUT = 60
_POLL = (10, 18)  # 10 san × 18 ≈ 3 dəqiqə

SCOPES = "user.info.basic,video.publish,video.list"


class TikTokError(Exception):
    """Paylaşımın/OAuth-un hər hansı mərhələsində yaranan xəta (istifadəçiyə göstərmək üçün)."""


def app_configured() -> bool:
    """TikTok app kimliyi (.env) qurulubmu — bunsuz heç bir workspace qoşula bilməz."""
    return bool(settings.tiktok_client_key and settings.tiktok_client_secret and settings.tiktok_redirect_uri)


@dataclass(frozen=True)
class TikTokAccount:
    """Bir workspace-in ÖZ TikTok hesabı (token cütü + open_id)."""
    access_token: str
    refresh_token: str
    open_id: str

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.open_id)


def account_for(workspace) -> TikTokAccount | None:
    """Workspace-in TikTok hesabını qaytarır, qoşulmayıbsa/paket söndürülübsə None."""
    if workspace is None or not getattr(workspace, "tiktok_addon_enabled", False):
        return None
    account = TikTokAccount(
        (workspace.tiktok_access_token or "").strip(),
        (workspace.tiktok_refresh_token or "").strip(),
        (workspace.tiktok_open_id or "").strip(),
    )
    return account if account.configured else None


def is_configured(account: "TikTokAccount | None" = None) -> bool:
    return bool(account and account.configured)


def authorize_url(state: str) -> str:
    """İstifadəçini TikTok icazə səhifəsinə yönləndirən URL."""
    from urllib.parse import urlencode

    params = {
        "client_key": settings.tiktok_client_key,
        "scope": SCOPES,
        "response_type": "code",
        "redirect_uri": settings.tiktok_redirect_uri,
        "state": state,
    }
    return f"{AUTH_BASE}/v2/auth/authorize/?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """OAuth kodunu access/refresh token cütü ilə dəyişir.

    Qaytarır: {"access_token", "refresh_token", "open_id", "expires_in"}.
    """
    try:
        resp = requests.post(
            f"{API_BASE}/v2/oauth/token/",
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.tiktok_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TikTokError(f"Token mübadiləsi uğursuz oldu (şəbəkə): {exc}") from exc
    data = resp.json() if resp.content else {}
    if not resp.ok or not data.get("access_token"):
        raise TikTokError(f"Token mübadiləsi xətası: {data.get('error_description') or resp.text[:300]}")
    return data


def refresh_access_token(refresh_token: str) -> dict:
    """Vaxtı bitmiş access token-i `refresh_token` ilə yeniləyir."""
    try:
        resp = requests.post(
            f"{API_BASE}/v2/oauth/token/",
            data={
                "client_key": settings.tiktok_client_key,
                "client_secret": settings.tiktok_client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TikTokError(f"Token yenilənməsi uğursuz oldu (şəbəkə): {exc}") from exc
    data = resp.json() if resp.content else {}
    if not resp.ok or not data.get("access_token"):
        raise TikTokError(f"Token yenilənməsi xətası: {data.get('error_description') or resp.text[:300]}")
    return data


def ensure_fresh(workspace) -> TikTokAccount | None:
    """Lazım gələrsə tokeni yeniləyib workspace-ə YAZIR (çağıran `db.commit()` etməlidir)."""
    account = account_for(workspace)
    if not account:
        return None
    expires_at = workspace.tiktok_token_expires_at
    if expires_at and expires_at > datetime.utcnow() + timedelta(minutes=2):
        return account
    try:
        data = refresh_access_token(account.refresh_token)
    except TikTokError:
        logger.warning("TikTok token yenilənmədi (workspace %s) — yenidən qoşulma lazımdır", workspace.id)
        return None
    workspace.tiktok_access_token = data["access_token"]
    workspace.tiktok_refresh_token = data.get("refresh_token", account.refresh_token)
    workspace.tiktok_token_expires_at = datetime.utcnow() + timedelta(seconds=int(data.get("expires_in", 0) or 0))
    return TikTokAccount(workspace.tiktok_access_token, workspace.tiktok_refresh_token, account.open_id)


def _headers(account: TikTokAccount) -> dict:
    return {"Authorization": f"Bearer {account.access_token}", "Content-Type": "application/json; charset=UTF-8"}


def _err(resp: requests.Response) -> str:
    try:
        err = resp.json().get("error", {})
        msg = err.get("message") or resp.text[:300]
        code = err.get("code")
        return f"{msg} (kod {code})" if code else msg
    except Exception:
        return resp.text[:300]


def _default_privacy_level(account: TikTokAccount) -> str:
    """Hesabın icazə verdiyi privacy seçimlərindən uyğun olanı tapır.

    Audit keçməmiş app-lar üçün TikTok yalnız SELF_ONLY qaytarır — özbaşına
    PUBLIC_TO_EVERYONE göndərmək "unaudited_client_can_only_post_private" xətası ilə rədd olunur.
    """
    try:
        resp = requests.post(
            f"{API_BASE}/v2/post/publish/creator_info/query/",
            headers=_headers(account),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TikTokError(f"Hesab məlumatı alınmadı (şəbəkə): {exc}") from exc
    if not resp.ok:
        raise TikTokError(f"Hesab məlumatı xətası: {_err(resp)}")
    options = (resp.json().get("data") or {}).get("privacy_level_options") or []
    if not options:
        raise TikTokError("Hesabın heç bir paylaşım icazəsi yoxdur (creator_info boşdur).")
    # DİQQƏT (canlı sınaqda tapıldı): `creator_info` audit keçməmiş app üçün BELƏ
    # FOLLOWER_OF_CREATOR/MUTUAL_FOLLOW_FRIENDS kimi seçimləri sadalayır, amma faktiki paylaşımda
    # TikTok bunları rədd edir — "unaudited_client_can_only_post_to_private_accounts" xətası.
    # Ona görə PUBLIC_TO_EVERYONE yoxdursa (yəni app hələ audit keçməyib) SELF_ONLY-ni İLK növbədə
    # sınayırıq — digər "yarımaçıq" seçimlər unaudited app-lar üçün işləmir.
    if "PUBLIC_TO_EVERYONE" in options:
        return "PUBLIC_TO_EVERYONE"
    if "SELF_ONLY" in options:
        return "SELF_ONLY"
    return options[0]


def publish_video(account: TikTokAccount, video_url: str, caption: str) -> dict:
    """Videonu TikTok-a dərc edir (Direct Post, PULL_FROM_URL mənbəyi).

    Uğurda {'id': <publish_id>} qaytarır (TikTok media dərhal permalink vermir — profil
    linkindən yoxlanılmalıdır), uğursuzluqda TikTokError qaldırır.
    """
    if not is_configured(account):
        raise TikTokError(
            "Bu workspace-ə TikTok hesabı qoşulmayıb. Brand Kit bölməsindən qoşun."
        )
    if video_url.startswith(("http://127.0.0.1", "http://localhost", "http://host.docker.internal")):
        raise TikTokError(
            f"Video URL-i lokaldır ({video_url[:60]}…). TikTok faylı ÖZÜ yükləyir, ona görə "
            "ünvan internetdən əlçatan olmalıdır."
        )

    privacy_level = _default_privacy_level(account)
    try:
        init = requests.post(
            f"{API_BASE}/v2/post/publish/video/init/",
            headers=_headers(account),
            json={
                "post_info": {
                    "title": (caption or "")[:2200],
                    "privacy_level": privacy_level,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TikTokError(f"Paylaşım başladıla bilmədi (şəbəkə): {exc}") from exc
    if not init.ok:
        raise TikTokError(f"Paylaşım başlatma xətası: {_err(init)}")
    publish_id = (init.json().get("data") or {}).get("publish_id")
    if not publish_id:
        raise TikTokError(f"Paylaşım ID-si qaytarılmadı: {init.text[:300]}")

    video_id = _wait_until_ready(account, publish_id)
    logger.info("TikTok-a dərc olundu: publish_id=%s video_id=%s (privacy=%s)", publish_id, video_id, privacy_level)
    return {"id": video_id or publish_id, "publish_id": publish_id, "video_id": video_id, "privacy_level": privacy_level}


def _wait_until_ready(account: TikTokAccount, publish_id: str) -> str | None:
    """FINISHED olana qədər gözləyir və uğurlu olarsa TikTok video ID-sini qaytarır.

    `publicaly_available_post_id` YALNIZ paylaşım PUBLIC_TO_EVERYONE olanda dolur — statistika
    sorğusu (`fetch_video_stats`) üçün lazımdır. SELF_ONLY/audit keçməmiş paylaşımlarda boş qala
    bilər, bu, xəta deyil (bax `publish_video`-nun çağıranı)."""
    interval, max_attempts = _POLL
    status = None
    for attempt in range(1, max_attempts + 1):
        time.sleep(interval)
        try:
            resp = requests.post(
                f"{API_BASE}/v2/post/publish/status/fetch/",
                headers=_headers(account),
                json={"publish_id": publish_id},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise TikTokError(f"Paylaşım statusu oxunmadı (şəbəkə): {exc}") from exc
        if not resp.ok:
            raise TikTokError(f"Paylaşım statusu xətası: {_err(resp)}")

        data = resp.json().get("data") or {}
        status = data.get("status")
        if status == "PUBLISH_COMPLETE":
            logger.info("TikTok konteyneri hazırdır (cəhd %s): %s", attempt, publish_id)
            video_ids = data.get("publicaly_available_post_id") or []
            return str(video_ids[0]) if video_ids else None
        if status == "FAILED":
            raise TikTokError(f"Paylaşım uğursuz oldu: {data.get('fail_reason') or '—'}")

    raise TikTokError(
        f"Paylaşım {max_attempts * interval} saniyə ərzində tamamlanmadı (son status: {status})."
    )


VIDEO_STATS_FIELDS = "id,view_count,like_count,comment_count,share_count"


def fetch_video_stats(account: TikTokAccount, video_id: str) -> dict:
    """Dərc olunmuş videonun statistikasını qaytarır (`video.list` scope tələb edir).

    Yalnız `publish_video`-nun `video_id` qaytardığı hallarda (adətən PUBLIC_TO_EVERYONE)
    işləyir — SELF_ONLY paylaşımlar üçün TikTok video ID-si açıq siyahıda görünmür."""
    try:
        resp = requests.post(
            f"{API_BASE}/v2/video/query/?fields={VIDEO_STATS_FIELDS}",
            headers=_headers(account),
            json={"filters": {"video_ids": [video_id]}},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise TikTokError(f"Video statistikası alınmadı (şəbəkə): {exc}") from exc
    if not resp.ok:
        raise TikTokError(f"Video statistikası xətası: {_err(resp)}")
    videos = (resp.json().get("data") or {}).get("videos") or []
    if not videos:
        raise TikTokError(f"Video tapılmadı (video_id={video_id}).")
    video = videos[0]
    return {
        "views": int(video.get("view_count") or 0),
        "likes": int(video.get("like_count") or 0),
        "comments": int(video.get("comment_count") or 0),
        "shares": int(video.get("share_count") or 0),
    }
