"""Veo 3.1 ilə qısa video (Reel / Story / TikTok).

NİYƏ: plan günlərinin bir hissəsi Reel-dir, amma material üçün yalnız STATİK şəkil
hazırlanırdı. Video-first platformada (TikTok yalnız Reel qəbul edir) bu, əskik idi.

DİQQƏT — BU ÖDƏNİŞLİDİR. Veo-nun pulsuz tarifi YOXDUR. Ona görə defolt olaraq SÖNÜLÜDÜR
(`VEO_ENABLED=false`); açmadan heç bir sorğu getmir və heç bir xərc yaranmır.
Qiymət (2026-08 · Veo 3.1, 720p): lite $0.05/san, fast $0.10/san, standard $0.40/san.
8 saniyəlik Reel lite ilə ≈ $0.40.

TEXNİKİ: Veo uzunmüddətli əməliyyatdır — sorğu dərhal `operation` qaytarır, video 1–2
dəqiqə sonra hazır olur. Ona görə burada AYRI iki addım var: `start()` və `collect()`.
Generasiya sorğusunu bloklamırıq.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

import requests

from app.core import settings

logger = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = 60
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "static" / "generated"

# Şaquli formatlar — Reel, Story, TikTok. Kvadrat POST üçün video mənasızdır.
VERTICAL_FORMATS = {"REEL", "STORY"}

# Günlük limit Bakı gününə görə hesablanır (bax `used_today`).
BAKU = ZoneInfo("Asia/Baku")


def enabled() -> bool:
    """Ödənişli olduğu üçün AÇIQ razılıq tələb edir: açar + bayraq."""
    return bool(settings.gemini_api_key and settings.veo_enabled)


def used_today(db) -> int:
    from sqlalchemy import func as sa_func

    from app.db_models import VeoUsage

    # `VeoUsage.created_at` bazada `func.now()` ilə UTC yazılır, `date.today()` isə
    # SERVERİN YERLİ tarixini verir. Bakı UTC+4 olduğu üçün gecə 00:00-04:00 arası yerli tarix
    # UTC-dən BİR GÜN QABAQDA olur: `start` gələcəkdə qalır, sayğac sıfırlanır və günlük limit
    # həmin saatlarda tamamilə işləmirdi (Veo ÖDƏNİŞLİDİR — real pul riski).
    # Düzəliş: Bakı gününün başlanğıcını hesabla və UTC-yə çevirib müqayisə et.
    start = (
        datetime.now(BAKU).replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc).replace(tzinfo=None)
    )
    return db.query(sa_func.count(VeoUsage.id)).filter(VeoUsage.created_at >= start).scalar() or 0


def budget(db) -> dict:
    """Günlük vəziyyət — interfeysdə göstərmək və qərar vermək üçün."""
    used = used_today(db)
    limit = max(0, settings.veo_daily_limit)
    return {
        "used": used,
        "limit": limit,
        "left": max(0, limit - used),
        "spent": round(used * settings.veo_cost_per_video, 2),
        "cap": round(limit * settings.veo_cost_per_video, 2),
    }


def allowed(db) -> bool:
    """SƏRT KƏSMƏ. Google büdcəsi yalnız xəbərdarlıq göndərdiyi üçün kəsmə buradadır."""
    if not enabled():
        return False
    if settings.veo_daily_limit <= 0:
        return False
    return used_today(db) < settings.veo_daily_limit


def record(db, workspace_id: int | None, asset_id: int | None) -> None:
    """Sayğacı artırır. Sorğu GEDƏNDƏN SONRA çağırılır — cəhd də pula yazılır."""
    from app.db_models import VeoUsage

    db.add(VeoUsage(workspace_id=workspace_id, asset_id=asset_id, model=settings.veo_model))
    db.commit()


def build_prompt(direction: dict, palette: str = "") -> str:
    parts = []
    for key, label in (("subject", "Subject"), ("composition", "Camera"),
                       ("lighting", "Lighting")):
        value = direction.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{label}: {value.strip()}")
    if palette:
        parts.append(f"Colour palette, use ONLY: {palette}")
    parts.append(
        "Short vertical social video, slow deliberate camera move, premium editorial "
        "product film, no on-screen text, no logo."
    )
    return " ".join(parts)[:1500]


def start(direction: dict, palette: str = "", seconds: int = 8) -> str | None:
    """Generasiyanı başladır və `operation` adını qaytarır. Videonu GÖZLƏMİR."""
    if not enabled():
        return None
    prompt = build_prompt(direction, palette)
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": "9:16",
            "resolution": "720p",
            # RƏQƏM olmalıdır — sənəddə sətir kimi yazılıb, amma API sətri rədd edir
            # (canlı sınaqda 400 INVALID_ARGUMENT).
            "durationSeconds": seconds if seconds in (4, 6, 8) else 8,
        },
    }
    try:
        response = requests.post(
            f"{BASE}/models/{settings.veo_model}:predictLongRunning",
            params={"key": settings.gemini_api_key}, json=body, timeout=TIMEOUT,
        )
        response.raise_for_status()
        name = (response.json() or {}).get("name")
    except (requests.RequestException, ValueError) as exc:
        # Açar sorğu parametrindədir — `exc` mətnində tam URL olur, ona görə yalnız status.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("Veo başladıla bilmədi (status=%s, %s)", status, type(exc).__name__)
        return None
    if not name:
        logger.warning("Veo cavabında operation adı yoxdur")
    return name


def collect(operation: str) -> str | None:
    """Əməliyyatı yoxlayır. Hazırdırsa videonu endirib nisbi ünvanını qaytarır.

    Hələ hazır deyilsə də `None` qaytarır — çağıran tərəf sonra yenidən yoxlamalıdır.
    """
    if not (operation and settings.gemini_api_key):
        return None
    try:
        response = requests.get(
            f"{BASE}/{operation}", params={"key": settings.gemini_api_key}, timeout=TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("Veo yoxlanışı uğursuz (status=%s, %s)", status, type(exc).__name__)
        return None

    if not payload.get("done"):
        return None
    if payload.get("error"):
        logger.warning("Veo generasiyası xəta ilə bitdi: %s", str(payload["error"])[:160])
        return None

    uri = _video_uri(payload)
    if not uri:
        logger.warning("Veo nəticəsində video ünvanı yoxdur")
        return None
    try:
        media = requests.get(uri, params={"key": settings.gemini_api_key}, timeout=TIMEOUT * 3)
        media.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Veo videosu endirilə bilmədi (%s)", type(exc).__name__)
        return None
    if not media.content:
        return None

    name = operation.rsplit("/", 1)[-1][:40] + ".mp4"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / name).write_bytes(media.content)
    return f"/static/generated/{name}"


def _video_uri(payload: dict) -> str | None:
    response = (payload or {}).get("response") or {}
    samples = (response.get("generateVideoResponse") or {}).get("generatedSamples") or []
    for sample in samples:
        uri = ((sample or {}).get("video") or {}).get("uri")
        if uri:
            return uri
    return None
