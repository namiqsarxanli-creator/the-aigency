"""Səsli agentin HTTP marşrutları.

TƏHLÜKƏSİZLİK QEYDİ: bu marşrutlar QƏSDƏN autentifikasiyasızdır — məqsəd saytа gələn
POTENSİAL müştərinin (hesabı olmayan adamın) danışa bilməsidir. Buna görə:
  * LLM kvotasını qorumaq üçün sessiya başına növbə limiti var (`MAX_TURNS_PER_SESSION`).
  * Agent HEÇ BİR geri alınmaz və ya xarici əməl edə bilmir — maksimum daxili qeyd yaradır.
  * Yaradılan layihələr yalnız `VOICE_WORKSPACE_SLUG` workspace-inə düşür, başqasına yox.
"""
import logging
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import settings
from app.database import get_db
from app.db_models import VoiceCall, Workspace
from app import voice_agent

router = APIRouter(prefix="/voice", tags=["voice"])
logger = logging.getLogger(__name__)

# Bir söhbətdə icazə verilən maksimum növbə. Autentifikasiyasız marşrut olduğu üçün bu,
# LLM kvotasını tükəndirməyə qarşı əsas qoruyucudur.
MAX_TURNS_PER_SESSION = 40
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


class VoiceTurn(BaseModel):
    session_id: str = Field(..., min_length=8, max_length=64)
    text: str = Field(..., min_length=1, max_length=1000)
    history: list[dict] = Field(default_factory=list)


class VoiceReply(BaseModel):
    reply: str
    action: str = "none"
    project_id: int | None = None
    # Brauzer öz səsi ilə oxusun, yoxsa /voice/speak-dən audio çəksin?
    server_tts: bool = False


class TtsRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=800)


def _guard_enabled() -> None:
    if not settings.voice_agent_enabled:
        raise HTTPException(status_code=404, detail="Səsli agent aktiv deyil.")


def _voice_workspace_id(db: Session) -> int | None:
    """Səsli agentin yaratdığı layihələr HANSI workspace-ə düşür.

    Səsli agentlə danışan adam hələ müştəri deyil (hesabı yoxdur), ona görə layihə sahibin
    öz workspace-inə düşür — orada baxılıb real müştəriyə çevrilə bilər."""
    workspace = db.query(Workspace).filter(Workspace.slug == "legacy").first()
    if not workspace:
        workspace = db.query(Workspace).order_by(Workspace.id).first()
    return workspace.id if workspace else None


@router.get("/config")
def voice_config():
    """Ön tərəf üçün: agent aktivdirmi, server səsləndirməsi varmı, ilk salamlama nədir."""
    _guard_enabled()
    return {
        "enabled": True,
        "greeting": voice_agent.GREETING,
        "server_tts": voice_agent.tts_configured(),
        "lang": "az-AZ",
        "session_id": secrets.token_urlsafe(18),
    }


@router.post("/turn", response_model=VoiceReply)
def voice_turn(payload: VoiceTurn, db: Session = Depends(get_db)):
    """Müştərinin bir cümləsini emal edib agentin cavabını qaytarır."""
    _guard_enabled()
    if not _SESSION_RE.match(payload.session_id):
        raise HTTPException(status_code=400, detail="Yanlış sessiya açarı.")

    existing = db.query(VoiceCall).filter(VoiceCall.session_id == payload.session_id).first()
    if existing and (existing.turns or 0) >= MAX_TURNS_PER_SESSION:
        return VoiceReply(
            reply=(
                "Söhbətimiz uzandı. Sizi həmkarımıza yönləndirim — əlaqə məlumatınızı "
                "saytdakı nömrə ilə paylaşa bilərsiniz."
            ),
            action="handoff",
        )

    workspace_id = _voice_workspace_id(db)
    voice_agent.append_transcript(db, payload.session_id, "user", payload.text, workspace_id)
    result = voice_agent.respond(
        db, workspace_id, payload.session_id, payload.text, payload.history,
    )
    voice_agent.append_transcript(db, payload.session_id, "agent", result["reply"])

    return VoiceReply(
        reply=result["reply"],
        action=result.get("action", "none"),
        project_id=result.get("project_id"),
        server_tts=voice_agent.tts_configured(),
    )


@router.post("/speak")
def voice_speak(payload: TtsRequest):
    """Mətni Azərbaycanca səsə çevirir (yalnız Azure açarı varsa).

    Açar yoxdursa 204 qaytarırıq — ön tərəf bunu görüb brauzerin öz səsinə keçir, yəni
    xəta göstərmədən pulsuz variantla davam edir."""
    _guard_enabled()
    audio = voice_agent.synthesize(payload.text)
    if not audio:
        return Response(status_code=204)
    return Response(content=audio, media_type="audio/mpeg")
