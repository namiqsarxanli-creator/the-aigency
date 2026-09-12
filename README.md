# The Agency — AI Agentlərindən İbarət Avtonom Yaradıcı Şirkət

Bir brif verirsiniz (məs. *"eko-dostu qəhvə brendi üçün launch kampaniyası"*), sistem özü bir
"şirkət" kimi işə düşür: **CEO** agenti brifi tapşırıqlara bölür, **Strateq**, **Kopirayter**,
**Dizayner** və **Developer** agentləri növbə ilə işləyir, **QA (Tənqidçi)** agenti hər işi
yoxlayıb ya təsdiqləyir, ya da geri qaytarır. Bütün proses dashboard-da **canlı** izlənir
(WebSocket), sonda hazır bir landing page (deliverable) sizin təsdiqinizi gözləyir.

## Sürətli başlanğıc

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

`.env.example` faylını `.env` kimi kopyalayın və ən azı **Groq** API açarınızı yazın (pulsuz):
https://console.groq.com/keys

```bash
uvicorn main:app --reload --port 8800
```

Brauzerdə: `http://localhost:8800`

> Heç bir açar olmasa, sistem yenə işləyir — hər agent üçün nümunə (fallback) mətn istifadə
> olunur ki, axın dayanmasın, amma real nəticə üçün ən azı bir açar lazımdır.

### Testlər

```bash
pytest
```

244 test: workspace izolyasiyası, boru xəttinin vəziyyət maşını, yenidən yazdırma + versiya
arxivi, token qeydiyyatı, ixrac, prompt sağlamlığı, səsli agent planlaşdırması və s.
**Testlər şəbəkəyə çıxmır** — LLM və şəkil axtarışı `tests/conftest.py`-də mock-lanır, ona
görə kvota yandırmır və provayder işləmədikdə də keçir.

### LLM provayder zənciri (Groq → Gemini → Hugging Face)

Groq-un pulsuz tarifi tez-tez dəqiqəlik sürət limitinə (429) dəyir — xüsusən uzun layihələrdə,
sonrakı rollar (Developer) daha böyük kontekstlə çağırılanda. Ona görə sistem 3 provayderi
**sırayla** sınayır: `_call_llm()` əvvəlcə Groq-u sınayır (3 cəhd, gözləyərək), uğursuz olsa
avtomatik **Gemini**-yə, o da olmasa **Hugging Face**-ə keçir. Hər üçü OpenAI-uyğun
`/chat/completions` formatı təqdim etdiyi üçün eyni kodla çağırılır ([app/agency.py](app/agency.py)
`_providers()` / `_call_llm()`). `.env`-də yalnız açarını qoyduğunuz provayderlər sınanır —
GEMINI_API_KEY/HF_API_KEY boşdursa, sadəcə keçilir.

## Necə işləyir

1. **Brif** → `POST /agency/brief` → yeni layihə `BRIEF` statusu ilə yaranır.
2. **CEO (Orkestrator)** brifi 4 tapşırığa bölür: Strateq → Kopirayter → Dizayner → Developer.
3. Hər tapşırıq: rol agenti işləyir → **QA** yoxlayır → `APPROVE` (DONE) və ya `REVISE`
   (maks. 2 dəfə geri qaytarılır, sonra məcburi keçir — sonsuz döngə yoxdur).
4. Bütün tapşırıqlar bitəndə Developer-in HTML çıxışı **deliverable** kimi saxlanılır, layihə
   `AWAITING_APPROVAL`-a keçir.
5. Siz `/agency/{id}/approve` və ya `/reject` ilə son sözü deyirsiniz.

`POST /agency/{id}/run` bütün addımları ardıcıl işlədir və **hər addımdan sonra** WebSocket
(`/ws/live`) üzərindən dashboard-a canlı hadisə göndərir — ona görə brifi göndərəndə komandanın
işini addım-addım "canlı ofis" kimi izləyirsiniz.

### Avtonomluq (fon dövrəsi)

Server başlayanda `app/scheduler.py`-dəki `agency_loop()` arxa fonda hər **6 saniyədə** bir aktiv
(`BRIEF`/`IN_PROGRESS`) layihələri özü irəlilədir. Yəni `/run` çağırmasanız belə (məs. layihə
Telegram-dan `/brief` əmri ilə yaradılıbsa), sistem heç bir manual toxunuş olmadan öz-özünə işini
tamamlayıb `AWAITING_APPROVAL`-a çatır — həqiqətən özbaşına işləyən bir "şirkət".

### Telegram / n8n (ixtiyari)

`n8n_workflows/` qovluğunda iki hazır workflow var (n8n-də **Import from File** ilə yükləyin,
Telegram credential-ı və `host.docker.internal:8800` ünvanını öz mühitinizə uyğunlaşdırın):

1. **`1_agency_notify_workflow.json`** — hər dəqiqə `GET /agency/pending-approval` sorğusu edir,
   təsdiq gözləyən yeni layihə taparsa Telegram-a `/tesdiq <id>` / `/redd <id>` əmrləri ilə
   bildiriş göndərir, sonra `POST /agency/{id}/mark-notified` çağırıb təkrar bildirişin qarşısını
   alır.
2. **`2_agency_telegram_commands_workflow.json`** — Telegram-dan gələn `/brief <mətn>`,
   `/tesdiq <id>`, `/redd <id>` əmrlərini tanıyıb müvafiq endpoint-ə yönləndirir və nəticəni
   Telegram-a geri yazır.

#### ⚠️ API açarı (n8n işləməzdən əvvəl vacib)

`.env`-dəki `AGENCY_API_KEY` doldurulubsa (tövsiyə olunur), backend-ə gedən bütün n8n sorğuları
`X-API-Key` başlığı göndərməlidir — əks halda **401** alacaqlar. Workflow-lardakı 6 HTTP node
artıq `={{ $env.AGENCY_API_KEY }}` göndərmək üçün konfiqurasiya edilib, sizə yalnız həmin
dəyişəni n8n konteynerinə vermək qalır:

```bash
docker run -d --name n8n -p 5678:5678 \
  -e AGENCY_API_KEY="<.env-dəki eyni açar>" \
  -e N8N_BLOCK_ENV_ACCESS_IN_NODE=false \
  -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

`N8N_BLOCK_ENV_ACCESS_IN_NODE=false` olmasa n8n node daxilindən `$env`-ə girişi bloklayır və
başlıq boş gedər. **Alternativ (docker-a toxunmadan):** hər HTTP node-un "Header Parameters"
sahəsində `={{ $env.AGENCY_API_KEY }}` yerinə açarın özünü yapışdırın.

## API

| Metod & yol | Nə edir |
|---|---|
| `POST /agency/brief` | Yeni layihə yaradır (`{brief}` → `{id, status}`) |
| `POST /agency/{id}/run` | Layihəni terminal vəziyyətə qədər addım-addım işlədir, WS-ə yayımlayır |
| `GET /agency/{id}` | Layihə + tapşırıqlar + mesajlar (JSON) |
| `GET /agency/projects` | Son 50 layihənin siyahısı |
| `POST /agency/{id}/approve` \| `/reject` | İnsan mərhələsi (yalnız `AWAITING_APPROVAL`-dan) |
| `GET /agency/pending-approval` | Bildirilməmiş, təsdiq gözləyən layihələr (n8n üçün) |
| `POST /agency/{id}/mark-notified` | Bildiriş göndərildikdən sonra işarələmək üçün (n8n üçün) |
| `GET /health` | Status yoxlanışı |
| `GET /docs` | Avtomatik Swagger sənədləri |

## Struktur

```
app/
  core.py        — .env / tənzimləmələr
  database.py    — SQLAlchemy engine/session
  db_models.py   — AgentProject / AgentTask / AgentMessage
  models.py      — Pydantic sxemləri
  agency.py      — 6 agent rolu + vəziyyət maşını (əsas məntiq)
  scheduler.py   — avtonom fon dövrəsi (agency_loop)
  api.py         — JSON endpoint-lər
  web.py         — tək-səhifəlik dashboard route-u
  ws.py          — WebSocket broadcast meneceri
templates/       — Jinja2 (base.html + agency.html)
static/          — agency.css + agency.js
n8n_workflows/   — Telegram bildiriş + əmr workflow-ları (ixtiyari)
main.py          — FastAPI giriş nöqtəsi
```

## Məlum məhdudiyyətlər

- Endpoint-lərdə autentifikasiya yoxdur — demo/lokal istifadə üçün nəzərdə tutulub.
- LLM JSON qaytarmasa, sistem generik fallback plan/qərarla davam edir (axın dayanmır, amma
  keyfiyyət aşağı düşə bilər).
- Dizayner "şəkil" əslində Pollinations.ai-nin açarsız URL-idir — şəkil yalnız o URL əlçatan
  olduqca görünür.
- `run` sinxron/ardıcıldır (bir layihə eyni anda bir addım) — çoxlu paralel layihə üçün ayrıca
  növbə sistemi lazım olardı.
