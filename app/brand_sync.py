"""Layihə nəticəsindən Brand Kit təklifləri (audit #1).

PROBLEM: Brand Kit yalnız-forma mənbə idi — layihə nəticələrindən geri yazan heç bir kod
yox idi. «Pipeline sınıqdır» deyil, pipeline YOX idi.

DİZAYN QƏRARI — avtomatik yazma YOX, TƏSDİQLİ təklif. Brand Kit bütün generasiyanın
qidalandığı mənbədir; ora səssiz yazmaq onu vaxtla korlayar. Beləliklə avtomatikləşmə
faydası qalır, nəzarət isə istifadəçidə.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agency import _call_llm, _extract_json
from app.db_models import AgentProject, AgentTask, BrandKitSuggestion, Workspace

logger = logging.getLogger(__name__)

# Yalnız bu sahələr təklif oluna bilər. Loqo, rəng və qadağan ifadələr QƏSDƏN kənardadır —
# onlar brendin sərt qərarlarıdır, mətn analizindən çıxarılmamalıdır.
SUGGESTABLE = {
    "brand_audience": "Hədəf auditoriya",
    "brand_voice": "Ünsiyyət tonu",
    "brand_products": "Məhsul/xidmətlər",
    "brand_description": "Brend haqqında",
}

SYSTEM = (
    "Sən brend strateqisən. Sənə brendin MÖVCUD təsviri və bir layihənin nəticəsi verilir. "
    "Mövcud təsvirdə ÇATIŞMAYAN və ya KÖHNƏLMİŞ yerləri tapırsan.\n\n"
    "QAYDALAR:\n"
    "1. Yalnız layihə nəticəsində HƏQİQƏTƏN olan məlumatdan təklif ver. Uydurma.\n"
    "2. Mövcud dəyər onsuz da yaxşıdırsa, həmin sahəni ÜMUMİYYƏTLƏ qaytarma.\n"
    "3. Ən çoxu 3 təklif. Az təklif çox təklifdən yaxşıdır.\n"
    "4. `suggested` sahəsi TAM əvəzedici mətndir — fərq deyil, bütöv yeni dəyər.\n\n"
    "CAVAB: yalnız JSON. Boş nəticə də etibarlıdır: {\"suggestions\": []}"
)


def _project_text(db: Session, project: AgentProject) -> str:
    parts = [f"BRİF: {project.brief or ''}"]
    for task in db.query(AgentTask).filter(AgentTask.project_id == project.id).all():
        if task.output:
            parts.append(f"[{task.role}]\n{task.output[:900]}")
    return "\n\n".join(parts)[:6000]


def collect_suggestions(db: Session, project: AgentProject) -> int:
    """Layihə bitəndə çağırılır. Yaradılan təklif sayını qaytarır.

    Razılıq YOXDURSA heç nə etmir: brend məlumatını modelə göndərmək lazımdır, bu isə
    məhz razılığın əhatə etdiyi şeydir.
    """
    if not project.workspace_id:
        return 0
    workspace = db.get(Workspace, project.workspace_id)
    if not workspace or not workspace.brand_ai_consent:
        return 0

    current = {
        field: (getattr(workspace, field, "") or "").strip()
        for field in SUGGESTABLE
    }
    user_msg = (
        "MÖVCUD BRAND KIT:\n"
        + "\n".join(f"- {field}: {value or '(boş)'}" for field, value in current.items())
        + f"\n\nLAYİHƏ NƏTİCƏSİ:\n{_project_text(db, project)}\n\n"
        'Format: {"suggestions": [{"field": "brand_voice", "suggested": "...", "rationale": "..."}]}\n'
        f"İcazəli field dəyərləri: {', '.join(SUGGESTABLE)}"
    )
    raw = _call_llm(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_msg}],
        max_tokens=700, temperature=0.3, model_tier="nano",
        usage_ctx={"workspace_id": workspace.id, "feature": "brand_sync"},
    )
    data = _extract_json(raw) if raw else None
    items = (data or {}).get("suggestions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return 0

    created = 0
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        field = (item.get("field") or "").strip()
        suggested = (item.get("suggested") or "").strip()
        if field not in SUGGESTABLE or len(suggested) < 10:
            continue
        if suggested == current.get(field):
            continue
        # Eyni sahə üçün gözləyən təklif varsa yenisini yaratmırıq — siyahı şişməsin.
        exists = db.query(BrandKitSuggestion).filter(
            BrandKitSuggestion.workspace_id == workspace.id,
            BrandKitSuggestion.field == field,
            BrandKitSuggestion.status == "PENDING",
        ).first()
        if exists:
            continue
        db.add(BrandKitSuggestion(
            workspace_id=workspace.id, source_project_id=project.id, field=field,
            current_value=current.get(field), suggested_value=suggested[:4000],
            rationale=(item.get("rationale") or "")[:400],
        ))
        created += 1
    db.commit()
    if created:
        logger.info("Brand Kit üçün %s təklif yaradıldı (layihə %s)", created, project.id)
    return created


def apply_suggestion(db: Session, workspace: Workspace, suggestion: BrandKitSuggestion) -> None:
    """Təklifi Brand Kit-ə yazır. YALNIZ istifadəçi qəbul edəndə çağırılır."""
    if suggestion.field in SUGGESTABLE and suggestion.status == "PENDING":
        setattr(workspace, suggestion.field, suggestion.suggested_value)
        suggestion.status = "ACCEPTED"
        db.commit()
