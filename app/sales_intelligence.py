import json
import re
import time
from datetime import datetime, timedelta
from html import unescape
from urllib.parse import urljoin, urlparse

import requests

from app.db_models import LeadAudit, MeetingBrief, SalesActivity, SalesLead, SalesProposal


def _has(pattern: str, body: str) -> bool:
    return bool(re.search(pattern, body, re.I | re.S))


def _text(pattern: str, body: str) -> str:
    match = re.search(pattern, body, re.I | re.S)
    return re.sub(r"\s+", " ", unescape(match.group(1))).strip() if match else ""


def _count(pattern: str, body: str) -> int:
    return len(re.findall(pattern, body, re.I | re.S))


# Prioritet etiketləri MÜŞTƏRİ üçündür, mühəndis üçün yox. Əvvəl "KRİTİK / P1 / P2 / P3"
# yazılırdı — restoran və ya mağaza sahibi bunun nə demək olduğunu bilmir və hesabat
# "texniki sənəd" təsiri bağışlayırdı. İndi hər tapıntı sadə üç səviyyədən biri ilə gəlir.
TECILI = "Təcili"      # pul/müştəri birbaşa itir
VACIB = "Vacib"        # nəzərəçarpan itki, amma dərhal deyil
FAYDALI = "Faydalı"    # yaxşılaşdırma, təcili deyil


def _section(name: str, score: int, maximum: int, findings: list[str]) -> dict:
    return {"name": name, "score": max(0, min(score, maximum)), "max": maximum, "findings": findings}


def _seconds(ms) -> str:
    """Millisaniyəni müştərinin başa düşdüyü saniyəyə çevirir (1240 ms -> '1.2 saniyə')."""
    return f"{ms / 1000:.1f} saniyə" if ms is not None else "ölçülə bilmədi"


def audit_lead(db, lead: SalesLead) -> LeadAudit:
    """Saytı 8 istiqamətdə yoxlayır və fakt → təsir → addım formatında hesabat yaradır."""
    strengths, issues, opportunities, sections = [], [], [], []
    evidence = {"checked_url": lead.website, "checked_at": datetime.utcnow().isoformat() + "Z"}
    body = ""
    final_url = lead.website or ""
    elapsed_ms = None
    if lead.website:
        try:
            started = time.perf_counter()
            response = requests.get(lead.website, timeout=15, headers={"User-Agent": "TheAgencyAudit/2.0"})
            elapsed_ms = round((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            body = response.text[:1_000_000]
            final_url = response.url
            evidence.update(status=response.status_code, final_url=final_url, response_ms=elapsed_ms,
                            html_kb=round(len(response.content) / 1024, 1))
        except requests.RequestException as exc:
            issues.append(f"{TECILI} · Saytınız açılmadı. Sizi axtaran müştəri boş səhifə görür və çox güman rəqibə keçir. Hostinq/domen vəziyyəti yoxlanmalıdır.")
            evidence["fetch_error"] = type(exc).__name__
    else:
        issues.append(f"{TECILI} · Şirkətin rəsmi saytı yoxdur. Müştəri sizi axtaranda etibarlı məlumat tapa bilmir və sifariş verəcək yer olmur.")
        opportunities.append(f"{VACIB} · Telefon, WhatsApp və aydın sifariş düyməsi olan sadə bir səhifə hazırlayaq — telefonda mükəmməl görünsün.")

    # Texniki vəziyyət — 15
    points, findings = 0, []
    if body:
        points += 4; findings.append("Sayt normal açılır.")
        if urlparse(final_url).scheme == "https": points += 3; strengths.append("Sayt təhlükəsiz bağlantı ilə işləyir (ünvanda kilid işarəsi görünür).")
        else: issues.append(f"{TECILI} · Saytda təhlükəsizlik kilidi yoxdur. Brauzer ziyarətçiyə xəbərdarlıq göstərir — bu, müştərini qorxudub geri qaytarır.")
        if elapsed_ms is not None and elapsed_ms <= 1200: points += 4; strengths.append(f"Sayt sürətli açılır ({_seconds(elapsed_ms)}).")
        elif elapsed_ms is not None and elapsed_ms <= 2500: points += 2; findings.append(f"Saytın açılma sürəti ortadır ({_seconds(elapsed_ms)}).")
        else: issues.append(f"{VACIB} · Sayt gec açılır ({_seconds(elapsed_ms)}). Hər əlavə saniyə ziyarətçilərin bir hissəsinin gözləmədən getməsi deməkdir.")
        if evidence.get("html_kb", 0) <= 250: points += 2
        elif evidence.get("html_kb", 0) > 700: issues.append(f"{FAYDALI} · Səhifə ağırdır ({evidence['html_kb']} KB). Mobil internetdə yavaş yüklənir.")
        if _has(r'<meta[^>]+name=["\']viewport["\']', body): points += 2
        else: issues.append(f"{TECILI} · Sayt telefon ekranına uyğunlaşmır. Ziyarətçilərin böyük hissəsi telefondan girdiyi üçün bu, birbaşa müştəri itkisidir.")
    sections.append(_section("Saytın işləkliyi və sürəti", points, 15, findings))

    # SEO və indeksləmə — 18
    points, findings = 0, []
    title = _text(r"<title[^>]*>(.*?)</title>", body)
    description = _text(r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']', body)
    if not description: description = _text(r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']', body)
    h1_count = _count(r"<h1\b", body)
    evidence.update(title=title, title_length=len(title), description_length=len(description), h1_count=h1_count)
    if 20 <= len(title) <= 65: points += 4
    elif title: points += 2; issues.append(f"{VACIB} · Google-da görünən başlıq uyğun uzunluqda deyil ({len(title)} simvol; ideal 20-65). Çox qısa və ya uzun başlıq axtarışda kəsilir.")
    else: issues.append(f"{TECILI} · Səhifənin başlığı yoxdur. Google axtarış nəticəsində sizin adınıza nə yazacağını bilmir.")
    if 70 <= len(description) <= 170: points += 4
    elif description: points += 2; issues.append(f"{VACIB} · Google-da başlığın altında görünən izah mətni uyğun uzunluqda deyil ({len(description)} simvol; ideal 70-170).")
    else: issues.append(f"{TECILI} · Google-da başlığın altında görünəcək izah mətni yoxdur — Google saytdan təsadüfi cümlə seçir və bu, çox vaxt reklam kimi işləmir.")
    if h1_count == 1: points += 3
    elif h1_count == 0: issues.append(f"{VACIB} · Səhifənin əsas başlığı yoxdur. Ziyarətçi saytı açan kimi nə satdığınızı dərhal anlamır.")
    else: issues.append(f"{FAYDALI} · Səhifədə {h1_count} ədəd əsas başlıq var; bir dənə olmalıdır ki, mövzu aydın görünsün.")
    if _has(r'<link[^>]+rel=["\']canonical["\']', body): points += 2
    else: issues.append(f"{FAYDALI} · Eyni səhifənin təkrar ünvanlarını Google-a bildirən qeyd yoxdur; axtarışda özünüzlə rəqabət apara bilərsiniz.")
    if _has(r'<html[^>]+lang=', body): points += 1
    if body and final_url:
        origin = f"{urlparse(final_url).scheme}://{urlparse(final_url).netloc}"
        for filename, label in (("/robots.txt", "Google-a yol göstərən fayl"), ("/sitemap.xml", "Səhifə xəritəsi")):
            try:
                check = requests.get(urljoin(origin, filename), timeout=6, headers={"User-Agent": "TheAgencyAudit/2.0"})
                if check.ok and len(check.text.strip()) > 20: points += 2; findings.append(f"{label} mövcuddur.")
                else: opportunities.append(f"{VACIB} · {label} yoxdur — Google saytınızın bütün səhifələrini tapmaya bilər.")
            except requests.RequestException: opportunities.append(f"{FAYDALI} · {label} yoxlanıla bilmədi.")
    sections.append(_section("Google-da tapılma", points, 18, findings))

    # Lokal mövcudluq — 12
    points, findings = 0, []
    if lead.phone: points += 3; strengths.append("Saytda telefon nömrəsi açıq görünür.")
    else: issues.append(f"{TECILI} · Saytda telefon nömrəsi görünmür. Sifariş vermək istəyən müştəri sizinlə dərhal əlaqə saxlaya bilmir və axtarışını davam etdirir.")
    if lead.email: points += 2
    if lead.address: points += 2
    if _has(r"google\.com/maps|maps\.google|openstreetmap|schema\.org/(localbusiness|restaurant)", body): points += 3
    else: opportunities.append(f"{VACIB} · Saytda xəritə və Google-dakı biznes profiliniz bağlanmayıb. Yaxınlıqda axtaran müştərilər sizi tapmır.")
    if lead.city and lead.city.lower() in body.lower(): points += 2
    sections.append(_section("Yerli tapılma (ünvan, xəritə)", points, 12, findings))

    # Konversiya yolu — 18
    points, findings = 0, []
    cta_count = len(re.findall(r"rezerv|book|order|sifariş|əlaqə|contact|zəng|call|whatsapp|demo|müraciət|get quote", body, re.I))
    forms = _count(r"<form\b", body)
    evidence.update(cta_signals=cta_count, forms=forms)
    if cta_count >= 3: points += 6; strengths.append("Saytda sifariş və əlaqə düymələri var.")
    elif cta_count: points += 3; issues.append(f"{VACIB} · Sifariş düymələri var, amma kifayət qədər gözə çarpmır. Müştəri nə edəcəyini axtarmalı olur.")
    else: issues.append(f"{TECILI} · Saytda aydın sifariş, rezervasiya və ya əlaqə düyməsi yoxdur. Ziyarətçi maraqlansa belə nə edəcəyini bilmir.")
    if forms: points += 3; findings.append(f"Saytda {forms} müraciət forması var.")
    else: opportunities.append(f"{TECILI} · Müraciət forması yoxdur. Maraqlanan ziyarətçinin adını və nömrəsini toplaya bilmirsiniz — o adam izsiz gedir.")
    if _has(r"wa\.me|api\.whatsapp|whatsapp", body): points += 3
    if _has(r"tel:|mailto:", body): points += 2
    if _has(r"thank.you|success|təşəkkür", body): points += 1
    if _has(r"price|pricing|qiymət|menu|menyu|package|paket", body): points += 3
    else: opportunities.append(f"{VACIB} · Qiymət və ya paketlər haqqında məlumat yoxdur. Müştərilərin çoxu təxmini qiymət görmədən əlaqə saxlamır.")
    sections.append(_section("Sifariş və əlaqə yolu", points, 18, findings))

    # Etibar — 12
    points, findings = 0, []
    if _has(r"review|testimonial|rəy|rating|ulduz", body): points += 4
    else: issues.append(f"{VACIB} · Müştəri rəyləri görünmür. Yeni müştəri sizə güvənmək üçün başqalarının təcrübəsini görmək istəyir.")
    if _has(r"about|haqqımızda|komanda|team|founder", body): points += 2
    if _has(r"privacy|məxfilik|terms|şərtlər", body): points += 2
    else: issues.append(f"{FAYDALI} · Məxfilik siyasəti və istifadə şərtləri səhifələri yoxdur; onlayn ödəniş və reklam üçün tələb oluna bilər.")
    if _has(r"instagram|facebook|linkedin|tiktok|youtube", body): points += 2
    else: opportunities.append(f"{VACIB} · Sosial şəbəkə hesablarınız sayta bağlanmayıb. Ziyarətçi işinizin canlı olduğunu görmür.")
    if _has(r"award|sertifikat|certificate|partner|tərəfdaş", body): points += 2
    sections.append(_section("Etibar (rəylər, sənədlər)", points, 12, findings))

    # Kontent — 10
    points, findings = 0, []
    words = len(re.sub(r"<[^>]+>", " ", body).split()); evidence["visible_word_estimate"] = words
    if words >= 250: points += 3
    elif body: issues.append(f"{VACIB} · Saytda mətn çox azdır. Nə etdiyiniz və rəqiblərdən nə ilə fərqləndiyiniz izah olunmur.")
    if _count(r"<h2\b", body) >= 2: points += 2
    if _has(r"blog|xəbər|məqalə|case study|portfolio|layihələr", body): points += 2
    else: opportunities.append(f"{FAYDALI} · Görülmüş iş nümunələri və faydalı məqalələr yoxdur — bunlar peşəkarlığınızı sübut edir.")
    if _has(r"biz sizə|sizə kömək|nəticə|fayda|benefit|problem", body): points += 3
    sections.append(_section("Məzmun və fərqlənmə", points, 10, findings))

    # Ölçmə — 8
    points, findings = 0, []
    if _has(r"googletagmanager|gtag\(|google-analytics|G-[A-Z0-9]+", body): points += 4; findings.append("Ziyarətçi statistikası (Google) quraşdırılıb.")
    else: issues.append(f"{TECILI} · Ziyarətçi sayğacı quraşdırılmayıb. Sayta kimin gəldiyini və nə etdiyini ölçə bilmirsiniz — reklama xərclənən pul kor gedir.")
    if _has(r"connect\.facebook\.net|fbq\(|facebook.*pixel", body): points += 2
    else: opportunities.append(f"{VACIB} · Facebook/Instagram reklamlarının nəticəsini ölçən kod yoxdur. Hansı reklamın satış gətirdiyini bilmək mümkün deyil.")
    if _has(r"hotjar|clarity\.ms|mouseflow", body): points += 2
    sections.append(_section("Ölçmə və statistika", points, 8, findings))

    # Accessibility və paylaşım — 7
    points, findings = 0, []
    images = re.findall(r"<img\b[^>]*>", body, re.I)
    with_alt = sum(bool(re.search(r"\balt=[\"'][^\"']+[\"']", image, re.I)) for image in images)
    evidence.update(images=len(images), images_with_alt=with_alt)
    if not images or with_alt / len(images) >= .8: points += 3
    else: issues.append(f"{FAYDALI} · {len(images)} şəkildən yalnız {with_alt} ədədində izah mətni var. Bu mətn Google-a şəkildə nə olduğunu tanıdır.")
    if _has(r'<meta[^>]+property=["\']og:(title|image)', body): points += 2
    else: opportunities.append(f"{FAYDALI} · Saytın linki WhatsApp və ya Facebook-da paylaşılanda şəkil və başlıq görünmür — link boş və etibarsız görünür.")
    if _has(r"aria-label|<label\b", body): points += 2
    sections.append(_section("Rahat istifadə və paylaşım", points, 7, findings))

    score = sum(item["score"] for item in sections)
    if not body: score = min(score, 20)
    # Plan MÜŞTƏRİYƏ oxunur — hər gün "nə edəcəyik" və "bu sizə nə verir" formatındadır.
    action_plan = [
        "1-ci gün · Ziyarətçi sayğacını quraşdırırıq ki, sayta kimin gəldiyi və neçəsinin sifariş verdiyi rəqəmlə görünsün.",
        "2-ci gün · Sifariş düyməsini, telefonu, WhatsApp-ı və qısa müraciət formasını gözə çarpan yerə çıxarırıq.",
        "3-cü gün · Google-da görünən başlıq və izah mətnini düzəldirik ki, axtarışda daha çox klik alasınız.",
        "4-cü gün · Müştəri rəylərini, görülmüş işləri və komanda səhifəsini əlavə edirik — güvən üçün.",
        "5-ci gün · Müştərinin əsas sualına cavab verən 2 sosial media materialı hazırlayırıq.",
        "6-cı gün · Google xəritə profilinizi sayta bağlayırıq ki, yaxınlıqda axtaranlar sizi tapsın.",
        "7-ci gün · Hər şeyi telefondan yoxlayırıq: sürət, formanın işləməsi və ölçmənin düzgünlüyü.",
    ]
    details = {"version": 2, "sections": sections, "evidence": evidence,
               "priorities": issues[:5], "action_plan": action_plan}
    audit = LeadAudit(
        lead_id=lead.id, score=score,
        summary=f"{lead.company_name} üçün saytın 8 istiqamət üzrə yoxlanışı: 100 baldan {score}. "
                f"{len(issues)} problem və {len(opportunities)} yaxşılaşdırma imkanı tapıldı.",
        strengths_json=json.dumps(strengths, ensure_ascii=False),
        issues_json=json.dumps(issues, ensure_ascii=False),
        opportunities_json=json.dumps(opportunities, ensure_ascii=False),
        details_json=json.dumps(details, ensure_ascii=False),
    )
    db.add(audit); db.commit(); db.refresh(audit)
    return audit


def create_proposal(db, workspace_id: int, lead: SalesLead, audit: LeadAudit | None,
                    language: str = "AZ") -> SalesProposal:
    language = "EN" if str(language).upper() == "EN" else "AZ"
    issues = json.loads(audit.issues_json or "[]") if audit else []
    details = json.loads(audit.details_json or "{}") if audit else {}
    if language == "EN":
        # DİQQƏT: açarlar `audit_lead`-dəki `_section(...)` adları ilə HƏRFBƏHƏRF eyni olmalıdır.
        # Bölmə adı dəyişəndə buranı da yeniləyin, əks halda tərcümə səssizcə işləməz və
        # ingiliscə təklifə Azərbaycanca bölmə adı düşər (`test_proposal_en_translates_sections` qoruyur).
        section_names = {
            "Saytın işləkliyi və sürəti": "site speed and reliability",
            "Google-da tapılma": "being found on Google",
            "Yerli tapılma (ünvan, xəritə)": "local visibility on the map",
            "Sifariş və əlaqə yolu": "how visitors place an order or get in touch",
            "Etibar (rəylər, sənədlər)": "customer trust and reviews",
            "Məzmun və fərqlənmə": "what makes you different",
            "Ölçmə və statistika": "measuring what actually works",
            "Rahat istifadə və paylaşım": "ease of use and link sharing",
        }
        weakest = sorted(details.get("sections", []), key=lambda item: item.get("score", 0) / max(item.get("max", 1), 1))[:3]
        gaps = ", ".join(section_names.get(item.get("name"), item.get("name", "your online presence")) for item in weakest)
        problem = (f"We checked your website and the weakest areas are: {gaps or 'your online sales journey'}. "
                   f"Your current score is {audit.score} out of 100." if audit else
                   "Your website and customer flow are not yet working together as one measurable system.")
        solution = ("In 7 days we fix the most urgent items: we set up visitor tracking so you can see real "
                    "numbers, make the order and contact buttons impossible to miss, improve how you show up "
                    "on Google, add customer reviews, and show you exactly where enquiries are being lost.")
    else:
        problem = " ".join(issues[:3]) or "Saytınız və müştəri axını hazırda ölçülən bir sistem kimi işləmir."
        solution = ("7 gün ərzində ən təcili məsələləri həll edirik: ziyarətçi ölçməsini quraşdırırıq, "
                    "sifariş düymələrini gücləndiririk, Google-da tapılmanı yaxşılaşdırırıq, müştəri "
                    "rəylərini əlavə edirik və müraciətlərin harada itdiyini rəqəmlə göstəririk.")
    proposal = SalesProposal(workspace_id=workspace_id, lead_id=lead.id, language=language,
                             problem=problem, solution=solution)
    db.add(proposal); db.commit(); db.refresh(proposal)
    return proposal


def create_outreach_sequence(db, workspace_id: int, lead: SalesLead):
    messages = [
        ("INITIAL", "Saytınız üzrə qısa pulsuz yoxlama", lead.outreach_message),
        ("FOLLOW_UP_3D", "Qısa əlavə", f"Salam, {lead.company_name}. Öncəki mesajıma qısa əlavə: sizə uyğun 3 inkişaf nöqtəsini ödənişsiz paylaşa bilərik."),
        ("FOLLOW_UP_7D", "Son mesaj", f"Salam, {lead.company_name}. Mövzu hazırda aktual deyilsə, narahat etməyəcəyik. Gələcək üçün qısa yoxlama nəticəsini saxlayaq?"),
    ]
    delays = [0, 3, 7]
    for (kind, subject, content), days in zip(messages, delays):
        db.add(SalesActivity(workspace_id=workspace_id, lead_id=lead.id, activity_type=kind, subject=subject, content=content, due_at=datetime.utcnow() + timedelta(days=days)))
    db.commit()


def create_meeting_brief(db, workspace_id: int, lead: SalesLead):
    brief = MeetingBrief(
        workspace_id=workspace_id, lead_id=lead.id,
        questions_json=json.dumps(["Hazırda yeni müştərilər əsasən haradan gəlir?", "Marketinqdə ən böyük çətinlik nədir?", "Növbəti 90 gün üçün əsas satış məqsədi nədir?", "Kontent və reklam üçün qərarı kim verir?"], ensure_ascii=False),
        objections_json=json.dumps(["Qiymət yüksəkdir — kiçik, 7 günlük sınaq işi ilə başlayaq, nəticəni rəqəmlə görəsiniz.", "Vaxtımız yoxdur — işi tam biz görürük, sizdən yalnız təsdiq gözlənilir.", "Özümüz edirik — komandanızı əvəz etmirik, sadəcə hazırlanma sürətini artırırıq."], ensure_ascii=False),
        agenda="5 dəq tanışlıq · 10 dəq hazırkı vəziyyət · 10 dəq yoxlama nəticələri · 5 dəq təklif və növbəti addım",
    )
    db.add(brief); db.commit(); db.refresh(brief); return brief
