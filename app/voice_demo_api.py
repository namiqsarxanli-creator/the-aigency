""""Zəng et" işarəsi — canlı təqdimat üçün, təqdim edənin öz telefonuna bir klikli zəng.

Ayrıca səhifə YOXDUR (qəsdən) — bu, hər səhifədə (bax `templates/base.html`) görünən üzən
bir işarədir. Klik → `POST /voice-demo/call` → Twilio HƏMİŞƏ `settings.demo_call_phone_number`-ə
zəng edir → Twilio səsi `/voice-demo/media-stream` WebSocket-inə ötürür → bu server səsi
OpenAI Realtime API ilə (Twilio ↔ OpenAI) iki tərəfli körpü kimi daşıyır.

Bu, `app/voice_api.py`-dəki brauzer səsli agentindən AYRIDIR (o, sayta gələn müştəri ilə
mətn-mətn danışır); burada real telefon xətti və canlı səs var.
"""

import asyncio
import json
import logging
import secrets
import subprocess
import sys
from pathlib import Path

import websockets
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import context_from_request, is_platform_owner
from app.core import settings
from app.database import SessionLocal, get_db
from app.db_models import DemoCall
from app import telephony, voice_pitch

router = APIRouter(prefix="/voice-demo", tags=["voice-demo"])
logger = logging.getLogger(__name__)

REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={settings.openai_realtime_model}"

# Canlı danışıq mətni (yalnız yaddaşda) — `/voice-demo/mic` səhifəsi bunu sorğulayır.
# Yekun mətn zəng bitəndə `DemoCall.transcript`-ə yazılır (bax `_finish_call`).
LIVE_TRANSCRIPTS: dict[int, list[str]] = {}

# Mikrofon müştərisi (scripts/mic_call.py) ayrıca proses kimi işləyir: brauzerin mikrofon
# icazəsi bloklanan hallarda yeganə işlək yoldur. Eyni anda yalnız bir zəng.
_mic_process: subprocess.Popen | None = None


@router.get("/status")
def voice_demo_status(request: Request, db: Session = Depends(get_db)):
    """İşarənin özü (bax `base.html`) görünüb-görünməyəcəyini və aktivliyini bundan öyrənir."""
    context = context_from_request(request, db)
    if not context or not is_platform_owner(context):
        return {"visible": False}
    return {
        "visible": True,
        "ready": telephony.configured() and bool(settings.demo_call_phone_number),
    }


@router.post("/call")
def voice_demo_call(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context or not is_platform_owner(context):
        raise HTTPException(403, "İcazə yoxdur.")
    if not settings.demo_call_phone_number:
        raise HTTPException(400, ".env-də DEMO_CALL_PHONE_NUMBER doldurulmayıb.")

    demo_call = DemoCall(
        workspace_id=context.workspace.id, call_token=secrets.token_urlsafe(24),
        phone_number=settings.demo_call_phone_number, status="initiated",
    )
    db.add(demo_call)
    db.commit()
    db.refresh(demo_call)

    try:
        call_sid = telephony.start_call(settings.demo_call_phone_number, demo_call.call_token)
    except telephony.TelephonyError as exc:
        db.delete(demo_call)
        db.commit()
        raise HTTPException(400, str(exc)) from exc

    demo_call.call_sid = call_sid
    db.commit()
    return {"ok": True, "call_sid": call_sid}


@router.get("/test", response_class=HTMLResponse)
def voice_demo_test_page(request: Request, db: Session = Depends(get_db)):
    """Twilio-suz sinaq: brauzer mikrofonu Twilio-nun yerini tutur, YALNIZ OpenAI xerci
    isleyir. Eyni /media-stream websocket-i, eyni agent beynini isledir — kod tekrari yoxdur."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context):
        return RedirectResponse("/", status_code=303)
    html = (Path(__file__).resolve().parents[1] / "static" / "voice_demo_test.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@router.post("/test-token")
def voice_demo_test_token(request: Request, db: Session = Depends(get_db)):
    """Test sehifesi ucun DemoCall qeydi acir - Twilio-ya HEC BIR sorgu getmir, sifir xerc."""
    context = context_from_request(request, db)
    if not context or not is_platform_owner(context):
        raise HTTPException(403, "İcazə yoxdur.")
    demo_call = DemoCall(
        workspace_id=context.workspace.id, call_token=secrets.token_urlsafe(24),
        phone_number="brauzer-sınağı", status="initiated",
    )
    db.add(demo_call)
    db.commit()
    return {"call_token": demo_call.call_token}


@router.get("/test-transcript")
def voice_demo_test_transcript(call_token: str, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context or not is_platform_owner(context):
        raise HTTPException(403, "İcazə yoxdur.")
    call = db.query(DemoCall).filter(DemoCall.call_token == call_token).first()
    if not call:
        raise HTTPException(404, "Tapılmadı.")
    return {"status": call.status, "transcript": call.transcript or ""}


@router.get("/mic", response_class=HTMLResponse)
def voice_demo_mic_page(request: Request, db: Session = Depends(get_db)):
    """Kompüterin mikrofonu ilə danışıq səhifəsi — Twilio-suz, sıfır xərc.

    Brauzer mikrofonu OXUMUR (Chrome-da icazə bloklanmışdı) — düymə serverdə
    `scripts/mic_call.py`-ı işə salır, səs birbaşa Windows-un mikrofonundan gedir."""
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    if not is_platform_owner(context):
        return RedirectResponse("/", status_code=303)
    html = (Path(__file__).resolve().parents[1] / "static" / "voice_demo_mic.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@router.post("/mic/start")
def voice_demo_mic_start(request: Request, db: Session = Depends(get_db)):
    global _mic_process
    context = context_from_request(request, db)
    if not context or not is_platform_owner(context):
        raise HTTPException(403, "İcazə yoxdur.")
    if _mic_process and _mic_process.poll() is None:
        raise HTTPException(400, "Danışıq artıq gedir — əvvəlcə bitirin.")

    demo_call = DemoCall(
        workspace_id=context.workspace.id, call_token=secrets.token_urlsafe(24),
        phone_number="mikrofon-sınağı", status="initiated",
    )
    db.add(demo_call)
    db.commit()
    db.refresh(demo_call)
    LIVE_TRANSCRIPTS[demo_call.id] = []

    root = Path(__file__).resolve().parents[1]
    _mic_process = subprocess.Popen(
        [sys.executable, str(root / "scripts" / "mic_call.py"), "--token", demo_call.call_token],
        cwd=str(root),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    logger.info("Mikrofon danışığı başladıldı: zəng #%s", demo_call.id)
    return {"ok": True, "call_id": demo_call.id}


@router.post("/mic/stop")
def voice_demo_mic_stop(request: Request, db: Session = Depends(get_db)):
    global _mic_process
    context = context_from_request(request, db)
    if not context or not is_platform_owner(context):
        raise HTTPException(403, "İcazə yoxdur.")
    if _mic_process and _mic_process.poll() is None:
        _mic_process.terminate()
        logger.info("Mikrofon danışığı dayandırıldı.")
    _mic_process = None
    return {"ok": True}


@router.get("/mic/transcript")
def voice_demo_mic_transcript(call_id: int, request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context or not is_platform_owner(context):
        raise HTTPException(403, "İcazə yoxdur.")
    running = bool(_mic_process and _mic_process.poll() is None)
    return {"running": running, "lines": LIVE_TRANSCRIPTS.get(call_id, [])}


def _turn_detection() -> dict:
    """Bax: MainLessons/CallCenterAI/main.py `_turn_detection()` — eyni tapinti burada da
    tetbiq olunur: telefon xettinde enerji-esasli VAD ya kuyu danisiq sanir, ya sakit sesi
    buraxir. Semantik VAD cumlenin bitib-bitmediyine baxdigi ucun her ikisini heller."""
    if settings.voice_call_vad_mode == "semantic":
        return {
            "type": "semantic_vad",
            "eagerness": settings.voice_call_vad_eagerness,
            "interrupt_response": True,
        }
    return {
        "type": "server_vad", "threshold": 0.7,
        "prefix_padding_ms": 300, "silence_duration_ms": 800,
    }


def _load_call_context() -> dict | None:
    """Zəngdən əvvəl CRM-dən hədəf şirkətin kontekstini oxuyur (bax `voice_pitch.build_call_context`)."""
    db = SessionLocal()
    try:
        return voice_pitch.build_call_context(db)
    except Exception:
        logger.exception("Zəng konteksti oxuna bilmədi — ümumi skriptlə davam edilir")
        return None
    finally:
        db.close()


async def _configure_session(openai_ws, context: dict | None = None) -> None:
    await openai_ws.send(json.dumps({
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": settings.openai_realtime_model,
            "output_modalities": ["audio"],
            "instructions": voice_pitch.system_prompt(context),
            "audio": {
                "input": {
                    "format": {"type": "audio/pcmu"},
                    "turn_detection": _turn_detection(),
                    # gpt-4o-transcribe, whisper-1-den ferqli olaraq kontekst modelidir:
                    # telefon xettinin dar zolagli/kuyu sesinde ve azerbaycan dilinde
                    # nezere carpacaq derecede daha az "uydurur" (canli zeng transkripti
                    # #6-da whisper-1 qonagin sozlerini tamam basqa cumlelere cevirmisdi).
                    # `prompt`: modelin lugetini bu zengde tez-tez kececeyi ifadelere teref
                    # yonledir — canli zengde "maraqli deyil" -> "maraqlidir" (EKS meна!) ve
                    # "vaxtim yoxdur" -> "plastik mocuzedir" kimi tam yanlis transkript
                    # gorulmusdu (dar-zolagli telefon sesinin qacinilmaz riski, amma bu
                    # domen sozlerini onceden gostermek ehtimali azaldir).
                    "transcription": {
                        "model": "gpt-4o-transcribe", "language": "az",
                        "prompt": (
                            "Telefon satış zəngi. Tez-tez keçən sözlər: maraqlı deyil, "
                            "maraqlıdır, vaxtım yoxdur, bahalıdır, özümüz edirik, sabah, "
                            "bu gün, gələn həftə, bazar ertəsi, çərşənbə axşamı, çərşənbə, "
                            "cümə axşamı, cümə, saat, sentyabr, oktyabr, düzdür, bəli, yox."
                        ),
                    },
                },
                "output": {"format": {"type": "audio/pcmu"}, "voice": settings.openai_realtime_voice},
            },
            "tools": voice_pitch.TOOLS,
            "tool_choice": "auto",
        },
    }))
    await openai_ws.send(json.dumps({
        "type": "conversation.item.create",
        "item": {
            "type": "message", "role": "user",
            "content": [{"type": "input_text", "text": "Zəng açıldı, qarşı tərəf dəstəyi götürdü. Özünü tanıt və danışığa başla."}],
        },
    }))
    await openai_ws.send(json.dumps({"type": "response.create"}))


@router.websocket("/media-stream")
async def voice_demo_media_stream(websocket: WebSocket):
    await websocket.accept()
    logger.info("Voice demo media stream qoşuldu")

    state = {
        "demo_call_id": None, "stream_sid": None,
        "media_ts": 0, "response_start_ts": None, "assistant_item": None,
        "transcript_lines": [],
    }

    try:
        async with websockets.connect(
            REALTIME_URL,
            additional_headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            max_size=None,
        ) as openai_ws:
            call_context = await asyncio.to_thread(_load_call_context)
            if call_context:
                logger.info("Zəng konteksti: %s (%s)", call_context["sirket"], call_context["sehir"])
            await _configure_session(openai_ws, call_context)

            async def twilio_to_openai():
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    event = data.get("event")

                    if event == "media":
                        state["media_ts"] = int(data["media"]["timestamp"])
                        await openai_ws.send(json.dumps({
                            "type": "input_audio_buffer.append",
                            "audio": data["media"]["payload"],
                        }))
                    elif event == "start":
                        start = data["start"]
                        state["stream_sid"] = start["streamSid"]
                        token = start.get("customParameters", {}).get("call_token")
                        state["demo_call_id"] = await asyncio.to_thread(_resolve_call_id, token)
                        logger.info("Voice demo stream başladı: token=%s", token)
                    elif event == "stop":
                        break
                await openai_ws.close()

            async def openai_to_twilio():
                async for raw in openai_ws:
                    response = json.loads(raw)
                    rtype = response.get("type")

                    if rtype in ("response.output_audio.delta", "response.audio.delta"):
                        await websocket.send_json({
                            "event": "media", "streamSid": state["stream_sid"],
                            "media": {"payload": response["delta"]},
                        })
                        if state["response_start_ts"] is None:
                            state["response_start_ts"] = state["media_ts"]
                        if response.get("item_id"):
                            state["assistant_item"] = response["item_id"]

                    elif rtype == "input_audio_buffer.speech_started":
                        elapsed = state["media_ts"] - (state["response_start_ts"] or state["media_ts"])
                        if state["assistant_item"] and elapsed > 700:
                            await openai_ws.send(json.dumps({
                                "type": "conversation.item.truncate",
                                "item_id": state["assistant_item"], "content_index": 0,
                                "audio_end_ms": max(elapsed, 0),
                            }))
                            await websocket.send_json({"event": "clear", "streamSid": state["stream_sid"]})
                            state["assistant_item"] = None
                            state["response_start_ts"] = None

                    elif rtype == "response.function_call_arguments.done":
                        result = await asyncio.to_thread(
                            voice_pitch.handle_tool_call, response["name"],
                            response.get("arguments", "{}"), state["demo_call_id"],
                        )
                        logger.info("Voice demo funksiyası: %s -> %s", response["name"], result)
                        await openai_ws.send(json.dumps({
                            "type": "conversation.item.create",
                            "item": {
                                "type": "function_call_output",
                                "call_id": response["call_id"],
                                "output": json.dumps(result, ensure_ascii=False),
                            },
                        }))
                        await openai_ws.send(json.dumps({"type": "response.create"}))

                    elif rtype == "conversation.item.input_audio_transcription.completed":
                        _record_line(state, "Qonaq", response.get("transcript", ""))

                    elif rtype in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
                        _record_line(state, "AI", response.get("transcript", ""))
                        state["response_start_ts"] = None

                    elif rtype == "error":
                        logger.error("Realtime xətası: %s", response.get("error"))

            await asyncio.gather(twilio_to_openai(), openai_to_twilio())

    except WebSocketDisconnect:
        logger.info("Twilio bağlantını kəsdi")
    except Exception:
        logger.exception("Voice demo media stream xətası")
    finally:
        await asyncio.to_thread(_finish_call, state)


def _record_line(state: dict, who: str, text: str) -> None:
    if not text or voice_pitch.is_hallucination(who, text):
        return
    logger.info("%s: %s", who, text)
    line = f"{who}: {text}"
    state["transcript_lines"].append(line)
    call_id = state.get("demo_call_id")
    if call_id is not None and call_id in LIVE_TRANSCRIPTS:
        LIVE_TRANSCRIPTS[call_id].append(line)


def _resolve_call_id(token: str | None) -> int | None:
    if not token:
        return None
    db = SessionLocal()
    try:
        call = db.query(DemoCall).filter(DemoCall.call_token == token).first()
        return call.id if call else None
    finally:
        db.close()


def _finish_call(state: dict) -> None:
    call_id = state.get("demo_call_id")
    if not call_id:
        return
    db = SessionLocal()
    try:
        call = db.get(DemoCall, call_id)
        if call:
            call.status = "completed"
            call.transcript = "\n".join(state["transcript_lines"])
            db.commit()
    finally:
        db.close()
