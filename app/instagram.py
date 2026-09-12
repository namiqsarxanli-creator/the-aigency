"""Instagram Graph API ilə paylaşım (rəsmi yol).

İki addımlı axın (Meta-nın tələb etdiyi kimi):
  1. Media konteyneri yarat: POST /{ig_user_id}/media  (image_url və ya video_url + caption)
  2. Konteyneri dərc et:      POST /{ig_user_id}/media_publish  (creation_id)

Video (Reels) üçün arada üçüncü addım var: konteyner Instagram tərəfindən emal olunur,
`status_code` FINISHED olana qədər gözlənilir (bax `_wait_until_ready`).

VACİB: `image_url`/`video_url` İCTİMAİ olmalıdır — Meta faylı həmin ünvandan ÖZÜ yükləyir.
Lokal `127.0.0.1`/`host.docker.internal` YARAMAZ. Ona görə `settings.public_base_url` ictimai
(ngrok və s.) olmalıdır. Şəkil JPEG olmalı, <8MB (bizim /image endpoint-i uyğundur).

Hesab Business və ya Creator olmalıdır; adi şəxsi hesab bu API ilə paylaşa bilmir. Öz
hesabınıza paylaşmaq üçün tam App Review lazım deyil — hesabı app-a tester kimi əlavə
etmək kifayətdir.

Host haqqında: `INSTAGRAM_API_HOST` defolt olaraq `graph.instagram.com`-dur ("Instagram
login" axını, Facebook Page tələb etmir). Facebook Page üzərindən qurulmuş app üçün onu
`https://graph.facebook.com` edin — tokenlər bir-birini ƏVƏZ ETMİR.
"""
import logging
import time
from dataclasses import dataclass

import requests

from app.core import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IgAccount:
    """Bir workspace-in ÖZ Instagram hesabı (token + IG user id)."""
    access_token: str
    user_id: str

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.user_id)


def account_for(workspace) -> IgAccount | None:
    """Workspace-in Instagram hesabını qaytarır, qoşulmayıbsa None.

    QLOBAL `.env` HESABINA FALLBACK QƏSDƏN YOXDUR. Əvvəl bütün funksiyalar birbaşa
    `settings.instagram_access_token` oxuyurdu — yəni İSTƏNİLƏN müştərinin "Paylaş" düyməsi
    kontenti tətbiq SAHİBİNİN Instagram hesabına dərc edirdi. Fallback qaytarsaq həmin
    səhv geri qayıdar. Sahibin öz hesabı köçürmə zamanı onun workspace-inə yazılır
    (bax `database.initialize_database`).
    """
    if workspace is None or not getattr(workspace, "instagram_addon_enabled", False):
        return None
    account = IgAccount(
        (workspace.instagram_access_token or "").strip(),
        (workspace.instagram_user_id or "").strip(),
    )
    return account if account.configured else None


REQUEST_TIMEOUT = 60

# Konteynerin emalını gözləmə parametrləri. ŞƏKİL ÜÇÜN DƏ LAZIMDIR — konteyner dərhal
# hazır olmur; FINISHED gözləmədən media_publish çağırsaq Meta belə cavab verir:
#   "Media ID is not available" (kod 9007, subcode 2207027)
_IMAGE_POLL = (3, 20)   # 3 san × 20 ≈ 1 dəqiqə
_VIDEO_POLL = (15, 20)  # 15 san × 20 ≈ 5 dəqiqə


class InstagramError(Exception):
    """Paylaşımın hər hansı mərhələsində yaranan xəta (istifadəçiyə göstərmək üçün mesajla)."""


def is_configured(account: "IgAccount | None" = None) -> bool:
    """Verilmiş workspace hesabının paylaşıma hazır olub-olmadığı."""
    return bool(account and account.configured)


def _base() -> str:
    return f"{settings.instagram_api_host}/{settings.instagram_api_version}"


def _guard(account: IgAccount, media_url: str) -> None:
    """Paylaşımdan əvvəl konfiqurasiyanı və media ünvanını yoxlayır.

    Ünvanın ictimai olub-olmadığını MƏHZ verilən URL üzərindən yoxlayırıq — çağıran tərəf
    (bax `api._instagram_image_url`) PUBLIC_BASE_URL lokal olanda mənbə URL-ini birbaşa
    verə bilər, ona görə PUBLIC_BASE_URL-ə baxmaq düzgün olmazdı.
    """
    if not is_configured(account):
        raise InstagramError(
            "Bu workspace-ə Instagram hesabı qoşulmayıb. Avtomatik paylaşım əlavə paketdir — "
            "hesabınızı qoşduqdan sonra aktivləşir."
        )
    if media_url.startswith(("http://127.0.0.1", "http://localhost", "http://host.docker.internal")):
        raise InstagramError(
            f"Media URL-i lokaldır ({media_url[:60]}…). Instagram faylı ÖZÜ yükləyir, ona görə "
            "ünvan internetdən əlçatan olmalıdır — port 8800-ü tunellə açıb PUBLIC_BASE_URL-i yeniləyin."
        )


def _create_container(account: IgAccount, payload: dict) -> str:
    """Media konteyneri yaradır və creation_id qaytarır."""
    try:
        create = requests.post(
            f"{_base()}/{account.user_id}/media",
            data={**payload, "access_token": account.access_token},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise InstagramError(f"Media konteyneri yaradıla bilmədi (şəbəkə): {exc}") from exc
    if not create.ok:
        raise InstagramError(f"Media konteyneri xətası: {_err(create)}")
    creation_id = create.json().get("id")
    if not creation_id:
        raise InstagramError(f"Media konteyneri ID qaytarmadı: {create.text[:300]}")
    return creation_id


def _wait_until_ready(account: IgAccount, creation_id: str, poll: tuple = _IMAGE_POLL) -> None:
    """Konteyner Instagram tərəfindən emal olunana qədər gözləyir.

    Şəkil üçün də lazımdır — konteyner dərhal hazır olmur (bax yuxarıdakı qeyd).
    """
    interval, max_attempts = poll
    for attempt in range(1, max_attempts + 1):
        time.sleep(interval)
        try:
            resp = requests.get(
                f"{_base()}/{creation_id}",
                params={"fields": "status_code,status", "access_token": account.access_token},
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            raise InstagramError(f"Konteyner statusu oxunmadı (şəbəkə): {exc}") from exc
        if not resp.ok:
            raise InstagramError(f"Konteyner statusu xətası: {_err(resp)}")

        status = resp.json().get("status_code")
        if status == "FINISHED":
            logger.info("Konteyner hazırdır (cəhd %s): %s", attempt, creation_id)
            return
        if status in ("ERROR", "EXPIRED"):
            raise InstagramError(
                f"Media emalı uğursuz oldu ({status}): {resp.json().get('status') or '—'}"
            )

    raise InstagramError(
        f"Media {max_attempts * interval} saniyə ərzində emal olunmadı (son status: {status})."
    )


def publish_photo(account: IgAccount, image_url: str, caption: str) -> dict:
    """Şəkli + caption-u Instagram-a dərc edir. Uğurda {'id': <media_id>, 'permalink': <url|None>}
    qaytarır, uğursuzluqda InstagramError qaldırır."""
    _guard(account, image_url)
    creation_id = _create_container(account, {"image_url": image_url, "caption": caption})
    _wait_until_ready(account, creation_id, _IMAGE_POLL)
    return _publish(account, creation_id)


def publish_reel(account: IgAccount, video_url: str, caption: str, share_to_feed: bool = True) -> dict:
    """Videonu Reels kimi dərc edir. Video MP4/MOV (H.264 + AAC), 3–900 saniyə, ≤1 GB
    olmalıdır; 9:16 nisbəti tövsiyə olunur."""
    _guard(account, video_url)
    creation_id = _create_container(account, {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true" if share_to_feed else "false",
    })
    _wait_until_ready(account, creation_id, _VIDEO_POLL)
    return _publish(account, creation_id)


def publish_story(account: IgAccount, media_url: str, is_video: bool = False) -> dict:
    """Şəkli və ya videonu Story kimi dərc edir (24 saatdan sonra itir).

    DİQQƏT — Story API-nin məhdudiyyətləri (kodla aşıla bilməz):
      * `caption` YOXDUR — göndərilsə də ignor olunur. Mətn görünməlidirsə şəklin
        ÜZƏRİNƏ çəkilməlidir (şəkil generasiyası mərhələsində).
      * Sticker, sorğu, link, musiqi, mention — API-dən əlavə edilmir.
      * Highlight-a əlavə etmək də API-dən mümkün deyil.
    Ölçü: 9:16 (1080×1920) tövsiyə olunur; video ≤ 60 saniyə.
    """
    _guard(account, media_url)
    payload = {"media_type": "STORIES"}
    payload["video_url" if is_video else "image_url"] = media_url
    creation_id = _create_container(account, payload)
    _wait_until_ready(account, creation_id, _VIDEO_POLL if is_video else _IMAGE_POLL)
    return _publish(account, creation_id)


def share_post_to_story(account: IgAccount, media_id: str) -> dict:
    """Artıq dərc olunmuş postun şəklini/videosunu Story kimi yenidən paylaşır.

    DİQQƏT — bu, Instagram-ın "Postu story-yə əlavə et" funksiyası DEYİL. Həmin funksiya
    postu sticker kimi göstərir, `@istifadəçi` yazır və üzərinə klikləyəndə posta aparır;
    **API-də belə imkan yoxdur**. Burada sadəcə eyni media adi story kimi yenidən dərc
    olunur — posta keçid və müəlliflik göstəricisi OLMUR.

    Texniki qeyd: `media_url` Instagram CDN-in imzalı və müddəti bitən ünvanıdır. Dərhal
    yenidən paylaşım üçün yararlıdır; köhnə postlar üçün media əvvəlcə öz proksimizdən
    keçirilməlidir.
    """
    try:
        resp = requests.get(
            f"{_base()}/{media_id}",
            params={"fields": "media_url,media_type", "access_token": account.access_token},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise InstagramError(f"Post məlumatı alınmadı (şəbəkə): {exc}") from exc
    if not resp.ok:
        raise InstagramError(f"Post məlumatı xətası: {_err(resp)}")

    data = resp.json()
    media_url = data.get("media_url")
    if not media_url:
        raise InstagramError(f"Postun media ünvanı yoxdur (media_id={media_id}).")

    return publish_story(account, media_url, is_video=data.get("media_type") == "VIDEO")


def _publish(account: IgAccount, creation_id: str) -> dict:
    """Hazır konteyneri dərc edir və {'id', 'permalink'} qaytarır."""
    ig_id = account.user_id
    token = account.access_token

    try:
        publish = requests.post(
            f"{_base()}/{ig_id}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise InstagramError(f"Dərc mərhələsi (şəbəkə): {exc}") from exc
    if not publish.ok:
        raise InstagramError(f"Dərc xətası: {_err(publish)}")
    media_id = publish.json().get("id")
    if not media_id:
        raise InstagramError(f"Dərc ID qaytarmadı: {publish.text[:300]}")

    # Permalink (ixtiyari — alınmasa problem deyil)
    permalink = None
    try:
        info = requests.get(
            f"{_base()}/{media_id}",
            params={"fields": "permalink", "access_token": token},
            timeout=REQUEST_TIMEOUT,
        )
        if info.ok:
            permalink = info.json().get("permalink")
    except requests.RequestException:
        pass

    logger.info("Instagram-a dərc olundu: media_id=%s", media_id)
    return {"id": media_id, "permalink": permalink}


def _err(resp: requests.Response) -> str:
    """Meta xəta cavabından oxunaqlı mesaj çıxarır."""
    try:
        err = resp.json().get("error", {})
        msg = err.get("message") or resp.text[:300]
        code = err.get("code")
        return f"{msg} (kod {code})" if code else msg
    except Exception:
        return resp.text[:300]
