"""Kampaniya planının məzmununu konkretləşdirən qat (audit #3).

PROBLEM: kampaniya generatorunda LLM ÜMUMİYYƏTLƏ iştirak etmirdi. Plan sabit beat hovuzundan
(`campaigns.PHASE_BEATS`) yığılırdı, ona görə hər brend üçün eyni çıxırdı — «prompt şablonlarını
təkmilləşdirmək» mümkün deyildi, çünki təkmilləşdiriləcək prompt yox idi.

DİZAYN — hibrid, tam LLM deyil:
  * Faza bölgüsü (Diqqət → Dəyər → Etibar → Təklif → Yekun) DETERMİNİST qalır. O, yaxşı
    işləyir və proqnozlaşdırıla biləndir; atmağa ehtiyac yoxdur.
  * Yalnız GÜN SƏVİYYƏSİNDƏKİ mətn modeldən gəlir — fazaya bir çağırış, günə bir yox.
    30 günlük plan üçün bu, 30 deyil 5 çağırış deməkdir və faza daxilində ardıcıllığı qoruyur.
  * Çıxış ortaq uyğunluq qatından keçir.
  * Model uğursuz olsa, şablon mətni OLDUĞU KİMİ QALIR. Plan heç vaxt boş olmur — sadəcə
    bəzən ümumi olur, indiki kimi.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.agency import _call_llm, _extract_json, brand_context_for_workspace
from app.campaigns import formats_for, phase_distribution
from app.compliance import LABEL_RE, check_text, rules_from_workspace
from app.db_models import Campaign, CampaignDay, Workspace

logger = logging.getLogger(__name__)

MAX_DAYS_PER_CALL = 12   # bir çağırışda bundan çox gün istəsək cavab kəsilir

PHASE_INTENT = {
    "hook": "Auditoriyanın diqqətini tutmaq: onların real problemini adı ilə demək.",
    "value": "Dəyər vermək: konkret, tətbiq edilə bilən fayda — satış yox, kömək.",
    "trust": "Şübhəni azaltmaq: proses, sübut, dürüst cavablar, etirazların qarşılanması.",
    "offer": "Təklifi aydın etmək: nə alırlar, necə başlayırlar, niyə indi.",
    "close": "Dövrü bağlamaq: xülasə, dialoq, növbəti addım.",
}

CAMPAIGN_SYSTEM = (
    "Sən Azərbaycan bazarı üçün işləyən sosial media strateqisən. Sənə bir brend, bir məqsəd "
    "və kampaniyanın BİR MƏRHƏLƏSİ verilir. Sən həmin mərhələnin günlərini planlaşdırırsan.\n\n"

    "QAYDALAR:\n"
    "1. Hər gün FƏRQLİ bir bucaqdan yanaşmalıdır. Eyni fikri başqa sözlərlə təkrarlamaq qadağandır.\n"
    "2. Mətn KONKRET olmalıdır — brendin öz məhsulundan, auditoriyasının öz problemindən danış. "
    "«Keyfiyyətli xidmət», «peşəkar yanaşma» kimi hər brendə yaraşan ifadələr YAZMA.\n"
    "3. Rəqəm, faiz, endirim, zəmanət yalnız sənə verilən məlumatda varsa yazıla bilər. "
    "Yoxdursa ümumiyyətlə yazma.\n"
    "4. `theme` istehsal etiketidir (nə haqqındadır), `hook` auditoriyaya deyilən ilk cümlədir, "
    "`cta` isə onlardan istənilən konkret addımdır.\n"
    "5. Mətnin içində sahə adı, «Auditoriya:», «Məqsəd:» kimi etiket və «·» ayırıcısı OLMAMALIDIR.\n\n"

    "CAVAB FORMATI: yalnız JSON obyekti — birinci simvol «{», sonuncu «}». İzah yazma."
)


def _phase_ranges(duration: int) -> list[tuple[str, str, list[int]]]:
    """(faza açarı, etiket, həmin fazaya düşən gün nömrələri)."""
    ranges, cursor = [], 1
    for key, label, count in phase_distribution(duration):
        ranges.append((key, label, list(range(cursor, cursor + count))))
        cursor += count
    return ranges


def _prompt(campaign, workspace, label: str, key: str, days: list[CampaignDay], brand: str) -> str:
    lines = "\n".join(
        f"- Gün {d.day_number}: platforma {d.platform}, format {d.content_type} "
        f"(bu platformada icazəli formatlar: {', '.join(formats_for(d.platform))})"
        for d in days
    )
    return (
        f"{brand}\n\n" if brand else ""
    ) + (
        f"KAMPANİYA: {campaign.name}\n"
        f"MƏQSƏD: {campaign.objective}\n"
        f"AUDİTORİYA: {campaign.audience or 'müəyyən edilməyib'}\n\n"
        f"MƏRHƏLƏ: {label} — {PHASE_INTENT.get(key, '')}\n"
        f"Bu mərhələnin günləri:\n{lines}\n\n"
        "Hər gün üçün bir obyekt qaytar:\n"
        '{"days": [{"day": 1, "theme": "...", "hook": "...", "cta": "..."}]}'
    )


def _usable(item: dict, rules) -> bool:
    """Bir günün mətni tətbiq edilə bilərmi."""
    theme, hook, cta = (item.get("theme") or ""), (item.get("hook") or ""), (item.get("cta") or "")
    if not (theme.strip() and hook.strip()):
        return False
    for field_name, text in (("theme", theme), ("hook", hook), ("cta", cta)):
        if LABEL_RE.search(text) or "·" in text:
            return False
        if check_text(text, rules, label=field_name):
            return False
    return True


def enrich_campaign(db: Session, workspace: Workspace, campaign: Campaign) -> dict:
    """Plan günlərinin mətnini brendə uyğunlaşdırır.

    Heç vaxt istisna atmır və heç vaxt planı boşaltmır — tətbiq edilə bilməyən gün
    şablon mətni ilə qalır. Nə qədər günün dəyişdiyini qaytarır.
    """
    days = sorted(campaign.days, key=lambda d: d.day_number)
    if not days:
        return {"updated": 0, "skipped": 0, "calls": 0}

    brand = brand_context_for_workspace(workspace)
    rules = rules_from_workspace(workspace)
    by_number = {d.day_number: d for d in days}
    usage_ctx = {"workspace_id": workspace.id, "feature": "campaign"}
    updated = skipped = calls = 0

    for key, label, numbers in _phase_ranges(len(days)):
        phase_days = [by_number[n] for n in numbers if n in by_number]
        for start in range(0, len(phase_days), MAX_DAYS_PER_CALL):
            chunk = phase_days[start:start + MAX_DAYS_PER_CALL]
            calls += 1
            raw = _call_llm(
                [
                    {"role": "system", "content": CAMPAIGN_SYSTEM},
                    {"role": "user", "content": _prompt(campaign, workspace, label, key, chunk, brand)},
                ],
                max_tokens=180 * len(chunk) + 200,
                temperature=0.7,
                model_tier="nano",
                usage_ctx=usage_ctx,
            )
            data = _extract_json(raw) if raw else None
            items = (data or {}).get("days") if isinstance(data, dict) else None
            if not isinstance(items, list):
                skipped += len(chunk)
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                day = by_number.get(item.get("day"))
                if day is None or day not in chunk:
                    continue
                if not _usable(item, rules):
                    skipped += 1
                    continue
                day.theme = (item.get("theme") or "").strip()[:300]
                day.hook = (item.get("hook") or "").strip()[:500]
                day.cta = (item.get("cta") or "").strip()[:300]
                updated += 1

    db.commit()
    logger.info(
        "Kampaniya %s zənginləşdirildi: %s gün yeniləndi, %s şablonda qaldı, %s çağırış",
        campaign.id, updated, skipped, calls,
    )
    return {"updated": updated, "skipped": skipped, "calls": calls}
