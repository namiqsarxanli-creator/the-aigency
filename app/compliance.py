"""Brend uyğunluğu yoxlaması — mətn səviyyəsində, ORTAQ.

NİYƏ AYRI MODUL: qadağan ifadə və terminologiya yoxlaması əvvəl YALNIZ Studio+ boru
xəttində vardı. Agent layihələri (`agency.py`) və kampaniya generatoru ondan keçmirdi,
ona görə həmin yollarda qadağan ifadə sərbəst çıxırdı — «checker işləmir» şikayətinin
əsl səbəbi bu idi (audit #10).

Modul QƏSDƏN saf datadır: nə DB, nə ORM, nə şəbəkə. `ComplianceRules` dondurulmuş
dataclass-dır və işçi thread-lərə təhlükəsiz ötürülə bilir — bu kod bazasında ORM
obyektinə işçi thread-dən toxunmaq artıq bir dəfə problem yaradıb.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Sahə etiketinin məzmuna sızması ("Auditoriya: …") — SC-1 imzası.
LABEL_RE = re.compile(r"\b(Auditoriya|Məqsəd|Faza|Mövzu|CTA|Format)\s*:", re.IGNORECASE)

# Nəticə vəd edən feillər. Konkret söz siyahısı kifayət etmir: «bərpa edən formula»
# qadağan siyahısında olmasa da sübutsuz iddiadır.
CLAIM_RE = re.compile(
    r"\b(bərpa ed|müalicə ed|sağald|aradan qaldır|yox ed|həll ed|zəmanət)\w*",
    re.IGNORECASE,
)

# DİQQƏT — «yazın» və «seçin» burada YOXDUR: onlar adi çağırışlardır («Şərhdə yazın»)
# və siyahıya salınanda hər düzgün CTA yer tutucu kimi rədd olunurdu.
PLACEHOLDER_RE = re.compile(
    r"(göstərin|izah edin|təqdim edin|əlavə edin|daxil edin|buraya yazın)\s*[.!…]?$",
    re.IGNORECASE,
)

_GLOSSARY_SEP = re.compile(r"\s*(?:->|→|=>|:)\s*")


def parse_glossary(value: str | None) -> list[list[str]]:
    """«səhv -> düzgün» sətirlərini cütlərə çevirir. Pozuq sətir sadəcə atılır."""
    pairs = []
    for line in split_lines(value):
        parts = _GLOSSARY_SEP.split(line, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            pairs.append([parts[0].strip(), parts[1].strip()])
    return pairs


def split_lines(value: str | None) -> list[str]:
    return [line.strip(" -•\t") for line in (value or "").splitlines() if line.strip(" -•\t")]


def split_phrases(value: str | None) -> list[str]:
    """Qadağan ifadələr üçün: sətir sonu VƏ vergül/nöqtəli vergüllə bölür.

    NİYƏ: istifadəçilər bu siyahını təbii şəkildə bir sətirdə vergüllə yazırlar
    («Möcüzəvi nəticə, dərhal müalicə, zəmanətli nəticə, …»). Yalnız sətir sonuna görə
    bölsək, bütün siyahı BİR ifadə olur və nəticə hər iki istiqamətdə səhv çıxır:
    «möcüzəvi nəticə» tutulmur, «problemlərini» sözü olan adi cümlə isə bloklanır.
    Canlı LUMÉA Brand Kit-ində məhz belə oldu.
    """
    out = []
    for line in split_lines(value):
        for part in re.split(r"[,;]", line):
            cleaned = part.strip(" .-•\t")
            if len(cleaned) >= 3:
                out.append(cleaned)
    return out


@dataclass(frozen=True)
class ComplianceRules:
    """Yoxlama üçün lazım olan hər şey — ORM-siz, thread-təhlükəsiz."""

    must_avoid: tuple[str, ...] = ()
    glossary: tuple[tuple[str, str], ...] = ()
    allowed_facts: tuple[str, ...] = ()

    @property
    def empty(self) -> bool:
        return not (self.must_avoid or self.glossary)


EMPTY_RULES = ComplianceRules()


def rules_from_workspace(workspace) -> ComplianceRules:
    """Workspace-dən qaydaları çıxarır. ÇAĞIRIŞ ƏSAS THREAD-DƏN OLMALIDIR (ORM oxuyur)."""
    if workspace is None:
        return EMPTY_RULES
    return ComplianceRules(
        must_avoid=tuple(split_phrases(getattr(workspace, "brand_forbidden_phrases", "") or "")[:30]),
        glossary=tuple(
            (wrong, right)
            for wrong, right in parse_glossary(getattr(workspace, "brand_glossary", "") or "")[:30]
        ),
        allowed_facts=tuple(split_lines(getattr(workspace, "brand_products", "") or "")[:12]),
    )


def _phrase_hit(phrase: str, lowered: str) -> bool:
    """Tam ifadə, ya da onun bütün sözləri ardıcıl olmasa da mətndə varsa.

    Tam uyğunluq kifayət etmir: «möcüzəvi nəticə» siyahıdadırsa «möcüzəvi effekt» keçirdi.
    Ona görə ifadənin ƏSAS sözü (ən uzunu) tək başına da tutulur.
    """
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    if phrase in lowered:
        return True
    # Kök üzrə tutuş YALNIZ qısa ifadələr üçün. «möcüzəvi nəticə» → «möcüzəvi» düzgündür;
    # «bütün dəri problemlərini həll edir» kimi uzun TƏSVİRLƏRDƏ isə ən uzun söz
    # («problemlərini») adi mətnlərdə də olur və yalan pozitiv verir. Uzun ifadələr
    # yalnız tam uyğunluqla tutulur.
    words = re.split(r"\s+", phrase)
    if len(words) > 2:
        return False
    candidates = [w for w in words if len(w) > 4]
    return bool(candidates) and max(candidates, key=len) in lowered


def check_text(text: str, rules: ComplianceRules, label: str = "mətn") -> list[str]:
    """Bir mətn parçasını yoxlayır. Pozuntuların insan oxuya biləcəyi siyahısını qaytarır."""
    problems: list[str] = []
    stripped = (text or "").strip()
    if not stripped:
        return problems
    lowered = stripped.lower()
    allowed = " ".join(rules.allowed_facts).lower()

    for phrase in rules.must_avoid:
        if _phrase_hit(phrase, lowered):
            problems.append(f"{label}: qadağan ifadə «{phrase}»")

    for wrong, right in rules.glossary:
        if wrong.lower() in lowered and right.lower() not in lowered:
            problems.append(f"{label}: «{wrong}» yerinə «{right}» yazılmalıdır")

    for match in CLAIM_RE.finditer(stripped):
        token = match.group(0)
        if token.lower() not in allowed:
            problems.append(f"{label}: sübutsuz iddia «{token}»")

    return list(dict.fromkeys(problems))


def repair_instruction(problems: list[str]) -> str:
    """Pozuntuları modelə geri verməyə hazır təlimat mətni."""
    return (
        "Çıxışında brend qaydalarına zidd yerlər var:\n"
        + "\n".join(f"- {p}" for p in problems)
        + "\nYalnız həmin yerləri düzəlt. Qalan mətni olduğu kimi saxla."
    )
