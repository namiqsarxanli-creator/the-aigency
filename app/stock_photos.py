"""Brif üçün real, yüksək keyfiyyətli və istifadəsi izlənə bilən stok foto seçimi."""
import logging
import re
import math
from dataclasses import dataclass

import requests

from app.core import settings

logger = logging.getLogger(__name__)


@dataclass
class StockPhoto:
    url: str
    source: str
    page_url: str = ""
    credit: str = ""
    relevance_score: float = 0.0


# Subject matching is deliberately stronger than palette/style matching. A golden
# landscape must not beat a serum photo merely because the brief asks for gold.
_SUBJECTS = (
    {"serum", "serums", "dropper"}, {"cream", "creams", "moisturizer", "moisturiser"},
    {"coffee", "espresso", "cappuccino"}, {"restaurant", "dining", "food", "meal"},
    {"shoe", "shoes", "sneaker", "sneakers", "footwear"},
    {"hair", "hairstyle", "hairdresser"}, {"skin", "skincare", "cosmetics", "beauty"},
    {"car", "cars", "automobile", "vehicle"}, {"fitness", "gym", "workout", "exercise"},
)
_STYLE_WORDS = {"white", "black", "grey", "golden", "gold", "green", "blue", "pink",
                "orange", "yellow", "light", "shadow", "marble", "minimal", "luxury",
                "premium", "background", "product", "bottle", "glass", "table"}


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (value or "").lower()))


def _candidate_score(query: str, description: str, width: int, height: int) -> float | None:
    """Metadata relevance, not an image-vision judgment; reject unsupported matches."""
    if min(width or 0, height or 0) < 700:
        return None
    wanted, actual = _tokens(query), _tokens(description)
    # Specific subjects precede broader categories such as skincare.
    subject = next((group for group in _SUBJECTS if wanted & group), None)
    if subject and not actual & subject:
        return None
    meaningful = wanted - _STYLE_WORDS
    if not subject and not actual & meaningful:
        return None
    matched = wanted & actual
    relevance = sum(1 if word in _STYLE_WORDS else 6 for word in matched)
    if subject:
        relevance += 15
    coverage = len(matched) / max(1, len(wanted))
    aspect = abs(math.log(width / height))
    return relevance + 5 * coverage + min(min(width, height) / 1000, 2) - min(aspect, 2)


def _best_candidate(query: str, candidates: list[tuple[StockPhoto, str, int, int]]) -> StockPhoto | None:
    ranked = []
    for photo, description, width, height in candidates:
        score = _candidate_score(query, description, width, height)
        if photo.url and score is not None:
            photo.relevance_score = score
            ranked.append(photo)
    return max(ranked, key=lambda photo: photo.relevance_score, default=None)


# Vizual brif/istiqamət mətni çox vaxt Azərbaycancadır (bax `studio_ai`/`agency` prompt-ları),
# amma stok foto bazaları (Pexels/Unsplash/Pixabay) İNGİLİSCƏ açar sözlərlə işləyir. Əvvəlki
# yanaşma (`[A-Za-z0-9-]+` ilə süzmək) ə/ğ/ı/ş/ö/ü/ç olan hər sözü PARÇALAYIB mənasız hərf
# qırıntılarına çevirirdi ("işıq" → "i", "q") — nəticədə axtarış sorğusu zibilə çevrilir və
# mövzuyla əlaqəsi olmayan foto (məs. küçə bazarı) qayıdırdı (canlı istifadəçi tapıntısı).
# Həll: əvvəlcə hərfləri transliterasiya edirik (sözlər BÜTÖV qalır), sonra ən çox rast gəlinən
# marketinq/vizual söz ehtiyatını ingiliscəyə tərcümə edirik. Tam lüğət deyil — bacardığımızı
# tərcümə edir, qalanını (əsasən köməkçi sözlər) ataraq axtarışı korlamaqdan qorunur.
_AZ_TRANSLIT = str.maketrans({
    "ə": "e", "Ə": "E", "ğ": "g", "Ğ": "G", "ı": "i", "I": "i", "İ": "I",
    "ö": "o", "Ö": "O", "ü": "u", "Ü": "U", "ç": "c", "Ç": "C", "ş": "s", "Ş": "S",
})
_AZ_TO_EN = {
    "serum": "serum", "serumu": "serum", "krem": "cream", "kremi": "cream",
    "sise": "bottle", "suse": "glass", "qutu": "box", "flakon": "bottle",
    "deri": "skin", "sac": "hair", "el": "hand", "uz": "face", "boyun": "neck",
    "kosmetika": "cosmetics", "gozellik": "beauty", "gozelli": "beauty",
    "mehsul": "product", "cicek": "flower", "yarpaq": "leaf",
    "payiz": "autumn", "yay": "summer", "qis": "winter", "yaz": "spring", "movsum": "season",
    "gunes": "sunlight", "isiq": "light", "isigi": "light", "kolge": "shadow",
    "ag": "white", "qara": "black", "boz": "grey", "qizili": "golden", "qehveyi": "brown",
    "yasil": "green", "mavi": "blue", "cehrayi": "pink", "narinci": "orange", "sari": "yellow",
    "masa": "table", "agac": "wood", "das": "stone", "mermer": "marble",
    "otaq": "room", "vanna": "bathroom", "banyo": "bathroom", "aciq": "outdoor",
    "gulumseyen": "smiling", "qadin": "woman", "kisi": "man", "qiz": "girl",
}
_AZ_STOPWORDS = {
    "kadr", "kadrda", "bir", "ve", "ki", "ucun", "ile", "olan", "kimi", "uzerinde",
    "daxilinde", "ortasinda", "icinde", "yungul", "yanasma", "kompozisiya", "reng",
    "dogal", "gun", "tutan", "brif", "brife", "uygun", "yalniz", "movzu",
}


def _clean_query(text: str) -> str:
    transliterated = (text or "").translate(_AZ_TRANSLIT)
    words = re.findall(r"[A-Za-z0-9]+", transliterated)
    ignored = {"photo", "photography", "professional", "realistic", "high", "quality", "image", "8k"}
    useful = []
    for word in words:
        lower = word.lower()
        if lower in ignored or lower in _AZ_STOPWORDS or len(lower) < 2:
            continue
        useful.append(_AZ_TO_EN.get(lower, word))
    if not useful:
        return "product photography"
    # Tərcümə olunmuş/tanınan sözlər önə çəkilir ki, qısaldılmış sorğularda (bax `find_stock_photo`)
    # ilk itən söz təsadüfi yox, ən az etibarlı olan olsun.
    subjects = set().union(*_SUBJECTS)
    useful.sort(key=lambda w: (w.lower() not in subjects, w.lower() in _STYLE_WORDS,
                              w.lower() not in _AZ_TO_EN.values()))
    return " ".join(list(dict.fromkeys(useful))[:8])


def _search_pexels(query: str) -> StockPhoto | None:
    if not settings.pexels_api_key:
        return None
    response = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": settings.pexels_api_key},
        params={"query": query, "orientation": "square", "size": "large", "per_page": 12},
        timeout=12,
    )
    response.raise_for_status()
    photos = response.json().get("photos") or []
    if not photos:
        return None
    return _best_candidate(query, [(
        StockPhoto(url=(photo.get("src") or {}).get("large2x") or (photo.get("src") or {}).get("large", ""),
                   source="Pexels", page_url=photo.get("url", ""), credit=photo.get("photographer", "")),
        photo.get("alt") or "", photo.get("width") or 0, photo.get("height") or 0,
    ) for photo in photos])


def _search_unsplash(query: str) -> StockPhoto | None:
    if not settings.unsplash_access_key:
        return None
    response = requests.get(
        "https://api.unsplash.com/search/photos",
        headers={"Authorization": f"Client-ID {settings.unsplash_access_key}"},
        params={"query": query, "orientation": "squarish", "per_page": 12, "content_filter": "high"},
        timeout=12,
    )
    response.raise_for_status()
    results = response.json().get("results") or []
    if not results:
        return None
    return _best_candidate(query, [(
        StockPhoto(url=(photo.get("urls") or {}).get("regular", ""), source="Unsplash",
                   page_url=(photo.get("links") or {}).get("html", ""),
                   credit=(photo.get("user") or {}).get("name", "")),
        " ".join([photo.get("alt_description") or "", photo.get("description") or ""] +
                 [tag.get("title", "") for tag in photo.get("tags", [])]),
        photo.get("width") or 0, photo.get("height") or 0,
    ) for photo in results])


def _search_pixabay(query: str) -> StockPhoto | None:
    if not settings.pixabay_api_key:
        return None
    response = requests.get(
        "https://pixabay.com/api/",
        params={
            "key": settings.pixabay_api_key, "q": query, "image_type": "photo",
            "safesearch": "true", "per_page": 12, "min_width": 900,
        },
        timeout=12,
    )
    response.raise_for_status()
    hits = response.json().get("hits") or []
    if not hits:
        return None
    return _best_candidate(query, [(
        StockPhoto(url=hit.get("largeImageURL") or hit.get("webformatURL", ""), source="Pixabay",
                   page_url=hit.get("pageURL", ""), credit=hit.get("user", "")),
        hit.get("tags") or "", hit.get("imageWidth") or 0, hit.get("imageHeight") or 0,
    ) for hit in hits])


# Commons-da PDF/DjVu sənədlərin səhifə renderləri də "şəkil" kimi qaytarılır (köhnə qəzet və
# kitab skanları) — texniki olaraq JPEG və böyük ölçülüdür, amma marketinq vizualı kimi yararsızdır.
_DOCUMENT_SCAN_MARKERS = (".pdf/", ".djvu/", ".pdf.jpg", ".djvu.jpg", "/page1-", "/page2-")


def _is_document_scan(url: str) -> bool:
    low = url.lower()
    return any(marker in low for marker in _DOCUMENT_SCAN_MARKERS)


def _search_commons(query: str) -> StockPhoto | None:
    response = requests.get(
        "https://commons.wikimedia.org/w/api.php",
        params={
            "action": "query", "generator": "search", "gsrsearch": query,
            "gsrnamespace": 6, "gsrlimit": 15, "prop": "imageinfo",
            "iiprop": "url|size|extmetadata", "iiurlwidth": 1600, "format": "json",
        },
        headers={"User-Agent": "TheAgency/1.0 (local creative workspace)"},
        timeout=15,
    )
    response.raise_for_status()
    pages = (response.json().get("query") or {}).get("pages") or {}
    candidates = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        url = info.get("thumburl") or info.get("url", "")
        width, height = info.get("thumbwidth", 0), info.get("thumbheight", 0)
        if not url.lower().split("?")[0].endswith((".jpg", ".jpeg", ".png", ".webp")):
            continue
        if _is_document_scan(url):
            continue
        if min(width or 0, height or 0) < 700:
            continue
        meta = info.get("extmetadata") or {}
        license_name = (meta.get("LicenseShortName") or {}).get("value", "")
        if not any(tag in license_name.lower() for tag in ("cc", "public domain")):
            continue
        description = page.get("title", "") + " " + re.sub(
            r"<[^>]+>", "", (meta.get("ImageDescription") or {}).get("value", ""))
        score = _candidate_score(query, description, width, height)
        if score is not None:
            candidates.append((score, page, info, meta))
    if not candidates:
        return None
    score, page, info, meta = max(candidates, key=lambda item: item[0])
    artist = re.sub(r"<[^>]+>", "", (meta.get("Artist") or {}).get("value", ""))
    return StockPhoto(
        url=info.get("thumburl") or info["url"], source="Wikimedia Commons",
        page_url=info.get("descriptionurl", ""), credit=artist[:160], relevance_score=score,
    )


def find_stock_photo(search_terms: str, include_commons: bool = True) -> StockPhoto | None:
    """`include_commons=False` yalnız real stok bazalarını (Pexels/Unsplash/Pixabay) sınayır.

    NİYƏ: Wikimedia Commons ensiklopedik arxivdir — marketinq üçün çox vaxt mövzuya zəif uyğun
    nəticə verir və şəkilləri BRAUZERDƏN birbaşa açılanda 429 (hotlink məhdudiyyəti) qaytarır,
    yəni səhifədə sınıq görünür. Ona görə o, yalnız SON çarə kimi işlədilir (bax `_step_work`)."""
    query = _clean_query(search_terms)
    words = query.split()
    # Foto bazaları uzun generativ promptdan çox, 2-4 konkret sözlə yaxşı nəticə verir.
    queries = list(dict.fromkeys((query, " ".join(words[:4]), " ".join(words[:3]), " ".join(words[:2]))))
    # Sıra: Pexels (ən səxavətli limit) -> Unsplash (ən yüksək keyfiyyət) -> Pixabay (ən geniş çeşid).
    # Açarı olmayan provayder öz-özünə None qaytarıb keçilir, ona görə hamısını sadalamaq təhlükəsizdir.
    stock_providers = (_search_pexels, _search_unsplash, _search_pixabay)
    providers = stock_providers + (_search_commons,) if include_commons else stock_providers
    for provider in providers:
        for candidate_query in queries:
            if not candidate_query:
                continue
            try:
                result = provider(candidate_query)
                if result:
                    return result
            except (requests.RequestException, KeyError, ValueError) as exc:
                logger.warning("Stock foto provayderi cavab vermədi (%s): %s", provider.__name__, exc)
                break
    return None
