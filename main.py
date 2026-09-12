"""The Aigency — AI agentlərindən ibarət avtonom yaradıcı komanda. FastAPI giriş nöqtəsi."""
import asyncio
import logging
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.db_models  # noqa: F401  — create_all-dan əvvəl bütün modellər qeydiyyatdan keçsin
from app.api import router as api_router
from app.voice_api import router as voice_router
from app.voice_demo_api import router as voice_demo_router
from app.database import initialize_database
from app.scheduler import agency_loop
from app.web import router as web_router
from app.ws import manager
from app.auth import SESSION_COOKIE, context_from_token
from app.database import SessionLocal
from app.core import settings, validate_production_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="The Aigency — AI Agent Company", version="1.0.0")
page_templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

production_errors = validate_production_settings()
if production_errors:
    raise RuntimeError("Təhlükəsiz olmayan production konfiqurasiyası: " + "; ".join(production_errors))


@app.middleware("http")
async def security_boundary(request: Request, call_next):
    """Sessiyalı mutasiyalarda same-origin yoxlaması və brauzer təhlükəsizlik başlıqları."""
    unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    if unsafe and request.cookies.get(SESSION_COOKIE) and not request.headers.get("x-api-key"):
        source = request.headers.get("origin") or request.headers.get("referer")
        if source:
            source_host = urlparse(source).netloc.lower()
            request_host = request.headers.get("host", "").lower()
            if source_host != request_host:
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "Cross-site sorğu bloklandı."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; media-src 'self' https://d8j0ntlcm91z4.cloudfront.net; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self' ws: wss:; frame-ancestors 'none'"
    )
    return response


@app.middleware("http")
async def force_utf8_charset(request: Request, call_next):
    """`application/json` cavablarına açıq `charset=utf-8` əlavə edir. Onsuz bəzi HTTP
    client-lər (n8n-in daxili client-i də daxil olmaqla) kodlaşdırmanı özləri təxmin edir və
    Azərbaycan hərflərini (ə, ı, ş, ç...) səhv dekodlaya bilir — bu, Telegram bildirişlərində
    mətnin korlanmasına səbəb olurdu."""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(api_router)
app.include_router(voice_router)
app.include_router(voice_demo_router)
from app.demo import router as demo_router
app.include_router(demo_router)
from app import n8n_proxy
if n8n_proxy.enabled():
    # Yalnız N8N_INTERNAL_URL doldurulanda qeydiyyatdan keçir (bax app/n8n_proxy.py).
    app.include_router(n8n_proxy.router)
app.include_router(web_router)


@app.exception_handler(StarletteHTTPException)
async def branded_http_error(request: Request, exc: StarletteHTTPException):
    """Brauzer səhifələri üçün brend 404, API üçün isə əvvəlki JSON müqaviləsi."""
    if exc.status_code != 404:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
    wants_json = request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", "")
    if wants_json:
        return JSONResponse({"detail": exc.detail}, status_code=404, headers=exc.headers)
    return page_templates.TemplateResponse(request, "404.html", {"requested_path": request.url.path}, status_code=404)

try:
    initialize_database()
except Exception:
    logger.exception("Verilənlər bazası cədvəlləri yaradıla bilmədi")


@app.on_event("startup")
async def start_agency_loop() -> None:
    if settings.worker_mode == "embedded":
        asyncio.create_task(agency_loop())
        logger.info("Embedded factory scheduler başladıldı")
    else:
        logger.info("Celery rejimi aktivdir; scheduler web prosesində başladılmadı")


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    db = SessionLocal()
    try:
        context = context_from_token(websocket.cookies.get(SESSION_COOKIE), db)
        if not context:
            await websocket.close(code=4401)
            return
        workspace_id = context.workspace.id
    finally:
        db.close()
    await manager.connect(websocket, workspace_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
