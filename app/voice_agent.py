"""Səsli qəbul agenti — saytda "Zəng et" düyməsinə basan müştəri ilə Azərbaycanca danışır.

NİYƏ BRAUZER SƏSİ (telefon yox): real +994 nömrəsi ayrıca kommersiya məsələsidir (Azercell
beynəlxalq yönləndirməni dəstəkləmir, +994 DID-lər bahadır). Brauzer səsi telefoniya xərci
OLMADAN eyni AI təcrübəsini verir; sonradan nömrə qoşulsa yalnız giriş nöqtəsi dəyişir,
buradakı "beyin" olduğu kimi qalır.

XƏRC MODELİ (hamısı pulsuz həddə):
  * Nitq tanıma  — brauzerin öz Web Speech API-si (server heç nə ödəmir, audio yüklənmir)
  * Beyin        — mövcud LLM zənciri (Groq və s.)
  * Səsləndirmə  — brauzerin öz səsi, yoxdursa Azure F0 (ayda 0.5M simvol pulsuz)

AGENT NƏ EDƏ BİLƏR (`ACTIONS`): xidməti izah edir, brif qəbul edib layihə yaradır, əlaqə
məlumatı yazıb geri zəng növbəsinə salır. Heç bir geri alınmaz və ya xarici əməl etmir —
maksimum daxili qeyd yaradır.
"""
import json
import logging
import re

import requests
from sqlalchemy.orm import Session

from app.agency import _call_llm, create_project
from app.core import settings
from app.db_models import VoiceCall

logger = logging.getLogger(__name__)

# Modelin seçə biləcəyi əməllər. Qəsdən DAR saxlanılıb — səsli agent yalnız bunları edə bilər.
ACTIONS = ("none", "create_brief", "capture_lead", "handoff")

SYSTEM_PROMPT = """Sən "The Aigency" adlı AI marketinq studiyasının telefon operatorusan.
Zəng edən müştəri ilə AZƏRBAYCAN DİLİNDƏ, təbii danışıq dilində söhbət edirsən.

ŞİRKƏT NƏ EDİR:
- Müştəri bir brif verir (məs. "eko qəhvə brendi üçün kampaniya"), 10 ixtisaslaşmış AI agent
  (strateq, kopirayter, dizayner, developer, satış, marketinq, analitika, hüquq, maliyyə)
  həmin brif üzərində işləyib hazır nəticə çıxarır: landing page və ya sosial media postu,
  satış mətnləri, marketinq planı, KPI-lar, hüquqi yoxlama və büdcə.
- Nəticə müştərinin təsdiqinə göndərilir; PDF hesabat və ZIP arxiv kimi təhvil verilir.
- Əsas paket bunların hamısını əhatə edir. Instagram-a AVTOMATİK dərc ayrıca əlavə paketdir.

DANIŞIQ QAYDALARI:
- QISA danış. Bu, telefon söhbətidir — hər cavabın 1-2 cümlə olsun, maksimum 3.
- Sadə, canlı dildə danış. Maddələr, başlıqlar, emoji, markdown İŞLƏTMƏ — bu mətn səsləndiriləcək.
- Rəqəm və qiymət uydurma. Konkret qiymət soruşulsa: dəqiq təklif üçün əlaqə saxlanılacağını de.
- Bilmədiyini uydurma. Bilmirsənsə bunu de və insana ötürməyi təklif et.
- Bir anda BİR sual ver.

NƏ ETMƏLİSƏN:
1. Salamla, nə ilə kömək edə biləcəyini soruş.
2. Müştəri iş sifariş etmək istəyirsə — nə istədiyini aydınlaşdır (məhsul/xidmət, hədəf
   auditoriya, kanal). Kifayət qədər məlumat yığılanda "create_brief" əməlini seç.
3. Müştəri sadəcə məlumat/qiymət istəyirsə və ya sonra əlaqə saxlanılmasını istəyirsə —
   adını və əlaqə nömrəsini soruş, sonra "capture_lead" əməlini seç.
4. Söhbət mürəkkəbləşsə, şikayət olsa, ya da müştəri insan istəsə — "handoff" seç.

CAVAB FORMATI — YALNIZ bu JSON, başqa heç nə:
{"reply": "<səsləndiriləcək cavabın>", "action": "none|create_brief|capture_lead|handoff",
 "brief": "<create_brief seçmisənsə tam brif mətni, yoxsa boş>",
 "caller_name": "<öyrəndinsə ad, yoxsa boş>",
 "caller_phone": "<öyrəndinsə nömrə, yoxsa boş>"}"""

GREETING = (
    "Salam, The Aigency-yə xoş gəlmisiniz. Mən süni intellekt operatoruyam. "
    "Sizə necə kömək edə bilərəm?"
)
# LLM ümumiyyətlə cavab vermədikdə deyiləcək söz — sükut qalmasın.
FALLBACK_REPLY = (
    "Üzr istəyirəm, sizi tam eşidə bilmədim. Zəhmət olmasa bir daha təkrar edin."
)


def _clean_for_speech(text: str) -> str:
    """Səsləndirməyə göndərilən mətni təmizləyir.

    Model qaydaya baxmayaraq bəzən markdown/emoji qaytarır — səs mühərriki bunları
    ya hərfbəhərf oxuyur, ya da qəribə fasilələr verir."""
    text = re.sub(r"[*_#`>|]+", " ", text or "")
    text = re.sub(r"^\s*[-•]\s*", "", text, flags=re.MULTILINE)
    # Emoji və digər simvol blokları
    text = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _history_messages(history: list[dict]) -> list[dict]:
    """Ön tərəfdən gələn söhbət tarixçəsini LLM formatına çevirir (yalnız son 12 növbə —
    telefon söhbətində daha uzunu həm lazımsızdır, həm token yandırır)."""
    messages = []
    for turn in (history or [])[-12:]:
        role = "assistant" if turn.get("role") == "agent" else "user"
        content = (turn.get("text") or "").strip()
        if content:
            messages.append({"role": role, "content": content[:800]})
    return messages


def respond(
    db: Session, workspace_id: int | None, session_id: str, user_text: str,
    history: list[dict] | None = None,
) -> dict:
    """Bir danışıq növbəsini emal edir: cavab mətni + seçilmiş əməl.

    Həmişə istifadəyə yararlı dict qaytarır — LLM sıradan çıxsa belə səsli axın dayanmamalıdır.
    """
    user_text = (user_text or "").strip()
    if not user_text:
        return {"reply": FALLBACK_REPLY, "action": "none"}

    raw = _call_llm(
        [{"role": "system", "content": SYSTEM_PROMPT}, *_history_messages(history),
         {"role": "user", "content": user_text[:1000]}],
        max_tokens=320,
        temperature=0.5,
        usage_ctx={"workspace_id": workspace_id, "role": "voice_agent"},
    )

    parsed = None
    if raw:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                parsed = None

    if not parsed or not isinstance(parsed, dict):
        # JSON alınmadısa xam mətni cavab kimi işlədirik — söhbət davam etsin.
        return {"reply": _clean_for_speech(raw) or FALLBACK_REPLY, "action": "none"}

    action = parsed.get("action") if parsed.get("action") in ACTIONS else "none"
    reply = _clean_for_speech(parsed.get("reply") or "") or FALLBACK_REPLY
    result = {
        "reply": reply,
        "action": action,
        "caller_name": (parsed.get("caller_name") or "").strip()[:120],
        "caller_phone": (parsed.get("caller_phone") or "").strip()[:40],
    }

    call = _get_or_create_call(db, session_id, workspace_id)
    _touch_call(call, result)
    if action == "create_brief":
        brief = (parsed.get("brief") or "").strip()
        # Çox qısa brif faydasızdır — layihə yaratmırıq, amma söhbət davam edir.
        if len(brief) >= 15 and workspace_id:
            project = create_project(db, brief, workspace_id=workspace_id)
            call.created_project_id = project.id
            result["project_id"] = project.id
        else:
            result["action"] = "none"
    db.commit()
    return result


def _get_or_create_call(db: Session, session_id: str, workspace_id: int | None) -> VoiceCall:
    """Zəng qeydini tapır, yoxdursa yaradır.

    Bu, `append_transcript` (növbədən ƏVVƏL çağırılır) və `_touch_call` (növbədən SONRA
    çağırılır) üçün ORTAQ giriş nöqtəsidir. Əvvəl hər ikisi ayrıca "tap, yoxdursa None qaytar"
    məntiqi ilə işləyirdi — nəticədə müştərinin İLK mesajı `append_transcript`-də səssizcə
    itirilirdi, çünki `VoiceCall` sətri hələ yaranmamışdı (canlı testdə tapıldı)."""
    call = db.query(VoiceCall).filter(VoiceCall.session_id == session_id).first()
    if not call:
        call = VoiceCall(session_id=session_id, workspace_id=workspace_id)
        db.add(call)
        db.flush()
    return call


def _touch_call(call: VoiceCall, result: dict) -> None:
    """Zəng qeydini agentin cavabına görə yeniləyir."""
    if result.get("caller_name"):
        call.caller_name = result["caller_name"]
    if result.get("caller_phone"):
        call.caller_phone = result["caller_phone"]
    if result.get("action") in ("capture_lead", "handoff", "create_brief"):
        call.outcome = result["action"]
    call.turns = (call.turns or 0) + 1


def append_transcript(
    db: Session, session_id: str, speaker: str, text: str, workspace_id: int | None = None,
) -> None:
    """Söhbətin mətnini zəng qeydinə əlavə edir (operator sonra oxuya bilsin)."""
    call = _get_or_create_call(db, session_id, workspace_id)
    line = f"{'Müştəri' if speaker == 'user' else 'AI'}: {(text or '').strip()}"
    call.transcript = f"{call.transcript}\n{line}" if call.transcript else line
    db.commit()


# ---------------------------------------------------------------------------
# Səsləndirmə (yalnız brauzerdə Azərbaycanca səs olmayanda lazım olur)
# ---------------------------------------------------------------------------

def tts_configured() -> bool:
    return bool(settings.azure_speech_key and settings.azure_speech_region)


def synthesize(text: str) -> bytes | None:
    """Azure ilə Azərbaycanca səs sintezi. Açar yoxdursa None — ön tərəf brauzerin öz
    səsinə keçir. Pulsuz F0 tarifi ayda 0.5M simvoldur, bu istifadə üçün bol-bol kifayətdir."""
    if not tts_configured():
        return None
    clean = _clean_for_speech(text)[:800]
    if not clean:
        return None
    ssml = (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="az-AZ">'
        f'<voice name="{settings.azure_speech_voice}">{_xml_escape(clean)}</voice></speak>'
    )
    try:
        response = requests.post(
            f"https://{settings.azure_speech_region}.tts.speech.microsoft.com/cognitiveservices/v1",
            headers={
                "Ocp-Apim-Subscription-Key": settings.azure_speech_key,
                "Content-Type": "application/ssml+xml",
                # 16kHz mono MP3 — telefon keyfiyyəti üçün kifayətdir və kiçikdir.
                "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
                "User-Agent": "the-agency-voice",
            },
            data=ssml.encode("utf-8"),
            timeout=15,
        )
        response.raise_for_status()
        return response.content
    except requests.RequestException:
        logger.warning("Azure TTS uğursuz oldu — brauzer səsinə keçilir", exc_info=True)
        return None


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;")
        .replace(">", "&gt;").replace('"', "&quot;")
    )
