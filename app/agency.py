"""
The Aigency — AI agentlərindən ibarət avtonom yaradıcı komanda.

Axın:
  BRIEF        -> Orkestrator (CEO) brifi 4 tapşırığa bölür (Strateq, Kopirayter, Dizayner, Developer)
  IN_PROGRESS  -> hər tapşırıq növbə ilə: rol agenti işləyir -> REVIEW -> Tənqidçi (QA) təsdiqləyir
                  ya da geri qaytarır (revision limiti: 2)
  (hamısı DONE)-> Developer-in HTML çıxışı yığılıb deliverable kimi saxlanılır -> AWAITING_APPROVAL
  AWAITING_APPROVAL -> insan approve/reject edir -> DELIVERED / REJECTED

`advance_project()` vəziyyət maşınını YALNIZ BİR addım irəli aparır və bir hadisə (dict) qaytarır
— bu hadisə çağıran tərəfindən WebSocket vasitəsilə dashboard-a yayımlanır. Beləliklə uzun bir
layihə, addım-addım, canlı izlənən bir "iş günü" kimi görünür.
"""
import json
import logging
import re
import secrets
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import settings
from app.ai_telemetry import budget_available
from app.compliance import EMPTY_RULES, ComplianceRules, check_text, repair_instruction, rules_from_workspace
from app.stock_photos import find_stock_photo
from app.db_models import AgentMessage, AgentProject, AgentTask, AgentTaskVersion, Campaign, LlmUsage, Workspace

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 22
MAX_LLM_RETRIES = 2
_PROVIDER_COOLDOWN: dict[str, float] = {}
_PROVIDER_COOLDOWN_LOCK = threading.Lock()

# --- Token/xərc qeydiyyatı -------------------------------------------------
# LLM sorğuları paralel worker thread-lərdən gedir, ona görə DB-yə BİRBAŞA yazmırıq: bu, məhz
# əvvəl tapdığımız "eyni Session-u paralel thread-lərdən sorğulamaq" bugunu təkrarlayardı.
# Əvəzində qeydlər sadə dict kimi thread-təhlükəsiz bufer siyahısına yığılır və ƏSAS thread
# uyğun anda (`flush_usage`) hamısını bir dəfəyə DB-yə yazır.
_USAGE_BUFFER: list[dict] = []
_USAGE_LOCK = threading.Lock()


def _record_usage(entry: dict) -> None:
    with _USAGE_LOCK:
        _USAGE_BUFFER.append(entry)


def flush_usage(db: Session) -> int:
    """Buferdəki token qeydlərini DB-yə yazır. YALNIZ əsas thread-dən çağırılmalıdır."""
    with _USAGE_LOCK:
        pending, _USAGE_BUFFER[:] = list(_USAGE_BUFFER), []
    if not pending:
        return 0
    try:
        db.add_all([LlmUsage(**row) for row in pending])
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Token qeydləri yazıla bilmədi (%s sətir itdi)", len(pending))
        return 0
    return len(pending)

# Hamısı OpenAI-uyğun /chat/completions formatı təqdim edir — eyni kodla çağırıla bilirlər.
# Sırayla sınanır: biri açarsızdırsa keçilir, açarı olub uğursuz olsa (rate limit və s.) növbətiyə keçilir.
# OPENAI QƏSDƏN BU SİYAHIDA DEYİL. Həmin açar ÖDƏNİŞLİDİR və YALNIZ şəkil generasiyası üçün
# saxlanılır (`app/openai_images.py`). Mətn üçün Groq/Gemini/Cerebras/OpenRouter/HF pulsuz
# zənciri kifayətdir.
def _providers() -> list[dict]:
    return [
        {
            "name": "Groq",
            "url": "https://api.groq.com/openai/v1/chat/completions",
            "key": settings.groq_api_key,
            "model": settings.groq_model,
            # gpt-oss modelləri gizli "reasoning" tokenləri sərf edir (Gemini-dəki eyni problem) —
            # bunlar max_tokens büdcəsini yeyib görünən cavabı kəsirdi. "none" dəstəklənmir (400
            # xətası verir), "low" reasoning-i minimuma endirib tam cavabın keçməsinə imkan verir.
            "extra_body": {"reasoning_effort": "low"},
        },
        {
            # Şəkil artıq OpenAI-dan gəldiyi üçün Gemini-nin kvotası mətn üçün sərbəstdir.
            "name": "Gemini",
            "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
            "key": settings.gemini_api_key,
            "model": settings.gemini_model,
            # gemini-2.5-flash "thinking" modelidir: gizli düşüncə tokenləri max_tokens büdcəsini
            # yeyir və görünən cavabdan yalnız qırıntı qalır. CANLI TAPINTI (layihə #37): 500
            # token verilmişdi, cavabın yalnız 19 tokeni (48 simvol) görünürdü — Satış Strateqi
            # hesabatı "HƏDƏF MÜŞTƏRİ: Bakıda yaşayan, 2" sözünün ortasında kəsilirdi, PDF-də
            # bölmələr boş görünürdü. Groq-dakı eyni problem üçün "reasoning_effort" artıq
            # işlədilirdi, Gemini-yə əlavə edilməmişdi.
            # ÖLÇÜLDÜ: "low" KÖMƏK ETMİR (yenə 18 token) — yalnız "none" düşüncəni tam söndürür.
            "extra_body": {"reasoning_effort": "none"},
        },
        {
            # Çox sürətli (custom LPU), yaxşı keyfiyyət (Llama 3.3 70B). Groq/Gemini-dən sonra —
            # trial krediti bitəndə (30 gün) açar boş qalar və sadəcə keçilir.
            "name": "Cerebras",
            "url": "https://api.cerebras.ai/v1/chat/completions",
            "key": settings.cerebras_api_key,
            "model": settings.cerebras_model,
        },
        {
            # Bir açarla onlarla pulsuz model. Yuxarıdakılar dəqiqəlik kvotanı doldurduqda əlavə
            # ehtiyat verir. Pulsuz limit gündə ~50 sorğu olduğu üçün ƏSAS yox, EHTİYAT kimi sonda.
            "name": "OpenRouter",
            "url": "https://openrouter.ai/api/v1/chat/completions",
            "key": settings.openrouter_api_key,
            "model": settings.openrouter_model,
        },
        {
            "name": "Hugging Face",
            "url": "https://router.huggingface.co/v1/chat/completions",
            "key": settings.hf_api_key,
            "model": settings.hf_model,
        },
    ]

# Departamentlər: əvvəlcə YARADICI komanda məhsulu/brendi hazırlayır (yalnız bu departament
# QA-dan keçir), SONRA DƏSTƏK departamentləri (satış, marketinq, analitika)
# həmin hazır məhsula əsaslanıb öz hesabatlarını yazır. Sıra vacibdir — dəstək rolları order_index-ə
# görə sonda gəlir ki, yaradıcı çıxışları kontekst kimi görsünlər. Dəstək rolları QA-dan KEÇMİR
# (məsləhət/dəstək çıxışıdır, istifadəçi onsuz da təsdiqdən əvvəl hamısını görür) — bu, çoxlu
# departament olsa da layihəni sürətli və kvota-qənaətcil saxlayır.
CREATIVE_SEQUENCE = ["strategist", "copywriter", "designer", "developer"]
SUPPORT_SEQUENCE = ["sales_strategist", "outreach_writer", "marketing", "analytics"]
ROLE_SEQUENCE = CREATIVE_SEQUENCE + SUPPORT_SEQUENCE
# Yalnız bu rollar QA (Tənqidçi) yoxlamasından keçir; qalanları birbaşa DONE olur.
QA_ROLES = {"developer"}
# Sadə sosial post üçün bu üç hesabat kifayətdir və eyni anda hazırlanır. Analitika real
# kampaniya datasından paneldə hesablanır.
SOCIAL_SUPPORT_SEQUENCE = ["outreach_writer", "marketing"]
# Dəstək rolları arasındakı asılılıqlar. Yaradıcı komanda bitəndən sonra dəstək departamentləri
# PARALEL işləyir (bir-birindən müstəqildir), amma outreach_writer satış strategiyasını əsas
# götürdüyü üçün sales_strategist bitməmiş başlaya bilməz — bu asılılıq qorunur.
SUPPORT_DEPS = {}
# Neçə dəstək rolunu eyni anda işlətmək. LLM sorğuları I/O-bound olduğu üçün thread kifayətdir;
# provayder rate-limitini partlatmamaq üçün 4-lə məhdudlaşdırılıb.
SUPPORT_PARALLELISM = 4
# Hansı rol hansı departamentə aiddir (UI qruplaşdırması və hesabatlar üçün).
ROLE_DEPARTMENT = {r: "creative" for r in CREATIVE_SEQUENCE}
ROLE_DEPARTMENT.update({
    "sales_strategist": "sales", "outreach_writer": "sales",
    "marketing": "marketing", "analytics": "analytics",
})
ROLE_LABELS = {
    "ceo": "CEO",
    "strategist": "Strateq",
    "copywriter": "Kopirayter",
    "designer": "Dizayner",
    "developer": "Developer",
    "sales_strategist": "Satış Strateqi",
    "outreach_writer": "Satış Kopirayteri",
    "marketing": "Marketinq",
    "analytics": "Analitika",
    "legal": "Hüquq/Uyğunluq",
    "finance": "Maliyyə",
    "critic": "Tənqidçi (QA)",
}
MAX_REVISIONS = 2


# ---------------------------------------------------------------------------
# LLM əsası
# ---------------------------------------------------------------------------

def _parse_retry_seconds(response: requests.Response) -> float | None:
    """429 cavabından gözləmə müddətini çıxarır: əvvəlcə `Retry-After` başlığı, sonra Groq-un
    JSON mesajındakı "try again in 6.45s" formatı. Tapılmasa None (naməlum, uzun ola bilər)."""
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    match = re.search(r"try again in ([\d.]+)s", response.text, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _call_provider(
    provider: dict, messages: list[dict], max_tokens: int, temperature: float,
    usage_ctx: dict | None = None,
) -> str | None:
    """Bir provayderə (Groq/Gemini/HF) sorğu göndərir.

    429 (rate limit) adətən DƏQİQƏLİK token kvotasıdır — dəqiqə dolmayınca sıfırlanmır, ona görə
    eyni provayderi bir neçə dəfə gözləyib təkrar sınamaq mənasızdır (yalnız işi ləngidir). Belə
    halda DƏRHAL None qaytarılır ki, `_call_llm` növbəti provayderə (müstəqil kvotası olan) keçsin.
    Yalnız keçici şəbəkə xətaları/5xx üçün qısa backoff-la təkrar cəhd edilir."""
    payload = {
        "model": provider["model"],
        "messages": messages,
        **provider.get("extra_body", {}),
    }
    payload[provider.get("token_param", "max_tokens")] = max_tokens
    if provider.get("supports_temperature", True):
        payload["temperature"] = temperature

    def _log_usage(ok: bool, error_kind: str | None, started: float, data: dict | None = None) -> None:
        """Bir sorğunun nəticəsini bufere yazır (DB-yə toxunmur — thread-təhlükəsizdir)."""
        usage = (data or {}).get("usage") or {}
        _record_usage({
            **(usage_ctx or {}),
            "provider": provider["name"],
            "model": provider.get("model"),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "latency_ms": int((time.monotonic() - started) * 1000),
            "ok": ok,
            "error_kind": error_kind,
        })

    for attempt in range(1, MAX_LLM_RETRIES + 1):
        started = time.monotonic()
        try:
            response = requests.post(
                provider["url"],
                headers={
                    "Authorization": f"Bearer {provider['key']}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException:
            logger.exception("%s sorğusu göndərilə bilmədi (cəhd %s/%s)", provider["name"], attempt, MAX_LLM_RETRIES)
            if attempt < MAX_LLM_RETRIES:
                time.sleep(min(2 ** attempt, 8))
                continue
            _log_usage(False, "network", started)
            return None

        if response.status_code == 429:
            # Bəzi provayderlər (Groq TPM limiti kimi) cavabda "N saniyə sonra təkrar cəhd edin"
            # göstərir — bu, DƏQİQƏLİK kvota deyil, TOKEN BÜDCƏSİdir və bir neçə saniyədə bərpa
            # olunur (paralel dəstək batch-i bunu tez-tez tetikləyir). Qısa gözləmə dəyərlidirsə
            # (≤10s) EYNİ provayderdə bir dəfə təkrar sınayırıq — bu, zəif fallback-lərə (yavaş HF)
            # düşməkdən qat-qat sürətlidir. Gecikmə göstərilməyibsə (RPM/gündəlik kvota kimi uzun
            # müddətli məhdudiyyət ehtimalı) DƏRHAL növbəti provayderə keçilir.
            retry_after = _parse_retry_seconds(response)
            # Bir rolun 429-u bütün paralel agentlər üçün eyni kvotanın dolduğunu göstərir.
            # Provayderi qısa müddətlik yaddaşda söndürürük ki, qalan rollar eyni uğursuz sorğunu
            # və gözləməni təkrarlamasın. Uzun/gündəlik limit mesajlarında 10 dəqiqə cooldown.
            cooldown = max(45.0, retry_after or 600.0)
            with _PROVIDER_COOLDOWN_LOCK:
                _PROVIDER_COOLDOWN[provider["name"]] = time.monotonic() + cooldown
            logger.warning(
                "%s 429 (rate limit) qaytardı — gözləmədən növbəti provayderə keçilir. Cavab: %s",
                provider["name"], response.text[:300],
            )
            _log_usage(False, "rate_limit", started)
            return None

        if response.status_code >= 500:
            logger.warning(
                "%s server xətası %s (cəhd %s/%s)", provider["name"], response.status_code, attempt, MAX_LLM_RETRIES,
            )
            if attempt < MAX_LLM_RETRIES:
                time.sleep(min(2 ** attempt, 8))
                continue
            _log_usage(False, "server", started)
            return None

        if response.status_code in (401, 402, 403):
            # Yanlış açar, bitmiş kredit və ya icazə problemi cari prosesdə öz-özünə düzəlməyəcək.
            with _PROVIDER_COOLDOWN_LOCK:
                _PROVIDER_COOLDOWN[provider["name"]] = time.monotonic() + 86400
            logger.warning("%s müvəqqəti deaktiv edildi (HTTP %s).", provider["name"], response.status_code)
            _log_usage(False, "payment", started)
            return None

        try:
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"].strip()
        except Exception:
            logger.exception("%s cavabı emal edilə bilmədi: %s", provider["name"], response.text[:300])
            _log_usage(False, "parse", started)
            return None
        _log_usage(True, None, started, data)
        return content

    return None


def _call_llm(
    messages: list[dict], max_tokens: int = 700, temperature: float = 0.5, model_tier: str = "mini",
    usage_ctx: dict | None = None,
) -> str | None:
    """Provayderləri sırayla sınayır (Groq -> Gemini -> Hugging Face). Açarı olmayanlar keçilir.
    Biri rate-limit/xəta versə (bütün retry-lərdən sonra) avtomatik növbətiyə keçilir."""
    workspace_id = (usage_ctx or {}).get("workspace_id")
    if not budget_available(workspace_id):
        logger.warning("Workspace %s üçün günlük AI büdcəsi dolub — lokal fallback işləyir.", workspace_id)
        return None
    available = [p for p in _providers() if p["key"]]
    if not available:
        logger.warning("Heç bir LLM açarı (GROQ/GEMINI/HF) tapılmadı — agent nümunə çıxışla davam edir.")
        return None

    now = time.monotonic()
    with _PROVIDER_COOLDOWN_LOCK:
        available = [p for p in available if _PROVIDER_COOLDOWN.get(p["name"], 0) <= now]
    for provider in available:
        selected = dict(provider)
        text = _call_provider(selected, messages, max_tokens, temperature, usage_ctx=usage_ctx)
        if text:
            return text
        logger.warning("%s uğursuz oldu, növbəti provayderə keçilir…", provider["name"])

    return None


def _extract_json(text: str) -> dict | None:
    """LLM bəzən ```json ... ``` daxilinə bükür ya da ətrafına mətn əlavə edir — buradan çıxarırıq."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    candidate = match.group(0) if match else text
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Rol prompt-ları
# ---------------------------------------------------------------------------

ORCHESTRATOR_SYSTEM = (
    "Sən 'The Aigency' adlı AI agentliyinin CEO-su və orkestratorusan. Departamentlərin var: "
    "(1) YARADICI (Strateq, Kopirayter, Dizayner, Developer) məhsulu/brendi hazırlayır; "
    "(2) SATIŞ (Satış Strateqi, Satış Kopirayteri); (3) MARKETİNQ; (4) ANALİTİKA. "
    "Müştəridən brif alırsan və onu uyğun departamentlərə bölüşdürürsən. Əvvəlcə "
    "brifin NƏ TƏLƏB ETDİYİNİ təyin et: əgər brif sosial media (Instagram, Facebook, post, "
    "paylaşım, reklam mətni) haqqındadırsa output_type=\"social_post\", əgər sayt/landing page/veb "
    "haqqındadırsa (ya da aydın deyilsə) output_type=\"landing_page\" seç. "
    "Cavabı YALNIZ bu formatda strict JSON kimi qaytar, əlavə mətn YAZMA:\n"
    '{"output_type":"landing_page","tasks":['
    '{"role":"strategist","title":"...","description":"..."},'
    '{"role":"copywriter","title":"...","description":"..."},'
    '{"role":"designer","title":"...","description":"..."},'
    '{"role":"developer","title":"...","description":"..."},'
    '{"role":"sales_strategist","title":"...","description":"..."},'
    '{"role":"outreach_writer","title":"...","description":"..."},'
    '{"role":"marketing","title":"...","description":"..."},'
    '{"role":"analytics","title":"...","description":"..."}]}\n'
    "Hər `description` bu brifə görə həmin rolun tam olaraq nə etməli olduğunu 1-2 cümlə ilə izah etsin. "
    "Developer-in description-u output_type-a uyğun olsun: social_post-da 'Instagram-a hazır post "
    "mətni yaz', landing_page-də 'tam HTML landing page yaz'. Satış/Marketinq rolları bu məhsulu "
    "satmağa/tanıtmağa, Analitika isə ölçmə planına yönəlsin."
)

STRATEGIST_SYSTEM = (
    "Sən 'The Aigency' komandasında Strateqsən. Verilən brifə görə: mövqeləndirmə (positioning), "
    "hədəf auditoriya və əsas mesaj (key message) təyin edirsən. Qısa, konkret, maddələr şəklində "
    "Azərbaycan dilində cavab ver (5-8 sətir)."
)

COPYWRITER_SYSTEM = (
    "Sən 'The Aigency' komandasında Kopirayter-sən. Strateqin işini əsas götürərək bir başlıq "
    "(headline), qısa şüar (tagline) və 2-3 cümləlik təsviri mətn (body copy) yazırsan. "
    "Azərbaycan dilində, cəlbedici və qısa yaz. Formatı belə et:\nBAŞLIQ: ...\nŞÜAR: ...\nMƏTN: ..."
)

DESIGNER_SYSTEM = (
    "Sən 'The Aigency' komandasında vizual kuratorsan. Brifə uyğun Pexels və açıq foto arxivlərində "
    "axtarış üçün 4-8 konkret İNGİLİSCƏ açar söz yaz. Əsas subyekt, məkan və foto üslubunu seç; "
    "'8k', 'high quality', 'AI', rəng adları və uzun cümlələr yazma. Tanınmış şəxs və marka adı "
    "istifadə etmə. YALNIZ axtarış sözlərini qaytar. Nümunə: artisan coffee shop interior barista."
)

DEVELOPER_SYSTEM = (
    "Sən 'The Aigency' komandasında Developer-sən. Kopirayterin mətni və dizaynerin şəklindən "
    "istifadə edərək TAM, TƏK-FAYLLI bir HTML landing page yazırsan (inline CSS, xarici asılılıq "
    "yoxdur). Səhifə: <!doctype html> ilə başlasın, lang=\"az\" olsun, mobil-uyğun (responsive) "
    "olsun, verilən şəkil URL-ini <img> ilə istifadə etsin, başlıq/şüar/mətni göstərsin, bir "
    "'Daha ətraflı' düyməsi olsun. Bu real backend olmayan bir demo/mockup olduğu üçün düymənin "
    "kliklənəndə GÖRÜNƏN bir reaksiya verməsi VACİBDİR — inline <script> ilə düyməyə onclick "
    "təyin et ki, basılanda kiçik bir təşəkkür mesajı olan bölmə görünsün (məs. display:none "
    "olan bir <div>-i göstər), döymə heç bir şey etməsin deyilə. YALNIZ HTML kodu qaytar — heç "
    "bir izah, heç bir ```markdown kod bloku işarəsi yazma."
)

# Brif sosial media (Instagram və s.) tələb edəndə Developer HTML yox, birbaşa paylaşıma hazır
# post mətni yazır — QA əvvəllər məhz bunun olmamasını (HTML-in Instagram-a uyğun olmadığını) REVISE
# səbəbi kimi göstərirdi, bu, həmin problemi kökündən həll edir.
DEVELOPER_SOCIAL_SYSTEM = (
    "Sən 'The Aigency' komandasında Developer-sən, amma bu layihə sosial media (Instagram) "
    "postudur — HEÇ VAXT HTML/kod yazma. Kopirayterin başlıq/şüar/mətnini və dizaynerin şəkil "
    "təsvirini əsas götürərək, Instagram-da BİRBAŞA PAYLAŞILA BİLƏN hazır post mətni yaz: "
    "cəlbedici açılış cümləsi, qısa gövdə mətni, aydın çağırış (call-to-action), sətir sonunda "
    "3-6 aid hashtag (#) və uyğun yerlərdə 1-3 emoji. Azərbaycan dilində, Instagram caption "
    "formatında (qısa paraqraflar, sətir aralarında boşluq). YALNIZ hazır post mətnini qaytar — "
    "heç bir HTML, heç bir izahat, heç bir ```markdown işarəsi."
)

# --- Satış departamenti ---
# Bütün dəstək departamenti promptlarının SONUNA əlavə olunur. Zəif/yüklənmiş LLM-lər (rate-limit
# fallback zəncirində) tez-tez rolu izah edən bir giriş cümləsi ilə başlayır (məs. "Hüquq/Uyğunluq
# departamentində işləyən kimi, mən aşağıdakı hesabatı yazacam:") — bu, həm token/vaxt itkisidir,
# həm də çıxışı fasada bənzədir. Aydın nümunə ilə göstərmək təkcə "yazma" demiş olmaqdan daha
# effektivdir.
# DİQQƏT — BU MƏTNƏ KONKRET BAŞLIQ NÜMUNƏSİ ƏLAVƏ ETMƏYİN.
# Bu qayda BÜTÜN dəstək rollarına eyni cür əlavə olunur. Əvvəllər burada hüquq bölməsinə xas
# konkret nümunə ("RİSKLİ İDDİALAR...") var idi və zəif modellər öz məzmununu yazmaq əvəzinə
# həmin nümunəni papağayı kimi təkrarlayırdı — Satış Strateqi və Analitika hesabatları hüquq
# mətni ilə başlayırdı (canlı istifadədə tapıldı). Sonra nümunə "HƏDƏF MÜŞTƏRİ" ilə əvəz edildi,
# amma bu da eyni problemdir: o, satış rolunun başlığıdır və digər rollara sızır.
# Qayda TAM MÜCƏRRƏD qalmalıdır. Qoruyucu: tests/test_prompts.py.
_NO_PREAMBLE_RULE = (
    "\n\nÇOX VACİB FORMAT QAYDASI: cavabın yuxarıda SƏNƏ verilmiş başlıqlardan birincisi ilə "
    "başlamalıdır — ilk simvoldan. Həmin başlıqdan ƏVVƏL heç bir söz, heç bir cümlə, heç bir "
    "özünütəqdim, heç bir giriş ifadəsi OLMAMALIDIR — nə qədər qısa olsa belə."
)

SALES_STRATEGIST_SYSTEM = (
    "Sən 'The Aigency' Satış departamentinin Satış Strateqisən. Yaradıcı komandanın hazırladığı "
    "məhsul/brend və brifə əsasən qısa, konkret SATIŞ STRATEGİYASI qurursan. Bu dörd başlığı ver:\n"
    "1) HƏDƏF MÜŞTƏRİ: kim, hara, hansı ehtiyacla alır (ideal alıcı profili);\n"
    "2) SATIŞ NÖQTƏLƏRİ: 3-4 əsas səbəb (niyə məhz bunu almalıdırlar);\n"
    "3) ETİRAZLAR: 1-2 əsas tərəddüd və onlara qısa cavab;\n"
    "4) TƏKLİF BUCAĞI: endirim/bonus/təcililik ideyası.\n"
    "Azərbaycan dilində, maddələr şəklində, 6-10 sətir. YALNIZ strategiyanı yaz, izahat yox."
    + _NO_PREAMBLE_RULE
)

OUTREACH_WRITER_SYSTEM = (
    "Sən 'The Aigency' Satış departamentinin Satış Kopirayterisən. Satış Strateqinin planını və "
    "hazır məhsul/brendi əsas götürərək, MÜŞTƏRİNİN BİRBAŞA İSTİFADƏ EDƏ BİLƏCƏYİ satış "
    "materiallarını yazırsan. Dəqiq bu dörd bölməni eyni başlıqlarla və bu sırada ver:\n\n"
    "📧 SOYUQ EMAIL:\n(mövzu sətri + qısa, şəxsi, dəyər-yönümlü mətn + aydın çağırış)\n\n"
    "💬 DM / MESAJ SKRIPTI:\n(təbii, 2-3 cümləlik birbaşa mesaj)\n\n"
    "🎤 SATIŞ PİTİ (30 saniyə):\n(şifahi deyilə bilən qısa təqdimat)\n\n"
    "🎁 KAMPANİYA TƏKLİFİ:\n(konkret endirim/bonus + təcililik elementi)\n\n"
    "Azərbaycan dilində, cəlbedici amma dürüst. YALNIZ materialları yaz — heç bir izahat, heç bir "
    "```markdown işarəsi."
    + _NO_PREAMBLE_RULE
)

# --- Marketinq departamenti ---
MARKETING_SYSTEM = (
    "Sən 'The Aigency' Marketinq departamentindənsən. Hazır məhsul/brend və brifə əsasən qısa, "
    "praktik marketinq planı hazırlayırsan. Bu üç başlığı ver:\n"
    "1) 1 HƏFTƏLİK KONTENT TƏQVİMİ: 5-7 günlük cədvəl (hər gün: platforma + qısa post ideyası);\n"
    "2) PLATFORMAYA UYĞUN 2 POST: bir Instagram, bir başqa platforma (Facebook/TikTok) üçün qısa "
    "post mətni ideyası;\n"
    "3) REKLAM MƏTNİ (2 variant): qısa, fərqli çağırışlı ödənişli reklam mətni.\n"
    "Azərbaycan dilində, konkret və qısa. YALNIZ planı yaz."
    + _NO_PREAMBLE_RULE
)

# --- Analitika departamenti ---
ANALYTICS_SYSTEM = (
    "Sən 'The Aigency' Analitika departamentindənsən. Bu kampaniya/məhsul üçün NƏYİ ÖLÇMƏLİ olduğunu "
    "təyin edirsən. Bu dörd başlığı ver:\n"
    "1) ƏSAS KPI-lar: 3-5 ölçülə bilən göstərici (məs. çevrilmə faizi, CTR, əhatə);\n"
    "2) UĞUR MEYARLARI: hansı rəqəm 'uğur' sayılır (real hədəflər);\n"
    "3) A/B TEST İDEYALARI: 2-3 sınaq (nəyi nə ilə müqayisə etmək);\n"
    "4) İZLƏMƏ PLANI: hansı alətlə/necə ölçmək (qısa).\n"
    "Azərbaycan dilində, maddələr şəklində, qısa. YALNIZ hesabatı yaz."
    + _NO_PREAMBLE_RULE
)

# --- Hüquq / Uyğunluq departamenti ---
LEGAL_SYSTEM = (
    "Sən 'The Aigency' Hüquq/Uyğunluq departamentindənsən. Yaradıcı və satış materiallarını RİSK "
    "baxımından yoxlayırsan. Bu üç başlığı ver:\n"
    "1) RİSKLİ İDDİALAR: mətndə sübutsuz/şişirdilmiş və ya qanuni risk yarada biləcək iddialar "
    "(məs. sağlamlıq/müalicə vədləri) — hər birini qısa izah et;\n"
    "2) DÜZƏLİŞ TƏKLİFLƏRİ: həmin iddiaları necə daha təhlükəsiz ifadə etmək;\n"
    "3) DISCLAIMER-lər: əlavə olunası qısa hüquqi qeydlər (varsa).\n"
    "Risk yoxdursa 'RİSKLİ İDDİALAR: aşkar risk tapılmadı.' yaz. Azərbaycan dilində, qısa və "
    "praktik. Bu, peşəkar hüquqi məsləhət deyil, ilkin yoxlamadır — bunu 3-cü başlıqdan sonra bir "
    "qeyd kimi əlavə et, giriş cümləsi kimi YOX. YALNIZ hesabatı yaz."
    + _NO_PREAMBLE_RULE
)

# --- Maliyyə departamenti ---
FINANCE_SYSTEM = (
    "Sən 'The Aigency' Maliyyə departamentindənsən. Bu məhsul/kampaniya üçün qısa maliyyə görünüşü "
    "hazırlayırsan. Bu üç başlığı ver:\n"
    "1) QİYMƏT STRATEGİYASI: təklif olunan qiymət(lər) və məntiq (məs. dəyər-əsaslı, rəqabət);\n"
    "2) KAMPANİYA BÜDCƏSİ: təxmini xərc bölgüsü (reklam, kontent, digər) — faiz və ya nisbət kimi;\n"
    "3) ROI PROQNOZU: real fərziyyələrlə gözlənilən gəlir/gəlirlilik təxmini.\n"
    "Dəqiq rəqəm yoxdursa əsaslandırılmış TƏXMİN ver və fərziyyələri qeyd et. Azərbaycan dilində, "
    "qısa. YALNIZ hesabatı yaz."
    + _NO_PREAMBLE_RULE
)

CRITIC_SYSTEM = (
    "Sən 'The Aigency' komandasında Tənqidçi/QA-san. Sənə bir rolun çıxışı verilir, sən onu brifə "
    "uyğunluq, keyfiyyət və dəqiqlik baxımından qiymətləndirirsən. Cavabı YALNIZ bu strict JSON "
    'formatında qaytar: {"verdict":"APPROVE","feedback":"..."} və ya '
    '{"verdict":"REVISE","feedback":"nə düzəldilməlidir"}. Həddindən artıq sərt olma — yalnız '
    "aydın problem varsa REVISE de."
)


def _run_orchestrator(
    brief: str, retry_feedback: str | None = None, brand_context: str = "",
    usage_ctx: dict | None = None,
) -> dict | None:
    user_content = f"Müştəri brifi: {brief}"
    if brand_context:
        user_content += f"\n\nMƏCBURİ BRAND MEMORY — bütün tapşırıqlar buna uyğun olmalıdır:\n{brand_context}"
    if retry_feedback:
        # Bu, əvvəlki cəhdin təkrarıdır — CEO planı bu şikayəti HƏLL EDƏCƏK şəkildə qurmalıdır,
        # yoxsa komanda eyni səhvi təkrarlayıb müştərini yenidən narazı sala bilər.
        user_content += (
            f"\n\nDİQQƏT: bu, əvvəlki cəhdin TƏKRARIDIR. Müştəri əvvəlki nəticəni bu SƏBƏBDƏN rədd "
            f"etdi: \"{retry_feedback}\". Tapşırıq təsvirlərini (description) bu problemi konkret "
            f"həll edəcək şəkildə yaz — hər rol NƏYİ FƏRQLİ etməli olduğunu bilsin."
        )
    text = _call_llm(
        [
            {"role": "system", "content": ORCHESTRATOR_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        max_tokens=600,
        temperature=0.4,
        usage_ctx={**(usage_ctx or {}), "role": "ceo"},
    )
    return _extract_json(text) if text else None


def _run_role(
    role: str, brief: str, description: str, context: list[tuple[str, str]], output_type: str = "landing_page",
    retry_feedback: str | None = None, brand_context: str = "", usage_ctx: dict | None = None,
    extra_instruction: str | None = None, compliance: ComplianceRules = EMPTY_RULES,
) -> str | None:
    system_map = {
        "strategist": STRATEGIST_SYSTEM,
        "copywriter": COPYWRITER_SYSTEM,
        "designer": DESIGNER_SYSTEM,
        "developer": DEVELOPER_SOCIAL_SYSTEM if output_type == "social_post" else DEVELOPER_SYSTEM,
        "sales_strategist": SALES_STRATEGIST_SYSTEM,
        "outreach_writer": OUTREACH_WRITER_SYSTEM,
        "marketing": MARKETING_SYSTEM,
        "analytics": ANALYTICS_SYSTEM,
        "legal": LEGAL_SYSTEM,
        "finance": FINANCE_SYSTEM,
    }
    # Kontekst hər elementi ~800 simvola qədər qısaldılır — əks halda Developer-in tam HTML çıxışı
    # sonrakı 5+ rola tam ötürülüb prompt-u şişirdir və token limitini keçə bilər.
    def _clip(text: str, limit: int = 800) -> str:
        text = text or ""
        return text if len(text) <= limit else text[:limit] + " …(qısaldıldı)"
    context_lines = "\n\n".join(f"[{ROLE_LABELS.get(r, r)} işi]\n{_clip(out)}" for r, out in context)
    user_msg = f"Müştəri brifi: {brief}\n\nSənin tapşırığın: {description}"
    if brand_context:
        user_msg += f"\n\nMƏCBURİ BRAND MEMORY — çıxışın buna uyğun olmalıdır:\n{brand_context}"
    if retry_feedback:
        user_msg += (
            f"\n\nDİQQƏT — bu təkrar cəhddir, müştəri əvvəlki nəticəni bu səbəbdən rədd etdi: "
            f"\"{retry_feedback}\". İşini bu problemi nəzərə alaraq gör."
        )
    if context_lines:
        user_msg += f"\n\nKomandanın əvvəlki işləri:\n{context_lines}"
    if extra_instruction:
        # İstifadəçi bu bölməni yenidən yazdırır və konkret göstəriş verib. Ən sonda yerləşir ki,
        # modelin diqqətindən yayınmasın və digər qaydalardan ÜSTÜN tutulsun.
        user_msg += (
            f"\n\nİSTİFADƏÇİNİN ƏLAVƏ GÖSTƏRİŞİ (ƏN YÜKSƏK PRİORİTET) — əvvəlki variant "
            f"bəyənilmədi, bu dəfə buna əməl et:\n{extra_instruction}"
        )
    # Developer tam HTML+CSS+JS yazır — 1200 token çox vaxt kifayət etmirdi, çıxış ortada
    # kəsilib </body></html> belə yazılmırdı. 2400-ə qaldırıldı. Satış Kopirayteri və digər
    # çoxbölməli hesabat rolları 500-dən çox tələb edir.
    _MAX_TOKENS_BY_ROLE = {
        "developer": 2400,
        "outreach_writer": 900,
        "marketing": 900,
        # Satış Strateqi 4 bölmə yazır (HƏDƏF MÜŞTƏRİ / SATIŞ NÖQTƏLƏRİ / ETİRAZLAR / TƏKLİF
        # BUCAĞI) — default 500 token bunun üçün azdır, ölçüldükdə tam büdcəni yeyib sonu
        # kəsilirdi. Digər çoxbölməli dəstək rolları ilə eyniləşdirildi.
        "sales_strategist": 900,
        "analytics": 700,
        "legal": 700,
        "finance": 700,
    }
    max_tokens = _MAX_TOKENS_BY_ROLE.get(role, 500)
    messages = [
        {"role": "system", "content": system_map[role]},
        {"role": "user", "content": user_msg},
    ]
    tier = "nano" if role in {"analytics", "legal", "finance", "marketing", "sales_strategist"} else "mini"
    ctx = {**(usage_ctx or {}), "role": role}
    output = _call_llm(messages, max_tokens=max_tokens, temperature=0.6, model_tier=tier, usage_ctx=ctx)

    # UYĞUNLUQ YOXLAMASI (audit #10). Əvvəl yalnız Studio+ yolunda vardı, ona görə agent
    # layihələrində qadağan ifadə və səhv terminologiya sərbəst çıxırdı. Bir düzəliş cəhdi
    # verilir; yenə pozuntu qalsa çıxış BLOKLANMIR — layihəni tamamilə dayandırmaq daha
    # böyük ziyandır — amma jurnala düşür ki, təsdiq mərhələsində görünsün.
    if output and not compliance.empty:
        problems = check_text(output, compliance, label=ROLE_LABELS.get(role, role))
        if problems:
            logger.info("%s çıxışında %s uyğunluq pozuntusu — düzəliş cəhdi", role, len(problems))
            fixed = _call_llm(
                messages + [
                    {"role": "assistant", "content": output},
                    {"role": "user", "content": repair_instruction(problems)},
                ],
                max_tokens=max_tokens, temperature=0.3, model_tier=tier, usage_ctx=ctx,
            )
            if fixed:
                still = check_text(fixed, compliance, label=ROLE_LABELS.get(role, role))
                if len(still) < len(problems):
                    output = fixed
                    problems = still
            if problems:
                logger.warning("%s: düzəlişdən sonra da pozuntu qalır: %s", role, problems[:3])
    return output


def _run_critic(
    role: str, brief: str, output: str, brand_context: str = "", usage_ctx: dict | None = None,
) -> dict:
    text = _call_llm(
        [
            {"role": "system", "content": CRITIC_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Brif: {brief}\nBrand Memory: {brand_context or '(AI istifadəsinə icazə verilməyib)'}\n"
                    f"Rol: {ROLE_LABELS.get(role, role)}\nÇıxış:\n{output}"
                ),
            },
        ],
        max_tokens=300,
        temperature=0.3,
        usage_ctx={**(usage_ctx or {}), "role": "critic"},
    )
    parsed = _extract_json(text) if text else None
    if not parsed or "verdict" not in parsed:
        # LLM cavab vermədisə/parse olmadısa, axının dayanmaması üçün defolt APPROVE.
        return {"verdict": "APPROVE", "feedback": "(avtomatik təsdiq — QA cavabı alınmadı)"}
    return parsed


def _usable_image_prompt(text: str | None) -> bool:
    """Dizaynerdən İNGİLİSCƏ təsvir sözləri gözlənilir. LLM rate-limitə düşəndə ya boş qaytarır,
    ya da tapşırıq təsvirini Azərbaycanca təkrarlayır ("Brifə uyğun dizayner işini gör") — belə
    mətn şəkil generatoru üçün yararsızdır və nəticədə mövzu ilə bağlı olmayan şəkil çıxır."""
    if not text:
        return False
    # ə/ğ/ı/ş hərfləri ingiliscədə YOXDUR — varsa, deməli cavab Azərbaycanca mətndir, prompt deyil.
    if re.search(r"[əğışƏĞIŞ]", text):
        return False
    return len(re.findall(r"[A-Za-z]{3,}", text)) >= 3


def _image_terms_from_brief(brief: str) -> str:
    """Dizayner yararlı prompt vermədikdə şəkil mövzusunu BRİFİN ÖZÜNDƏN götürürük — sabit
    "modern business lifestyle" mətni brifə tamamilə yad şəkil verirdi."""
    text = re.sub(r"\s+", " ", brief or "").strip()
    return text[:180] or "modern business lifestyle"


def _pollinations_url(prompt: str) -> str:
    clean = (prompt or "brand illustration, minimalist, studio lighting").strip()[:300]
    # model=flux: pollinations-ın brifə/prompta ən sadiq (ən yaxşı prompt-adherence) modeli —
    # defolt model bəzən mövzudan uzaqlaşan generik nəticələr verirdi.
    # nologo=true: pollinations su nişanını gizlədir.
    # DİQQƏT: `enhance=true` QƏSDƏN ÇIXARILIB. O, promptu pollinations-ın öz LLM-i ilə
    # zənginləşdirirdi, amma indi cavab olaraq 200 + BOŞ gövdə (0 bayt) qaytarır — yəni
    # xəta kimi görünmür, sadəcə şəkil olmur. Nəticədə həmin URL-lər həm saytda, həm
    # Instagram-da sınırdı (Meta boş şəkildən konteyner yarada bilmir). Bax PROJECT_STATE.md, 55.
    params = "width=1024&height=1024&model=flux&nologo=true"
    return f"https://image.pollinations.ai/prompt/{quote(clean)}?{params}"


# ---------------------------------------------------------------------------
# Kömək funksiyaları
# ---------------------------------------------------------------------------

def _log_message(db: Session, project: AgentProject, from_role: str, to_role: str | None, kind: str, content: str) -> AgentMessage:
    msg = AgentMessage(project_id=project.id, from_role=from_role, to_role=to_role, kind=kind, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _event(project: AgentProject, msg: AgentMessage) -> dict:
    return {
        "type": "agent_event",
        "project_id": project.id,
        "workspace_id": project.workspace_id,
        "project_status": project.status,
        "from_role": msg.from_role,
        "to_role": msg.to_role,
        "kind": msg.kind,
        "content": msg.content,
    }


def new_share_token() -> str:
    """Müştəri linki üçün təxmin edilə bilməyən açar (ardıcıl ID ilə sadalamanın qarşısını alır)."""
    return secrets.token_urlsafe(24)


def create_project(
    db: Session, brief: str, telegram_chat_id: str | None = None, workspace_id: int | None = None
) -> AgentProject:
    project = AgentProject(
        brief=brief.strip(), status="BRIEF", telegram_chat_id=telegram_chat_id,
        workspace_id=workspace_id, share_token=new_share_token(),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def start_retry(db: Session, original: AgentProject, reason: str) -> tuple[AgentProject, dict]:
    """Rədd edilmiş layihədən eyni brif + rədd səbəbi ilə YENİ layihə yaradır ki, komanda nə üçün
    bəyənilmədiyini bilib təkrar cəhddə bunu düzəltsin. Aşkarlıq üçün yeni layihəyə dərhal (ceo
    rolundan) bir handoff mesajı yazılır ki, dashboard-da/Telegram-da niyə yeni layihə peyda
    olduğu aydın olsun."""
    retry = AgentProject(
        brief=original.brief, status="BRIEF",
        workspace_id=original.workspace_id,
        telegram_chat_id=original.telegram_chat_id,
        retry_feedback=reason.strip(), retry_of_id=original.id,
        share_token=new_share_token(),
    )
    db.add(retry)
    db.commit()
    db.refresh(retry)
    msg = _log_message(
        db, retry, from_role="ceo", to_role=None, kind="handoff",
        content=(
            f"⟳ Layihə #{original.id} rədd edildi (səbəb: \"{reason.strip()}\"). Bu səbəbi "
            f"nəzərə alaraq yeni cəhdə başlayıram."
        ),
    )
    return retry, _event(retry, msg)


def _usage_ctx(project: AgentProject) -> dict:
    """Token qeydlərini layihə/workspace-ə bağlayan kontekst (rol ayrıca əlavə olunur)."""
    return {"project_id": project.id, "workspace_id": project.workspace_id}


def _done_outputs(db: Session, project: AgentProject) -> list[tuple[str, str]]:
    tasks = (
        db.query(AgentTask)
        .filter(AgentTask.project_id == project.id, AgentTask.status == "DONE")
        .order_by(AgentTask.order_index)
        .all()
    )
    return [(t.role, t.output or "") for t in tasks]


def brand_context_for_workspace(workspace: Workspace | None) -> str:
    """Brand Memory mətni. Razılıq verilməyibsə boş qaytarır — Studio+ da bunu işlədir."""
    if not workspace or not workspace.brand_ai_consent:
        return ""
    fields = [
        ("Brend", workspace.name), ("Haqqında", workspace.brand_description),
        ("Auditoriya", workspace.brand_audience), ("Ünsiyyət tonu", workspace.brand_voice),
        ("Rənglər", workspace.brand_colors), ("Şriftlər", workspace.brand_fonts),
        ("Məhsul/xidmətlər", workspace.brand_products),
        ("Qadağan ifadələr", workspace.brand_forbidden_phrases),
    ]
    return "\n".join(f"- {label}: {value}" for label, value in fields if value)


def _brand_context(db: Session, project: AgentProject) -> str:
    if not project.workspace_id:
        return ""
    return brand_context_for_workspace(db.get(Workspace, project.workspace_id))


def _brand_field(brand: str, label: str) -> str:
    """`_brand_context`-in "- Label: dəyər" sətirlərindən birini çıxarır — tapılmasa boş."""
    prefix = f"- {label}: "
    for line in (brand or "").splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _marketing_fallback_plan(brief: str, brand: str) -> str:
    """Marketinq üçün ŞƏBLON ƏSASLI ehtiyat plan.

    NİYƏ LAZIMDIR: bütün LLM provayderləri eyni anda uğursuz olanda (rate limit/kvota — canlı
    sistemdə dəfələrlə baş verib) köhnə davranış "(Heç bir provayder cavab vermədi)" kimi boş
    üzrxahlıq yazırdı — hesabatda "marketinq planı YOXDUR" görünürdü. Marketinq planı hər layihədə
    MÜTLƏQ olmalıdır (istifadəçi tələbi), ona görə bu, uydurma detal DEYİL, real, işlək bir
    KANAL/TEZLİK/KPI skeletidir — brief və (varsa) brend adından qurulur. Provayderlər bərpa
    olananda istifadəçi «Yenidən yaz»la təfsilatlandıra bilər."""
    brand_name = _brand_field(brand, "Brend")
    products = _brand_field(brand, "Məhsul/xidmətlər")
    audience = _brand_field(brand, "Auditoriya")
    subject = brand_name or (brief or "").strip()[:80] or "məhsul/xidmət"

    lines = [
        "MARKETİNQ PLANI (şablon əsaslı ehtiyat nüsxə — AI provayderləri həmin an əlçatan olmadığı üçün)",
        "",
        f"Fokus: {subject}",
    ]
    if products:
        lines.append(f"Təklif: {products}")
    lines.append(f"Hədəf auditoriya: {audience or 'brifə əsasən müəyyənləşdirilməli'}")
    lines += [
        "",
        "Kanallar və tezlik:",
        "  • Instagram — 4-5 post/həftə + gündəlik Story",
        "  • TikTok/Reels — 2-3 qısa video/həftə",
        "  • Email/WhatsApp siyahısı — həftəlik 1 yeniləmə (varsa)",
        "",
        "Büdcə bölgüsü (indiqativ):",
        "  • 60% məzmun istehsalı + hədəflənmiş reklam",
        "  • 30% əməkdaşlıq/influencer sınaqları",
        "  • 10% A/B test və yeni kanal sınağı",
        "",
        "Əsas KPI-lar: əhatə (reach), aktivlik dərəcəsi (engagement rate), keçid sayı (CTR), satışa çevrilmə.",
        "",
        "Növbəti addım: LLM provayderi bərpa olunanda bu materialı Content Studio-da "
        "«Yenidən yaz» ilə brifə uyğun təfsilatlandırın.",
    ]
    return "\n".join(lines)


def _compliance(db: Session, project: AgentProject) -> ComplianceRules:
    """Uyğunluq qaydaları — ORM-siz surət. Razılıqdan ASILI DEYİL: yoxlama lokaldır,
    heç nə xarici provayderə göndərilmir; göndərilən yalnız modelin öz çıxışıdır."""
    if not project.workspace_id:
        return EMPTY_RULES
    return rules_from_workspace(db.get(Workspace, project.workspace_id))


# ---------------------------------------------------------------------------
# Vəziyyət maşını addımları
# ---------------------------------------------------------------------------

_SOCIAL_KEYWORDS = ("instagram", "sosial media", "sosial şəbəkə", "facebook", "post", "paylaşım", "hashtag", "reklam mətni")


def _guess_output_type(brief: str) -> str:
    low = brief.lower()
    return "social_post" if any(k in low for k in _SOCIAL_KEYWORDS) else "landing_page"


def _step_planning(db: Session, project: AgentProject) -> dict:
    # İdempotentlik qoruyucusu: bu layihə üçün tapşırıqlar artıq varsa, planlaşdırmanı TƏKRAR
    # etmirik. Normal işdə `locks.get_lock()` paralel irəliləməni onsuz da bloklayır, amma bu
    # yoxlama olmadan kilidi keçən hər hansı yol (məs. skript birbaşa `advance_project` çağırsa)
    # hər rolu İKİ dəfə yaradıb bütün işi ikiqat LLM sorğusu ilə təkrarlayır.
    if db.query(AgentTask).filter(AgentTask.project_id == project.id).first():
        project.status = "IN_PROGRESS"
        db.commit()
        msg = _log_message(
            db, project, from_role="ceo", to_role=None, kind="handoff",
            content="Plan artıq mövcuddur — təkrar planlaşdırma atlanıldı, iş davam edir.",
        )
        return _event(project, msg)

    plan = _run_orchestrator(
        project.brief, retry_feedback=project.retry_feedback,
        brand_context=_brand_context(db, project),
        usage_ctx=_usage_ctx(project),
    )
    tasks_plan = plan.get("tasks") if plan else None
    output_type = (plan or {}).get("output_type")
    if output_type not in ("landing_page", "social_post"):
        # LLM output_type göstərməyib (ya da pozuq JSON) — brifdəki açar sözlərə görə təxmin edirik.
        output_type = _guess_output_type(project.brief)
    project.output_type = output_type

    if not tasks_plan or not isinstance(tasks_plan, list):
        # Fallback: LLM cavab vermədi / JSON pozuqdursa, generik plan istifadə et ki, axın dayanmasın.
        tasks_plan = [
            {"role": r, "title": f"{ROLE_LABELS[r]} işi", "description": f"Brifə uyğun {ROLE_LABELS[r].lower()} işini gör."}
            for r in ROLE_SEQUENCE
        ]

    by_role = {t.get("role"): t for t in tasks_plan if isinstance(t, dict)}
    active_sequence = (
        CREATIVE_SEQUENCE + SOCIAL_SUPPORT_SEQUENCE
        if output_type == "social_post" else ROLE_SEQUENCE
    )
    summary_lines = []
    for idx, role in enumerate(active_sequence):
        item = by_role.get(role, {})
        title = item.get("title") or f"{ROLE_LABELS[role]} işi"
        description = item.get("description") or ""
        db.add(
            AgentTask(
                project_id=project.id,
                role=role,
                title=title,
                description=description,
                status="TODO",
                order_index=idx,
            )
        )
        summary_lines.append(f"• {ROLE_LABELS[role]}: {title}")
    db.commit()

    project.status = "IN_PROGRESS"
    db.commit()

    content = "Layihə planı hazırdır:\n" + "\n".join(summary_lines)
    if project.retry_feedback:
        content = (
            f"⟳ Bu, #{project.retry_of_id} layihəsinin təkrar cəhdidir (rədd səbəbi: "
            f"\"{project.retry_feedback}\").\n\n" + content
        )
    msg = _log_message(db, project, from_role="ceo", to_role=None, kind="handoff", content=content)
    return _event(project, msg)


def _resolve_designer_output(db: Session, project: AgentProject, output: str | None) -> str | None:
    """Dizaynerin mətn cavabını real şəkil URL-inə çevirir.

    Dizayner generativ prompt yox, real foto üçün kurasiya olunmuş axtarış sözləri verir.
    SIRA VACİBDİR: 1) Pexels (real, mövzuya uyğun, sərbəst hotlink edilə bilən foto);
    2) AI generasiyası (brifə uyğun, həmişə əlçatan); 3) SON ÇARƏ Wikimedia Commons.
    Commons ən sona qoyulub, çünki ensiklopedik arxiv olduğu üçün marketinq brifinə çox vaxt
    zəif uyğun gəlir (köhnə qəzet/kitab skanları) və brauzerdən açılanda 429 verib sınıq
    görünür — yəni ondan əvvəl AI şəkli həm daha uyğun, həm də etibarlı olur."""
    search_terms = output if _usable_image_prompt(output) else _image_terms_from_brief(project.brief)
    photo = find_stock_photo(search_terms, include_commons=False)
    if not photo and not settings.allow_ai_image_fallback:
        photo = find_stock_photo(search_terms, include_commons=True)
    if photo:
        _log_message(
            db, project, from_role="designer", to_role=None, kind="source",
            content=f"Vizual mənbə: {photo.source} · {photo.credit or 'müəllif göstərilməyib'} · {photo.page_url}",
        )
        return photo.url
    if settings.allow_ai_image_fallback:
        return _pollinations_url(search_terms)
    return None


def _step_work(db: Session, project: AgentProject, task: AgentTask) -> dict:
    task.status = "DOING"
    db.commit()

    context = _done_outputs(db, project)
    output = _run_role(
        task.role, project.brief, task.description or task.title, context, project.output_type,
        retry_feedback=project.retry_feedback, brand_context=_brand_context(db, project),
        compliance=_compliance(db, project),
        usage_ctx=_usage_ctx(project),
    )

    if task.role == "designer":
        output = _resolve_designer_output(db, project, output)
    elif output is None and task.role == "marketing":
        output = _marketing_fallback_plan(project.brief, _brand_context(db, project))
    elif output is None:
        output = f"(Heç bir LLM provayderi (Groq/Gemini/HF) cavab vermədi — {ROLE_LABELS[task.role]} üçün nümunə çıxış istifadə olunur.)"

    task.output = output
    preview = (output or "")[:220]

    if task.role in QA_ROLES:
        # Yaradıcı deliverable rolları QA yoxlamasına gedir.
        task.status = "REVIEW"
        db.commit()
        msg = _log_message(
            db, project, from_role=task.role, to_role="critic", kind="handoff",
            content=f"[{task.title}] işim hazırdır, QA-ya göndərirəm:\n{preview}",
        )
        return _event(project, msg)

    # Dəstək departamentləri (satış/marketinq/analitika/hüquq/maliyyə) — QA-sız birbaşa DONE.
    task.status = "DONE"
    db.commit()
    msg = _log_message(
        db, project, from_role=task.role, to_role=None, kind="handoff",
        content=f"[{task.title}] hesabatım hazırdır:\n{preview}",
    )
    return _event(project, msg)


def _ready_support_tasks(db: Session, project: AgentProject) -> list[AgentTask]:
    """Asılılıqları ödənmiş, hələ işlənməmiş dəstək tapşırıqları (paralel işlədilə bilər)."""
    tasks = db.query(AgentTask).filter(AgentTask.project_id == project.id).all()
    done_roles = {t.role for t in tasks if t.status == "DONE"}
    ready = []
    for task in tasks:
        if task.role in CREATIVE_SEQUENCE or task.status not in ("TODO", "DOING"):
            continue
        if all(dep in done_roles for dep in SUPPORT_DEPS.get(task.role, [])):
            ready.append(task)
    return ready


def _step_support_batch(db: Session, project: AgentProject, tasks: list[AgentTask]) -> dict:
    """Bir neçə dəstək departamentini EYNI ANDA (paralel) işlədir və hamısını DONE edir.
    LLM sorğuları (`_run_role`) DB-yə toxunmur — yalnız HTTP-dir. AMMA VACİB: SQLAlchemy-nin
    `expire_on_commit` defolt davranışı `db.commit()`-dən sonra HƏR bir ORM obyektinin bütün
    atributlarını "expired" edir — sonra həmin atributa toxunmaq (məs. `task.role`) avtomatik
    DB-dən yenidən yükləmə (lazy-load) sorğusu göndərir. Worker thread-lərdə ORM obyektinə
    (`task`, `project`) BİRBAŞA toxunmaq bu yolla eyni `db` Session-u paralel thread-lərdən
    sorğulamağa gətirib çıxarır — bu, SQLite korrupsiyası/`ObjectDeletedError` səbəbi idi (canlı
    testdə tapıldı). Həll: hər şeyi commit-dən ƏVVƏL sadə Python dəyişənlərinə çıxarırıq ki,
    worker thread-lər ORM-a HEÇ TOXUNMASIN."""
    context = _done_outputs(db, project)  # hamısı üçün eyni snapshot (bir-birindən müstəqildirlər)
    brand = _brand_context(db, project)
    # Qaydalar ƏSAS THREAD-də bir dəfə çıxarılır: aşağıdakı batch ThreadPoolExecutor ilə
    # işləyir və işçi thread-dən ORM obyektinə toxunmaq bu kod bazasında artıq problem yaradıb.
    rules = _compliance(db, project)
    brief, output_type, retry_feedback = project.brief, project.output_type, project.retry_feedback
    usage_ctx = _usage_ctx(project)  # commit-dən ƏVVƏL oxunur (ORM expire riskinə düşməsin)
    # (task_id, role, description-or-title, title) — sırf primitivlər, ORM obyekti YOX.
    plain_tasks = [(t.id, t.role, t.description or t.title, t.title) for t in tasks]

    for task in tasks:
        task.status = "DOING"
    db.commit()

    def _work(item: tuple[int, str, str, str]) -> tuple[int, str, str, str | None]:
        task_id, role, description, title = item
        out = _run_role(
            role, brief, description, context,
            output_type, retry_feedback=retry_feedback, brand_context=brand, compliance=rules,
            usage_ctx=usage_ctx,
        )
        return task_id, role, title, out

    results: dict[int, tuple[str, str, str | None]] = {}
    with ThreadPoolExecutor(max_workers=SUPPORT_PARALLELISM) as pool:
        for task_id, role, title, out in pool.map(_work, plain_tasks):
            results[task_id] = (role, title, out)

    labels = []
    for task in tasks:
        role, title, out = results[task.id]
        if out is None and role == "marketing":
            out = _marketing_fallback_plan(brief, brand)
        elif out is None:
            out = f"(Heç bir LLM provayderi cavab vermədi — {ROLE_LABELS[role]} çıxışı hazırlana bilmədi.)"
        task.output = out
        task.status = "DONE"
        labels.append(ROLE_LABELS.get(role, role))
        _log_message(
            db, project, from_role=role, to_role=None, kind="handoff",
            content=f"[{title}] hesabatım hazırdır:\n{(out or '')[:220]}",
        )
    db.commit()

    msg = _log_message(
        db, project, from_role="ceo", to_role=None, kind="decision",
        content=f"Dəstək departamentləri paralel tamamlandı: {', '.join(labels)}.",
    )
    return _event(project, msg)


def _step_review(db: Session, project: AgentProject, task: AgentTask) -> dict:
    verdict = _run_critic(
        task.role, project.brief, task.output or "", _brand_context(db, project),
        usage_ctx=_usage_ctx(project),
    )
    decision = (verdict.get("verdict") or "APPROVE").upper()
    feedback = verdict.get("feedback") or ""

    if decision == "REVISE" and task.revision_count < MAX_REVISIONS:
        task.revision_count += 1
        task.status = "TODO"
        db.commit()
        msg = _log_message(
            db, project, from_role="critic", to_role=task.role, kind="critique",
            content=f"[{task.title}] REVISE (#{task.revision_count}): {feedback}",
        )
        return _event(project, msg)

    # APPROVE, ya da revision limiti dolub — məcburi keç.
    task.status = "DONE"
    db.commit()
    note = feedback if decision == "APPROVE" else f"(revision limiti doldu, davam edilir) {feedback}"
    msg = _log_message(
        db, project, from_role="critic", to_role=task.role, kind="decision",
        content=f"[{task.title}] APPROVE: {note}",
    )
    return _event(project, msg)


def _step_assemble(db: Session, project: AgentProject) -> dict:
    dev_task = (
        db.query(AgentTask)
        .filter(AgentTask.project_id == project.id, AgentTask.role == "developer")
        .first()
    )
    designer_task = (
        db.query(AgentTask)
        .filter(AgentTask.project_id == project.id, AgentTask.role == "designer")
        .first()
    )

    outreach_task = (
        db.query(AgentTask)
        .filter(AgentTask.project_id == project.id, AgentTask.role == "outreach_writer")
        .first()
    )

    content = (dev_task.output or "").strip()
    # Bəzən LLM ```html ... ``` (ya da sadəcə ``` ... ```) bloku ilə bükür — təmizləyirik.
    content = re.sub(r"^```(?:html)?\s*|\s*```$", "", content, flags=re.IGNORECASE | re.MULTILINE).strip()
    if project.output_type == "social_post":
        # LLM bəzən bütün caption-u bir cüt dırnaqla qaytarır; paylaşımda bunlar görünməməlidir.
        content = re.sub(r'^(["“])(.*)(["”])$', r'\2', content, flags=re.DOTALL).strip()

    if not content:
        content = (
            "<p>Deliverable hazırlana bilmədi.</p>" if project.output_type != "social_post"
            else "(Post mətni hazırlana bilmədi.)"
        )
    project.deliverable_html = content
    project.deliverable_image_url = designer_task.output if designer_task else None
    # Satış departamentinin çıxışı — yaradıcı deliverable-dan ayrıca saxlanılır.
    sales_kit = (outreach_task.output or "").strip() if outreach_task else ""
    sales_kit = sales_kit.replace("**", "")
    project.sales_kit = sales_kit or "(Satış materialları hazırlana bilmədi.)"
    project.status = "AWAITING_APPROVAL"
    db.commit()

    _draft_campaign_for(db, project)
    try:
        from app.brand_sync import collect_suggestions

        collect_suggestions(db, project)
    except Exception:  # noqa: BLE001 — təklif toplama çatdırılmanı bloklamamalıdır
        db.rollback()
        logger.warning("Brand Kit təklifləri toplanmadı (layihə %s)", project.id, exc_info=True)

    msg = _log_message(
        db, project, from_role="ceo", to_role=None, kind="decision",
        content="Bütün tapşırıqlar tamamlandı ✅ Nəticə təsdiqinizi gözləyir.",
    )
    return _event(project, msg)


def _draft_campaign_for(db: Session, project: AgentProject) -> None:
    """Layihə bitəndə kampaniya QARALAMASI yaradır (audit #2).

    MƏHSUL QƏRARI — status `DRAFT`, `PLANNED` deyil, və təqvimdə görünmür. Əks halda hər
    layihə istifadəçinin təqvimini doldurar. İstifadəçi kampaniyalar səhifəsində baxıb
    özü işə salır.

    İDEMPOTENT: `source_project_id` sayəsində layihə təkrar işə salınsa da ikinci qaralama
    yaranmır. Uğursuzluq layihəni HEÇ VAXT dayandırmır — nəticə onsuz da hazırdır.
    """
    from app.campaigns import create_campaign

    if not project.workspace_id:
        return
    try:
        exists = db.query(Campaign).filter(Campaign.source_project_id == project.id).first()
        if exists:
            return
        workspace = db.get(Workspace, project.workspace_id)
        if not workspace:
            return
        name = (project.brief or "Yeni kampaniya").strip().splitlines()[0][:80]
        campaign = create_campaign(
            db, workspace, f"{name} — qaralama",
            project.brief or "layihə nəticəsindən yaranan kampaniya",
            workspace.brand_audience or "", "Instagram", "",
        )
        campaign.status = "DRAFT"
        campaign.source_project_id = project.id
        db.commit()
        logger.info("Layihə %s üçün kampaniya qaralaması yaradıldı (id=%s)", project.id, campaign.id)
    except Exception:  # noqa: BLE001 — qaralama layihənin çatdırılmasını bloklamamalıdır
        db.rollback()
        logger.warning("Kampaniya qaralaması yaradıla bilmədi (layihə %s)", project.id, exc_info=True)


# Yenidən yazdırma yalnız iş bitəndən sonra mənalıdır — layihə hələ işləyirsə, boru xətti
# onsuz da həmin tapşırığı dəyişdirə bilər (yarış vəziyyəti).
REGENERABLE_STATUSES = {"AWAITING_APPROVAL", "DELIVERED", "REJECTED"}


def regenerate_task(
    db: Session, project: AgentProject, task: AgentTask, instruction: str | None = None,
) -> dict:
    """TƏK bir departamentin çıxışını yenidən yazdırır (bütün layihəni təkrar işlətmədən).

    Köhnə variant `AgentTaskVersion`-da arxivlənir, yenisi `task.output`-a yazılır. Yaradıcı
    rollardan biri dəyişdisə deliverable yenidən yığılır ki, müştəriyə göstərilən nəticə
    tapşırıqlarla uyğunsuz qalmasın. QA burada işə salınmır — istifadəçi özü nəzarətçidir."""
    previous = task.output
    # Arxivləmə: ilk dəfə yenidən yazdırırıqsa, MÖVCUD çıxış "versiya 1" kimi saxlanılır.
    next_version = (
        db.query(func.max(AgentTaskVersion.version_no))
        .filter(AgentTaskVersion.task_id == task.id)
        .scalar() or 0
    ) + 1
    db.add(AgentTaskVersion(
        task_id=task.id, version_no=next_version, output=previous, instruction=None,
    ))

    context = [(r, out) for r, out in _done_outputs(db, project) if r != task.role]
    output = _run_role(
        task.role, project.brief, task.description or task.title, context, project.output_type,
        retry_feedback=project.retry_feedback, brand_context=_brand_context(db, project),
        compliance=_compliance(db, project),
        usage_ctx=_usage_ctx(project), extra_instruction=instruction,
    )
    if task.role == "designer":
        output = _resolve_designer_output(db, project, output)

    if not output:
        # Yeni variant alınmadı — KÖHNƏNİ SAXLAYIRIQ. Əks halda istifadəçi bir düymə ilə hazır
        # işini itirərdi. Arxiv sətrini də geri alırıq ki, saxta "versiya" qalmasın.
        db.rollback()
        msg = _log_message(
            db, project, from_role=task.role, to_role=None, kind="critique",
            content=(
                f"[{task.title}] yenidən yazıla bilmədi — heç bir LLM provayderi cavab vermədi. "
                f"Əvvəlki variant olduğu kimi saxlanıldı."
            ),
        )
        db.commit()
        flush_usage(db)
        return _event(project, msg)

    task.output = output
    task.revision_count = (task.revision_count or 0) + 1
    task.status = "DONE"
    db.commit()

    # Deliverable yaradıcı rollardan asılıdır — biri dəyişibsə yenidən yığılmalıdır.
    if task.role in CREATIVE_SEQUENCE or task.role == "outreach_writer":
        previous_status = project.status
        _step_assemble(db, project)
        # `_step_assemble` statusu AWAITING_APPROVAL edir; artıq təsdiqlənmiş/rədd edilmiş
        # layihənin statusunu geri qaytarmırıq ki, iş axını qəflətən geriyə sürüşməsin.
        if previous_status in ("DELIVERED", "REJECTED"):
            project.status = previous_status
            db.commit()

    note = f" (göstəriş: {instruction.strip()})" if instruction and instruction.strip() else ""
    msg = _log_message(
        db, project, from_role=task.role, to_role=None, kind="handoff",
        content=f"🔄 [{task.title}] yenidən yazıldı (v{next_version + 1}){note}:\n{(output or '')[:220]}",
    )
    db.commit()
    flush_usage(db)
    return _event(project, msg)


TERMINAL_STATUSES = {"AWAITING_APPROVAL", "DELIVERED", "REJECTED"}


def advance_project(db: Session, project: AgentProject) -> dict | None:
    """Vəziyyət maşınını bir addım irəli aparır. Görüləcək iş qalmayıbsa None qaytarır."""
    try:
        return _advance_project_inner(db, project)
    finally:
        # Addım boyu (paralel thread-lər daxil) yığılmış token qeydlərini indi — ƏSAS thread-də,
        # bütün worker-lər bitəndən sonra — DB-yə yazırıq.
        flush_usage(db)


def _advance_project_inner(db: Session, project: AgentProject) -> dict | None:
    db.refresh(project)

    if project.status == "BRIEF":
        return _step_planning(db, project)

    if project.status == "IN_PROGRESS":
        review_task = (
            db.query(AgentTask)
            .filter(AgentTask.project_id == project.id, AgentTask.status == "REVIEW")
            .order_by(AgentTask.order_index)
            .first()
        )
        if review_task:
            return _step_review(db, project, review_task)

        # Yaradıcı rollar ARDICIL işləyir (bir-birinə bağlıdır: kopirayter strateqi, developer
        # dizayneri əsas götürür) və hər biri QA-dan keçir.
        next_creative = (
            db.query(AgentTask)
            .filter(
                AgentTask.project_id == project.id,
                AgentTask.role.in_(CREATIVE_SEQUENCE),
                AgentTask.status.in_(["TODO", "DOING"]),
            )
            .order_by(AgentTask.order_index)
            .first()
        )
        if next_creative:
            return _step_work(db, project, next_creative)

        # Yaradıcı komanda bitib — dəstək departamentləri PARALEL işləyir (bir-birindən
        # müstəqildir, QA-sızdır). Bu, layihəni əhəmiyyətli sürətləndirir.
        ready_support = _ready_support_tasks(db, project)
        if ready_support:
            return _step_support_batch(db, project, ready_support)

        return _step_assemble(db, project)

    return None  # AWAITING_APPROVAL / DELIVERED / REJECTED — insan növbəsi ya da bitib
