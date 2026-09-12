"""Zeng agentinin xarakteri — "Aysel" adli satis numayendesi.

Skript `MainLessons/CallCenterAI/agent.py`-deki satis agentinden goturulub: etiraz emali,
sesli tesdiq ve bos saat yoxlamasi ile REAL satis danisigi. NIYE: evvelki versiya sirketin
OZUNU teqdim eden reklam monoloqu idi — canli zengde qarsi teref danisiga qatila bilmirdi,
agent ise "maraqli deyil" cavabina baxmayaraq gorus teyin edirdi.

Ferqi: CallCenterAI CRM-deki lead-e zeng edir ve neticeni CRM-e yazir; bu agent ise
teqdim edenin gosterdiyi NOMREYE zeng edir ve gorusu `pitch_meetings` cedveline yazir.
"""

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BAKU = ZoneInfo("Asia/Baku")
BUSINESS_DAYS = range(0, 5)  # Bazar ertesi - Cume (Python: 0=B.e)
BUSINESS_HOURS = range(10, 18)  # 10:00 - 17:00 başlanğıclı saatlıq növbələr
MAX_SUGGESTIONS = 2

SALES_PROMPT = """Sen "The Aigency" adli reqemsal marketinq studiyasinin satis numayendesisen.
Adin Aysel-dir. AZERBAYCAN DILINDE, tebii telefon danisigi ile danisirsan.

SIRKET NE SATIR:
Kicik ve orta biznesler ucun reqemsal gorunus xidmeti — sosial media kontenti, kampaniya
planlari, reklam metnleri ve sayt/landing sehifeleri. Isi AI agentlerinden ibaret komanda
gorur, ona gore hazirlanma muddeti gunlerle olcurulur, heftelerle yox.
Baslangic paket 299 manatdan baslayir. DAHA DEQIQ RAQAM DEME — qiymet isin hecmine gore
deyisir, deqiq teklifi gorusde veririk.

ESAS MEQSED — 15 deqiqelik onlayn gorus teyin etmek.
Zengde is baglamaga calisma. Yegane hedef: qarsi terefin teqvimine qisa gorus salmaq.

DANISIQ QAYDALARI:
- EN VACIB QAYDA — ESITMEDIYINI UYDURMA. Telefon xetti dar zolaqlidir, sozler tez-tez
  sehv esidilir. Qarsi terefin dediyinden EMIN DEYILSENSE, cavab vermeden once qisaca
  tesdiqle: "Duz basa dusdumse, ... dediniz, elemi?" Emin olmadan MOVQE TUTMA.
- QARSI TEREFIN AGZINA SOZ QOYMA. O demediyi bir seyi "siz dediniz ki..." deye tekrarlama.
- OZ SESINI QARSI TEREFIN SESI ILE QARISDIRMA. Telefonda oz sozlerin bezen geri exo kimi
  qayidir. Eger "esitdiyin" sey senin ozunun az once dediyin cumleye oxsayirsa, ONA CAVAB
  VERME — sadece sakit gozle ki, qarsi teref danissin.
- ILK CUMLEDE ozunu tanit ve suni intellekt assistenti oldugunu ac-aciq de. Gizletme.
- SALAMLASMA YALNIZ BIR DEFEDIR. Ondan sonraki hec bir cavabin "salam" ile baslamasin
  ve ozunu ikinci defe tanitma — sohbet davam edir, yeni zeng deyil.
- QISA danis: her cavab 1-2 cumle. Telefon sohbetidir, muhazire deyil.
- Bir defede BIR sual ver, cavabi gozle.
- Qarsi teref sozunu kesirse dayan, qulaq as.
- SIRKET HAQQINDA REKLAM MONOLOQU OXUMA. AI agentlerinin siyahisini, texnologiya adlarini
  ve imkanlari sadalama — qarsi terefi bu maraqlandirmir, sohbeti oldurur.
- Uydurma: konkret qiymet, musteri adi, statistika, zemanet verme. Bilmirsense
  "bunu gorusde deqiqlesdirek" de.
- Ilk "yox"da geri cekilme — asagidaki ETIRAZ bolmesine bax. Amma IKI cehdden sonra dayan.

ESITMEDIKDE (telefon xetti kefiyyetsizdir):
- Qarsi terefin sozu anlasilmaz, yarimciq ve ya menasizdirsa, onun uzerine CAVAB UYDURMA.
  Sadece "baglanti bir az kesildi, tekrar edersiniz?" de.
- HEC VAXT ikinci defe eyni seyi "tekrar edersiniz" deme — ikinci defe anlamasan, movzunu
  sadelesdirib QAPALI sual ver: "Qisa sual verim — bu hefte 15 deqiqe vaxtiniz olar?"
- Etiraz, vaxt ve ya "he/yox" kimi QERAR bildiren cavablarda sehv esitmek bahaliya basa gelir:
  bele cavablari her zaman qisaca tekrarlayib tesdiqlet, sonra davam et.

ETIRAZLARLA IS — EN VACIB HISSE:
Telefonda ilk "yox" demek demek olar hemise refleksdir, real qerar deyil. Ona gore HER
etiraza en azi bir defe qarsi arqument ver. Ucluk qaydasi ile isle:
  1) TESDIQ ET — qarsi terefi haqli cixar, mubahise etme ("Basa dusurem, tamamile normaldir").
  2) QARSI ARQUMENT — bir cumle, konkret ve fayda uzerinden. Umumi soz isletme.
  3) KICIK SUAL — boyuk "beli" isteme, kicik addim teklif et ("cersenbe 15 deqiqe ayira bilersiz?").

Etirazlar ve cavablari:
- "MARAQLI DEYIL" -> Sebebini oyren, ele bilmeden geri cekilme: "Basa dusurem. Bir sey
  deqiqlesdirim — hazirda yeni musteri axini sizi qane edir, yoxsa sadece vaxt meselesidir?"
  Cavaba gore davam et: axin yaxsidirsa "onda sizin ucun sistem qurmaq daha az isdir" de,
  vaxt meselesidirse asagidaki vaxt etirazina kec.
- "VAXTIM YOXDUR" -> "Mehz ona gore zeng edirem — isi tam biz goruruk, sizden ayda bir
  defe tesdiq gozlenilir. Gorus ozu 15 deqiqedir." Sonra: "Bu hefte yox, gelen hefte
  hansi gun daha sakit olur?"
- "BAHALIDIR" (qiymeti bilmeden deyilirse) -> "Qiymeti hele demedim, cunki isin hecmine
  gore deyisir. Kicik, 7 gunluk sinaq isi ile baslamaq olar — neticeni reqemle gorub sonra
  qerar verersiniz." Sonra: "Bele bir sinaq isini muzakire etmek ucun 15 deqiqe ayirarsiz?"
- "OZUMUZ EDIRIK / SMM-cimiz var" -> "Cox yaxsi, onda temeliniz var. Biz komandani evez
  etmirik — hazirlanma suretini artiririq, ayliq kontenti gunlerle yox saatlarla veririk."
- "MUSTERI ONSUZ DA GELIR" -> "Xosdur esitmek. Sual sudur: gelen musterilerin haradan
  geldiyini olcursunuzmu? Olculmeyende ugurlu kanali artirmaq mumkun olmur."
- "MATERIAL GONDER, BAXIM" -> Bu, yumsaq imtinadir. Once gorusu bir de teklif et:
  "Gonderirem, amma 15 deqiqelik sohbetde konkret sizin ucun gosterse daha faydali olar."
- "KIM SINIZ / HARADAN TAPDINIZ NOMREMI?" -> Duz cavab ver: aciq menbelerden (xerite,
  biznes katalogu) tapdiq. Gizletme, yalan danisma.

DAYANMA QAYDASI: Iki qarsi arqumentden sonra qarsi teref hele de "yox" deyirse ISRAR ETME.
Nezaketle "vaxtiniz ucun tesekkur, narahat etmeyecem" de ve sohbeti bitir.
Qarsi teref qeti/eseblidirse ve ya "bir daha zeng etme" deyirse — DERHAL dayan.

TARIX QAYDASI (COX VACIBDIR):
Azerbaycanda hefte gunleri danisiqda SIRA ILE deyilir:
1-ci gun = bazar ertesi, 2-ci gun = cersenbe axsami, 3-cu gun = cersenbe,
4-cu gun = cume axsami, 5-ci gun = cume, sonra senbe ve bazar.
Qarsi teref "3-cu gun" deyirse bu CERSENBEDIR, "novbeti hefte" deyirse gelen heftenin
hemin gunudur.
TARIXI OZUN HESABLAMA — asagidaki TEQVIM cedvelinden BIRBASA GOTUR. Bu, senin ozunun
hesabladigin tarixden HEMISE daha etibarlidir (canli sinaqda model "cersenbe" deyib
tesdiq aldiqdan sonra funksiyani sehv tarixle — "cume" gunu ile — cagirmisdi, cunki
tarixi zehnen hesablamisdi). Cedvelde gunu tap, YYYY-MM-DD-ni oradan istifade et.

{teqvim}

GORUS TEYIN ETME QAYDASI (BU IKI ADDIM HEC VAXT BIR CAVABDA BIRLESDIRILMIR):
- Vaxt teklif etmezden EVVEL bos_saatlari_yoxla funksiyasini cagir.
- Gun ve saati QARSI TEREF secmelidir. Sen ozunden vaxt uydurma.
- ADDIM 1 — TESDIQ SUALI: qarsi teref gun/saat deyende, HEMIN CAVABDA gorus_teyin_et
  funksiyasini CAGIRMA. Yalniz esitdiyini tekrarlayib sual ver: "Cersenbe, 9 sentyabr
  saat 14:00 — duzdurmu?" ve DAYAN, qarsi terefin novbeti sozunu gozle. Telefon xetti
  bezen sozu tersine esidir (meselen "maraqli deyil" "maraqlidir" kimi transkript ola
  bilir) — bu tesdiq addimi mehz belə sehvleri tutmaq ucundur, ATLAMA.
- ADDIM 2 — FUNKSIYA CAGIRISI: yalniz qarsi teref NOVBETI CAVABINDA aciq tesdiq
  edende ("beli", "duzdur", "he" ve b.) gorus_teyin_et funksiyasini cagir. Tesdiq
  gelmese (susma, basqa mövzu, aydinsiz cavab) funksiyani CAGIRMA, sualı tekrar ver.
- Funksiyani cagirdiqdan sonra onun qaytardigi VAXTI tekrarla. Cavab "dolu" gelerse — BU "DOLUDUR"
  SOZUNU ISLETME, kobud sesler. Yumsaq de ki hemin vaxt ucun basqa gorusunuz var, sonra AÇIQ SUAL
  ver: "Sizə hansı saat uyğun olardı?" Qarsi teref oz vaxtini deyende onunla davam et (tekrar
  bos_saatlari_yoxla/gorus_teyin_et cagirmaqla). Yalniz qarsi teref "sən de" kimi bir sey desə,
  funksiyanin qaytardigi alternativ vaxtlari TEKLIF kimi (diqte etmeden) qeyd et.

BASLANGIC: Ozunu tanit, suni intellekt oldugunu de ve danismaga bir deqiqe vaxti
olub-olmadigini sorus. Sirket haqqinda uzun izahat VERME."""

TOOLS = [
    {
        "type": "function",
        "name": "bos_saatlari_yoxla",
        "description": (
            "Verilmis tarix ucun bos gorus saatlarini qaytarir. Vaxt teklif etmezden EVVEL cagir."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "tarix": {"type": "string", "description": "YYYY-MM-DD formatinda tarix."},
            },
            "required": ["tarix"],
        },
    },
    {
        "type": "function",
        "name": "gorus_teyin_et",
        "description": (
            "Qarsi teref konkret gun/saati SESLI TESDIQ etdikden sonra cagir. Novbe cedvelini "
            "yoxlayir: bosdursa gorusu yazir, doludursa en yaxin bos vaxtlari qaytarir."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "elaqe_shexs": {"type": "string", "description": "Danisdigin sexsin adi."},
                "tarix": {"type": "string", "description": "Gorus tarixi, YYYY-MM-DD formatinda."},
                "saat": {"type": "string", "description": "Gorus saati, HH:MM, 24 saatliq, Baki vaxti."},
                "qeyd": {"type": "string", "description": "Qarsi terefin esas problemi/maragi."},
            },
            "required": ["tarix", "saat"],
        },
    },
]

AZ_WEEKDAYS = [
    "bazar ertəsi", "çərşənbə axşamı", "çərşənbə",
    "cümə axşamı", "cümə", "şənbə", "bazar",
]
AZ_MONTHS = [
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr",
]


def az_date(value: date) -> str:
    return f"{AZ_WEEKDAYS[value.weekday()]}, {value.day} {AZ_MONTHS[value.month - 1]}"


def build_call_context(db) -> dict | None:
    """Zəngin KİMƏ edildiyini CRM-dən götürür — danışığın keyfiyyətini məhz bu müəyyən edir.

    NİYƏ (canlı tapıntı, 12 sentyabr): əvvəlki CallCenterAI prototipində zəng HƏMİŞƏ konkret
    bir lead üçün olurdu və prompta şirkətin adı, sahəsi, ona GÖNDƏRDİYİMİZ emailin mövzusu
    və audit nəticəsi yazılırdı. Agent "3 gün əvvəl sizə mail yazmışdıq" deyə bilirdi — söhbət
    konkret və təbii çıxırdı. Layihə3-ə köçürəndə YALNIZ ümumi mətn skripti götürülmüşdü;
    kontekst olmayanda agentin deməyə konkret sözü qalmır, ümumi cümlələrə keçir və danışıq
    nəzərəçarpacaq dərəcədə pisləşir. Bu funksiya həmin konteksti geri qaytarır.

    Seçim: həm auditi, həm də hazırlanmış outreach mesajı olan ƏN YÜKSƏK BALLI lead — yəni
    agentin danışmağa ən çox konkret materialı olan şirkət.
    """
    from app.db_models import LeadAudit, SalesActivity, SalesLead

    lead = (
        db.query(SalesLead)
        .filter(
            SalesLead.id.in_(db.query(LeadAudit.lead_id)),
            SalesLead.id.in_(db.query(SalesActivity.lead_id)),
        )
        .order_by(SalesLead.score.desc(), SalesLead.id.desc())
        .first()
    )
    if lead is None:
        return None

    audit = (
        db.query(LeadAudit).filter(LeadAudit.lead_id == lead.id)
        .order_by(LeadAudit.id.desc()).first()
    )
    email = (
        db.query(SalesActivity).filter(SalesActivity.lead_id == lead.id)
        .order_by(SalesActivity.id).first()
    )

    gun_evvel = None
    if email is not None and email.created_at:
        gun_evvel = max(1, (datetime.utcnow() - email.created_at).days)

    return {
        "sirket": lead.company_name,
        "saha": (lead.category or "").replace("_", " "),
        "sehir": (lead.city or "").strip().title(),
        "email_movzu": getattr(email, "subject", None),
        "email_metn": (getattr(email, "content", "") or "")[:400],
        "email_gun_evvel": gun_evvel,
        "audit": getattr(audit, "summary", None),
    }


def _context_block(context: dict | None) -> str:
    if not context:
        return ""

    if context.get("email_movzu"):
        ne_vaxt = (
            f"{context['email_gun_evvel']} gun evvel"
            if context.get("email_gun_evvel") else "bir muddet evvel"
        )
        email_setri = (
            f"Bu sirkete {ne_vaxt} email gondermisik — movzu: \"{context['email_movzu']}\". "
            f"Mezmun: {context['email_metn']}"
            "\nZENGE MEHZ BU EMAILIN DAVAMI KIMI BASLA: evvelce emaili xatirlat, sonra sorus "
            "ki, baxa biliblermi. Bu, zengi soyuq zeng olmaqdan cixarir."
        )
    else:
        email_setri = "Bu sirkete hele email gondermemisik — zeng ilk temasdir."

    audit_setri = (
        f"\nKomandamiz onlarin reqemsal gorunusunu yoxlayib: {context['audit']}"
        "\nBALI, FAIZI VE PROBLEM SAYINI SESLENDIRME — telefonda bu reqemler tehqir kimi qebul "
        "olunur. Problemin OZUNU adi dille, bir cumle ile de."
        if context.get("audit") else ""
    )

    return (
        "\n\nKIME ZENG EDIRSEN:\n"
        f"Sirket: {context['sirket']}. Saha: {context['saha']}. Seher: {context['sehir']}.\n"
        f"{email_setri}{audit_setri}\n"
        "Sirketin adini danisiqda ISLET — bu, zengi konkret ve tebii edir."
    )


def _upcoming_calendar(days: int = 14) -> str:
    """Növbəti N günün YYYY-MM-DD + gün adı cədvəli — modelin ÖZÜ tarix arifmetikası
    aparmasının qarşısını alır (bax `TARIX QAYDASI`, canlı sınaqda tapılmış baq)."""
    lines = []
    for i in range(days):
        d = date.today() + timedelta(days=i)
        lines.append(f"{d.isoformat()} = {az_date(d)}")
    return "\n".join(lines)


def system_prompt(context: dict | None = None) -> str:
    today = date.today()
    prompt = SALES_PROMPT.replace("{teqvim}", _upcoming_calendar())
    return (
        f"{prompt}{_context_block(context)}"
        f"\n\nBugün: {today.isoformat()} — {az_date(today)}."
    )


def az_datetime(value: datetime) -> str:
    return f"{az_date(value.date())} saat {value.strftime('%H:%M')}"


def _parse_slot(tarix: str, saat: str) -> datetime | None:
    try:
        naive = datetime.strptime(f"{tarix} {saat}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None
    return naive.replace(tzinfo=BAKU)


def _is_business_slot(local_dt: datetime) -> bool:
    return local_dt.weekday() in BUSINESS_DAYS and local_dt.hour in BUSINESS_HOURS and local_dt.minute == 0


def _iter_business_slots(start: datetime):
    """`start`-dan etibarən, iş saatlarına (B.e–Cümə, 10:00–17:00, Bakı vaxtı) uyğun
    saatlıq növbələri sırayla qaytarır — iki həftəlik axtarış kifayətdir."""
    current = start.replace(minute=0, second=0, microsecond=0)
    if start.minute or start.second or start.microsecond:
        current += timedelta(hours=1)
    for _ in range(24 * 14):
        if _is_business_slot(current):
            yield current
        current += timedelta(hours=1)


def _booked_slots_utc(db) -> set:
    from app.db_models import PitchMeeting

    return {row.scheduled_at for row in db.query(PitchMeeting.scheduled_at).all()}


def _book_slot(db, local_dt: datetime, demo_call_id: int | None, note: str | None) -> None:
    from app.db_models import PitchMeeting

    db.add(PitchMeeting(
        demo_call_id=demo_call_id,
        scheduled_at=local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None),
        note=(note or None),
    ))
    db.commit()


def free_slots(db, tarix: str) -> dict:
    """Verilmiş gün üçün boş iş saatları — agent vaxt təklif etməzdən əvvəl bunu çağırır.

    Günün ADI da qaytarılır: model "3-cü gün" kimi ifadələri özü tarixə çevirəndə səhv
    salırdı (bax `MainLessons/CallCenterAI/agent.py`-dəki eyni qeyd), ona görə təsdiqi
    həmişə bu cavabdakı ad üzərindən etməlidir."""
    try:
        day = datetime.strptime(tarix, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {"ok": False, "error": "Tarix YYYY-MM-DD formatında olmalıdır."}

    now_baku = datetime.now(BAKU)
    booked_utc = _booked_slots_utc(db)
    slots = []
    for hour in BUSINESS_HOURS:
        local_dt = datetime(day.year, day.month, day.day, hour, tzinfo=BAKU)
        if local_dt < now_baku:
            continue
        if local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None) not in booked_utc:
            slots.append(f"{hour:02d}:00")

    if day.weekday() not in BUSINESS_DAYS:
        return {"ok": True, "gun": az_date(day), "bos_saatlar": [],
                "qeyd": "Bu gün iş günü deyil (B.e–Cümə işləyirik)."}
    return {"ok": True, "gun": az_date(day), "bos_saatlar": slots}


def schedule_meeting(db, tarix: str, saat: str, demo_call_id: int | None = None,
                     elaqe_shexs: str = "", qeyd: str = "") -> dict:
    """Növbə cədvəlinə baxaraq gün/saatı təyin edir, doludursa alternativ təklif edir."""
    requested = _parse_slot(tarix, saat)
    if requested is None:
        return {"ok": False, "error": "Tarix/saat formatı anlaşılmadı (YYYY-MM-DD, HH:MM istənilir)."}

    now_baku = datetime.now(BAKU)
    if requested < now_baku:
        return {"ok": False, "error": "Bu vaxt artıq keçib, gələcək bir vaxt seçin."}

    booked_utc = _booked_slots_utc(db)

    def is_free(local_dt: datetime) -> bool:
        return local_dt.astimezone(ZoneInfo("UTC")).replace(tzinfo=None) not in booked_utc

    if _is_business_slot(requested) and is_free(requested):
        _book_slot(db, requested, demo_call_id, " — ".join(p for p in (elaqe_shexs, qeyd) if p)[:255])
        return {
            "ok": True, "status": "tesdiqlendi",
            "vaxt": az_datetime(requested),
            "mesaj": f"Görüş təsdiqləndi: {az_datetime(requested)}.",
        }

    alternatives = []
    for slot in _iter_business_slots(requested):
        if is_free(slot):
            alternatives.append(az_datetime(slot))
        if len(alternatives) >= MAX_SUGGESTIONS:
            break

    # "artiq doludur" kimi kobud ifade evezine yumsaq dil: hemin vaxt ucun basqa gorus
    # oldugunu bildirib, konkret alternativleri DIKTE ETMEDEN, qarsi terefden sorusaraq
    # teklif etmek ucun (bax SALES_PROMPT-daki GORUS TEYIN ETME QAYDASI).
    reason = "bu vaxt iş saatlarından kənardır" if not _is_business_slot(requested) else "həmin vaxt üçün başqa görüşümüz var"
    return {
        "ok": True, "status": "dolu",
        "sebeb": reason,
        "alternativler": alternatives,
        "mesaj": (
            f"{reason.capitalize()}. Sizə hansı saat uyğun olardı? "
            f"(istəsəniz təklif: {', '.join(alternatives) if alternatives else 'tapılmadı'})"
        ),
    }


def handle_tool_call(name: str, arguments: str, demo_call_id: int | None = None) -> dict:
    from app.database import SessionLocal

    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        args = {}
    if name not in ("gorus_teyin_et", "bos_saatlari_yoxla"):
        return {"ok": False, "error": f"Bilinmeyen funksiya: {name}"}

    db = SessionLocal()
    try:
        if name == "bos_saatlari_yoxla":
            return free_slots(db, args.get("tarix", ""))
        return schedule_meeting(
            db, args.get("tarix", ""), args.get("saat", ""), demo_call_id,
            elaqe_shexs=args.get("elaqe_shexs", ""), qeyd=args.get("qeyd", ""),
        )
    finally:
        db.close()


# Whisper sukut esidende bu ifadeleri uydurur - transkriptde saxlamaga deyməz.
HALLUCINATIONS = ("izlədiyiniz üçün", "izlediyiniz", "təşəkkür edirəm.", "thanks for watching", "abunə ol")


def is_hallucination(who: str, text: str) -> bool:
    # `who != "AI"` — evvel burada sabit "Musteri" etiketi yazilmisdi, cagiran teref ise
    # "Qonaq" gonderirdi: netice filtr HEC VAXT islemirdi ve Whisper-in sukut uydurmalari
    # ("izlediyiniz ucun tesekkurler") transkripte dusurdu. Etiketden asili olmasin deye
    # AI-dan qeyri her kes ucun tetbiq olunur.
    return who != "AI" and len(text) < 60 and any(h in text.lower() for h in HALLUCINATIONS)
