"""LLM token/xərc hesabatı — `LlmUsage` sətirlərini provayder və rol üzrə yekunlaşdırır.

Niyə lazımdır: pulsuz provayder kvotaları daim dolur, amma hansı rolun/provayderin nə qədər
sərf etdiyi görünmürdü. Bu hesabat "hansı departament limiti yeyir" sualına dəqiq cavab verir.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from .db_models import LlmUsage
from .ai_telemetry import estimate_cost_microusd


def _cutoff(days: int) -> datetime:
    """`LlmUsage.created_at` DB tərəfli `func.now()` ilə yazılır (SQLite-da UTC, timezone-suz),
    ona görə müqayisə üçün də timezone-suz UTC lazımdır."""
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)

# Rol açarlarının insan oxunaqlı adları (agency.ROLE_LABELS ilə eyni, amma dairəvi importdan
# qaçmaq üçün burada təkrarlanır — bu modul yalnız hesabat üçündür).
ROLE_LABELS = {
    "ceo": "CEO (planlaşdırma)", "strategist": "Strateq", "copywriter": "Kopirayter",
    "designer": "Dizayner", "developer": "Developer", "sales_strategist": "Satış Strateqi",
    "outreach_writer": "Satış Kopirayteri", "marketing": "Marketinq", "analytics": "Analitika",
    "legal": "Hüquq/Uyğunluq", "finance": "Maliyyə", "critic": "QA (Tənqidçi)",
}
ERROR_LABELS = {
    "rate_limit": "Limit doldu (429)",
    "payment": "Ödəniş/açar problemi (401/402/403)",
    "server": "Provayder server xətası (5xx)",
    "network": "Şəbəkə xətası",
    "parse": "Cavab oxuna bilmədi",
}


def _rows(db: Session, workspace_id: int, group_column, days: int):
    since = _cutoff(days)
    return (
        db.query(
            group_column.label("label"),
            func.count(LlmUsage.id).label("calls"),
            func.sum(case((LlmUsage.ok.is_(True), 1), else_=0)).label("ok_calls"),
            func.sum(LlmUsage.prompt_tokens).label("prompt_tokens"),
            func.sum(LlmUsage.completion_tokens).label("completion_tokens"),
            func.sum(LlmUsage.total_tokens).label("total_tokens"),
            func.avg(LlmUsage.latency_ms).label("avg_latency_ms"),
        )
        .filter(LlmUsage.workspace_id == workspace_id, LlmUsage.created_at >= since)
        .group_by(group_column)
        .all()
    )


def _serialize(rows, label_map: dict | None = None) -> list[dict]:
    out = []
    for row in rows:
        raw = row.label or "(naməlum)"
        out.append({
            "label": (label_map or {}).get(raw, raw),
            "calls": int(row.calls or 0),
            "ok_calls": int(row.ok_calls or 0),
            "prompt_tokens": int(row.prompt_tokens or 0),
            "completion_tokens": int(row.completion_tokens or 0),
            "total_tokens": int(row.total_tokens or 0),
            "avg_latency_ms": int(row.avg_latency_ms or 0),
        })
    out.sort(key=lambda item: (item["total_tokens"], item["calls"]), reverse=True)
    return out


def build_usage_report(db: Session, workspace_id: int, days: int = 30) -> dict:
    since = _cutoff(days)
    base = db.query(LlmUsage).filter(
        LlmUsage.workspace_id == workspace_id, LlmUsage.created_at >= since
    )
    total_calls = base.count()
    if not total_calls:
        return {
            "has_data": False, "total_calls": 0, "total_tokens": 0, "failed_calls": 0,
            "estimated_cost_usd": 0.0, "by_provider": [], "by_role": [], "failures": {},
        }

    total_tokens = int(
        db.query(func.sum(LlmUsage.total_tokens))
        .filter(LlmUsage.workspace_id == workspace_id, LlmUsage.created_at >= since)
        .scalar() or 0
    )
    failed_calls = base.filter(LlmUsage.ok.is_(False)).count()
    cost_rows = base.filter(LlmUsage.ok.is_(True)).with_entities(
        LlmUsage.model, LlmUsage.prompt_tokens, LlmUsage.completion_tokens
    ).all()
    estimated_cost_usd = sum(
        estimate_cost_microusd(model or "", prompt or 0, completion or 0)
        for model, prompt, completion in cost_rows
    ) / 1_000_000

    failure_rows = (
        db.query(LlmUsage.error_kind, func.count(LlmUsage.id))
        .filter(
            LlmUsage.workspace_id == workspace_id,
            LlmUsage.created_at >= since,
            LlmUsage.ok.is_(False),
        )
        .group_by(LlmUsage.error_kind)
        .all()
    )
    failures = {
        ERROR_LABELS.get(kind or "", kind or "(naməlum)"): int(count)
        for kind, count in failure_rows
    }

    return {
        "has_data": True,
        "total_calls": total_calls,
        "total_tokens": total_tokens,
        "failed_calls": failed_calls,
        "estimated_cost_usd": estimated_cost_usd,
        "by_provider": _serialize(_rows(db, workspace_id, LlmUsage.provider, days)),
        "by_role": _serialize(_rows(db, workspace_id, LlmUsage.role, days), ROLE_LABELS),
        "failures": failures,
    }
