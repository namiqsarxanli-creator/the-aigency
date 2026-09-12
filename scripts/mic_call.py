"""Brauzersiz zəng sınağı — mikrofon birbaşa Windows-dan oxunur.

NİYƏ: `/voice-demo/test` səhifəsi brauzerin mikrofon icazəsindən asılıdır; Chrome-da
icazə "Block" kimi ilişib qalanda (və ya avtomatlaşdırılmış tab-da) heç bir kod düzəlişi
kömək etmir. Bu skript eyni WebSocket körpüsünə (`/voice-demo/media-stream`) qoşulur,
Twilio-nun göndərdiyi formatın eynisini göndərir — yəni server, agent və görüş yazılması
real zənglə tam eynidir, sadəcə telefon xətti yerinə kompüterin mikrofonu işləyir.

XƏRC: Twilio-ya heç nə getmir. Yalnız OpenAI Realtime səs haqqı.

İstifadə:  .venv\\Scripts\\python.exe scripts\\mic_call.py
Dayandırmaq: Ctrl+C
"""

import asyncio
import base64
import json
import queue
import secrets
import sys
import threading
import time
from pathlib import Path

import numpy as np
import sounddevice as sd
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal          # noqa: E402
from app.db_models import DemoCall, Workspace  # noqa: E402

WS_URL = "ws://127.0.0.1:8800/voice-demo/media-stream"
DEVICE_RATE = 48000      # kompüterin səs kartı adətən 48 kHz işləyir
PHONE_RATE = 8000        # Twilio/OpenAI ilə eyni: 8 kHz mulaw
RATIO = DEVICE_RATE // PHONE_RATE
BLOCK = 960              # 20 ms @ 48 kHz — Twilio-nun kadr ölçüsü ilə eyni
# Dinamikdən danışanda exo-nun qarşısını alır (bax `send_mic`). Qulaqlıq taxsanız
# False edin — o zaman Ayselin sözünü ortada kəsmək də mümkün olur.
MIC_GATE = True
# Səs bitəndən sonra mikrofonun bağlı qaldığı əlavə vaxt: otağın əks-sədası və səs
# kartının buferi üçün ehtiyat. Çox kiçik olsa AI öz səsini eşidib özü ilə danışır.
ECHO_TAIL = 0.35

mic_queue: queue.Queue = queue.Queue()
speaker_buffer = np.zeros(0, dtype=np.float32)
speaker_lock = threading.Lock()
# Səsin dinamikdə NƏ VAXT bitəcəyi (monotonik saat). Yalnız buferin boş olmasına baxmaq
# AZDIR: səs kartının öz buferi var, buferimiz boşalandan sonra da səs 100-200 ms çıxmağa
# davam edir və mikrofon məhz o quyruğu tutur (canlı sınaqda AI özü ilə danışmağa başladı).
speaking_until = 0.0
output_latency = 0.2


# --- G.711 mu-law (telefon standartı), numpy ilə: Python 3.13+ `audioop`-u silib ---
BIAS_CONST = 0x84
CLIP = 32635


def to_mulaw(samples: np.ndarray) -> bytes:
    s = np.clip((samples * 32767).astype(np.int32), -CLIP, CLIP)
    sign = np.where(s < 0, 0x80, 0).astype(np.int32)
    s = np.abs(s) + BIAS_CONST
    # Eksponent = en yuksek qurulmus bitin mövqeyi - 7 (G.711). Kicikden boyuye gedirik
    # ki, sertini odeyen EN BOYUK eksponent qalsin.
    exponent = np.zeros_like(s)
    for exp in range(8):
        exponent = np.where(s >= (1 << (exp + 7)), exp, exponent)
    mantissa = (s >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8).tobytes()


def from_mulaw(payload: bytes) -> np.ndarray:
    b = (~np.frombuffer(payload, dtype=np.uint8) & 0xFF).astype(np.int32)
    sign = b & 0x80
    exponent = (b >> 4) & 0x07
    mantissa = b & 0x0F
    sample = (((mantissa << 3) + BIAS_CONST) << exponent) - BIAS_CONST
    return np.where(sign > 0, -sample, sample).astype(np.float32) / 32768.0


def _mic_callback(indata, frames, time_info, status):
    mono = indata[:, 0]
    mic_queue.put(to_mulaw(mono[::RATIO]))       # 48 kHz -> 8 kHz


def _speaker_callback(outdata, frames, time_info, status):
    global speaker_buffer
    with speaker_lock:
        take = min(frames, len(speaker_buffer))
        outdata[:take, 0] = speaker_buffer[:take]
        outdata[take:, 0] = 0.0
        speaker_buffer = speaker_buffer[take:]


def _new_call_token() -> tuple[str, int]:
    """Öz zəng qeydini açır. Serverdən `--token` gəlibsə, mövcud qeyd işlədilir."""
    if len(sys.argv) > 2 and sys.argv[1] == "--token":
        token = sys.argv[2]
        db = SessionLocal()
        try:
            call = db.query(DemoCall).filter(DemoCall.call_token == token).first()
            return token, (call.id if call else 0)
        finally:
            db.close()

    db = SessionLocal()
    try:
        workspace = db.query(Workspace).filter(Workspace.slug == "legacy").first()
        call = DemoCall(
            workspace_id=workspace.id, call_token=secrets.token_urlsafe(24),
            phone_number="mikrofon-sınağı", status="initiated",
        )
        db.add(call)
        db.commit()
        return call.call_token, call.id
    finally:
        db.close()


async def main() -> None:
    global speaker_buffer, output_latency
    token, call_id = _new_call_token()
    print(f"Zəng qeydi #{call_id} açıldı. Qoşulur…", flush=True)

    async with websockets.connect(WS_URL, max_size=None) as ws:
        await ws.send(json.dumps({
            "event": "start",
            "start": {"streamSid": "MIC_TEST", "customParameters": {"call_token": token}},
        }))
        print("Qoşuldu. Aysel indi danışacaq — mikrofona danışın. Bitirmək: Ctrl+C\n")

        with sd.InputStream(samplerate=DEVICE_RATE, blocksize=BLOCK, channels=1,
                            dtype="float32", callback=_mic_callback), \
             sd.OutputStream(samplerate=DEVICE_RATE, blocksize=BLOCK, channels=1,
                             dtype="float32", callback=_speaker_callback) as out_stream:
            output_latency = float(out_stream.latency) + 0.05
            print(f"Səs kartı gecikməsi: {output_latency:.3f}s", flush=True)

            async def send_mic():
                """Yarım-duplex: Aysel danışarkən mikrofon susdurulur.

                Brauzerdən fərqli olaraq burada exo-ləğvi (AEC) yoxdur — dinamikdən çıxan
                səsi mikrofon geri tutsa, AI öz sözünü kəsəcək. Ona görə səsləndirmə
                gedərkən (və bitdikdən 150 ms sonraya qədər, exo quyruğu üçün) mikrofon
                kadrları göndərilmir. Qulaqlıqla tam ikitərəfli danışıq üçün
                MIC_GATE = False edin."""
                timestamp = 0
                while True:
                    try:
                        chunk = mic_queue.get_nowait()
                    except queue.Empty:
                        await asyncio.sleep(0.005)
                        continue

                    with speaker_lock:
                        silent_at = speaking_until + output_latency + ECHO_TAIL
                    if MIC_GATE and time.monotonic() < silent_at:
                        continue                      # exo getməsin deyə kadrı atırıq

                    timestamp += 20
                    await ws.send(json.dumps({
                        "event": "media",
                        "media": {"timestamp": str(timestamp),
                                  "payload": base64.b64encode(chunk).decode()},
                    }))

            async def receive_audio():
                global speaker_buffer, speaking_until
                async for raw in ws:
                    data = json.loads(raw)
                    if data.get("event") == "media":
                        pcm = from_mulaw(base64.b64decode(data["media"]["payload"]))
                        with speaker_lock:
                            speaker_buffer = np.concatenate([speaker_buffer, np.repeat(pcm, RATIO)])
                            # Səsin bitmə anını irəli sürüşdürürük (parçalar real vaxtdan
                            # sürətli gəlir, ona görə növbəyə düzülür).
                            speaking_until = max(speaking_until, time.monotonic()) + len(pcm) / PHONE_RATE
                    elif data.get("event") == "clear":      # AI sözü kəsildi
                        with speaker_lock:
                            speaker_buffer = np.zeros(0, dtype=np.float32)
                            speaking_until = 0.0

            await asyncio.gather(send_mic(), receive_audio())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDayandırıldı.")
