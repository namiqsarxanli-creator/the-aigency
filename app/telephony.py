"""Twilio ile geden zeng — Control Room-dakı "bir klik zeng" duymesinin arxasi.

Yalniz Twilio-nu isledir (hesab artiq qurulub, sinanib). Genişlenmek lazim olsa,
`MainLessons/CallCenterAI/providers.py`-deki eyni Provider abstraksiyasi buraya da
kocurule biler — hazirda tekbir provayder oldugu ucun sade saxlanilib.
"""

from functools import lru_cache

from app.core import settings


class TelephonyError(RuntimeError):
    """Zeng baslatmaq alinmayanda — sebeb duz istifadeciye gosterile bilir."""


def _twilio():
    """Twilio SDK-ni YALNIZ zeng anında yukleyir.

    NIYE MODUL SEVIYYESINDE DEYIL: zeng opsional funksiyadir (Control Room-dakı bir dugme),
    lakin `main.py` bu modulu startup-da import edir — SDK yoxdursa ve ya deyisik/xarab
    versiyadirsa butun sayt acilmirdi. Canli hadise: PyCharm layihenin oz venv-i evezine
    QL kokundeki umumi venv ile isledi, orada `twilio` paketi `appier`-i cekir, o da pozuq
    bir `.env` setrinde `ValueError` atirdi — netice: ERR_CONNECTION_REFUSED, hec bir izah yox.
    Indi belə hallar yalniz zeng anında, aydın mesajla uze cixir."""
    try:
        from twilio.base.exceptions import TwilioRestException
        from twilio.rest import Client
    except Exception as exc:  # ImportError DEYIL: xarab paket ixtiyari xeta ata bilir
        raise TelephonyError(
            f"Twilio SDK yuklenmedi ({exc.__class__.__name__}: {exc}). Zeng funksiyasi "
            "islemir — `pip install twilio` ile duzgun versiyani qurun."
        ) from exc
    return Client, TwilioRestException


@lru_cache(maxsize=1)
def sdk_available() -> bool:
    """Twilio SDK hemin muhitde ISLEK sekilde yuklenirmi.

    `configured()`-in bir hissesidir: SDK yoxdursa/xarabdirsa zeng funksiyasi sadece
    SONDURULMUS sayilir (interfeysde xeta banneri cixmir) — bax `_twilio()`-daki qeyd.
    Netice kesle saxlanilir: `/voice-demo/status` her sehife acilisinda cagirilir, xarab
    paketde ise import cehdi hər defe bahali ola bilir."""
    try:
        _twilio()
    except TelephonyError:
        return False
    return True


def configured() -> bool:
    return bool(
        settings.twilio_account_sid and settings.twilio_auth_token
        and settings.twilio_from_number and settings.voice_call_public_domain
        and sdk_available()
    )


def stream_url() -> str:
    return f"wss://{settings.voice_call_public_domain}/voice-demo/media-stream"


def start_call(to_number: str, call_token: str) -> str:
    """Verilmis nomreye zeng edir, `call_token`-i Twilio-ya <Parameter> ile oturur.

    DIQQET: Twilio <Stream url>-dan sorgu parametrlerini (?token=..) SILIR — buna gore
    token URL-de yox, <Parameter> teqinde gonderilir (canli testde tesdiqlenmis usul,
    bax MainLessons/CallCenterAI/providers.py-deki eyni qeyd)."""
    if not configured():
        raise TelephonyError(
            "Zeng ucun .env-de TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER "
            "ve VOICE_CALL_PUBLIC_DOMAIN (ngrok domeni) doldurulmalidir."
        )
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Connect>"
        f'<Stream url="{stream_url()}">'
        f'<Parameter name="call_token" value="{call_token}" />'
        "</Stream></Connect></Response>"
    )
    Client, TwilioRestException = _twilio()
    client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
    try:
        call = client.calls.create(to=to_number, from_=settings.twilio_from_number, twiml=twiml)
    except TwilioRestException as exc:
        raise TelephonyError(f"Twilio {exc.code}: {exc.msg}") from exc
    return call.sid
