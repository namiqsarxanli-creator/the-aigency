"""Buffer (buffer.com) GraphQL API ilə Instagram-a paylaşım.

Meta-nın Facebook-developer-hesabı tələb edən rəsmi Instagram Graph API-sinin ƏVƏZİNƏ istifadə
olunur — Buffer öz tərəfində artıq Meta app-ı qeydiyyatdan keçirib, biz sadəcə Buffer hesabımıza
Instagram-ı BİRBAŞA (Facebook-suz) qoşub Buffer-in Personal API Key-i ilə işləyirik.

Axın:
  1. `organizations` sorğusu ilə organizationId al (API key bir neçə təşkilata aid ola bilər).
  2. `channels` sorğusu ilə həmin təşkilatın qoşulu kanallarından "instagram" servisli olanın
     ID-sini tap (BUFFER_CHANNEL_ID boşdursa avtomatik).
  3. `createPost` mutasiyası ilə şəkil+mətni dərhal növbəyə əlavə et.

VACİB: Buffer da şəkli `media.url`-dən ÖZÜ yükləyir — bu ünvan İCTİMAİ olmalıdır (bax
`app.instagram`-dakı eyni qeyd, `settings.public_base_url`).

Dəqiq GraphQL sahə/enum adları rəsmi sənəddən (developers.buffer.com) götürülüb, amma Buffer bunu
dəyişə bilər — server tərəfdən `MutationError`/`errors` gələrsə, mesaj olduğu kimi yuxarı ötürülür
ki, problem aydın görünsün (kor-koranə "uğurlu" göstərilmir).
"""
import logging

import requests

from app.core import settings

logger = logging.getLogger(__name__)

API_URL = "https://api.buffer.com"
REQUEST_TIMEOUT = 60


class BufferError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.buffer_api_key)


def _gql(query: str, variables: dict | None = None) -> dict:
    try:
        resp = requests.post(
            API_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.buffer_api_key}",
            },
            json={"query": query, "variables": variables or {}},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise BufferError(f"Buffer-ə sorğu göndərilə bilmədi (şəbəkə): {exc}") from exc
    if not resp.ok:
        raise BufferError(f"Buffer HTTP xətası {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    if data.get("errors"):
        raise BufferError(f"Buffer GraphQL xətası: {data['errors']}")
    return data.get("data") or {}


def _get_organization_id() -> str:
    data = _gql("query { organizations { id name } }")
    orgs = data.get("organizations") or []
    if not orgs:
        raise BufferError("Bu Buffer API açarına bağlı heç bir təşkilat tapılmadı.")
    return orgs[0]["id"]


def _get_instagram_channel_id(organization_id: str) -> str:
    if settings.buffer_channel_id:
        return settings.buffer_channel_id
    data = _gql(
        "query($input: ChannelsInput!) { channels(input: $input) { id service displayName } }",
        {"input": {"organizationId": organization_id}},
    )
    channels = data.get("channels") or []
    ig = next((c for c in channels if (c.get("service") or "").lower() == "instagram"), None)
    if not ig:
        names = ", ".join(f"{c.get('displayName')} ({c.get('service')})" for c in channels) or "(heç biri)"
        raise BufferError(
            f"Buffer hesabında Instagram kanalı tapılmadı. Qoşulu kanallar: {names}. "
            "Buffer-də Settings → Channels-dan Instagram-ı qoşduğunuzdan əmin olun."
        )
    return ig["id"]


def publish_photo(image_url: str, caption: str) -> dict:
    """Şəkli + caption-u Buffer üzərindən Instagram-a göndərir. Uğurda
    {'id': <post_id>, 'permalink': None} qaytarır (Buffer birbaşa permalink qaytarmır)."""
    if not is_configured():
        raise BufferError("Buffer konfiqurasiya olunmayıb (.env: BUFFER_API_KEY).")
    if settings.public_base_url.startswith(("http://127.0.0.1", "http://localhost")):
        raise BufferError(
            "Şəkil URL-i ictimai deyil (PUBLIC_BASE_URL hələ lokaldır) — Buffer şəkli özü "
            "yükləyə bilməz. Port 8800-ü ictimai edib PUBLIC_BASE_URL-i yeniləyin."
        )

    org_id = _get_organization_id()
    channel_id = _get_instagram_channel_id(org_id)

    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess {
          post { id text dueAt }
        }
        ... on MutationError {
          message
        }
      }
    }
    """
    variables = {
        "input": {
            "channelId": channel_id,
            "text": caption,
            "schedulingType": "automatic",
            "mode": "addToQueue",
            "media": [{"url": image_url}],
        }
    }
    data = _gql(mutation, variables)
    result = (data.get("createPost") or {})
    if "message" in result:  # MutationError qaytarıldı
        raise BufferError(f"Buffer paylaşımı rədd etdi: {result['message']}")
    post = result.get("post")
    if not post or not post.get("id"):
        raise BufferError(f"Buffer gözlənilməz cavab qaytardı: {data}")

    logger.info("Buffer üzərindən Instagram-a növbəyə əlavə edildi: post_id=%s", post["id"])
    return {"id": post["id"], "permalink": None}
