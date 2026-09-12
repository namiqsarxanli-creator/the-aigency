"""OpenAI Sora ilə qısa video (Reel / Story / TikTok) — Veo-ya alternativ.

NİYƏ: Veo (`app/veo.py`) Google Cloud billing tələb edir və hesabda ödəniş problemi var idi.
Eyni açar (OPENAI_API_KEY) onsuz da şəkil üçün işlədilir və işləkdir, ona görə video üçün də
həmin provayderdən istifadə etmək məntiqlidir.

DİQQƏT — BU ÖDƏNİŞLİDİR, pulsuz tarifi yoxdur. `nano_banana`/`openai_images`-dən fərqli olaraq
BURADA sinxron generate() var (yaratma + gözləmə + endirmə bir funksiyada) — Veo-nun start/collect
ayrılığı YOXDUR, çünki Sora adətən 1-2 dəqiqəyə hazır olur və bunu ayrı skriptlərdən (ya da
gələcəkdə background task-dan) sinxron çağırmaq kifayətdir.

TEXNİKİ: `POST /v1/videos` → {id, status}. Status "queued"/"in_progress" olarkən
`GET /v1/videos/{id}` ilə pollanır. "completed" olanda `GET /v1/videos/{id}/content`
bayt qaytarır (1 saat etibarlıdır, ona görə DƏRHAL diskə yazılır).
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import requests

from app.core import settings

logger = logging.getLogger(__name__)

BASE = "https://api.openai.com/v1/videos"
TIMEOUT = 60
POLL_INTERVAL_SECONDS = 6
POLL_MAX_ATTEMPTS = 40  # ~4 dəqiqə
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "static" / "generated"


def configured() -> bool:
    return bool(settings.openai_api_key)


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.openai_api_key}"}


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


def generate(direction: dict, palette: str = "") -> str | None:
    """Video yaradır, hazır olana qədər gözləyir, endirib nisbi ünvanını qaytarır.

    Bir neçə dəqiqə bloklaya bilər (Sora sinxron deyil) — çağıran tərəf bunu bilməlidir.
    Uğursuzluqda `None`."""
    if not configured():
        return None
    prompt = build_prompt(direction, palette)
    if not prompt.strip():
        return None

    try:
        response = requests.post(
            BASE, headers=_headers(),
            json={
                "model": settings.openai_video_model,
                "prompt": prompt,
                "size": settings.openai_video_size,
                "seconds": settings.openai_video_seconds,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        video_id = (response.json() or {}).get("id")
    except (requests.RequestException, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("Sora başladıla bilmədi (status=%s, %s)", status, type(exc).__name__)
        return None
    if not video_id:
        logger.warning("Sora cavabında video ID yoxdur")
        return None

    for _ in range(POLL_MAX_ATTEMPTS):
        time.sleep(POLL_INTERVAL_SECONDS)
        try:
            poll = requests.get(f"{BASE}/{video_id}", headers=_headers(), timeout=TIMEOUT)
            poll.raise_for_status()
            payload = poll.json() or {}
        except (requests.RequestException, ValueError) as exc:
            logger.warning("Sora sorğusu uğursuz oldu (%s)", type(exc).__name__)
            continue

        status = payload.get("status")
        if status == "completed":
            return _download(video_id, prompt)
        if status == "failed":
            logger.warning("Sora generasiyası uğursuz oldu: %s", str(payload.get("error"))[:200])
            return None
        # "queued" / "in_progress" — davam et

    logger.warning("Sora vaxtında hazır olmadı (video %s)", video_id)
    return None


def _download(video_id: str, prompt: str) -> str | None:
    try:
        media = requests.get(f"{BASE}/{video_id}/content", headers=_headers(), timeout=TIMEOUT * 3)
        media.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Sora videosu endirilə bilmədi (%s)", type(exc).__name__)
        return None
    if not media.content:
        return None

    stem = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:24]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / f"{stem}.mp4").write_bytes(media.content)

    # Thumbnail ixtiyaridir — statik önizləmə üçün (video preview-i dəstəkləməyən yerlərdə).
    # Uğursuz olsa videonun özünü BLOKLAMIR.
    try:
        thumb = requests.get(
            f"{BASE}/{video_id}/content", headers=_headers(),
            params={"variant": "thumbnail"}, timeout=TIMEOUT,
        )
        thumb.raise_for_status()
        if thumb.content:
            (OUTPUT_DIR / f"{stem}.thumb.webp").write_bytes(thumb.content)
    except requests.RequestException:
        pass

    return f"/static/generated/{stem}.mp4"
