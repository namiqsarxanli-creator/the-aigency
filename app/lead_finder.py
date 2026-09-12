"""Public business discovery and deterministic lead qualification."""
from dataclasses import dataclass
import html

import requests


CATEGORY_TAGS = {
    "restaurant": [("amenity", "restaurant"), ("amenity", "cafe")],
    "clinic": [("amenity", "clinic"), ("healthcare", "clinic"), ("amenity", "dentist")],
    "beauty": [("shop", "beauty"), ("shop", "hairdresser")],
    "hotel": [("tourism", "hotel"), ("tourism", "guest_house")],
    "real_estate": [("office", "estate_agent")],
    "fitness": [("leisure", "fitness_centre"), ("leisure", "sports_centre")],
    "education": [("amenity", "school"), ("amenity", "language_school"), ("office", "educational_institution")],
    "retail": [("shop", None)],
}


@dataclass
class FoundLead:
    company_name: str
    category: str
    city: str
    address: str
    website: str
    phone: str
    email: str
    source_external_id: str
    source_url: str
    score: int
    outreach_message: str


def _lead_score(tags: dict) -> int:
    score = 25
    if tags.get("website") or tags.get("contact:website"):
        score += 25
    if tags.get("phone") or tags.get("contact:phone"):
        score += 18
    if tags.get("email") or tags.get("contact:email"):
        score += 20
    if tags.get("contact:instagram") or tags.get("contact:facebook"):
        score += 7
    if tags.get("addr:street") or tags.get("addr:full"):
        score += 5
    return min(score, 100)


def _address(tags: dict) -> str:
    if tags.get("addr:full"):
        return tags["addr:full"]
    parts = [tags.get("addr:street"), tags.get("addr:housenumber")]
    return " ".join(str(part) for part in parts if part)


def _safe_website(value: str) -> str:
    value = str(value or "").strip()
    if value.startswith("www."):
        value = "https://" + value
    return value if value.lower().startswith(("https://", "http://")) else ""


# DİQQƏT: əvvəllər mesaj HƏMİŞƏ Azərbaycanca yazılırdı — Türkiyə/başqa ölkədəki lead-lərə də
# Azərbaycanca ilk mesaj gedirdi, mənasız görünürdü (canlı istifadəçi tapıntısı). İndi axtarış
# formunda dil seçilir və mesaj o dildə yazılır. Tam tərcümə mühərriki YOXDUR — bu, sadəcə
# 3 hazır şablon (AZ/TR/EN) arasından seçimdir, LLM sorğusu tələb etmir.
OUTREACH_LANGUAGES = {"az": "Azərbaycanca", "tr": "Türkçe", "en": "English"}

_OUTREACH_TEMPLATES = {
    "az": (
        "Salam, {name} komandası. {city} üzrə {category} sahəsində fəaliyyətinizi gördük. "
        "Brendiniz üçün sosial media görünüşü və müştəri cəlbetmə imkanları barədə qısa, "
        "öhdəliksiz audit hazırlamaq istərdik. Uyğundursa, 3 konkret inkişaf təklifini göndərək."
    ),
    "tr": (
        "Merhaba, {name} ekibi. {city} bölgesinde {category} alanındaki faaliyetinizi fark ettik. "
        "Markanız için sosyal medya görünürlüğü ve müşteri kazanımı konusunda kısa, ücretsiz "
        "bir denetim hazırlamak isteriz. Uygunsa, 3 somut geliştirme önerisi gönderelim."
    ),
    "en": (
        "Hi {name} team, we came across your {category} business in {city}. We'd like to put "
        "together a short, no-obligation audit of your social media presence and customer "
        "acquisition opportunities. If that's of interest, we'll send over 3 concrete suggestions."
    ),
}
_CATEGORY_LABELS = {
    "az": {"restaurant": "restoran", "clinic": "klinika", "beauty": "gözəllik", "hotel": "otel",
           "real_estate": "daşınmaz əmlak", "fitness": "fitnes", "education": "təhsil", "retail": "pərakəndə satış"},
    "tr": {"restaurant": "restoran", "clinic": "klinik", "beauty": "güzellik", "hotel": "otel",
           "real_estate": "gayrimenkul", "fitness": "fitness", "education": "eğitim", "retail": "perakende"},
    "en": {"restaurant": "restaurant", "clinic": "clinic", "beauty": "beauty", "hotel": "hotel",
           "real_estate": "real estate", "fitness": "fitness", "education": "education", "retail": "retail"},
}


def _outreach(name: str, category: str, city: str, language: str = "az") -> str:
    language = language if language in _OUTREACH_TEMPLATES else "az"
    category_label = _CATEGORY_LABELS[language].get(category, category)
    return _OUTREACH_TEMPLATES[language].format(name=name, city=city, category=category_label)


def discover_businesses(
    city: str, category: str, limit: int = 25, country: str = "", language: str = "az",
) -> list[FoundLead]:
    """Dünyanın istənilən şəhərində OSM biznesləri tapır.

    Ölkənin ayrıca verilməsi Paris/Texas və Paris/France kimi eyni adlı şəhərlərin
    qarışmasının qarşısını alır. Köhnə "Baku, Azerbaijan" formatı da işləməyə davam edir.
    """
    tags = CATEGORY_TAGS.get(category, CATEGORY_TAGS["retail"])
    city = " ".join(str(city or "").split())[:120]
    country = " ".join(str(country or "").split())[:120]
    location_query = ", ".join(part for part in (city, country) if part)
    geo = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": location_query, "format": "jsonv2", "limit": 1,
                "addressdetails": 1, "featuretype": "city", "accept-language": "az,en"},
        headers={"User-Agent": "TheAgencyLeadFinder/1.0"}, timeout=15,
    )
    geo.raise_for_status()
    places = geo.json()
    if not places:
        return []
    address = places[0].get("address") or {}
    resolved_city = address.get("city") or address.get("town") or address.get("municipality") or city
    resolved_country = address.get("country") or country
    resolved_location = ", ".join(part for part in (resolved_city, resolved_country) if part)
    south, north, west, east = [float(v) for v in places[0]["boundingbox"]]
    bbox = f"{south},{west},{north},{east}"
    clauses = []
    for key, value in tags:
        selector = f'["{key}"]' if value is None else f'["{key}"="{value}"]'
        for object_type in ("node", "way", "relation"):
            clauses.append(f"{object_type}{selector}({bbox});")
    query = f"[out:json][timeout:25];({''.join(clauses)});out center tags {max(limit * 3, 50)};"
    response = requests.post(
        "https://overpass-api.de/api/interpreter", data={"data": query},
        headers={"User-Agent": "TheAgencyLeadFinder/1.0"}, timeout=35,
    )
    response.raise_for_status()

    results = []
    seen = set()
    for element in response.json().get("elements", []):
        item_tags = element.get("tags") or {}
        name = html.unescape(str(item_tags.get("name") or "").strip())
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        external_id = f"osm:{element.get('type')}:{element.get('id')}"
        results.append(FoundLead(
            company_name=name, category=category, city=resolved_location, address=_address(item_tags),
            website=_safe_website(item_tags.get("website") or item_tags.get("contact:website")),
            phone=item_tags.get("phone") or item_tags.get("contact:phone") or "",
            email=item_tags.get("email") or item_tags.get("contact:email") or "",
            source_external_id=external_id,
            source_url=f"https://www.openstreetmap.org/{element.get('type')}/{element.get('id')}",
            score=_lead_score(item_tags),
            outreach_message=_outreach(name, category, resolved_location, language),
        ))
    return sorted(results, key=lambda lead: lead.score, reverse=True)[:limit]
