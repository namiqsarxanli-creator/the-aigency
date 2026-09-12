"""Təqdimat rejimi: bir cümlədən tam zəncirə, bir ekranda, canlı.

NİYƏ AYRI MODUL: bu, məhsulun iş axını deyil — nümayiş üçün qurulmuş VİTRİNDİR. Mövcud
marşrutlara toxunmur ki, demo üçün edilən heç bir güzəşt real axına sızmasın.

AXIN: brif → kampaniya planı (faza + LLM) → ilk günlər materiala → hər material üçün
başlıq/caption/vizual + şəkil → hamısı ekranda bir-bir görünür.

TEXNİKİ QEYD: nəticə SSE ilə axıdılır, çünki tam zəncir 30–60 saniyə çəkir və boş ekran
təqdimatı öldürür. Generator ÖZ DB sessiyasını açır və içəri yalnız ID-lər ötürülür —
bu kod bazasında ORM obyektini başqa thread-ə ötürmək artıq problem yaradıb.
"""
from __future__ import annotations

import json
import logging
import traceback

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlalchemy.orm import Session

from app.auth import context_from_request
from app.database import SessionLocal, get_db

logger = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).resolve().parents[1] / "templates")

DEMO_DURATION = 7        # təqdimat üçün bir həftə kifayətdir
DEMO_MATERIALS = 3       # ilk üç gün materiala çevrilir — daha çoxu səhnədə uzun çəkir


def _event(kind: str, **payload) -> str:
    return f"data: {json.dumps({'kind': kind, **payload}, ensure_ascii=False)}\n\n"


@router.get("/demo", response_class=HTMLResponse)
def demo_page(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(request, "demo.html", {
        "current_user": context.user, "current_workspace": context.workspace,
        "membership": context.membership,
    })


@router.get("/demo/stream")
def demo_stream(request: Request, db: Session = Depends(get_db)):
    context = context_from_request(request, db)
    if not context:
        return RedirectResponse("/login", status_code=303)
    brief = (request.query_params.get("brief") or "").strip()[:400]
    if len(brief) < 10:
        return StreamingResponse(
            iter([_event("error", message="Ən azı 10 simvolluq brif yazın.")]),
            media_type="text/event-stream",
        )
    # YALNIZ ID ötürülür — ORM obyekti generatorun sessiyasına aid deyil.
    workspace_id = context.workspace.id
    return StreamingResponse(
        _run(workspace_id, brief), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run(workspace_id: int, brief: str):
    from app.campaign_ai import enrich_campaign
    from app.campaigns import create_campaign
    from app.content_studio import apply_result, create_asset, format_for_campaign_type
    from app.db_models import Workspace
    from app.studio_ai import brief_from_campaign_day, generate_draft

    db = SessionLocal()
    try:
        workspace = db.get(Workspace, workspace_id)
        if workspace is None:
            yield _event("error", message="Workspace tapılmadı.")
            return

        yield _event("step", text="Kampaniya quruluşu hazırlanır…")
        campaign = create_campaign(
            db, workspace, brief[:80], brief, workspace.brand_audience or "",
            "Instagram, TikTok", "", duration_days=DEMO_DURATION,
        )
        yield _event("campaign", id=campaign.id, name=campaign.name, days=len(campaign.days))

        yield _event("step", text="Plan brendə uyğunlaşdırılır…")
        stats = enrich_campaign(db, workspace, campaign)
        days = sorted(campaign.days, key=lambda d: d.day_number)
        yield _event("plan", updated=stats["updated"], days=[
            {"n": d.day_number, "platform": d.platform, "format": d.content_type,
             "theme": d.theme, "hook": d.hook}
            for d in days
        ])

        for day in days[:DEMO_MATERIALS]:
            yield _event("step", text=f"Gün {day.day_number} materiala çevrilir…")
            asset = create_asset(
                db, workspace,
                title=f"{campaign.name} · Gün {day.day_number} · {day.content_type}"[:180],
                content_format=format_for_campaign_type(day.content_type),
                headline="", caption="", visual_brief="",
            )
            day_brief = brief_from_campaign_day(day, workspace)
            asset.brief_json = day_brief.to_json()
            db.commit()
            apply_result(db, asset, generate_draft(workspace, day_brief))
            db.refresh(asset)
            yield _event(
                "material", id=asset.id, day=day.day_number, platform=day.platform,
                format=asset.format, status=asset.status,
                headline=asset.headline or "", caption=asset.caption or "",
                image=asset.image_url or "", image_source=asset.image_source or "",
                needs=json.loads(asset.needs_input or "[]"),
            )

        yield _event("done", campaign_id=campaign.id)
    except Exception:  # noqa: BLE001 — səhnədə çökmə görünməməlidir
        logger.exception("Demo axını uğursuz oldu")
        yield _event("error", message="Zəncir yarımçıq qaldı: " + traceback.format_exc(limit=1)[:200])
    finally:
        db.close()
