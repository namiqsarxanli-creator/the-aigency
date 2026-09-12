"""Studio+ generasiya boru xətti: brif → kontekst → model → doğrulama → düzəliş.

NİYƏ BU MODUL VAR: əvvəl Studio+-da generasiya addımı ÜMUMİYYƏTLƏ yox idi. `create_asset()`
ona verilən sətirləri bazaya yazırdı, o sətirlər isə kampaniya generatorunun şablonları idi.
Müştəri caption yerində metadata görürdü (audit SC-1…SC-4).

ƏSAS QAYDA: məzmun sahəsinə heç vaxt yer tutucu yazılmır. Model bir sahəni doldura bilmirsə,
o sahə `needs_input` siyahısına düşür və material `NEEDS_INPUT` statusu ilə qalır. Dürüst
boşluq saxta məzmundan yaxşıdır — bugünkü sistemin əsas günahı elə boşluğu şablonla doldurub
onu hazır məhsul kimi göstərmək idi.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from app.agency import _call_llm, _extract_json, brand_context_for_workspace
from app.compliance import ComplianceRules, check_text
from app.compliance import parse_glossary as _parse_glossary
from app.compliance import split_phrases as _split_phrases
from app.content_studio import RATIOS, SLIDE_ROLES

logger = logging.getLogger(__name__)

MAX_HEADLINE = 90
MIN_CAPTION = 40
MAX_CAPTION = 2200          # Instagram limiti
MAX_HASHTAGS = 8
MIN_CAROUSEL_SLIDES = 4

GOALS = [
    ("kesf", "Kəşf", "Bizi tanımayan adama çatmaq"),
    ("maraq", "Maraq", "Maraqlananı daha dərinə çəkmək"),
    ("etibar", "Etibar", "Şübhəni aradan qaldırmaq"),
    ("sifaris", "Sifariş", "Konkret addıma çağırmaq"),
]
TONES = [
    ("neytral", "Neytral"),
    ("isti", "İsti"),
    ("birbasa", "Birbaşa"),
    ("oynaq", "Oynaq"),
]
GOAL_LABELS = {key: label for key, label, _ in GOALS}
TONE_LABELS = dict(TONES)

# Bir kliklik düzəlişlər — brif dəyişmir, promptun sonuna bir cümlə əlavə olunur.
DELTAS = {
    "qisa": ("Daha qısa", "Caption-u təxminən 40% qısalt, mənanı və faktları saxla."),
    "isti": ("Daha isti", "Tonu daha səmimi et, oxucuya birbaşa müraciəti artır."),
    "birbasa": ("Daha birbaşa", "Girişi tamamilə at, ilk cümlədən əsas fikrə keç."),
    "emojisiz": ("Emoji-siz", "Heç bir emoji istifadə etmə."),
    "basliq": ("Yalnız başlıq", "Yalnız üç yeni başlıq variantı ver; caption və slaydları dəyişmə."),
}


# ---------------------------------------------------------------------------
# 1 · Giriş normalizasiyası
# ---------------------------------------------------------------------------

@dataclass
class StudioBrief:
    """Strukturlaşdırılmış giriş. Sərbəst mətn qutusu istifadəçidən prompt mühəndisi olmağı
    tələb edirdi — bu, onun əvəzidir."""

    content_format: str = "POST"
    goal: str = "maraq"
    subject: str = ""
    facts: list[str] = field(default_factory=list)
    cta: str = ""
    tone: str = "neytral"
    must_avoid: list[str] = field(default_factory=list)
    campaign_note: str = ""
    # Brand Kit-dən gələnlər. AYRI SAXLANILIR, çünki bunların prompta düşməsi
    # `brand_ai_consent`-dən asılıdır — lokal doğrulama isə razılıqdan asılı deyil
    # (heç nə kənara göndərilmir).
    brand_facts: list[str] = field(default_factory=list)
    glossary: list[list[str]] = field(default_factory=list)   # [[səhv, düzgün], ...]
    palette: str = ""
    consent: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @staticmethod
    def from_json(raw: str | None) -> StudioBrief | None:
        try:
            data = json.loads(raw or "")
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None
        known = {f for f in StudioBrief().__dict__}
        return StudioBrief(**{k: v for k, v in data.items() if k in known})


def _lines(value: str | None) -> list[str]:
    return [line.strip(" -•\t") for line in (value or "").splitlines() if line.strip(" -•\t")]


_GLOSSARY_SEP = re.compile(r"\s*(?:->|→|=>|:)\s*")


# Parser ortaq moduldadır — qaydalar iki yerdə saxlanmasın.
parse_glossary = _parse_glossary


def _brand_fields(workspace) -> dict:
    """Brand Kit-dən brifə keçən sahələr.

    Razılıq bayrağı da brifə yazılır ki, PROMPTU quran funksiya nəyi göndərə biləcəyini
    bilsin. Sahələrin özü həmişə doldurulur, çünki lokal doğrulama üçün lazımdır və
    doğrulama heç nəyi kənara göndərmir — razılıq yalnız xarici provayderə göndərməyə aiddir.
    """
    return {
        "must_avoid": _split_phrases(getattr(workspace, "brand_forbidden_phrases", "") or "")[:30],
        "brand_facts": _lines(getattr(workspace, "brand_products", "") or "")[:12],
        "glossary": parse_glossary(getattr(workspace, "brand_glossary", "") or "")[:30],
        "palette": (getattr(workspace, "brand_colors", "") or "").strip()[:300],
        "consent": bool(getattr(workspace, "brand_ai_consent", False)),
    }


def brief_from_form(form: dict, workspace) -> StudioBrief:
    """Formadan gələn dəyərləri brifə çevirir. Qadağan ifadələr Brand Memory-dən gəlir."""
    get = lambda key, limit=400: ((form.get(key) or [""])[0].strip())[:limit]
    # Format İSTİFADƏÇİ GİRİŞİDİR. Əvvəl birbaşa `create_asset`-ə ötürülürdü və naməlum
    # dəyər orada `ValueError` atıb səhifəni 500 ilə çökdürürdü (canlı sınaqda təsdiqləndi).
    # Naməlum format artıq səssizcə POST-a düşür — bu, məzmun qərarı deyil, forma qərarıdır.
    content_format = (get("format", 30) or "POST").upper()
    if content_format not in RATIOS:
        content_format = "POST"
    return StudioBrief(
        content_format=content_format,
        goal=get("goal", 20) or "maraq",
        subject=get("subject", 300),
        facts=_lines(get("facts", 2000))[:12],
        cta=get("cta", 200),
        tone=get("tone", 20) or "neytral",
        **_brand_fields(workspace),
    )


def brief_from_campaign_day(day, workspace) -> StudioBrief:
    """Plan günündən brif. Gün sahələri NİYYƏT kimi ötürülür, məzmun kimi yox (SC-1)."""
    campaign = day.campaign
    return StudioBrief(
        content_format=(day.content_type or "POST").upper(),
        goal="maraq",
        subject=(workspace.brand_products or workspace.brand_description or workspace.name or "").strip()[:300],
        facts=[],
        cta=(day.cta or "").strip()[:200],
        tone="neytral",
        **_brand_fields(workspace),
        campaign_note=(
            f"{campaign.name}, {day.day_number}-ci gün · faza niyyəti: {day.theme} · "
            f"platforma: {day.platform} · kampaniya məqsədi: {campaign.objective}"
        )[:500],
    )


# ---------------------------------------------------------------------------
# 2 · Kontekst
# ---------------------------------------------------------------------------

def studio_context(workspace, brief: StudioBrief) -> str:
    parts = []
    brand = brand_context_for_workspace(workspace)
    if brand:
        parts.append("BREND:\n" + brand)
    if brief.subject:
        parts.append(f"MÖVZU: {brief.subject}")
    if brief.campaign_note:
        parts.append(f"KAMPANİYA MÖVQEYİ: {brief.campaign_note}")
    # Brand Kit-dəki təklif də təsdiqlənmiş faktdır — ona görə forma sahəsi ilə birləşir.
    # Əvvəl yalnız forma sahəsi sayılırdı və nəticədə modelin Brand Kit-dən götürdüyü həqiqi
    # rəqəm («İlk 100 ön sifarişə 15% endirim») doğrulamada UYDURMA kimi rədd olunurdu.
    facts = list(brief.facts) + (brief.brand_facts if brief.consent else [])
    if facts:
        parts.append("TƏSDİQLƏNMİŞ FAKTLAR:\n" + "\n".join(f"- {fact}" for fact in facts))
    else:
        parts.append(
            "TƏSDİQLƏNMİŞ FAKTLAR: heç biri verilməyib — rəqəm, faiz, endirim, tarix, zəmanət "
            "və müştəri rəyi YAZMAQ TAMAMİLƏ QADAĞANDIR."
        )
    if brief.must_avoid:
        parts.append("QADAĞAN İFADƏLƏR:\n" + "\n".join(f"- {p}" for p in brief.must_avoid))
    if brief.consent and brief.glossary:
        parts.append(
            "TERMİNOLOGİYA — bu sözləri MƏHZ bu şəkildə yaz:\n"
            + "\n".join(f"- «{wrong}» YOX, «{right}» yaz" for wrong, right in brief.glossary)
        )
    if brief.consent and brief.palette:
        parts.append(
            "RƏNG PALİTRASI — visual_direction.palette sahəsində YALNIZ bunlar işlənə bilər, "
            "başqa rəng adı və ya HEX yazma:\n" + brief.palette
        )
    return "\n\n".join(parts)


STUDIO_SYSTEM = (
    "Sən Azərbaycan bazarı üçün işləyən təcrübəli sosial media kopiraytersən. "
    "Sənə brend məlumatı, kampaniya mövqeyi və təsdiqlənmiş faktlar verilir. "
    "Sən BİR material yazırsan.\n\n"

    "QAYDALAR:\n"
    "1. FAKT QADAĞASI — rəqəm, faiz, endirim, tarix, zəmanət müddəti, müştəri sayı və ya "
    "müştəri rəyi yalnız «TƏSDİQLƏNMİŞ FAKTLAR» bölməsindən götürülə bilər. Orada yoxdursa "
    "ümumiyyətlə yazma; təxmin etmə, yuvarlaqlaşdırma, nümunə kimi də yazma.\n"

    "2. YER TUTUCU QADAĞASI — məlumat çatmırsa boşluq qoyma və «... əlavə edin», "
    "«... göstərin», «buraya yazın» kimi təlimat mətni YAZMA. Əvəzinə həmin sahənin adını "
    "needs_input siyahısına at və qalanını yaz.\n"

    "3. DİL — mətn insanın danışdığı kimi olmalıdır. Sahə adı, iki nöqtəli etiket "
    "(«Auditoriya:», «Məqsəd:»), «·» ayırıcısı və ya kateqoriya adı mətnin içində "
    "GÖRÜNMƏMƏLİDİR.\n"

    "4. TON — sənə verilən ton təlimatına tam əməl et. Qadağan ifadələr siyahısındakı "
    "sözlərin heç birini işlətmə.\n"

    "5. UZUNLUQ — başlıq ən çoxu 90 simvol; caption 200–900 simvol; hər hashtag «#» ilə "
    "başlayan tək söz, ən çoxu 8 ədəd; emoji ən çoxu 2 ədəd və yalnız caption-da.\n\n"

    "CAVAB FORMATI: cavabın YALNIZ bir JSON obyekti olmalıdır — birinci simvol «{», "
    "sonuncu simvol «}». Markdown kod bloku, izah, giriş cümləsi OLMAMALIDIR."
)


def build_user_message(brief: StudioBrief, context: str, extra: str = "") -> str:
    slide_hint = ""
    if brief.content_format == "CAROUSEL":
        roles = ", ".join(role for role, _ in SLIDE_ROLES)
        slide_hint = (
            f"\n\nBu CAROUSEL-dir: `slides` sahəsinə {MIN_CAROUSEL_SLIDES}–7 slayd yaz. "
            f"Rollar bu sıradan seçilir: {roles}."
        )
    schema = {
        "headline_options": ["...", "...", "..."],
        "caption": "...",
        "hashtags": ["#..."],
        "visual_direction": {
            "subject": "kadrda nə var", "composition": "rakurs və kadr",
            "lighting": "işıq", "palette": "rəng istiqaməti",
        },
        "slides": [{"role": "hook", "headline": "...", "body": "..."}],
        "needs_input": ["çatışmayan məlumatın adı"],
        "confidence": "high",
    }
    return (
        f"{context}\n\n"
        f"FORMAT: {brief.content_format}\n"
        f"MƏQSƏD: {GOAL_LABELS.get(brief.goal, brief.goal)}\n"
        f"TON: {TONE_LABELS.get(brief.tone, brief.tone)}\n"
        f"NÖVBƏTİ ADDIM (CTA): {brief.cta or 'sərbəst seç'}"
        f"{slide_hint}{extra}\n\n"
        f"Tam olaraq bu açarlarla JSON qaytar:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
    )


# ---------------------------------------------------------------------------
# 3 · Doğrulama (audit §05) — promptdan daha vacibdir
# ---------------------------------------------------------------------------

_LABEL_RE = re.compile(r"\b(Auditoriya|Məqsəd|Faza|Mövzu|CTA|Format)\s*:", re.IGNORECASE)
# DİQQƏT — «yazın» və «seçin» BURADA YOXDUR. Onlar Azərbaycan dilində ən adi
# çağırışlardır («Şərhdə yazın», «Uyğun olanı seçin») və siyahıya salınanda hər
# düzgün CTA yer tutucu kimi rədd olunurdu. Yalnız MƏZMUN SLOTUNA ünvanlanmış
# təlimat feilləri qalır.
_PLACEHOLDER_RE = re.compile(
    r"(göstərin|izah edin|təqdim edin|əlavə edin|daxil edin|buraya yazın)\s*[.!…]?$",
    re.IGNORECASE,
)
_NUMBER_RE = re.compile(r"\d[\d\s.,]*\s*(%|faiz|manat|azn|ay|il|gün|dəfə|müştəri)?", re.IGNORECASE)


def _customer_texts(data: dict) -> list[tuple[str, str]]:
    """Yalnız MÜŞTƏRİNİN OXUYACAĞI mətnlər. `visual_direction` istehsal brifidir — orada
    etiket və «·» normaldır, ona görə yoxlanmır."""
    out = []
    for index, item in enumerate(data.get("headline_options") or [], start=1):
        if isinstance(item, str):
            out.append((f"başlıq {index}", item))
    if isinstance(data.get("caption"), str):
        out.append(("caption", data["caption"]))
    for index, slide in enumerate(data.get("slides") or [], start=1):
        if isinstance(slide, dict):
            for key in ("headline", "body"):
                if isinstance(slide.get(key), str):
                    out.append((f"slayd {index} {key}", slide[key]))
    return out


def validate(data: dict, brief: StudioBrief) -> list[str]:
    """Pozuntuların KONKRET siyahısı — düzəliş çağırışına birbaşa ötürülür."""
    problems: list[str] = []

    options = data.get("headline_options")
    if not isinstance(options, list) or not any(isinstance(o, str) and o.strip() for o in options):
        problems.append("headline_options: ən azı bir başlıq lazımdır")
    caption = data.get("caption")
    if not isinstance(caption, str) or len(caption.strip()) < MIN_CAPTION:
        problems.append(f"caption: ən azı {MIN_CAPTION} simvol olmalıdır")
    elif len(caption) > MAX_CAPTION:
        problems.append(f"caption: {MAX_CAPTION} simvoldan uzundur")

    if brief.content_format == "CAROUSEL":
        slides = data.get("slides")
        if not isinstance(slides, list) or len(slides) < MIN_CAROUSEL_SLIDES:
            problems.append(f"slides: carousel üçün ən azı {MIN_CAROUSEL_SLIDES} slayd lazımdır")

    hashtags = data.get("hashtags") or []
    if isinstance(hashtags, list) and len(hashtags) > MAX_HASHTAGS:
        problems.append(f"hashtags: {MAX_HASHTAGS} ədəddən çoxdur")

    for name, text in _customer_texts(data):
        stripped = text.strip()
        if not stripped:
            continue
        if "·" in text or _LABEL_RE.search(text):
            problems.append(f"{name}: mətnin içində sahə etiketi var")
        if _PLACEHOLDER_RE.search(stripped):
            problems.append(f"{name}: məzmun yox, təlimat yazılıb")
        # Qadağan ifadə, terminologiya və sübutsuz iddia ORTAQ qatdan yoxlanılır (audit #10) —
        # eyni qaydalar agent layihələrinə də tətbiq olunur.
        problems.extend(check_text(text, _rules(brief), label=name))
        if name.startswith("başlıq") and len(stripped) > MAX_HEADLINE:
            problems.append(f"{name}: {MAX_HEADLINE} simvoldan uzundur")

    problems.extend(_unsourced_numbers(data, brief))
    problems.extend(_palette_violations(data, brief))
    # Eyni problem bir neçə dəfə çıxa bilər — sıra qorunaraq təkrarlar atılır.
    return list(dict.fromkeys(problems))



# Brend palitrasında olmayan rəng adları. HEX dəyərləri ayrıca yoxlanılır.
# YALNIZ XROMATİK rənglər. «ağ», «qara», «boz» qəsdən YOXDUR: onlar neytraldır və demək
# olar hər palitranın təsvirində işlənir. LUMÉA-nın öz palitrası açıq fil sümüyüdür
# (#F4EFE6), ona görə modelin onu «yumşaq ağ» adlandırması pozuntu deyil — canlı sınaqda
# məhz bu, düzgün çıxışı NEEDS_INPUT-a saldı. Şikayətin əsl mövzusu MAVİ idi, ağ yox.
_COLOR_WORDS = (
    "mavi", "göy", "blue", "yaşıl", "green", "çəhrayı", "pink",
    "qırmızı", "red", "bənövşəyi", "purple", "narıncı", "orange", "sarı", "yellow",
)
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\b")


def _rules(brief: StudioBrief) -> ComplianceRules:
    """Brifi ortaq yoxlayıcının gözlədiyi formaya salır."""
    return ComplianceRules(
        must_avoid=tuple(brief.must_avoid),
        glossary=tuple((w, r) for w, r in brief.glossary),
        allowed_facts=tuple(_all_facts(brief)),
    )


def _palette_violations(data: dict, brief: StudioBrief) -> list[str]:
    """Vizual istiqamətdəki rəng brend palitrasına uyğun olmalıdır (audit #8).

    Model palitranı görmədikdə standart kosmetika estetikasına — mavi-ağa — meyl edir.
    """
    if not brief.palette:
        return []
    direction = data.get("visual_direction")
    if not isinstance(direction, dict):
        return []
    text = " ".join(str(v) for v in direction.values() if isinstance(v, str)).lower()
    allowed = brief.palette.lower()
    found = [
        f"palette: brend palitrasında olmayan rəng «{word}»"
        for word in _COLOR_WORDS
        if word in text and word not in allowed
    ]
    found += [
        f"palette: brend palitrasında olmayan HEX «{hex_value}»"
        for hex_value in _HEX_RE.findall(text)
        if hex_value.lower() not in allowed
    ]
    return found


def _all_facts(brief: StudioBrief) -> list[str]:
    """Rəqəm və iddia üçün icazəli mənbə: forma sahəsi + Brand Kit-dəki təklif."""
    return list(brief.facts) + list(brief.brand_facts)


def _unsourced_numbers(data: dict, brief: StudioBrief) -> list[str]:
    """Faktlarda olmayan rəqəm — hallüsinasiya riski. Faktlar verilibsə yumşaq davranırıq."""
    allowed = " ".join(_all_facts(brief)).lower()
    found = []
    for name, text in _customer_texts(data):
        for match in _NUMBER_RE.finditer(text):
            token = match.group(0).strip()
            digits = re.sub(r"\D", "", token)
            # Tək rəqəmli sadalama ("3 addım") adi kopiraytinqdir, iddia deyil.
            if len(digits) < 2 or digits in allowed:
                continue
            found.append(f"{name}: mənbəsiz rəqəm «{token}»")
    return found


# ---------------------------------------------------------------------------
# 4 · Generasiya + düzəliş dövrəsi
# ---------------------------------------------------------------------------

ALL_FIELDS = ["başlıq", "caption", "vizual istiqamət"]


def _empty_result(reason: str, brief: StudioBrief) -> dict:
    """Model olmadıqda və ya iki cəhddən sonra: UYDURMA MƏZMUN YAZILMIR."""
    return {
        "ok": False, "reason": reason,
        "headline_options": [], "caption": "", "hashtags": [],
        "visual_direction": {}, "slides": [],
        "needs_input": ALL_FIELDS if brief.content_format != "CAROUSEL" else ALL_FIELDS + ["slaydlar"],
        "confidence": "low",
    }


def generate_draft(workspace, brief: StudioBrief, extra_instruction: str = "") -> dict:
    """Bir generasiya + ən çoxu bir düzəliş cəhdi.

    Heç vaxt istisna atmır — çağıran tərəf `ok` sahəsinə baxır. `ok=False` olduqda material
    `NEEDS_INPUT` statusu ilə, BOŞ məzmun sahələri və görünən səbəblə saxlanılmalıdır.
    """
    context = studio_context(workspace, brief)
    extra = f"\n\nƏLAVƏ TƏLİMAT: {extra_instruction}" if extra_instruction else ""
    messages = [
        {"role": "system", "content": STUDIO_SYSTEM},
        {"role": "user", "content": build_user_message(brief, context, extra)},
    ]
    usage_ctx = {"workspace_id": workspace.id, "feature": "studio"}
    # CAROUSEL cavabı xeyli uzundur (3 başlıq + caption + 4–7 slayd + vizual + hashtag).
    # 900 token onda tez-tez ORTADA KƏSİLİRDİ: JSON pozulur, düzəliş cəhdi də kəsilir və
    # material səbəbsiz `NEEDS_INPUT` olurdu. Canlı demoda üç kartdan biri belə boş qaldı.
    max_tokens = 1600 if brief.content_format == "CAROUSEL" else 900

    raw = _call_llm(messages, max_tokens=max_tokens, temperature=0.6, model_tier="nano", usage_ctx=usage_ctx)
    if not raw:
        return _empty_result("Model əlçatan deyil və ya günlük büdcə dolub.", brief)

    data = _extract_json(raw)
    problems = validate(data, brief) if isinstance(data, dict) else ["cavab JSON deyil"]

    if problems:
        logger.info("Studio+ ilk cavabda %s problem — düzəliş cəhdi", len(problems))
        repair = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content":
                "Cavabında bu problemlər var:\n" + "\n".join(f"- {p}" for p in problems) +
                "\nYalnız həmin sahələri düzəlt. Qalanını olduğu kimi saxla. Yenə yalnız JSON qaytar."},
        ]
        raw = _call_llm(repair, max_tokens=max_tokens, temperature=0.3, model_tier="mini", usage_ctx=usage_ctx)
        data = _extract_json(raw) if raw else None
        problems = validate(data, brief) if isinstance(data, dict) else ["cavab JSON deyil"]
        if problems:
            logger.warning("Studio+ düzəlişdən sonra da pozuntu: %s", problems[:3])
            result = _empty_result(
                "Model iki cəhddə də keyfiyyət tələblərinə cavab vermədi: "
                + "; ".join(problems[:3]),
                brief,
            )
            return result

    return {
        "ok": True, "reason": "",
        "headline_options": [o.strip() for o in data.get("headline_options") or [] if isinstance(o, str) and o.strip()][:3],
        "caption": (data.get("caption") or "").strip(),
        "hashtags": [h.strip() for h in data.get("hashtags") or [] if isinstance(h, str) and h.strip()][:MAX_HASHTAGS],
        "visual_direction": data.get("visual_direction") if isinstance(data.get("visual_direction"), dict) else {},
        "slides": [s for s in (data.get("slides") or []) if isinstance(s, dict)],
        "needs_input": [str(n) for n in (data.get("needs_input") or []) if str(n).strip()][:8],
        # Etibar faktın OLUB-OLMAMASINDAN asılıdır, faktın haradan gəldiyindən yox.
        # Əvvəl yalnız forma sahəsinə baxırdı, ona görə Brand Kit-dəki təsdiqlənmiş
        # təkliflə yazılan material da «aşağı etibar» nişanı alırdı.
        "confidence": "low" if (data.get("confidence") or "").lower() == "low"
        or not _all_facts(brief) else "high",
    }


def visual_direction_text(direction: dict) -> str:
    """Strukturlu vizual istiqaməti brif mətninə çevirir (şəkil generatoruna da ötürülə bilər)."""
    labels = [("subject", "Kadr"), ("composition", "Kompozisiya"),
              ("lighting", "İşıq"), ("palette", "Rəng")]
    return " · ".join(
        f"{label}: {direction[key]}" for key, label in labels
        if isinstance(direction.get(key), str) and direction[key].strip()
    )
