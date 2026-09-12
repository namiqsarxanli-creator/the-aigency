"""OpenAI (gpt-image-1) ilə vizual brifdən şəkil.

NİYƏ: mətn zənciri pulsuz provayderlərə (Groq/Gemini) keçdi, ödənişli OpenAI açarı isə
YALNIZ şəkil üçün saxlanılır — bu, real HEX palitraya ən sadiq nəticəni verən addımdır.

FƏRQ: bu model URL yox, BASE64 bayt qaytarır (`nano_banana.py` ilə eyni naxış). Ona görə
fayl `static/generated/` altına yazılır və materialda yalnız nisbi ünvan saxlanılır.
"""
from __future__ import annotations

import base64
import hashlib
import logging
from pathlib import Path

import requests

from app.core import settings

logger = logging.getLogger(__name__)

ENDPOINT = "https://api.openai.com/v1/images/generations"
TIMEOUT = 90
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "static" / "generated"


def configured() -> bool:
    return bool(settings.openai_api_key)


def build_prompt(direction: dict, palette: str = "") -> str:
    """Strukturlu vizual istiqaməti şəkil promptuna çevirir (nano_banana ilə eyni naxış)."""
    parts = []
    for key, label in (("subject", "Subject"), ("composition", "Composition"),
                       ("lighting", "Lighting")):
        value = direction.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{label}: {value.strip()}")
    if palette:
        # Palitra ƏN SONDA və sərt formada — model onu son təlimat kimi daha yaxşı tutur.
        parts.append(f"Strict colour palette, use ONLY these colours: {palette}")
    parts.append(
        "Photorealistic product photography, premium editorial look, no text, "
        "no logo, no watermark, square 1:1 composition."
    )
    return " ".join(parts)[:1500]


def generate(direction: dict, palette: str = "") -> str | None:
    """Şəkil yaradır və nisbi ünvanını qaytarır. Uğursuzluqda `None` — çağıran tərəf
    mövcud ehtiyat zəncirinə (stok foto → Pollinations) keçir."""
    if not configured():
        return None
    prompt = build_prompt(direction, palette)
    if not prompt.strip():
        return None
    try:
        response = requests.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_image_model,
                "prompt": prompt,
                "size": settings.openai_image_size,
                "n": 1,
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("OpenAI şəkil generasiyası uğursuz oldu (status=%s, %s)", status, type(exc).__name__)
        return None

    data = _first_image(payload)
    if not data:
        logger.warning("OpenAI cavabında şəkil yoxdur")
        return None
    try:
        raw = base64.b64decode(data)
    except (ValueError, TypeError):
        logger.warning("OpenAI şəkil base64 açıla bilmədi")
        return None
    if not raw:
        return None

    # Ad promptun heşidir: eyni brif təkrar generasiya edilməsin, disk şişməsin.
    name = f"{hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:24]}.png"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / name).write_bytes(raw)
    return f"/static/generated/{name}"


def _first_image(payload: dict) -> str | None:
    for item in (payload or {}).get("data") or []:
        if isinstance(item, dict) and item.get("b64_json"):
            return item["b64_json"]
    return None
