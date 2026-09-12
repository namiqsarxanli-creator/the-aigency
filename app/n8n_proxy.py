""""Bir tunel, iki xidmət" — ngrok statik domenini n8n webhook-ları ilə paylaşır.

NİYƏ LAZIMDIR (canlı tapıntı, 11 sentyabr):
Pulsuz ngrok planında YALNIZ BİR statik domen var (`cursor-eleven-preteen.ngrok-free.dev`).
n8n-in Telegram trigger-i öz webhook-unu Telegram-da məhz bu domenlə qeydiyyatdan keçirib
(`WEBHOOK_URL` konteyner dəyişənindəki dəyər). Amma Twilio səsli demo üçün həmin tunel
8800 portuna (bu FastAPI tətbiqinə) yönəldilmişdi — nəticədə Telegram `/brief` mesajını
göndərəndə istək bu tətbiqə düşür və 404 alırdı; n8n heç vaxt xəbər tutmurdu.
(ngrok inspect jurnalı: `POST /webhook/agency-telegram-webhook/webhook -> 404`, 8 dəfə təkrar.)

HƏLL: tunel 8800-də qalır (Twilio işləyir), bu tətbiq isə `/webhook*` ilə başlayan istəkləri
olduğu kimi lokal n8n-ə ötürür. Beləliklə tək domen hər ikisinə xidmət edir və n8n-i
yenidən qurmaq / webhook URL-ini dəyişmək lazım gəlmir.

TƏHLÜKƏSİZLİK: yalnız n8n-in İCTİMAİ olması nəzərdə tutulan yolları (`/webhook`,
`/webhook-test`, `/webhook-waiting`) ötürülür — n8n-in idarəetmə API-si (`/rest/...`) və
redaktor interfeysi QƏSDƏN ötürülmür, yoxsa tunel n8n-i tam açıq buraxardı.
Defolt olaraq SÖNÜLÜDÜR: `N8N_INTERNAL_URL` boş qalsa (məs. bulud serverində, orada n8n yoxdur)
bu route-lar heç qeydiyyatdan da keçmir.
"""

import asyncio
import logging

import requests
from fastapi import APIRouter, Request, Response

from app.core import settings

router = APIRouter(tags=["n8n-proxy"])
logger = logging.getLogger(__name__)

PROXY_PREFIXES = ("webhook", "webhook-test", "webhook-waiting")

# Bu başlıqları ÖTÜRMÜRÜK: `host` n8n-in webhook axtarışını çaşdırır, qalanları isə
# gövdənin uzunluğu/kodlaşdırması ilə bağlıdır və `requests` onları yenidən hesablayır.
_SKIP_REQUEST_HEADERS = {"host", "content-length", "connection", "transfer-encoding", "accept-encoding"}
_SKIP_RESPONSE_HEADERS = {"content-length", "connection", "transfer-encoding", "content-encoding"}


def enabled() -> bool:
    return bool(settings.n8n_internal_url)


def _forward(method: str, url: str, params, headers: dict, body: bytes) -> requests.Response:
    return requests.request(
        method, url, params=params, headers=headers, data=body or None,
        timeout=30, allow_redirects=False,
    )


def _register(prefix: str) -> None:
    """Hər prefiks üçün AYRICA route — `/{prefix}/{path}` şəklində tutan bir route yazsaq,
    tətbiqin bütün digər səhifələri ilə toqquşar və əsl 404-ləri kölgələyərdi."""

    @router.api_route(
        f"/{prefix}/{{path:path}}",
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"],
        include_in_schema=False,
        name=f"n8n_proxy_{prefix.replace('-', '_')}",
    )
    async def _proxy(path: str, request: Request, _prefix: str = prefix) -> Response:
        target = f"{settings.n8n_internal_url.rstrip('/')}/{_prefix}/{path}"
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_REQUEST_HEADERS}
        body = await request.body()

        try:
            upstream = await asyncio.to_thread(
                _forward, request.method, target, dict(request.query_params), headers, body
            )
        except requests.RequestException as exc:
            logger.warning("n8n webhook proxy xətası (%s): %s", target, exc)
            return Response(
                status_code=502, content=b'{"detail":"n8n cavab vermir"}',
                media_type="application/json",
            )

        out_headers = {
            k: v for k, v in upstream.headers.items() if k.lower() not in _SKIP_RESPONSE_HEADERS
        }
        return Response(content=upstream.content, status_code=upstream.status_code, headers=out_headers)


for _prefix in PROXY_PREFIXES:
    _register(_prefix)
