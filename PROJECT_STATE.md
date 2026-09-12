# The Agency — Sessiya Konteksti / Vəziyyət Sənədi

> **Bu fayl nə üçündür:** Claude ilə söhbət pəncərəsi dolub yeni sessiya başlayanda, bu faylı
> oxutdurun ("PROJECT_STATE.md-i oxu və davam et") — bütün tarixçə, qərarlar və "öyrənilmiş
> dərslər" burada var, təkrar izah etməyə ehtiyac qalmır. **Claude hər böyük dəyişiklikdən sonra
> bu faylı SORUŞMADAN avtomatik yeniləyir** (istifadəçi qərarı).

## Son vəziyyət (ən son yenilənmə: 5-ci sessiya — Instagram paylaşımı quruldu)

- **Yeni (5-ci sessiya):** Instagram avtomatik paylaşımı quruldu və **həm post, həm Reels
  real olaraq paylaşıldı** (40, 49-cu maddələr). Kod `graph.instagram.com`-a keçirildi,
  `publish_reel()` əlavə olundu, n8n workflow-u quruldu (`xxWlkDOPHsIVJKA9`).
  **Qalan bloker:** `PUBLIC_BASE_URL` hələ lokaldır — The Agency-nin ÖZ şəkillərini paylaşmaq
  üçün backend (8800) ictimai olmalıdır (41-ci maddə). Xarici URL-lərlə paylaşım işləyir.


- **Yeni:** tək departamenti yenidən yazdırmaq (versiya arxivi ilə), `/usage` token/xərc paneli,
  PDF hesabat + ZIP ixracı, və layihənin ilk test dəsti (`pytest` → 46/46 keçir, şəbəkəsiz).
- **Windows qeydi:** `tzdata` paketi olmadan tətbiq ümumiyyətlə açılmır (bax: 36-cı maddə).
- **Təhlükəsizlik:** `AGENCY_API_KEY` artıq doldurulub və 3 avtomasiya marşrutu bağlanıb (37-ci
  maddə). **n8n-i növbəti dəfə işə salanda** konteynerə `AGENCY_API_KEY` +
  `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` vermək lazımdır, yoxsa workflow-lar 401 alacaq.
- Backend, n8n Approval Notify və Telegram Commands workflow-ları **işlək və test edilib**.
- **Docker Desktop bu kompüterdə avtomatik başlamır** — hər dəfə əl ilə açılmalıdır, əks halda
  n8n əlçatan olmur (aşağıdakı "Xarici asılılıqlar" cədvəlinə bax).
- Docker/n8n hər restart olanda n8n-in brauzer giriş sessiyası da sıfırlanır — yenidən sign-in
  lazımdır.

## Layihə nədir

**The Agency** — brif verirsiniz, AI agentlərindən ("CEO", Strateq, Kopirayter, Dizayner,
Developer, QA") ibarət avtonom "şirkət" onu icra edir, nəticəni Telegram-dan da idarə edə
bilirsiniz. Ətraflı memarlıq üçün bax: [README.md](README.md).

**Qovluq:** `C:\Users\USER\PycharmProjects\QL\MainLessons\Layihe3`
**İşə salma:** PyCharm-da [run.py](run.py)-a sağ-klik → Run (server + brauzer avtomatik açılır,
port 8800, `0.0.0.0`-a bağlanır ki, Docker/n8n ona çata bilsin).

## Xarici asılılıqlar (bunlar SİZİN kompüterinizdə ayrıca işləməlidir)

| Nə | Necə yoxlanılır | Qeyd |
|---|---|---|
| Backend (FastAPI) | `curl http://127.0.0.1:8800/health` | `run.py` və ya `uvicorn main:app --port 8800` |
| Docker Desktop | `docker ps` xəta versə ("failed to connect to the docker API") — Docker Desktop bağlıdır | Windows-da əl ilə açın, tam yüklənməsi ~30-60san çəkir |
| n8n (Docker) | `docker ps` → konteyner adı **`n8n`** | `http://localhost:5678`, brauzerdə giriş lazımdır. **Docker Desktop restart olanda n8n konteyneri də restart olur və brauzer giriş sessiyası sıfırlanır** — yenidən sign-in edin. |
| Cloudflare tunel (8800) | `curl http://127.0.0.1:4040` YOX — `tasklist \| grep cloudflared` | `cloudflared tunnel --url http://localhost:8800`. **URL hər başladıqda DƏYİŞİR** — çıxan ünvanı `Layihe3/.env`-də `PUBLIC_MEDIA_BASE_URL`-ə yazın, yoxsa Instagram şəkli yükləyə bilmir (bax 61). |
| Ngrok tunel | `curl http://127.0.0.1:4040/api/tunnels` | Domen: **`cursor-eleven-preteen.ngrok-free.dev`** (ngrok hesabında reserved/static domen). İşə salma: `ngrok http --url=cursor-eleven-preteen.ngrok-free.dev 5678` (köhnə `--domain` bayrağı deprecated edilib). **Bu proses hər Windows restart-da YENİDƏN başladılmalıdır**, avtomatik başlamır! **Diqqət: bu tunel yalnız port 5678-i (n8n) açır — backend (8800) hələ ictimai deyil, müştəri linki (aşağıya bax) hələ yalnız lokal şəbəkədə işləyir.** |
| Telegram bot | `demobot_bot` | Bot token n8n-in "Telegram account" credential-ında saxlanılır (id: `1FtYtFjmkARKGPBc`) |

> ⚠️ **Ən çox unudulan şey:** ngrok prosesi VƏ Docker Desktop. Telegram botu cavab vermirsə,
> İLK YOXLANACAQ ŞEYLƏR bunlardır: (1) `docker ps` işləyirmi (Docker Desktop açıqdırmı?),
> (2) `curl http://127.0.0.1:4040/api/tunnels` boş/xəta versə, ngrok ölüb, yenidən başladın.

## Sizin real Telegram chat ID-niz

`<TELEGRAM_CHAT_ID>` (real dəyər `.env`-də) — bu ID `n8n_workflows/2_...json`-dakı
`ALLOWED_CHAT_IDS` allowlist-ində və test briflərində hardcode olunub.

## Bu sessiyada tapılıb düzəldilən BÜTÜN buglar (xronoloji)

1. **Race condition** — manual `/run` + avtonom fon dövrəsi eyni layihəni paralel işlədib
   təkrarlanan tapşırıqlar yaradırdı → [app/locks.py](app/locks.py) (`asyncio.Lock` hər layihə üçün).
2. **API açarı `.env.example`-də** (git-ə düşəcəkdi) → `.env`-ə köçürüldü.
3. **`run.py` yalnız `127.0.0.1`-ə bağlanırdı** → Docker-dəki n8n `host.docker.internal:8800`-ə
   çata bilmirdi → `HOST = "0.0.0.0"` edildi.
4. **Groq tək-nöqtə-uğursuzluğu** (pulsuz tarif tez dolur, 6000 TPM limit) → **3-provayderli
   fallback zənciri**: Groq → Gemini → Hugging Face ([app/agency.py](app/agency.py) `_providers()`
   / `_call_llm()`). 429-da DƏRHAL növbətiyə keçir (gözləmə yoxdur, çünki dəqiqəlik kvota
   gözləməklə sıfırlanmır).
5. **Gemini model adı səhv idi** (`gemini-2.0-flash` bu açar üçün kvota=0) → `gemini-2.5-flash`-a
   keçirildi (5 model adı sınanıb işləyəni tapıldı).
6. **Developer HTML-i kəsilirdi** (`max_tokens=1200` yetmirdi, `</body></html>` yazılmırdı) →
   `2400`-ə qaldırıldı. **Gemini 2.5-in gizli "thinking" tokenləri** də büdcəni yeyirdi →
   `reasoning_effort: "none"` əlavə olundu (yalnız Gemini üçün, `extra_body`).
7. **"Daha ətraflı" düyməsi heç nə etmirdi** → Developer promptuna klikləndə **görünən reaksiya**
   (JS `onclick` + gizli mesaj göstərmə) tələbi əlavə olundu.
8. **n8n Telegram credential-ları 2 node-da yox idi** ("Təsdiq mesajı (brief)" və "(reject)") →
   node panelini açanda n8n avtomatik təyin etdi (yeganə credential olduğu üçün).
9. **Ngrok tunel oflayn idi** (`ERR_NGROK_3200`) → yenidən başladıldı.
10. **`telegram_chat_id` API-yə ƏDƏD kimi gəlirdi, Pydantic `str` gözləyirdi** → 422 xəta →
    [app/models.py](app/models.py)-də `field_validator(mode="before")` ilə avtomatik `str()`.
11. **Azərbaycan hərfləri Telegram bildirişlərində korlanırdı** (GBK-yə bənzər mojibake) →
    səbəb: `Content-Type: application/json`-da açıq `charset=utf-8` yox idi → n8n-in HTTP
    client-i kodlaşdırmanı səhv təxmin edirdi → [main.py](main.py)-də middleware əlavə olundu
    (`force_utf8_charset`).
12. **QA tez-tez "cavab alınmadı" görürdü** — səbəb: bir layihə 8-14 ardıcıl LLM sorğusu göndərir,
    bu partlayış bəzən provayderi anlıq rate-limitə salır (kod düzgün fallback verir, amma
    tezliyi azaltmaq üçün) → `/run` addımları arasına `0.6san` gecikmə əlavə olundu.
13. **QA-nın əsaslı şikayəti: Developer həmişə HTML yazırdı, hətta Instagram brifində də** →
    **`output_type` sistemi** əlavə olundu (bax aşağıda).

### 2-ci sessiya (encoding, müştəri linki, rədd-geri-bildirim)

14. **n8n IF node "'' string amma number gözlənilirdi" xətası** — `/agency/pending-approval`
    massiv qaytarırdı, n8n HTTP node onu həmişə ayrı item-lərə bölmürdü → **tək obyekt** (massiv
    yox) qaytarmağa keçirildi, boşdursa **204** qaytarılır ([app/api.py](app/api.py)).
15. **Telegram sendPhoto flaky idi** — pollinations şəkil URL-ini Telegram-ın özü yükləyirdi, bu
    10-30san çəkir və Telegram-ın timeout-unu keçirdi → yeni **`/agency/{id}/image`** keş
    endpoint-i: şəkli bir dəfə yükləyib yaddaşda saxlayır, n8n ondan `host.docker.internal`
    üzərindən ANINDA alır (n8n "Şəkli yüklə" node-u əlavə olundu, sonra Telegram-a binary kimi
    göndərilir).
16. **Azərbaycan hərfləri yenidən korlanırdı (mojibake, məs. "açılan" → "a莽谋lan")** — bu dəfə
    backend-in `charset=utf-8` header-i DÜZGÜN idi, amma n8n-in "Təsdiq gözləyənləri gətir" HTTP
    node-unun `options` sahəsi BOŞ idi (avtomatik encoding təxmini) → **`options.response.response.
    responseFormat: "json"`** açıq təyin edildi ki, n8n cavabı düzgün UTF-8 kimi dekodlasın.
17. **n8n-in gizli/sənədləşdirilməmiş qüsuru: aktiv workflow-un `PATCH` ilə redaktəsi DB-də
    görünür, amma canlı trigger (schedule/webhook) KÖHNƏ node-ları yaddaşda saxlayıb icra edir.**
    Sadə `PATCH {"active": false}` / `{"active": true}` bunu düzəltmir (server sahəni sükutla
    ignore edir). **Düzgün yol:** xüsusi endpoint-lər —
    `POST /rest/workflows/{id}/deactivate` (body yox), sonra
    `POST /rest/workflows/{id}/activate` (body: `{"versionId": "<cari versionId>"}`,
    GET-dən əvvəlcədən alınmalı). Bu, proqramla (REST API ilə) node dəyişəndə HƏR DƏFƏ lazımdır.
18. **Dizayner şəkilləri mövzuya zəif uyğun gəlirdi** — `_pollinations_url()` heç bir keyfiyyət
    parametri göndərmirdi → **`model=flux&enhance=true&nologo=true&width=1024&height=1024`**
    əlavə olundu (`enhance=true` pollinations-ın öz LLM-i ilə promptu zənginləşdirir, mövzuya
    sadiqliyi əhəmiyyətli artırır — canlı testlə vizual təsdiqləndi).

## Bu sessiyada əlavə olunan ÖZƏLLIKLƏR (sadəcə bug-fix deyil)

### 1. `output_type` — brifə uyğun çıxış növü
- CEO (`ORCHESTRATOR_SYSTEM`) brifi oxuyub `"output_type": "landing_page"` və ya `"social_post"`
  seçir (JSON plan daxilində). LLM göstərməzsə, açar sözlərlə təxmin edilir
  (`_guess_output_type()` — "instagram", "post", "paylaşım" və s.).
- `AgentProject.output_type` sütunu (default `"landing_page"`).
- `social_post` olanda Developer **`DEVELOPER_SOCIAL_SYSTEM`** promptu ilə işləyir — HTML YOX,
  birbaşa Instagram-a hazır caption (emoji + hashtag) yazır.
- Frontend (`agency.js`/`agency.html`/`agency.css`): `output_type == "social_post"` olanda
  iframe əvəzinə Instagram-stilində kart (`#socialPostPreview`) göstərilir.
- **Test edilib və işləyir:** "Instagram tanıtım postu" brifi → `social_post` + real caption
  (HTML yox); "tanıtım saytı" brifi → `landing_page` + tam HTML.

### 2. Telegram-a tam nəticə göndərmə
- n8n "Approval Notify" workflow-undakı "Telegram-a bildir" node-u `sendMessage`-dən
  **`sendPhoto`**-ya keçirildi: `Photo = {{ $json.deliverable_image_url }}`,
  `Caption` = brif + `/tesdiq`/`/redd` təklifləri (Markdown, çoxsətirli).

### 3. Təhlükəsizlik (ixtiyari, defolt söndürülüb)
- [app/core.py](app/core.py): `AGENCY_API_KEY` (.env-də boş = qorumasız, demo rejimi).
- [app/api.py](app/api.py): `require_api_key` dependency — dolarsa `X-API-Key` başlığı tələb
  olunur (`/brief`, `/run`, `/approve`, `/reject`, `/mark-notified`, `/pending-approval`).
  **DİQQƏT:** aktivləşdirsəniz, həm `static/agency.js` (veb dashboard düymələri), həm n8n-in
  bütün HTTP node-ları həmin başlığı göndərməlidir — hazırda ETMİRLƏR, ona görə açarı
  doldurmazdan əvvəl bunları da yeniləmək lazımdır.
- n8n Code node-una (`Əmri təhlil et`) **chat ID allowlist** (`ALLOWED_CHAT_IDS = [<TELEGRAM_CHAT_ID>]`)
  — yalnız bu ID-dən gələn Telegram əmrləri qəbul olunur.

### 4. Müştəriyə göndərilə bilən ictimai link (2-ci sessiya)
- **`GET /agency/{id}/view`** ([app/web.py](app/web.py)) — autentifikasiyasız, ictimai HTML
  səhifə. `landing_page` üçün `deliverable_html`-i (artıq tam sənəddir) xam qaytarır;
  `social_post` üçün [templates/customer_view.html](templates/customer_view.html) ilə
  Instagram-tərzi kart (şəkil + caption) göstərir. Status `AWAITING_APPROVAL`/`DELIVERED`
  deyilsə "hələ hazır deyil" göstərir.
- `pending-approval` cavabına **`view_url`** sahəsi əlavə olundu (`settings.public_base_url`
  + `/agency/{id}/view`), Telegram caption-una `🔗 Müştəriyə göndərmək üçün link:` sətri ilə
  daxil edildi.
- **YARIMÇIQ QALAN HİSSƏ:** `PUBLIC_BASE_URL` hazırda `.env`-də defolt `http://127.0.0.1:8800`
  — bu, yalnız LOKAL şəbəkədə açılır. Müştəri linki öz telefonundan/kompüterindən açsın deyə,
  port 8800-ü DƏ ayrıca ngrok ilə (və ya eyni ngrok-un ikinci tunel qaydası ilə) ictimailəşdirib
  `.env`-də `PUBLIC_BASE_URL`-i həmin ictimai ünvana dəyişmək lazımdır — bu, HƏLƏ EDİLMƏYİB.

### 5. Rədd-geri-bildirim dövrəsi (2-ci sessiya)
- `AgentProject`-ə üç yeni sütun: `reject_feedback` (bu layihə niyə rədd edildi), `retry_feedback`
  (bu layihə hansı səbəbdən yaranan təkrar cəhddir), `retry_of_id` (hansı layihənin təkrarıdır).
  **SQLite-a ALTER TABLE ilə əl ilə əlavə edildi** (məlumat itkisi olmadan — `agency.db`-ni
  silmək lazım gəlmədi, çünki artıq real Telegram-a göndərilmiş layihələr var idi).
- `POST /agency/{id}/reject` indi ixtiyari `{"reason": "..."}` body qəbul edir. Səbəb verilibsə,
  `agency.start_retry()` avtomatik EYNİ brif + səbəblə YENİ layihə yaradır və CEO-nun handoff
  mesajına "⟳ Layihə #X rədd edildi (səbəb: ...)" qeydini əlavə edir.
- `_run_orchestrator()` və `_run_role()` indi `retry_feedback` parametri qəbul edir və LLM-ə
  "bu təkrar cəhddir, bu səbəbdən rədd edildi, bunu düzəlt" göstərişini ötürür — canlı testlə
  təsdiqləndi (təkrar cəhddə mətn qısaldı, şəkil mövzuya daha uyğun oldu).
- **Web dashboard**: "Rədd et" düyməsi indi `window.prompt()` ilə səbəb soruşur (ixtiyari,
  boş buraxıla bilər).
- **Telegram**: `/redd {id} {səbəb mətni}` — id-dən sonrakı bütün mətn səbəb kimi tutulur
  (n8n-in "Əmri təhlil et" Code node-unda regex ilə). Səbəbsiz `/redd {id}` də işləyir (köhnə
  kimi, sadəcə rədd edir, təkrar cəhd başlatmır).

### 6. Satış departamenti (2-ci sessiya)
İki departament modeli: əvvəlcə **Yaradıcı komanda** (Strateq/Kopirayter/Dizayner/Developer)
məhsulu/brendi hazırlayır, SONRA **Satış departamenti** həmin hazır məhsula əsaslanıb satış
materialları yazır.
- İki yeni rol ([app/agency.py](app/agency.py)): **`sales_strategist`** ("Satış Strateqi" 📈 —
  hədəf müştəri, satış nöqtələri, etirazlar, təklif bucağı) və **`outreach_writer`**
  ("Satış Kopirayteri" 📧 — soyuq email + DM skripti + satış piti + kampaniya təklifi).
- `ROLE_SEQUENCE = CREATIVE_SEQUENCE + SALES_SEQUENCE` — satış rolları order_index-ə görə SONDA
  gəlir ki, yaradıcı çıxışları kontekst kimi görsünlər. `ROLE_DEPARTMENT` dict rolları
  departamentə bağlayır. Eyni `_step_work`/`_step_review`/QA dövrəsindən keçirlər.
- CEO orkestratoru indi 6 tapşırıq planlaşdırır (LLM satış tapşırıqlarını verməzsə, fallback
  generic təsvir yaradır — axın dayanmır).
- **`AgentProject.sales_kit`** (Text) sütunu — `_step_assemble` `outreach_writer` çıxışını bura
  yığır (yaradıcı `deliverable_html`-dan ayrı). **SQLite-a ALTER TABLE ilə əlavə edildi** (məlumat
  itkisi olmadan).
- Frontend: org-chart indi iki `.dept-group` qutusuna bölünüb (Yaradıcı / Satış); nəticə panelinə
  `#salesKit` bölməsi əlavə olundu. Müştəri `/view` səhifəsi (social_post) də satış materiallarını
  göstərir. `agency.css`-ə `.dept-group`/`.dept-label`/`.sales-kit` stilləri əlavə olundu.
- **Test edilib:** layihə #10 (Zeytun Bağı sabun) — 6 rol + QA işlədi (18 addım), sales_kit-də
  4 bölmə düzgün yarandı, dashboard və /view-də render olundu. (Qeyd: mətn keyfiyyəti işlədilən
  LLM provayderinə görə dəyişir; struktur/axın sabitdir.)

### 7. Daha 4 departament: Marketinq, Analitika, Hüquq, Maliyyə (2-ci sessiya)
Satışdan sonra 4 yeni **DƏSTƏK departamenti** əlavə olundu, hər biri TƏK agent (rol):
- **`marketing`** 📣 — 1 həftəlik kontent təqvimi + platformalara uyğun postlar + reklam mətni variantları.
- **`analytics`** 🔢 — KPI-lar, uğur meyarları, A/B test ideyaları, izləmə planı.
- **`legal`** ⚖️ — riskli/sübutsuz iddiaların yoxlanması, düzəliş təklifləri, disclaimer-lər
  (məs. fitness/sabun üçün sağlamlıq-müalicə vədlərini tutur). "Peşəkar hüquqi məsləhət deyil" qeydi var.
- **`finance`** 💰 — qiymət strategiyası, kampaniya büdcəsi, ROI proqnozu.

**Miqyaslana bilən dizayn qərarları (niyə belədir):**
- **`ROLE_SEQUENCE = CREATIVE_SEQUENCE + SUPPORT_SEQUENCE`** (`SUPPORT` = satış 2 + yeni 4 = 6 rol).
- **Yalnız yaradıcı rollar QA-dan keçir** (`QA_ROLES = set(CREATIVE_SEQUENCE)`); dəstək rolları
  `_step_work`-də birbaşa `DONE` olur (REVIEW atlanır). Səbəb: dəstək çıxışı məsləhət/hesabatdır,
  istifadəçi onsuz da təsdiqdən əvvəl hamısını görür — bu, 10 rol olsa belə layihəni sürətli və
  LLM-kvota-qənaətcil saxlayır (10 rol ≈ 16-18 addım, QA hər rola olsaydı ≈ 30+ olardı).
- **Kontekst qısaldılır** (`_run_role`-da hər əvvəlki çıxış ~800 simvola) — əks halda Developer-in
  tam HTML-i sonrakı 6 rola tam ötürülüb prompt-u şişirdib token limitini keçərdi.
- **Yeni departamentlər üçün DB sütunu YOXDUR** — çıxışları birbaşa `AgentTask`-dan (rol üzrə)
  oxunur. `sales_kit` sütunu qalır (o, /view və Telegram üçün lazımdır), amma 4 yeni departament
  frontend-də `project.tasks`-dan render olunur (dashboard-da açılan `<details>` kartları).
- Org-chart indi 6 `.dept-group` qutusu göstərir. Nəticə panelində satış paneli + `#deptReports`
  (marketinq/analitika/hüquq/maliyyə üçün açılan kartlar).
- **Test edilib:** layihə #11 (FitAz onlayn fitness) — 10 rol işlədi (18 addım), hər 6 dəstək
  departamenti dolu hesabat verdi; hüquq departamenti fitness sağlamlıq iddialarını düzgün tutdu.

### 8. Instagram avtomatik paylaşım (rəsmi Graph API) (2-ci sessiya)
Təsdiqlənən `social_post` layihəni istifadəçinin öz Instagram hesabına dərc edir.
- **[app/instagram.py](app/instagram.py)** — 2 addımlı Graph API axını: `/{ig_user_id}/media`
  (image_url + caption) → `/{ig_user_id}/media_publish` (creation_id) → permalink. Oxunaqlı
  xəta mesajları (`InstagramError`).
- **[app/api.py](app/api.py)**: `POST /agency/{id}/publish-instagram` — yalnız `social_post`,
  təkrar paylaşımı bloklayır (`instagram_published`), paylaşım təsdiq sayılır (status→DELIVERED).
  GERİ ALINMAYAN ictimai əməl olduğu üçün YALNIZ açıq istifadəçi əməli ilə (düymə/endpoint) baş
  verir — avtomatik yox.
- **[app/core.py](app/core.py)**: `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`,
  `INSTAGRAM_API_VERSION` (defolt `v21.0`). Boşdursa funksiya deaktiv.
- DB: `instagram_published` / `instagram_post_id` / `instagram_permalink` sütunları (ALTER TABLE
  ilə əlavə edildi).
- Frontend: nəticə panelində "📸 Instagram-da paylaş" düyməsi (yalnız social_post + awaiting/
  delivered), `window.confirm` təsdiqi, paylaşımdan sonra "paylaşıldı ✓" olur.
- **İSTİFADƏÇİNİN GÖRMƏLİ İŞLƏRİ (yalnız onlar edə bilər), HƏLƏ EDİLMƏYİB:**
  1. IG hesabı **Business/Creator** olmalı + Facebook Page-ə bağlı (adi hesab API ilə paylaşa bilmir).
  2. developers.facebook.com-da app + Instagram Graph API; öz hesabını tester/admin əlavə et
     (öz hesabına paylaşmaq üçün tam App Review lazım deyil).
  3. Uzunömürlü access token (`instagram_content_publish`+`instagram_basic`+`pages_read_engagement`)
     və IG Business hesab ID-si al → `.env`-ə yaz.
  4. **`PUBLIC_BASE_URL` İCTİMAİ olmalı** (port 8800 ngrok ilə açılmalı) — Meta şəkli
     `/agency/{id}/image`-dən özü yükləyir, lokal ünvan işləməz. Bu, hələ də açıq olan boşluqdur.
- **Kod yoxlanıldı** (token olmadan): endpoint "konfiqurasiya olunmayıb" xətası qaytarır, düymə
  social_post layihələrdə düzgün görünür. Real paylaşım token qoyulandan sonra sınanmalıdır.

### 9. Çox-hesablı (SaaS) platformaya çevrilmə + təhlükəsizlik auditi (3-cü sessiya)
İstifadəçi tərəfindən əlavə olunan böyük yeniliklər: **auth/workspace** (`app/auth.py` — PBKDF2
310k raund, server-side sessiya, hash-lənmiş token cookie), **Brand Kit** (workspace-ə bağlı brend
yaddaşı), **Kampaniyalar** (30 günlük plan generatoru), **Kontent Studiyası** (Post/Story/Carousel
draft + review), **Analitika** (KPI/ROAS + tövsiyələr), **stok foto** (Pexels/Wikimedia).

**Audit nəticəsi — yaxşı qurulmuş hissələr (dəyişdirilmədi):**
- Workspace izolyasiyası API-də möhkəmdir — canlı test: B hesabı A-nın layihəsini nə görür
  (404), nə siyahıda tapır (`[]`), nə də işlədə bilir (404).
- WebSocket workspace-scoped-dır (`ws.py`) və `workspace_id`-siz hadisələri bloklayır; `_event()`
  bunu daşıdığı üçün canlı lent qorunub.
- Brand Memory LLM promptuna YALNIZ `brand_ai_consent` açıq verildikdə əlavə olunur.

**Tapılıb DÜZƏLDİLƏN:**
19. **KRİTİK — ictimai müştəri linki sadalana bilirdi.** `/agency/{id}/view` ardıcıl ID ilə
    işlədiyi üçün anonim istifadəçi `/agency/1/view`, `/2/view` … deyə **bütün workspace-lərin**
    hazır nəticələrini oxuya bilirdi (tək istifadəçili demoda problem deyildi, çox-hesablı olandan
    sonra hesablar arası sızmadır). Həll: `AgentProject.share_token` (təxmin edilməyən,
    `secrets.token_urlsafe(24)`), yeni ictimai marşrut **`/s/{share_token}`**, köhnə marşrut
    silindi. Mövcud 12 layihəyə miqrasiya ilə token dolduruldu.
    **n8n-də DƏYİŞİKLİK LAZIM DEYİL** — workflow `view_url` sahəsini olduğu kimi oxuyur, biz
    sadəcə onun dəyərini token linkinə çevirdik (canlı test: köhnə link 404, yeni link 200).
20. **`_image_cache` limitsiz böyüyürdü** (yaddaş sızması) → 64 elementlik FIFO limiti.

**HƏLƏ AÇIQ (n8n redaktəsi tələb etdiyi üçün istifadəçi qərarına buraxıldı):**
- `AGENCY_API_KEY` boş olduğu üçün `require_api_key` **no-op**-dur, ona görə bunlar anonim açıqdır:
  `GET /agency/pending-approval` (bütün workspace-lərin gözləyən layihəsini qaytarır),
  `POST /agency/{id}/mark-notified` (canlı test: HTTP 200 — kənar şəxs bildirişi susdura bilər),
  `GET /agency/{id}/image` (ardıcıl ID ilə sadalana bilir).
  **Bağlamaq üçün:** `.env`-də `AGENCY_API_KEY` doldurun VƏ n8n-dəki bütün HTTP node-larına
  "Send Headers" ilə `X-API-Key` əlavə edin (əks halda Telegram axını 401 alıb dayanacaq).

### 10. Kampaniya ↔ Kontent Studiyası körpüsü (3-cü sessiya)
Əvvəl 30 günlük plan yaranırdı, amma günü materiala çevirmək üçün hər şey ƏL İLƏ yenidən
yazılmalı idi — iki modul bir-birindən qopuq idi. İndi tam dövrə var:

**İrəli axın:** `/campaigns` və `/calendar` səhifələrində hər gün kartında **"Materiala çevir →"**
düyməsi (`POST /campaigns/day/{day_id}/to-asset`, [app/web.py](app/web.py)) — gündən avtomatik
doldurulmuş draft yaradır: `title="Gün N · Reel"`, `headline=hook`, `caption=theme+CTA`,
`visual_brief=platform·tip·mövzu`, format isə gün tipindən çevrilir
(`content_studio.format_for_campaign_type`). **Yeni `REEL` formatı** əlavə olundu (9:16), çünki
kampaniya generatoru Reel istehsal edir, studiyada isə belə format yox idi.

**Geri axın (dövrənin bağlanması):** Studiyada material **APPROVED** ediləndə bağlı kampaniya
günü də avtomatik `APPROVED` olur (CHANGES_REQUESTED → `IN_REVIEW`) — təqvimdə hansı günün real
hazır olduğu əl ilə status yeniləmədən görünür. Çevirmə anında gün `PLANNED → IN_REVIEW` keçir.

**Detallar / niyə belədir:**
- **İdempotentdir** — gün üçün artıq material varsa yenisini yaratmır, mövcudunu açır; ona görə
  düyməyə təkrar basmaq dublikat yaratmır (düymə mətni də "Materialı aç →"-a dəyişir).
- `ContentAsset.campaign_day_id` sütunu artıq modeldə var idi, sadəcə heç vaxt doldurulmurdu —
  indi doldurulur; studiyada mənbə kampaniyaya keçid göstərilir.
- Kampaniya günü sorğusu `join(Campaign).filter(Campaign.workspace_id == …)` ilə scoped-dır.
- **Canlı test:** Reel günü → REEL/9:16 draft ✓; təkrar klik dublikat yaratmadı (asset sayı 1) ✓;
  material APPROVED → gün APPROVED ✓; **B hesabı A-nın gününü çevirə bilmədi** (redirect, asset
  yaranmadı) ✓; /campaigns 30 düymə, /calendar 33 düymə render olundu ✓.

### 11. Vizual keyfiyyət problemi — kök səbəb və həll (3-cü sessiya)
**Şikayət:** şəkillər həm keyfiyyətsiz idi (köhnə qəzet/kitab skanları), həm də səhifədə açılmırdı.

**Üç ayrı səbəb tapıldı:**
21. **`ALLOW_AI_IMAGE_FALLBACK` defolt `false` idi** → AI generasiyası tamamilə söndürülmüşdü.
    `PEXELS_API_KEY` də boş olduğu üçün yeganə qalan mənbə Wikimedia Commons idi. `.env`-də
    `true` edildi (+ `.env.example`-də izahla sənədləşdirildi). **Pexels açarı əlavə etsəniz
    (pulsuz, pexels.com/api) real fotolar daha yaxşı olar.**
22. **Wikimedia Commons sənəd skanları qaytarırdı** — PDF/DjVu səhifə renderləri (`…​.pdf/page1-…​.jpg`)
    texniki olaraq böyük JPEG olduğu üçün süzgəcdən keçirdi. `_is_document_scan()` əlavə olundu.
23. **Commons şəkilləri BRAUZERDƏN açılmırdı** — canlı test: `Referer` başlığı ilə sorğu **HTTP 429**
    qaytarır (hotlink məhdudiyyəti), yəni `<img>` teqi həmişə sınıq göstərirdi. Ona görə
    provayder sırası dəyişdirildi: **Pexels → AI generasiyası → (son çarə) Commons**
    (`find_stock_photo(..., include_commons=False)` + `_step_work`-dəki şərh).
24. **Dizayner cavab verməyəndə şəkil brifə yad olurdu** — sabit `"modern business lifestyle"`
    fallback-ı istifadə olunurdu. İndi `_usable_image_prompt()` cavabın həqiqətən ingiliscə prompt
    olduğunu yoxlayır (ə/ğ/ı/ş varsa — deməli LLM azərbaycanca tapşırıq mətnini təkrarlayıb, yararsızdır),
    yararsızdırsa `_image_terms_from_brief()` mövzunu **brifin özündən** götürür.
25. **`_step_planning` idempotent deyildi** — kilidi keçən hər hansı yol (məs. skript birbaşa
    `advance_project` çağırsa) hər rolu İKİ dəfə yaradırdı (test zamanı 20 tapşırıq yarandı).
    İndi tapşırıq artıq varsa planlaşdırma atlanılır.

**Canlı test (layihə #15, "Ren a Car" brifi):** tapşırıq sayı **10** (təkrarsız) ✓; mənbə
**AI/pollinations** ✓; prompt **"luxury car rental, sleek modern car, urban city street…"** —
brifə tam uyğun ✓; şəkil brauzer `Referer`-i ilə **HTTP 200** (429 yox) ✓; vizual yoxlanıldı —
real şəhər/avtomobil səhnəsi.

**Qalan məhdudiyyət (kod problemi deyil):** mətn keyfiyyəti pulsuz LLM tarifindən asılıdır.
Test zamanı logda **52 rate-limit** hadisəsi vardı; belə anlarda agentlər zəif/yarımçıq Azərbaycan
mətni verir ("təkəklərə", "Üzgünuşərən" kimi). Daha yaxşı nəticə üçün `GROQ_MODEL`-i daha güclü
modelə keçirmək və ya kvotası olan provayder əlavə etmək lazımdır.

### 12. Yeni pulsuz provayderlər (3-cü sessiya)
İstifadəçinin sorğusu ilə vizual/LLM mənbələri genişləndirildi. **Hamısı üçün istifadəçi öz
açarlarını `.env`-ə əlavə etdi, mən yalnız kodu qoşdum.**

**Şəkil provayderləri** ([app/stock_photos.py](app/stock_photos.py)) — yeni sıra:
**Pexels → Unsplash → Pixabay → (icazə verilibsə) AI → (son çarə) Wikimedia Commons.**
- `_search_unsplash()`, `_search_pixabay()` əlavə olundu (`settings.unsplash_access_key`,
  `settings.pixabay_api_key`). Açarı boş olan provayder sadəcə `None` qaytarıb keçilir.
- **Canlı test edildi:** Pexels açarı ilə real, mövzuya uyğun foto gəldi (Lotus idman avtomobili
  — əvvəlki AI-generasiya edilmiş şəkillərdən daha inandırıcı). Pixabay da ayrıca sınandı, işlədi.
- Pixabay-ın həm şəkil, həm VİDEO endpoint-i eyni açarla işləyir — video HƏLƏ tətbiq edilməyib
  (sistemdə ümumiyyətlə video-generasiya yoxdur, əvvəlki sessiyada ertələnib), amma açar hazırdır.

**LLM provayderləri** ([app/agency.py](app/agency.py) `_providers()`) — yeni zəncir:
**Groq → Cerebras → Gemini → OpenRouter → Hugging Face.**
- **OpenRouter** (`settings.openrouter_api_key/model`): pulsuz, kartsız, amma **model siyahısı
  TEZ-TEZ DƏYİŞİR** — ilk seçilən model (`deepseek-chat-v3-0324:free`) artıq mövcud deyildi (404),
  `google/gemma-4-31b-it:free`-yə keçirildi. Bu da PAYLAŞILAN HOVUZDA rate-limitə (429) düşdü —
  bizim öz limitimiz deyil, OpenRouter-in ümumi yükü. Fallback zənciri bunu düzgün idarə edir
  (sadəcə növbətiyə keçir), amma OpenRouter EHTİYAT rolunda olduğu üçün nadir hallarda çatılır.
- **Cerebras** (`settings.cerebras_api_key/model`): İYUL 2026-dan kartla $5 birdəfəlik trial
  krediti tələb edir (əvvəlki tam pulsuz tarif ləğv edilib). Model adı `llama-3.3-70b` artıq
  mövcud deyil (bu hesabda yalnız `gpt-oss-120b`, `gemma-4-31b` var — `gpt-oss-120b` seçildi).
  **Canlı test: HTTP 402 "Payment required"** — istifadəçinin hesabında trial krediti YOX-dur
  (kart əlavə edilib, amma kredit aktivləşməyib/bitib). Kod düzgündür, açar/model doğrudur —
  YALNIZ hesabda kredit qalanda işə düşəcək. İstifadəçi cloud.cerebras.ai-də billing tabını
  yoxlamalıdır.

**Nəticə:** Pexels + Pixabay canlı işləyir (əsas fayda buradan gəlir). Cerebras kod olaraq
hazırdır, hesab krediti aktivləşəndə əlavə addım lazım deyil.

### 13. Hüquq/Maliyyə şikayəti — kök səbəblər, paralel icra, kritik ORM bugu (3-cü sessiya)
İstifadəçi şikayəti: "Hüquq və Maliyyə bölməsi həm yaxşı işləmir, həm işi ləngidir." Araşdırma
bir prompt dizaynı bugu VƏ bir KRİTİK thread-təhlükəsizlik bugu üzə çıxardı.

**26. Prompt-lar arası "papağayı effekti" (tapıldı və düzəldildi):** bütün 6 dəstək roluna
(satış/marketing/analitika/hüquq/maliyyə) ortaq **`_NO_PREAMBLE_RULE`** əlavə etmişdim ki, giriş
cümlələrini ("Mən bu departamentdə işləyən kimi...") qadağan etsin. Amma qaydanın için*ə**
HÜQUQ-a xas konkret nümunə ("RİSKLİ İDDİALAR...") yazmışdım — zəif/yüklənmiş fallback modellər
öz məzmununu yazmaq əvəzinə bu nümunəni HƏRFİ TƏKRARLADI (canlı testdə: satış strateqi və
analitika "RİSKLİ İDDİALAR" ilə başladı!). **Həll:** nümunədən bütün konkret domen sözləri
çıxarılıb, YER TUTUCU (`[BİRİNCİ BAŞLIQ]`) ilə əvəz olundu. **İKİNCİ TUR:** hətta bu da bir
modeldə (finance) səhv nümunənin özünü demək olar hərfi təkrarlatdı — DƏRS: promptda YAZILMIŞ
"səhv nümunə" mətni belə zəif modellər üçün riskli ola bilər. Son həll: nümunə mətnini TAM
çıxarıb, yalnız **"cavabın ilk sözü sənin BİRİNCİ başlığın olmalıdır"** qaydasını qoydum — 3
ardıcıl təcrid edilmiş testdə (finance rolu) 3/3 düzgün nəticə verdi.

**27. Dəstək departamentləri PARALEL işləməyə keçirildi** (`_step_support_batch`,
`_ready_support_tasks`, `SUPPORT_DEPS`, `SUPPORT_PARALLELISM=4`): əvvəllər 6 dəstək rolu ARDICIL
işləyirdi (hər biri öz LLM sorğusunu gözləyirdi); indi `ThreadPoolExecutor` ilə eyni anda işləyir
(`outreach_writer` yalnız `sales_strategist` bitəndən sonra başlayır, `SUPPORT_DEPS` ilə qorunur).
**Ölçülmüş nəticə: 155s → 69s (2.2x sürətlənmə)**, sonrakı 5 ardıcıl testdə orta 60-100s aralığı.

**28. KRİTİK BUG (paralelləşdirmə zamanı üzə çıxdı, düzəldildi):** `_step_support_batch` `task`
statuslarını `DOING`-ə çevirib `db.commit()` çağıranda, SQLAlchemy-nin **defolt `expire_on_commit`**
davranışı BÜTÜN ORM obyektlərinin (`task`, `project`) atributlarını "expired" edir. Sonra worker
thread-lərdə `task.role`/`project.brief` kimi atributlara toxunmaq avtomatik **DB-dən yenidən
yükləmə** sorğusu göndərir — bu, EYNİ SQLAlchemy `Session`-u BİRDƏN ARTIQ thread-dən paralel
sorğulamağa gətirib çıxarır. Nəticə: təsadüfi `sqlite3.InterfaceError: bad parameter or other API
misuse` və ya `sqlalchemy.orm.exc.ObjectDeletedError` ilə **500 Internal Server Error** (canlı
testdə 5 icradan 2-3-də bir dəfə). **Həll:** bütün lazımi dəyərlər (`task.id/role/description/
title`, `project.brief/output_type/retry_feedback`) **commit-dən ƏVVƏL sadə Python dəyişənlərinə
çıxarılır**; worker thread-lər YALNIZ bu primitivlərlə işləyir, ORM obyektinə HEÇ TOXUNMUR.
**5 ardıcıl tam test sonra sıfır çökmə.** DƏRS: `ThreadPoolExecutor` + SQLAlchemy ORM birləşəndə
`expire_on_commit` gizli konkurensiya təhlükəsi yaradır — istənilən gələcək paralelləşdirmədə
eyni qaydaya əməl edilməlidir (ORM obyektini deyil, ondan çıxarılan primitiv dəyərləri ötür).
- **Əlavə qoruma:** [app/database.py](app/database.py) — SQLite **WAL jurnal rejiminə** keçirildi
  (`journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=10000`) — konkurent yazma/oxumada
  defolt "delete" rejimindən daha davamlıdır (əlavə təhlükəsizlik qatı, əsas düzəliş yuxarıdakıdır).

**29. Groq-un əsas modeli silinmişdi:** `llama-3.1-8b-instant` artıq mövcud deyildi (404) —
`openai/gpt-oss-20b`-yə keçirildi. Bu modelin gizli "reasoning" tokenləri var (Gemini-dəki eyni
problem) — `reasoning_effort:"none"` DƏSTƏKLƏNMİR (400 xətası), `"low"` işlədi və tokenləri
57-yə endirdi (108-dən), cavabın kəsilməsinin qarşısını aldı.

**30. Groq-un 429 (TPM) xətası ağıllı idarə olunur:** paralel batch 5 sorğunu eyni anda göndərəndə
Groq-un 8000 TPM limitini bir anda doldururdu. Groq-un cavabında "N saniyə sonra cəhd edin" göstərişi
var (bu, DƏQİQƏLİK/GÜNLÜK kvota deyil, tez bərpa olunan TOKEN BÜDCƏSİdir) — `_parse_retry_seconds()`
bunu oxuyur, ≤10s olarsa EYNİ provayderdə qısa gözləyib təkrar sınayır (zəif fallback-lərə
düşməkdən sürətlidir), uzun/naməlumdursa dərhal növbəti provayderə keçir (əvvəlki davranış).

**Nəticə:** Hüquq/Maliyyə (və bütün dəstək departamentləri) indi həm düzgün mövzuda cavab verir,
həm də 2x+ sürətlidir. Qalan minor keyfiyyət dəyişkənliyi (məs. bəzən 1-2 söz izi) bu gün
intensiv testdən Cerebras/HF kvotalarının tükənməsi ilə bağlıdır (provayder məsələsi, kod bugu
deyil) — kvotalar bərpa olunanda (HF aylıq, Cerebras billing) itəcək.

### 14. Dörd böyük özəllik + ilk test dəsti (4-cü sessiya)

**31. TƏK ROLU YENİDƏN YAZDIRMA + VERSİYA ARXİVİ** (`regenerate_task`, `app/agency.py`):
əvvəl bir departamentin cavabı bəyənilmirsə BÜTÜN layihəni rədd edib 10 agentin hamısını
yenidən işlətmək lazım gəlirdi (~70 saniyə + kvota israfı). İndi hər departament kartında
"🔄 Yenidən yaz" düyməsi + istəyə bağlı göstəriş sahəsi var ("qiymətləri manatla göstər").
Yeni cədvəl `agent_task_versions` köhnə variantı arxivləyir — "🕘 Köhnə variantlar" ilə baxıla bilər.
Marşrutlar: `POST /agency/{id}/task/{task_id}/regenerate`, `GET .../versions`.
**Kritik detal:** LLM cavab vermədikdə KÖHNƏ ÇIXIŞ SAXLANILIR (`db.rollback()`) — əks halda
istifadəçi bir düymə ilə hazır işini itirərdi. Yaradıcı rol dəyişdikdə deliverable yenidən
yığılır, amma DELIVERED/REJECTED statusu geri sürüşmür.

**32. TOKEN/XƏRC PANELİ** (`app/usage_report.py`, `templates/usage.html`, `/usage`):
`agency.py`-də `usage` sözü heç keçmirdi — 6 provayderin kvotası daim dolurdu, amma hansı
rolun nə qədər yediyi ölçülmürdü. İndi hər sorğu (uğurlu VƏ uğursuz) `llm_usage` cədvəlinə
yazılır: provayder, model, token sayı, gecikmə, uğursuzluq növü (rate_limit/payment/server/
network/parse). Panel provayder və departament üzrə qruplaşdırır.
**Thread təhlükəsizliyi (28-ci maddə ilə eyni tələ):** `_call_provider` paralel worker
thread-lərdən çağırılır, ona görə DB-yə BİRBAŞA YAZMIR — qeydlər `_USAGE_BUFFER` (lock ilə
qorunan sadə siyahı) yığılır, `advance_project` `finally` blokunda ƏSAS thread-dən
`flush_usage(db)` çağırır. Testlə qorunur (`test_call_provider_does_not_touch_database`).

**33. TƏHVİL PAKETİ — PDF hesabat + ZIP arxiv** (`app/export.py`):
agentlik aləti idi, amma müştəriyə fayl vermək yolu yox idi. İndi:
`GET /agency/{id}/export/report` (çap-hazır, tam müstəqil HTML) və `.../export/zip`.
**Niyə PDF kitabxanası YOX:** reportlab/fpdf Azərbaycan hərflərini (ə, ğ, ı, ş) yalnız ayrıca
Unicode TTF şrifti daxil edildikdə düzgün göstərir — həm ağır asılılıq, həm şrift faylı.
Çap-hazır HTML + brauzerin "PDF kimi saxla" funksiyası eyni nəticəni sıfır asılılıqla verir.
ZIP-də fayl adları transliterasiya olunur (`_slug`), məzmun UTF-8 qalır.

**34. İLK TEST DƏSTİ — 46 test** (`tests/`, `pytest.ini`): 3600+ sətir kodda bir dənə də test
yox idi; bu sessiyaya qədər hər bug yalnız ƏL İLƏ canlı test edərək tapılırdı.
Əhatə: workspace izolyasiyası (6), boru xətti vəziyyət maşını (9), yenidən yazdırma (7),
token qeydiyyatı (7), ixrac (8), prompt sağlamlığı (9).
**Testlər ŞƏBƏKƏYƏ ÇIXMIR** — `conftest.py` `_call_llm` və `find_stock_photo`-nu mock-layır;
soket bloklayıcı ilə yoxlanılıb (46/46 keçir). Yəni kvota yandırmır və provayder ölü olanda da işləyir.
**Niyə `dependency_overrides`:** `.env`-dəki `DATABASE_URL` `load_dotenv(override=True)` ilə
oxunduğu üçün `os.environ` ilə test bazasına keçmək MÜMKÜN DEYİL. Ayrıca, `TestClient` qəsdən
`with` bloksuz işlədilir ki, arxa fon planlayıcısı testlər zamanı layihələri irəlilətməsin.

**35. Testin dərhal tapdığı REAL bug — prompt papağayı (təkrar):** `_NO_PREAMBLE_RULE`-də
hələ də konkret başlıq nümunəsi ("HƏDƏF MÜŞTƏRİ" — satış rolunun başlığı) qalmışdı. Bu, 26-cı
maddədəki bugun eyni növüdür: ortaq qaydadakı istənilən konkret mətn zəif modellər tərəfindən
digər rollara kopyalanır. Qayda tam mücərrədləşdirildi + `test_shared_rule_contains_no_domain_specific_example`
qoruyucu kimi əlavə edildi. **Dərs: bu ortaq mətnə HEÇ VAXT konkret başlıq nümunəsi əlavə etməyin.**

**36. Windows-da tətbiq ümumiyyətlə açılmırdı:** yeni `app/night_shift.py`-dəki
`ZoneInfo("Asia/Baku")` `ZoneInfoNotFoundError` atırdı — Windows-da sistem timezone bazası yoxdur.
`tzdata==2026.3` `requirements.txt`-ə əlavə edildi (standart həll).

**37. TƏHLÜKƏSİZLİK BOŞLUĞU BAĞLANDI — `AGENCY_API_KEY`:** `/agency/pending-approval`,
`/agency/{id}/image` və `mark-notified` marşrutları açar boş olduqda TAMAMİLƏ autentifikasiyasız
idi və BÜTÜN workspace-lərin gözləyən layihələrini (brif mətni, Telegram chat ID, şəkil linki)
qaytarırdı — canlı sübut edilmişdi: ayrı hesabdan başqa workspace-in layihəsi oxundu.

Edilənlər:
- `.env`-də güclü açar yaradıldı (`secrets.token_urlsafe(32)`). `.env` gitignore-dadır.
- `/agency/{id}/image` marşrutuna `require_api_key` əlavə edildi (əvvəl heç bir qoruma yox idi).
- **Instagram üçün ayrıca ictimai ünvan:** `GET /s/{share_token}/image`. Meta şəkli ÖZÜ yükləyir
  və heç bir başlıq göndərə bilmir, ona görə açarla qorunan ünvan onun üçün yararsızdır. Yeni
  ünvanda ardıcıl ID yox, təxminedilməz token var — yəni `/agency/1/image`, `/2/image` … deyə
  sadalamaqla bütün workspace-lərin şəkillərini yığmaq artıq mümkün deyil.
  `publish_instagram` bu ünvanı istifadə edir.
- n8n-in 6 HTTP node-u `X-API-Key: ={{ $env.AGENCY_API_KEY }}` göndərmək üçün yeniləndi
  (açarın ÖZÜ JSON-a yazılmadı ki, workflow faylları sirr daşımasın).
- **n8n işə salmazdan əvvəl:** konteynerə `-e AGENCY_API_KEY=...` VƏ `-e N8N_BLOCK_ENV_ACCESS_IN_NODE=false`
  verilməlidir, əks halda `$env` bloklanır və başlıq boş gedib 401 alır (README-də tam əmr var).
  Alternativ: n8n UI-da hər node-un header sahəsinə açarı birbaşa yapışdırmaq.
- 6 yeni test (`tests/test_api_key_auth.py`) həm bağlanmanı, həm n8n-in işlədiyini qoruyur.

Canlı təsdiq: açarsız `pending-approval`/`image`/`mark-notified` → **401**; düzgün açarla → **200**;
`/s/{düzgün-token}/image` → **200 image/jpeg**; `/s/yanlış-token/image` → **404**; brauzer sessiyası
təsirlənməyib (dashboard bütün marşrutlarda 200).

**Qeyd — açar BOŞ qalarsa köhnə açıq davranış qayıdır** (qəsdən, lokal demo üçün). Yəni bu
qoruma `.env`-dən asılıdır; `.env` itsə/yenidən qurulsa açarı yenidən doldurmaq lazımdır.

**38. n8n tərəfi tamamlandı (Docker işə salındıqdan sonra).**

- `self-hosted-ai-starter-kit/.env`-ə `AGENCY_API_KEY` + `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`
  əlavə edildi (compose-da `env_file: .env` var, ona görə konteynerə avtomatik ötürülür).
  Həmin `.env` də gitignore-dadır. Konteyner `docker compose up -d --force-recreate n8n` ilə
  yeniləndi; hər iki dəyişən konteyner daxilində təsdiqləndi.
- **DİQQƏT — n8n bu quraşdırmada SQLite işlədir, Postgres YOX.** `docker exec n8n printenv`
  `DB_*` dəyişənlərini GÖSTƏRMİR və real baza `/home/node/.n8n/database.sqlite`-dır (~35 MB).
  Postgres-dəki `workflow_entity` cədvəli KÖHNƏ/ayrı nüsxədir. Workflow-ları yoxlamaq üçün
  `docker exec n8n n8n list:workflow` istifadə edin — postgres sorğusu yanlış nəticə verir
  (mən əvvəl məhz buna görə "workflow yoxdur" qərarına gəlmişdim, halbuki var idi).
- **Aktiv workflow-lar qısa müddət sınıq qaldı və düzəldildi:** `SA7ZRzGGVJ3PyfhJ`
  (Approval Notify) və `Wam8MF7p8DRkbYI9` (Telegram Commands) AKTİV idi və `X-API-Key`
  göndərmirdi — yəni açar qoyulan an 401 almağa başlamışdılar. Hər ikisi export → 3 HTTP
  node-a başlıq əlavə → eyni ID ilə import edildi (credential-lar qorundu). **İmport onları
  DEAKTİV EDİR**, ona görə sonra `n8n update:workflow --id=... --active=true` çağırılmalıdır
  (bu tələ növbəti dəfə də olacaq).
- **Uçdan-uca təsdiq (n8n konteynerinin İÇİNDƏN):** açarsız → **401**, `$AGENCY_API_KEY` ilə → **200**.
- **Təmizlənməli qalıq:** idxal zamanı 2 DUBLİKAT yarandı — `RGIOAck1FeRXfTkm` və
  `zx2ONbRIaantoWgF` (hər ikisi PASSİV, zərərsiz). Bu n8n versiyasında `delete:workflow` CLI
  əmri YOXDUR və 35 MB-lıq işlək bazada əl ilə SQL silmə riskli olduğu üçün toxunulmadı —
  **n8n UI-dan silin** (hər biri 2 klik).

### 15. Müştəri təcrübəsi düzəlişləri (5-ci sessiya)

**40. KRİTİK — Instagram paylaşımı ÇARPAZ-KİRAYƏÇİ idi.** `instagram.py`-nin BÜTÜN funksiyaları
birbaşa qlobal `settings.instagram_access_token` / `instagram_user_id` oxuyurdu. Yəni istənilən
müştəri workspace-indən "Instagram-da paylaş" düyməsinə basıldıqda kontent **tətbiq sahibinin
real, ictimai Instagram hesabına** dərc olunurdu. Bu, sadəcə "mənasız düymə" deyil, məlumat/
kontent sızması idi.

Həll — hesab workspace səviyyəsinə keçdi:
- `Workspace` modelinə `instagram_access_token`, `instagram_user_id`,
  `instagram_addon_enabled` sütunları (migrasiya `workspace_migrations`-a əlavə olundu).
- `instagram.IgAccount` + `account_for(workspace)`. **Qlobal .env-ə fallback QƏSDƏN YOXDUR** —
  fallback qoysaq eyni bug geri qayıdar (`test_no_fallback_to_global_env` qoruyur).
- `publish_photo/_reel/_story/_publish/_guard/_create_container/_wait_until_ready` hamısı
  artıq `account` parametri alır; heç biri qlobal ayarı oxumur.
- `POST /publish-instagram` qoşulmamış workspace üçün **402 Payment Required** qaytarır
  (UI düyməni gizlətsə də API birbaşa çağırıla bilər — server də bloklamalıdır).
- Birdəfəlik köçürmə: köhnə qlobal açar SAHİBİN (`legacy`) workspace-inə yazılır ki, onun
  mövcud quraşdırması işləməyə davam etsin; qalan bütün workspace-lər bağlı qalır.
  Canlı təsdiq: `legacy addon=True token=True`, digər 3 workspace `addon=False token=False`.

**41. Düymə əvəzinə paket təklifi (istifadəçi təklifi).** `ProjectDetail`-ə `instagram_available`
bayrağı əlavə olundu. Hesab qoşulmayıbsa "Paylaş" düyməsi göstərilmir — onun yerinə
`#instagramUpsell` bloku çıxır və yeni `/pricing#instagram` səhifəsinə aparır. Səbəb: hesabı
qoşulmamış müştəri üçün həmin düymə heç nə edə bilməzdi.

**42. Naviqasiya "Studio"/"Brif" linkləri işləmirdi — üç ayrı defekt tapıldı:**
- **`.intro-curtain` tələsi (əsas şübhəli):** bütün ekranı örtən, `pointer-events:auto`,
  `z-index:100` overlay-dir və yeganə çıxış yolu CSS animasiyasıdır. Animasiya tamamlanmasa
  (səhifə fon tabında açılıb — brauzer animasiyaları dayandırır) pərdə İLİŞİB QALIR və BÜTÜN
  kliklər ona dəyir. Sınaqda məhz bu baş verdi: 3.5 saniyə sonra da `visibility:visible`,
  `elementFromPoint(nav)` → `intro-curtain`. `base.html`-ə `animationend` + 2.6s zaman limitli
  silmə qoruyucusu əlavə edildi.
- **`.topnav{position:absolute}`** idi — səhifə sürüşən kimi naviqasiya yuxarı qaçırdı və
  linklər əlçatmaz olurdu. `position:fixed` edildi (+ sürüşəndə fon üçün `.topnav.scrolled`).
- **`#studio` ölü link idi** — hedef hero-dur, yəni scroll 0. Yuxarıdaykən (naviqasiyanın
  yeganə göründüyü yer) klikləmək HEÇ NƏ etmirdi. Artıq açıq şəkildə yuxarı sürüşdürülür.
- Ankerlər üçün `scrollIntoView` əsaslı işləyici əlavə olundu (`html`-də `scroll-snap-type:y`
  var və native fragment naviqasiyası ilə toqquşur) + `scroll-margin-top:70px`.
- **DÜRÜSTLÜK QEYDİ:** anker sürüşməsinin özünü test panelində TƏSDİQLƏYƏ BİLMƏDİM — həmin
  başsız panel ümumiyyətlə sürüşmür (`window.scrollTo(0,500)` da `scrollY=0` verir, halbuki
  sənəd 4207px-dir). Curtain silinməsi və `position:fixed` təsdiqləndi; sürüşmə real brauzerdə
  yoxlanılmalıdır.

**43. Ayrıca "Token" naviqasiya girişi silindi (istifadəçi qeydi).** Control Room-da onsuz da
"AI provayder sağlamlığı" bölməsi var və oradan "Tam token və xərc hesabatı →" ilə `/usage`-ə
keçilir. `/usage` səhifəsi SAXLANILDI (Control Room ona bağlıdır), yalnız naviqasiyadakı
təkrar giriş çıxarıldı.

### 16. Saytda səsli AI operator (6-cı sessiya)

**44. Əlaqə nömrəsi footer-də.** `.env`-də `CONTACT_PHONE`/`CONTACT_EMAIL`/`CONTACT_HOURS`
— boş qalsa HEÇ NƏ göstərilmir (yarımçıq/uydurma məlumat göstərməkdənsə gizlətmək düzgündür).
`app/core.py`-də `contact_phone_href()` `tel:` linkini normallaşdırır.

**45. Səsli AI agent — TELEFONİYA YOX, brauzer səsi (istifadəçi qərarı ilə).** İstifadəçi
əvvəlcə real +994 nömrəsi istədi; araşdırma göstərdi ki, (a) Twilio +994 nömrələrini sərbəst
satmır, (b) DID satıcıları $700/ay-a qədər ola bilir, (c) Azercell beynəlxalq nömrəyə
yönləndirməni dəstəkləmir. İstifadəçi ən ucuz variantı istədi → tam pulsuz arxitektura:
  - **Nitq tanıma:** brauzerin öz Web Speech API-si (`SpeechRecognition`, `lang="az-AZ"`) —
    server audio görmür, xərc yoxdur.
  - **Beyin:** mövcud LLM zənciri (Groq və s.), yeni fayl yoxdur.
  - **Səsləndirmə:** brauzerin öz Azərbaycanca səsi (varsa) → yoxdursa Azure Speech F0
    (pulsuz tarif, ayda 0.5M simvol) → o da yoxdursa sadəcə mətn göstərilir. Azure-da az-AZ
    üçün 2 neyron səs var: `az-AZ-BanuNeural` (qadın), `az-AZ-BabekNeural` (kişi).

**Yeni fayllar:**
  - `app/voice_agent.py` — `respond()` (LLM-ə sorğu, JSON parse, fallback), `synthesize()`
    (Azure TTS, açar yoxdursa None), `_clean_for_speech()` (markdown/emoji təmizliyi —
    səsləndirilən mətndə görünməməlidir).
  - `app/voice_api.py` — `GET /voice/config`, `POST /voice/turn`, `POST /voice/speak`.
    **QƏSDƏN autentifikasiyasız** (potensial müştərinin hesabı yoxdur) — kvota qorumaq üçün
    sessiya başına `MAX_TURNS_PER_SESSION=40` limiti var.
  - `static/voice-agent.js` + CSS — hər səhifədə üzən "📞" düyməsi, açılan panel, mikrofon/
    yazı ilə giriş, cavabı həm mətn, həm səslə göstərir.
  - `VoiceCall` cədvəli (`db_models.py`) — hər söhbətin qeydi: ad/nömrə (öyrənilsə), nəticə
    (`none/create_brief/capture_lead/handoff`), tam mətn tarixçəsi, yaradılmış layihə ID-si.

**Agentin edə biləcəyi YEGANƏ 3 əməl** (`ACTIONS`), qəsdən dar saxlanılıb:
  - `create_brief` — kifayət qədər konkret istək toplanıbsa avtomatik layihə yaradır
    (sahibin `legacy` workspace-inə düşür — zəng edən hələ hesablı müştəri deyil).
  - `capture_lead` — ad/nömrə yazıb `VoiceCall`-a qeyd edir.
  - `handoff` — söhbət mürəkkəbləşəndə insana yönləndirmə mesajı verir.
  Heç bir geri alınmaz və ya xarici əməl YOXDUR.

**KRİTİK BUG (canlı testdə tapıldı, dərhal düzəldildi):** `voice_api.voice_turn` əvvəlcə
`append_transcript(..., "user", ...)` çağırırdı, SONRA `respond()` `VoiceCall` sətrini
yaradırdı — yəni müştərinin İLK mesajı transkriptə səssizcə YAZILMIRDI (sətir hələ yox idi,
`append_transcript` "tap, yoxdursa heç nə etmə" məntiqi ilə işləyirdi). Həll: `_get_or_create_call()`
ortaq giriş nöqtəsi — həm `append_transcript`, həm `_touch_call` indi eyni funksiyadan
keçir. `test_transcript_is_recorded` bunu qoruyur.

**Canlı təsdiq:** `/voice/config` → salamlama + sessiya qaytarır; `/voice/turn` real Groq
sorğusu ilə düzgün Azərbaycanca cavab verir; brauzerdə widget açılır, yazı ilə göndərilən
mesaj server-ə gedib-qayıdır, konsolda xəta yoxdur.

**Dürüstlük qeydi — prompt tənzimlənməsi lazım ola bilər:** canlı sınaqda model çox
ehtiyatlı davranıb 3 dəfə ardıcıl aydınlaşdırıcı sual verdi, `create_brief`-ə keçmədi
(halbuki mock testlərdə həmin əməl düzgün işləyir — problem prompt "münasibətindədir",
kodda deyil). Real istifadədən sonra `SYSTEM_PROMPT`-u (voice_agent.py) daha tez qərara
gəlməyə təşviq etmək lazım gələ bilər.

**Söndürmək üçün:** `.env`-də `VOICE_AGENT_ENABLED=false`.

**39. `.env.example`-də REAL Instagram access token tapıldı və təmizləndi.** Fayl gitignore-da
DEYİL (`.env`-dən fərqli olaraq), yəni token commit olunub sızacaqdı. Token `.env`-ə köçürüldü
(itmədi), `.env.example`-də sahə boşaldıldı. **Qayda: `.env.example`-ə HEÇ VAXT real dəyər yazmayın.**
Bütün digər sahələr yoxlandı — təmizdir.

**40. Instagram paylaşımı QURULDU və real API ilə təsdiqləndi (5-ci sessiya).** Əvvəllər
`INSTAGRAM_ACCESS_TOKEN` boş idi və kod `graph.facebook.com`-a müraciət edirdi. Meta app
(`test`, App ID `892997936875804`) əslində **"API setup with Instagram login"** rejimindədir —
bu rejim Facebook Page TƏLƏB ETMİR və **`graph.instagram.com`** hostundan istifadə edir.
İki axının tokenləri bir-birini **ƏVƏZ ETMİR** (`graph.facebook.com`-a IG-login token
göndərəndə `Cannot parse access token` gəlir — bu, "token pozuqdur" demək deyil, sadəcə
səhv hostdur).

Səhv icazə adları da vaxt itkisinə səbəb oldu: Graph API Explorer-də köhnə `instagram_basic` /
`instagram_content_publish` seçilmişdi, halbuki bu rejim **yeni** adları istifadə edir:
`instagram_business_basic` + `instagram_business_content_publish`. Köhnə adlarla
"Invalid platform app" xətası çıxır.

Edilənlər: icazələr app-a əlavə edildi (hər ikisi "Ready for testing"), token generasiya olundu,
`app/core.py`-yə `INSTAGRAM_API_HOST` parametri gəldi, `app/instagram.py` yeni hosta keçirildi
və **`publish_reel()`** funksiyası əlavə olundu (video konteyneri `FINISHED` olana qədər
15 san × 20 gözləyir — şəkildən fərqli olaraq video dərhal hazır olmur).

| Sahə | Dəyər |
|---|---|
| Meta App ID | `892997936875804` |
| Instagram App ID | `2914679632200892` |
| Hesab | `ai.gencythe1` (`MEDIA_CREATOR`) |
| INSTAGRAM_USER_ID | `17841408322710419` |
| Host | `https://graph.instagram.com` (v23.0) |

**TAM TƏSDİQLƏNDİ:** n8n workflow-u uçtan-uca işlədi və real post paylaşıldı —
media `18070728227538182`, permalink `https://www.instagram.com/p/DcO7-7Qjovg/`
(2026-08-19, icra müddəti 13.4 san).

**41. AÇIQ BLOKER: `PUBLIC_BASE_URL` hələ lokaldır.** Instagram şəkli URL-dən ÖZÜ yükləyir,
ona görə `http://127.0.0.1:8800` ilə paylaşım mümkün deyil. Mövcud ngrok tuneli yalnız
port 5678-i (n8n) açır, backend 8800 ictimai deyil (bax "Xarici asılılıqlar" cədvəli).
İkinci tunel və ya reserved domen lazımdır.

**42. Media URL-i hər host-dan işləmir.** Wikimedia (`upload.wikimedia.org`) Meta-nın
yükləyicisini bloklayır — həm PNG, həm JPEG üçün eyni `error_subcode 2207052` gəlir. Xəta
mesajı "Only photo or video can be accepted" desə də, əsl səbəb formatda yox, host-un
Meta-ya icazə verməməsindədir. `www.gstatic.com` işlədi. **Debug edərkən əvvəlcə host-u
şübhələndirin, formatı yox.** Format tələbi ayrıca qüvvədədir: şəkil JPEG olmalıdır.

**44. n8n Instagram workflow-u quruldu (5-ci sessiya).** `The Agency — Instagram Publish`
(id **`xxWlkDOPHsIVJKA9`**), mənbə: [n8n_workflows/3_instagram_publish_workflow.json](n8n_workflows/3_instagram_publish_workflow.json).
İki giriş nöqtəsi var: Manual Trigger (test üçün hazır Set node ilə) və Webhook
`POST /webhook/agency/instagram-publish` (`media_type`, `image_url`/`video_url`, `caption`).

**Token workflow JSON-unda DEYİL** — n8n credential-ında saxlanılır: `Instagram Graph API`
(id `9ewXDqxraZD1MGRK`, tip `httpHeaderAuth`, `Authorization: Bearer <token>`). Bearer header
üsulu `graph.instagram.com` ilə yoxlanıb, işləyir. Credential mənbə fayla düşmədiyi üçün
repo-da sirr qalmır — yeni mühitdə əl ilə doldurulmalıdır.

Əvvəldən mövcud olan `AI to Instagram Auto Post` və `Gemini to Instagram Auto Post`
workflow-ları **tamamilə boşdur** (node yoxdur) — istifadə olunmur, silinə bilər.

**45. ƏN VACİB TAPINTI: ŞƏKİL konteyneri də dərhal hazır olmur.** İlk quraşdırmada
`publish_photo()` konteyner yaradıb dərhal `media_publish` çağırırdı (video üçün gözləmə var
idi, şəkil üçün yox). Meta cavabı:

```
"Media ID is not available" — kod 9007, subcode 2207027
error_user_msg: "The media is not ready for publishing, please wait for a moment"
```

Həll: həm `app/instagram.py`-də, həm n8n workflow-unda **şəkil də, video da eyni
"gözlə → status yoxla → FINISHED?" dövrəsindən** keçir. Şəkil üçün 3 san × 20, video üçün
15 san × 20. n8n-də `REELS-dir?` şaxələnməsi tamamilə silindi — xətti axın həm sadədir,
həm doğru.

**46. n8n xəta mesajları ümumidir, əsl səbəb "Error details"-dədir.** "Bad request - please
check your parameters" heç nə demir; node-u açıb **Error details → Full message** bölməsinə
baxın — Meta-nın tam JSON cavabı oradadır. Vaxt itirməmək üçün İLK ORAYA baxın.

**47. n8n HTTP Request: `contentType: 'form-urlencoded'` + `specifyBody: 'json'` İŞLƏMİR.**
"The value in the JSON Body field is not valid JSON" xətası verir (ifadə düzgün olsa belə).
`contentType: 'json'` istifadə edin — Instagram Graph API JSON body-ni qəbul edir (curl ilə
təsdiqləndi; query string də işləyir).

**48. İki trigger olan workflow-da n8n hansından başlayacağını ÖZÜ seçir.** Manual + Webhook
olanda defolt Webhook olur və "Waiting for you to call the Test URL" ilə asılı qalır — sanki
donub. Execute düyməsinin yanındakı **oxdan "from Test: Execute Workflow"** seçin. Səhifə hər
yenilənəndə bu seçim SIFIRLANIR.

**49. REELS də uçtan-uca test edildi və işlədi.** Permalink
`https://www.instagram.com/reel/DcO9DkSGt_q/`, media `18483218053106766`. Gözləmə dövrəsi
**4 dəfə** təkrarlandı (video ~20-30 saniyəyə hazır oldu) — yəni dövrə məntiqi real şəraitdə
də doğru işləyir.

**50. TƏLƏ: konteyner ID qaytarması videonun QƏBUL OLUNDUĞU demək DEYİL.** Meta videonu
asinxron yükləyir və doğrulayır. Yararsız/əlçatmaz video ilə də `POST /media` normal
`{"id":"..."}` qaytarır, xəta yalnız sonra `status_code: ERROR` kimi görünür. **Yeganə
etibarlı göstərici `status_code`-dur** — "ID gəldi, deməli oldu" deyə düşünməyin.

**51. Test media host-ları (yoxlanılıb).** Meta faylı özü yüklədiyi üçün host bloklamamalıdır:

| URL | Nəticə |
|---|---|
| `www.gstatic.com/webp/gallery/1.jpg` | ✅ şəkil üçün işləyir |
| `test-videos.co.uk/.../Big_Buck_Bunny_360_10s_1MB.mp4` | ✅ video üçün işləyir |
| `upload.wikimedia.org/...` | ❌ bloklayır (yanıldıcı format xətası verir) |
| `commondatastorage.googleapis.com/gtv-videos-bucket/...` | ❌ 403 → konteyner ERROR olur |
| `www.w3schools.com/html/mov_bbb.mp4` | ❌ 403 |

**52. `PUBLIC_BASE_URL` bloker-i YARIYA QƏDƏR aradan qaldırıldı (kod dəyişikliyi ilə).**
Yeni `api._instagram_image_url()` şəkil ünvanını belə seçir:
1. PUBLIC_BASE_URL ictimaidirsə → backend proksisi `/s/{token}/image` (ən etibarlısı, keşli).
2. Deyilsə → layihənin `deliverable_image_url`-i **birbaşa**, amma yalnız Meta-nın yükləyə
   bildiyi host-lardan (`images.pexels.com`, `images.unsplash.com`, `cdn.pixabay.com`).
3. Heç biri olmasa → izahlı xəta (əvvəlki kimi sərt blok yox).

`instagram._guard()` artıq PUBLIC_BASE_URL-ə yox, **verilən media URL-inə** baxır — çünki
indi lokal PUBLIC_BASE_URL-lə də ictimai mənbə URL-i ötürülə bilir.

**Mövcud 30 layihənin 15-i artıq tunelsiz paylaşıla bilər** (Pexels), qalan 15-i
pollinations/wikimedia olduğu üçün tunel tələb edir.

**53. NİYƏ POLLINATIONS BİRBAŞA İŞLƏMİR.** `image.pollinations.ai` şəkli sorğu anında
generasiya edir (onlarla saniyə). Meta-nın yükləyicisi gözləmir — konteyner yaratma anında
`{"error":{"code":1,"message":"An unknown error has occurred."}}` gəlir. Ona görə bu şəkillər
üçün backend proksisi (yəni ictimai PUBLIC_BASE_URL) şərtdir — proksi şəkli bir dəfə yükləyib
keşləyir (`_image_cache`) və Meta-ya dərhal verir.

**54. NGROK PULSUZ PLANDA İKİ TUNEL EYNİ VAXTDA İŞLƏMİR.** `ngrok.yml`-ə iki tunel yazıb
`ngrok start --all` etdikdə hər ikisi **eyni** `public_url`-i alır
(`cursor-eleven-preteen.ngrok-free.dev`) — pulsuz plan cəmi bir domen verir, domen
göstərilməyən tunel də həmin domeni götürür və marşrutlaşdırma pozulur. Sınandı və geri
qaytarıldı; `ngrok.yml` yenidən yalnız `authtoken`-dən ibarətdir. **Bu yolu təkrar sınamayın.**
Mümkün variantlar: (a) cloudflared quick tunnel (pulsuz, hesabsız, ayrıca URL),
(b) ngrok ödənişli plan, (c) şəkli n8n-in mövcud tuneli üzərindən proksiləmək.

**55. BUG: `enhance=true` pollinations-ı sındırırdı — 13 layihənin şəkli ölü idi.**
`image.pollinations.ai` bu parametrlə **200 + boş gövdə (0 bayt)** qaytarır. Xəta kimi
görünmür, ona görə uzun müddət nəzərə çarpmayıb. `_pollinations_url()`-dan çıxarıldı
(indi 63 KB gəlir). Bazadakı 7 sınıq URL də təmizləndi (`enhance=true` silindi).

**56. BUG: şəkil keşi BOŞ cavabı da keşləyirdi.** `_image_bytes()` `raise_for_status()`-dan
sonra `resp.content`-i birbaşa keşləyirdi; mənbə boş qaytaranda həmin layihənin şəkli
**əbədi 0 bayt** qalırdı və əsl səbəb görünməz olurdu. İndi boş cavab keşlənmir, 502 qaytarılır.

**57. Meta media yükləyicisi əvvəlcə HEAD sorğusu atır.** FastAPI `@router.get` HEAD-i
avtomatik əlavə ETMİR → 405 → Meta ümumi `code: 1` verir. `/s/{token}/image` indi
`api_route(methods=["GET","HEAD"])`-dır.

**58. ƏN ÇOX VAXT APARAN TƏLƏ: Meta uğursuz yükləməni URL üzrə KEŞLƏYİR.** Bir dəfə
alınmayan ünvan, məzmun düzələndən sonra da rədd olunur — həmişə eyni məlumatsız
`code: 1` ilə. `?v=<vaxt>` keş qıranı əlavə edildi (`_instagram_image_url`). **Debug
edərkən: URL-i dəyişdirmədən təkrar cəhd etmək YANILDICIDIR.**

**59. Paylaşım memarlığı: n8n əsasdır (istifadəçi qərarı).** Axın:
`/paylas <id>` → Təsdiqlə → **Instagram məlumatı al** (`GET /agency/{id}/instagram-payload`)
→ Paylaşılsın? → **Instagram-a paylaş** (n8n webhook) → **Nəticəni bazaya yaz**
(`POST /agency/{id}/mark-instagram-published`) → Telegram bildirişi.

Şəkil ünvanının seçilməsi (proksi/mənbə, keş qıran, host siyahısı) **yalnız Python-dadır**;
n8n hazır `image_url`-i ötürür. Beləliklə məntiq iki yerdə təkrarlanmır.

**UÇTAN-UCA TƏSDİQLƏNDİ (test layihəsi #31, kitab kafesi):** brif → run (6 addım) →
AWAITING_APPROVAL → approve → payload → n8n webhook → **paylaşıldı**
(`https://www.instagram.com/p/DcPBtsDjndQ/`) → bazaya yazıldı (status DELIVERED) →
təkrar paylaşım cəhdi düzgün bloklandı ("artıq paylaşılıb"). Yoxlanılmayan yeganə halqa:
Telegram trigger-in özü (telefon tələb edir) — qalan bütün addımlar eyni endpoint-lərdir.

**60. `PUBLIC_MEDIA_BASE_URL` — yeni və ayrıca sahə.** `PUBLIC_BASE_URL`-i https etmək
GÖRÜNMƏYƏN ZƏRƏR verir: `auth.set_session_cookie` çərəzi `Secure` işarələyir və
`http://127.0.0.1:8800` ilə **giriş işləmir** (testlər bunu tutdu). Ona görə media ünvanı
autentifikasiyadan ayrıldı: tətbiq lokal qalır, Meta isə tuneldən şəkli yükləyir.

**61. Cloudflare quick tunnel (8800 üçün).** `cloudflared tunnel --url http://localhost:8800`
— pulsuz, hesabsız, ngrok-dan müstəqil. **URL hər başladıqda DƏYİŞİR** →
`PUBLIC_MEDIA_BASE_URL`-i hər dəfə yeniləmək lazımdır. (ngrok-un pulsuz planı ikinci tunelə
imkan vermir, bax 54.)

**62. Backend `0.0.0.0`-a bağlanmalıdır, yoxsa n8n ona ÇATA BİLMİR.** Server sistem
Python-u ilə və yalnız `127.0.0.1`-ə bağlı işləyirdi → Docker-dəki n8n üçün
`host.docker.internal:8800` ölü idi. Düzgün işə salma: `run.py` (yaşıl ▶) və ya
`.venv/Scripts/python -m uvicorn main:app --host 0.0.0.0 --port 8800`.

**63. Telegram Commands workflow-u ARTIQ SINIQ İDİ (n8n loglarında görünürdü).**
Konteynerə `WEBHOOK_URL=http://localhost:5678` verilmişdi, Telegram isə HTTPS tələb edir →
aktivləşmə eksponensial gecikmə ilə (1024 → 2048 → 4096 san) təkrar-təkrar uğursuz olurdu.
n8n-dəki "Published" nişanı YANILDICI idi — bayraq bazada qalır, webhook isə qeydiyyatdan
keçmir. Düzəliş: `self-hosted-ai-starter-kit/.env`-ə
`WEBHOOK_URL=https://cursor-eleven-preteen.ngrok-free.dev` əlavə edildi və konteyner
`docker compose up -d --no-deps n8n` ilə yenidən yaradıldı (məlumat volume-dadır, itki yoxdur).
**Yoxlama üsulu:** `docker logs n8n | grep -i "activat"` — bayrağa yox, LOGA baxın.

**64. STORIES əlavə olundu — üç media növü də işləyir.** `media_type=STORIES` eyni
konteyner→gözlə→dərc axınından keçir. `MEDIA_CREATOR` hesabı ilə problemsiz işləyir
(Business hesab tələb olunmur). Real paylaşımla təsdiqləndi:
`https://www.instagram.com/stories/ai.gencythe1/3967810060881385870` (media 18093546299633554).

Story API-nin **kodla aşıla bilməyən** məhdudiyyətləri:
* `caption` YOXDUR — göndərilsə də ignor olunur. **Mətn görünməlidirsə şəklin ÜZƏRİNƏ
  çəkilməlidir** (şəkil generasiyası mərhələsində həll olunmalıdır).
* Sticker, sorğu, link, musiqi, mention — API-dən əlavə edilmir.
* Highlight-a əlavə etmək mümkün deyil; 24 saatdan sonra itir.
* Ölçü 9:16 (1080×1920) tövsiyə olunur, video ≤ 60 san.

Kod: `instagram.publish_story(media_url, is_video=False)`.
n8n: "Yoxla və hazırla" node-u indi IMAGE | REELS | STORIES qəbul edir.

**65. Instagram AI chatbot — ARAŞDIRILDI, HAZIRDA MÜMKÜN DEYİL.** Oxuma tərəfi işləyir
(`GET /me/conversations` 200 qaytarır), amma:
* Webhook üçün app **published** olmalıdır (panel açıq yazır).
* Development rejimində yalnız **tester hesablarla** mesajlaşmaq olar — real izləyicilərə
  cavab getmir.
* Bunu açmaq üçün App Review + **Business Verification** lazımdır, o da hüquqi şəxs
  sənədləri tələb edir. **İstifadəçinin şirkət hesabı yoxdur → bu yol bağlıdır.**

Alternativlər (istifadəçi hələ seçim etməyib): (a) veb chat + Instagram bio-da link —
layihədə FastAPI/LLM/bilik bazası onsuz da var, Meta asılılığı yoxdur; (b) mövcud Telegram
bota AI qolu; (c) ManyChat/Chatfuel kimi Meta tərəfindən artıq təsdiqlənmiş platforma
(öz App Review-a ehtiyac qalmır, adətən FB Page istəyir); (d) dev rejimində nümayiş botu.

**66. "Postu story-yə əlavə et" — API-DƏ YOXDUR, oxşarı var.** Instagram-ın öz funksiyası
(postu sticker kimi göstərir, `@istifadəçi` yazır, klikləyəndə posta aparır) API-dən
**əlçatan deyil** — belə parametr mövcud deyil. Story-yə link/sticker əlavə etmək də olmur.

Mümkün olan: postun `media_url`-ini götürüb **adi story kimi yenidən dərc etmək**. Şəkil
eyni olur, amma **posta keçid və müəlliflik göstəricisi OLMUR** — yəni "postuma baxın"
effekti alınmır. Trafik yönləndirmək lazımdırsa, çağırış şəklin ÜZƏRİNƏ yazılmalıdır.

Reallaşdırıldı:
* `instagram.share_post_to_story(media_id)` — `media_url` + `media_type` alır, story dərc edir.
* n8n: webhook-a `also_story: true` göndərsəniz, post dərc olunandan sonra eyni media
  avtomatik story kimi də paylaşılır. Cavabda hər ikisi qayıdır
  (`permalink` + `story_permalink`).

**n8n-də maraqlı həll:** story addımı üçün node təkrarlanmadı — workflow **öz webhook-una**
geri sorğu atır (`Story kimi paylaş` node-u), beləliklə sınanmış
konteyner→gözlə→statusYoxla→dərc zənciri olduğu kimi yenidən istifadə olunur. Sonsuz dövrə
riski yoxdur: ikinci çağırışda `media_type=STORIES` olur və `also_story` göndərilmir
(`Yoxla və hazırla` node-unda `mediaType !== 'STORIES'` şərti də var).

**Real test:** bir çağırışla post + story, 26.6 saniyə —
post `https://www.instagram.com/p/DcQgfrEjoxq/`,
story `https://www.instagram.com/stories/ai.gencythe1/3967814299569547639`.

**Texniki tələ:** `media_url` Instagram CDN-in **imzalı və müddəti bitən** ünvanıdır.
Dərhal yenidən paylaşım üçün işləyir, amma köhnə postu story-yə atmaq istəsəniz həmin URL
artıq ölü ola bilər — o halda media əvvəlcə öz proksimizdən keçirilməlidir.

**43. Token 60 gün etibarlıdır və YALNIZ BİR DƏFƏ göstərilir.** Yeniləmə:
`GET https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token&access_token=...`
Aylıq n8n Schedule Trigger ilə avtomatlaşdırıla bilər (hələ qurulmayıb).

## Vacib arxitektura qərarları / "niyə belədir"

- **SQLite avtomatik migrasiya etmir** — yeni sütun (`output_type`, `telegram_chat_id`,
  `notified`) əlavə edəndə köhnə `agency.db`-ni silib server-i yenidən başlatmaq lazımdır (demo
  layihə olduğu üçün məlumat itkisi qəbul edilir, bax [README.md](README.md)-dəki qeyd).
- **n8n JSON mənbə faylları** (`n8n_workflows/*.json`) əl ilə (ya linter ilə) canlı vəziyyətlə
  sinxron saxlanılır — dəyişiklik edəndə HƏM canlı n8n-də, HƏM bu fayllarda et.
- **`_call_llm()` provayder sırası: Groq → Gemini → HF.** 429-da dərhal keçid (retry yoxdur həmin
  provayderdə), yalnız 5xx/şəbəkə xətasında qısa backoff-la təkrar cəhd.
- **Kritik/QA fallback:** LLM cavab verməsə/JSON pozuqdursa → avtomatik `APPROVE`
  (`"(avtomatik təsdiq — QA cavabı alınmadı)"`) ki, axın dayanmasın.

## n8n UI-ni avtomatlaşdıranda öyrənilən dərslər (əgər yenidən lazım olsa)

- **Brauzer koordinat kalibrasiyası sessiyadan sessiyaya DƏYIŞIR** — screenshot ölçüsü ilə real
  səhifə ölçüsü arasında sabit nisbət YOXDUR, hər dəfə test klikləri ilə empirik yoxlamaq lazımdır
  (`document.addEventListener('click', ...)` ilə real koordinatı loqla, sonra nisbəti hesabla).
- **Azərbaycan xüsusi hərfləri (ə, ı, ş, ç, ö, ü) `computer.type()` ilə düzgün yazılmır** —
  onun əvəzinə: `element.focus()` + `document.execCommand('insertText', false, mətn)` (JS vasitəsilə).
  Clipboard API (`navigator.clipboard.writeText`) icazə xətası verir, işləmir.
- **n8n-in Fixed-input sahəsi "=" ilə başlayan mətn yazanda avtomatik "Expression" rejiminə
  keçir və mövcud məzmunu itirir** — ilk cəhddə boş qalır. Həll: iki mərhələdə et — əvvəlcə "="
  yazıb Expression rejiminə keçməsini gözlə, sonra YENİDƏN klikləyib əsl mətni (bu dəfə "="
  olmadan, artıq CodeMirror-dasan) daxil et.
- **n8n bu versiyada (2.27.4) "Active/Inactive" YOXDUR, "Publish/Unpublish" var** (n8n v2.0
  breaking change). Dəyişiklik etdikdən sonra Ctrl+S kifayət deyil — **Publish** də etmək lazımdır.
- **Birbaşa URL naviqasiyası (`navigate()`) n8n sessiyasını kəsir** (SPA-daxili keçid yox, tam
  reload) — yalnız daxili elementlərə klikləməklə (JS `element.click()` ilə) naviqasiya et.
- **Manual `fetch()` ilə n8n-in `/rest/*` API-sinə sorğu 401 qaytarır** (auth header/cookie
  fərqi bəlli olmadı) — bunun əvəzinə: real UI klikinin yaratdığı sorğunu
  `read_network_requests` ilə tutub oxu (bu, işlək və etibarlı üsuldur).
- **Telegram-ın hər bot üçün YALNIZ BİR webhook** icazəsi var — test/production URL arasında
  keçiddə diqqətli olun, Publish edəndə n8n avtomatik production URL-i qeydiyyatdan keçirir.

## n8n-i REST API ilə proqramlı redaktə edəndə öyrənilən dərslər (2-ci sessiya)

Brauzerdə n8n-ə giriş olunduqdan sonra `localStorage.getItem('n8n-browserId')`-i
`browser-id` header-i kimi göndərərək `/rest/workflows/{id}` (GET/PATCH) ilə node-ları
JS-dən birbaşa redaktə etmək mümkündür (UI-da klikləməkdən daha etibarlı).

- **`fetch('/rest/...')` sadə cookie ilə 401 qaytarır** — n8n sessiyanı `browser-id` header-inə
  bağlayır. Hər sorğuya `headers: {'browser-id': localStorage.getItem('n8n-browserId')}` əlavə et.
- **ƏN VACİB QÜSUR: aktiv workflow-a `PATCH` ilə edilən node dəyişiklikləri DB-də saxlanılır
  (GET dərhal düzgün göstərir), amma canlı trigger (schedule/webhook) HƏLƏ KÖHNƏ node-ları icra
  edir.** Sadə `PATCH {"active":false}` sonra `{"active":true}` KİFAYƏT ETMİR (server bu sahəni
  sükutla ignore edir, GET yenə `active:true` göstərir). **Düzgün ardıcıllıq:**
  1. `POST /rest/workflows/{id}/deactivate` (body yox)
  2. `GET /rest/workflows/{id}` → cari `versionId`-i al
  3. `POST /rest/workflows/{id}/activate` body: `{"versionId": "<addım 2-dəki id>"}`
  Bunu ETMƏSƏN, dəyişikliyin DB-də görünsə də icra zamanı işə düşmür (köhnə xəta təkrarlanır).
- Bu üsulla həm **Approval Notify** (`SA7ZRzGGVJ3PyfhJ`), həm **Telegram Commands**
  (`Wam8MF7p8DRkbYI9`) workflow-larının node-ları uğurla proqramla redaktə edildi (Code node
  JS-i, HTTP node parametrləri, Telegram node caption-u).
- Docker Desktop restart olanda n8n-in də restart olması brauzer sessiyasını sıfırlayır —
  yenidən `n8n-browserId`-i əldə etmək üçün istifadəçi yenidən sign-in etməlidir.

## Növbəti addımlar / könüllü təkmilləşdirmələr

- [ ] **Müştəri linkini (`/agency/{id}/view`) həqiqətən ictimai etmək** — port 8800-ü də ngrok
      (və ya başqa tunel) ilə açıb `.env`-də `PUBLIC_BASE_URL`-i yeniləmək. Hazırda bu link
      yalnız lokal şəbəkədə açılır, Telegram caption-unda göndərilsə də müştəri xaricdən aça
      bilməz.
- [ ] `AGENCY_API_KEY` aktivləşdirilsə, `static/agency.js` + bütün n8n HTTP node-larına
      `X-API-Key` header əlavə etmək lazımdır (hazırda edilməyib).
- [ ] Ngrok-u Windows başlanğıcında avtomatik işə salmaq (Task Scheduler və ya `nssm`).
- [ ] `n8n_workflows/*.json` mənbə fayllarının canlı n8n ilə tam sinxron olduğunu bir də yoxlamaq
      (hər ikisi paralel yenilənib, amma avtomatik diff yoxlanmayıb — xüsusilə `Rədd et` node-unun
      yeni `reason` body param-ı və Code node-un yeni regex-i mənbə JSON-larına köçürülməlidir).
- [ ] Test məlumatlarını (agency.db-dəki debug layihələr) təmizləmək istəyə bağlıdır.
- [ ] **Video-generasiya** (istifadəçi soruşdu, ertələndi) — pulsuz etibarlı API yoxdur, ödənişli
      servis (Runway/Luma) və async gözləmə məntiqi lazım olacaq. Konkret servis seçiləndə davam.
- [ ] **Real Instagram-a avtomatik paylaşım** (Meta Graph API) — təklif edildi, seçilmədi. Meta
      Developer hesabı + OAuth + uzun tətbiq təsdiq prosesi tələb edir.
- [ ] **Tam avtomatik müştəri çatdırılması** (email/telefon toplayıb birbaşa göndərmək) — B
      variantı kimi müzakirə edildi, hazırda A (paylaşıla bilən link) seçilib.

## Sürətli sınaq əmrləri (kopyala-yapışdır)

```bash
# Backend sağlamlıq
curl http://127.0.0.1:8800/health

# Ngrok tunel sağlamlığı
curl http://127.0.0.1:4040/api/tunnels

# n8n konteynerindən backend-ə çatma testi (production yol)
docker exec n8n wget -qO- http://host.docker.internal:8800/health

# Tam brif + run testi (output_type sınağı üçün brifi dəyişin)
curl -s -X POST http://127.0.0.1:8800/agency/brief -H "Content-Type: application/json" \
  -d '{"brief":"test brifi","telegram_chat_id":<TELEGRAM_CHAT_ID>}'
curl -s -X POST http://127.0.0.1:8800/agency/1/run
```

---

## Studio+ generasiya auditi (2026-08-21)

Tam audit sənədi: https://claude.ai/code/artifact/90d14f23-b51e-4bfd-a06e-8c6c07e4ce3f

**Əsas tapıntı:** `app/content_studio.py`-də heç bir LLM çağırışı YOXDUR. Modul generator deyil,
saxlama + önizləmə qatıdır. "Mənasız çıxış" şikayətinin səbəbi prompt deyil — məzmun sahələrinə
metadata yapışdırılmasıdır.

Tapıntılar (audit sənədində ID-lərlə):

| ID | Problem | Fayl | Status |
|----|---------|------|--------|
| SC-1 | `theme` sahəsinə `: {brand_products}` yapışdırılır, körpü onu caption-a köçürür | campaigns.py → web.py:311 | **BAĞLANDI (F1)** |
| SC-2 | `slides_json` yer tutucu təlimat saxlayır VƏ şablon onu heç oxumur (carousel adı 3 dəfə təkrarlayır) | content_studio.py:27 + content_studio.html | **BAĞLANDI (F0)** |
| SC-3 | `.visual-area` vizual brifi şəklin yerində göstərir | content_studio.html | **BAĞLANDI (F0)** |
| SC-4 | Brand Memory Studio+-da istifadə edilmir | content_studio.py | **BAĞLANDI (F3)** |
| SC-5 | `AssetReview.feedback` saxlanılır, heç bir kod oxumur | web.py | **BAĞLANDI (F5)** |
| SC-6 | Çıxış doğrulaması yoxdur | content_studio.py | **BAĞLANDI (F2)** |

**İcra sırası (qəsdən modelsizdən başlayır):**

- [x] **F0** — carousel `slides_json`-u oxusun, yer tutucu JSON silinsin, `.visual-area` brifi
      kreativ kimi göstərməsin. *(SC-2, SC-3 — bitdi)*
- [x] **F1** — `create_campaign` təmiz sahələr yazır (`theme=angle`), körpü caption-a `theme`
      köçürmür (`caption=day.cta`). Canlı bazada backfill: **150 plan günü + 9 DRAFT material**
      təmizləndi. Nüsxə: `agency.db.bak-sc1`. *(SC-1 — bitdi)*
      - Köhnə format `"{faza} · {bucaq}: {məhsul}"` idi (iki nöqtə ilə), `· məhsul` ilə deyil.
      - **1 APPROVED material** (id=1) hələ də köhnə caption daşıyır — qərara görə təsdiqlənmiş
        materiala toxunulmadı. İstənilsə əl ilə yenilənə bilər.
- [x] **F2** — `app/studio_ai.py:validate()`: sxem, sahə etiketi, yer tutucu, qadağan ifadə,
      uzunluq, **mənbəsiz rəqəm**. `NEEDS_INPUT` statusu əlavə olundu. *(SC-6 — bitdi)*
- [x] **F3** — `generate_draft()`: `STUDIO_SYSTEM`, JSON sxemi, `_call_llm(model_tier="nano")`,
      bir düzəliş cəhdi (`mini`, temperature 0.3), `usage_ctx` ötürülür. Brand Memory
      `brand_context_for_workspace()` ilə qoşuldu (razılıq yoxlanışı içindədir). *(SC-4 — bitdi)*
- [x] **F4** — bələdçili brif forması, 3 başlıq variantı (seçim marşrutu), 5 delta düyməsi,
      `needs_input` yoxlama siyahısı. Forma artıq caption/başlıq istəmir. *(bitdi)*
- [x] **F5** — `ContentAssetVersion` cədvəli; yenidən yazma köhnə nüsxəni arxivləyir;
      `APPROVED` materialın üstünə yazılmır; boş təlimatda son `CHANGES_REQUESTED` rəyi
      promptə ötürülür. *(SC-5 — bitdi)*

**Açıq qərarlar** (audit §08): köhnə materiallara toxunmamaq + "köhnə format" nişanı; model qatı
`nano`→`mini`; `facts` sahəsi məcburi olmasın amma boşdursa rəqəm/zəmanət tam qadağan +
`confidence: "low"`; `campaigns.py`-də `theme` → `angle` + `subject` ayrı sütunlar (ayrıca miqrasiya).

### Studio+ — bilməli olduqlarınız (F2–F5 sonrası)

- **Yeni fayl:** `app/studio_ai.py` — brif, prompt, doğrulama, generasiya. DB-yə toxunmur.
  Saxlama `app/content_studio.py`-dədir (`apply_result`, `archive_version`).
- **Yeni cədvəl:** `content_asset_versions`. Yeni sütunlar: `headline_options`, `hashtags`,
  `needs_input`, `confidence`, `brief_json`.
- **`no_network` fixture düzəldildi:** `studio_ai` `_call_llm`-i DƏYƏRLƏ import edir
  (`from app.agency import _call_llm`), ona görə `agency`-ni patch etmək kifayət etmirdi —
  testlər həqiqi OpenAI-a çıxırdı (429 ilə üzə çıxdı). İndi `studio_ai` ayrıca söndürülür.
  **Yeni modul `_call_llm` import edərsə, conftest-ə də əlavə edin.**
- **Təqvim körpüsü generasiya İŞLƏTMİR** — keçid ani olmalıdır. Gündən yalnız `brief_json`
  saxlanılır; istifadəçi Studio+-da «Yenidən yaz» ilə generasiyanı özü başladır.
- **Köhnə materiallar** `brief_json` saxlamır, ona görə yenidən yazıla bilmir — səhifə bunu
  açıq deyir. Yeni material yaratmaq lazımdır.

---

## Sistem geniş debug keçidi (2026-08-22)

Üsul: canlı serverdə real sessiya ilə bütün GET marşrutları, sonra POST-lar üçün pozulmuş
giriş və olmayan/yad resurs sınaqları, sonra çarpaz-workspace dağıdıcı əməliyyat cəhdləri.

**Tapılan və bağlanan iki qüsur:**

| ID | Problem | Fayl | Ciddilik |
|----|---------|------|----------|
| CAMP-1 | `/campaigns?id=X` tapılmayan id-də səssizcə BAŞQA kampaniyanı açırdı; müddət formasının `action`-ı ona bağlandığı üçün «Tətbiq et» səhv kampaniyanın günlərini silirdi | web.py `campaigns_page` | **Yüksək — məlumat itkisi** |
| STUDIO-1 | `POST /content-studio` naməlum `format` dəyərində 500 verirdi (`create_asset` `ValueError` atır, marşrut tutmurdu) | studio_ai.py `brief_from_form` | Orta |
| IMG-1 | Şəkil proksisi `User-Agent` göndərmirdi; Wikimedia UA-sız sorğunu 403 ilə rədd edir, ona görə Wikimedia-dan seçilmiş hər şəkil əbədi 502 verirdi | api.py `_image_bytes` | Orta — 2 layihə |

CAMP-1 Studio-dakı RC-3-ün eyni sinfidir — orada bağlanmışdı, kampaniyalarda qalmışdı.
Bu sinif üçün ümumi qayda: **konkret id istənilibsə və tapılmayıbsa, əvəzinə başqasını
göstərmə.** Yeni səhifə əlavə edəndə bunu yoxlayın.

**Təmiz çıxan sahələr** (sınandı, qüsur tapılmadı):
- Çarpaz-workspace: yad istifadəçi nə kampaniyanı qısalda, nə günü materiala çevirə bilir.
- Olmayan resurslara POST (`/campaigns/999999/duration`, `/content-studio/999999/*`,
  `/calendar/999999/status`, `/sales/999999/status`) — hamısı 303, çökmə yoxdur.
- Export/agency marşrutları yad id ilə — 404/401.
- `analytics/metrics` zibil girişlə, `brand-kit` `javascript:` loqo ilə — 303/400.
- `except:` (çılpaq tutuş) kod bazasında ümumiyyətlə yoxdur.

**Qeyd:** `/config` 404 verir, amma bu xəta deyil — `voice_api` router-i `/voice` prefiksindədir,
düzgün ünvan `/voice/config`.

**Test məlumatı:** yoxlama zamanı yaradılmış 11 istifadəçi, 10 workspace, 5 kampaniya və
58 plan günü bazadan təmizləndi. Nüsxə: `agency.db.bak-before-cleanup`.
Qalan: 5 real istifadəçi, 6 kampaniya, 13 material.

**IMG-1 haqqında:** uyğunsuzluq idi — `stock_photos` Wikimedia-da AXTARARKƏN UA göndərir
(`stock_photos.py:116`), tapılan şəkli YÜKLƏYƏN proksi isə göndərmirdi. Canlı ölçmə:
UA-sız `403` (126 bayt) · UA ilə `200` (51806 bayt). Düzəlişdən sonra `/agency/12/image`
**502 → 200**. Ortaq sabit: `app/core.py:HTTP_USER_AGENT`. Yeni uzaq şəkil yükləyən kod
yazanda onu istifadə edin.
Şəkil mənbələri: pollinations 13 · pexels 19 · **wikimedia 2** (təsirlənən layihələr).

**Yeni testlər:** `tests/test_regressions.py` (10 test) — hər ikisinin qoruyucusu, üstəgəl
çarpaz-workspace davranışının təsbiti. **Cəmi 166 test keçir.**

---

## LUMÉA yol xəritəsinin icrası (2026-08-22)

Yol xəritəsi: https://claude.ai/code/artifact/b4a6a071-ccd9-4a80-af0d-3e6c60cf4850
**204 test keçir.**

### İcra olunanlar

| # | İş | Fayl |
|---|----|------|
| 6 | Workspace adı `Kətan` → `LUMÉA Skin`; Brand Kit-ə **ad sahəsi** əlavə edildi (əvvəl ad yalnız qeydiyyatda yazılırdı) | web.py, brand_kit.html |
| 9 | **Terminologiya lüğəti** (`Workspace.brand_glossary`) — «səhv → düzgün» cütləri; həm prompta, həm doğrulamaya. Sübutsuz iddia nümunə yoxlaması (`bərpa ed…`, `müalicə ed…`) | compliance.py |
| 10 | Doğrulama **ortaq qata** çıxarıldı (`app/compliance.py`) və agent rollarına da tətbiq olundu; qadağan ifadə artıq **kök üzrə** tutulur («möcüzəvi nəticə» → «möcüzəvi effekt» də) | compliance.py, agency.py |
| 8 | **Palitra doğrulaması** — brend rəngindən kənar söz və HEX rədd olunur | studio_ai.py |
| 5 | `brand_products` artıq **təsdiqlənmiş fakt mənbəyidir** — Brand Kit-dəki təklif rəqəmi uydurma sayılmır | studio_ai.py |
| 4 | **Platforma imkanları cədvəli** — format platformaya uyğunlaşdırılır; TikTok yalnız Reel, LinkedIn Story almır | campaigns.py |
| 7 | Materiallara **avtomatik şəkil** — mövcud `find_stock_photo`/`_pollinations_url` zənciri qoşuldu (yeni provayder lazım olmadı) | content_studio.py |
| 3 | Kampaniya planına **hibrid LLM qatı** — faza bölgüsü determinist, gün mətnləri modeldən; fazaya bir çağırış; uğursuzluqda şablon qalır | campaign_ai.py |
| 2 | Layihə bitəndə **kampaniya qaralaması** — `DRAFT` statusu, təqvimdə görünmür, `source_project_id` ilə idempotent | agency.py |
| 1 | **Brand Kit təklif axını** — `BrandKitSuggestion` cədvəli; avtomatik YAZILMIR, istifadəçi qəbul edir; rəng/loqo/qadağan ifadələr təklif oluna bilmir | brand_sync.py |

### Sizin qərarınızı gözləyən

- [ ] **`brand_ai_consent` bayrağı hələ `False`** — Brand Kit HEÇ BİR prompta düşmür.
      `agency.py:brand_context_for_workspace` orada kəsir. 3, 5, 8, 9 maddələrinin
      nəticəsi bu bayraqdan asılıdır. Bu, məxfilik razılığıdır — Brand Kit səhifəsindəki qutu.
- [ ] **Terminologiya lüğəti boşdur.** «baryer» yazılışı Brand Kit-in ÖZÜNDƏDİR
      (`brand_products`), model onu köçürür. Hansı formanın düzgün olduğu sizin qərarınızdır;
      `baryer -> bariyer` sətri kifayətdir.
- [ ] **6 gün hələ platforma-format uyğunsuzdur** — hamısı TikTok + Story/Carousel/Post,
      statusu `IN_REVIEW` və hər birinin DRAFT materialı var. Miqrasiya qəsdən yalnız
      `PLANNED` günlərə toxundu. Siyahı: Sentyabr growth g3, g18 · Payız Kolleksiyası g6, g30 ·
      LUMÉA Skin · Barrier R g2, g6.

### Arxitektura qeydləri

- **`app/compliance.py` saf datadır** — nə DB, nə ORM, nə şəbəkə. `ComplianceRules`
  dondurulmuşdur və işçi thread-lərə təhlükəsiz ötürülür. Qaydalar ƏSAS THREAD-də
  `rules_from_workspace()` ilə çıxarılır.
- **Razılıq qapısının məntiqi:** brend məlumatı PROMPTA yalnız razılıqla düşür; LOKAL
  doğrulama razılıqdan asılı deyil, çünki heç nə kənara göndərmir. Test bunu qoruyur.
- **Dəyərlə import tələsi üçüncü dəfə üzə çıxdı** — `content_studio` `find_stock_photo`-nu
  dəyərlə import etmişdi və test həqiqi Pexels sorğusu etdi. İndi modul üzərindən çağırılır
  və conftest mənbə modulu söndürür. **Yeni kod `from x import name` yerinə `from app import x`
  işlətsin, əks halda test şəbəkəyə çıxır.**
- **Yalan pozitiv düzəlişi:** yer tutucu nümunəsindən «yazın» və «seçin» çıxarıldı —
  «Şərhdə yazın» ən adi CTA-dır və hər düzgün mətn rədd olunurdu.

Baza nüsxələri: `agency.db.bak-lumea` (bu işdən əvvəl), `agency.db.bak-sc1`, `agency.db.bak-before-cleanup`.

### Canlı yoxlama zamanı tapılan qüsur (2026-08-22)

**KANAL AÇLIĞI** — `assign_platform` əvvəl sadə növbə işlədirdi (`(gün-1) % kanal_sayı`).
Instagram bütün formatları qəbul etdiyi üçün növbəni udurdu:

```
Instagram + TikTok · 14 gün  ->  TikTok 0 gün   ← istifadəçi kanalı seçib, planda yoxdur
Instagram + TikTok · 30 gün  ->  TikTok 2 gün
```

İndi hər gün üçün formatı dəstəkləyən kanallardan **ən az yüklənmişi** seçilir:

```
Instagram + TikTok · 14 gün  ->  Instagram 12, TikTok 2   (plandakı bütün Reel günləri)
Instagram + TikTok · 30 gün  ->  Instagram 23, TikTok 7
TikTok + LinkedIn  · 30 gün  ->  TikTok 14, LinkedIn 16
```

`resize_campaign` uzatma zamanı mövcud günlərin yükünü nəzərə alır. Qoruyucu testlər:
`test_no_selected_channel_is_ever_starved`, `test_tiktok_gets_a_real_share_of_the_video_days`,
`test_extension_does_not_break_the_balance`. **Cəmi 207 test keçir.**

**Qeyd — test səhvi:** ilk yazdığım test «TikTok BÜTÜN Reel günlərini alsın» tələb edirdi.
Kod 8-dən 7-sini verdi, çünki yük bərabərləşəndə növbəti Reel Instagram-a keçir — bu,
balansın işlədiyini göstərir, qüsur deyil. Test zəiflədildi, kod yox.

### Kampaniya zənginləşdirməsi — canlı nəticə

14 günlük kampaniya **5 saniyədə** yarandı (faza başına bir çağırış). Nəticə şablondan
tamamilə fərqlidir və auditoriyaya xasdır; model hətta hook-ları platformaya uyğunlaşdırır
(«TikTokda dərini…», «TikTok videolarında…»). **Bu, `brand_ai_consent` HƏLƏ BAĞLI ikən
əldə olunub** — kampaniya girişi (ad, məqsəd, auditoriya) istifadəçinin öz məlumatıdır,
razılıq isə Brand Kit-ə aiddir.

---

## Sahibin göstərişi ilə edilənlər (2026-08-22)

İstifadəçi «hər birini özün et» dedi. Üç bənd icra olundu:

1. **`brand_ai_consent = True`** (workspace 1). Bu, məxfilik razılığıdır və sahibin
   açıq göstərişi ilə edildi. Brand Kit artıq bütün promptlara düşür.
2. **Terminologiya:** `brand_glossary = 'baryer -> bariyer'`. Mənbə mətni də düzəldildi —
   `brand_products` sahəsindəki «baryer» → «bariyer». Forma istifadəçinin ilkin
   siyahısından götürüldü, dil qərarı bizim deyil.
3. **6 uyğunsuz gün düzəldildi** (hamısı TikTok + Story/Carousel/Post → Reel). Hər birinin
   materialı da yeniləndi (format + aspect_ratio), köhnə nüsxələr `ContentAssetVersion`-a
   **arxivləndi** — geri qaytarıla bilir. Materiallar: #8, #10, #14, #15, #17, #21.

Nüsxə: `agency.db.bak-before-owner-actions`.

### Razılıq açılan kimi üzə çıxan iki qüsur

**A · Qadağan siyahısının parsinqi (ciddi).** LUMÉA siyahını BİR SƏTİRDƏ vergüllə yazmışdı.
Parser yalnız sətir sonuna görə bölürdü, ona görə bütün siyahı bir «ifadə» olurdu:

```
«möcüzəvi nəticə»  → TƏMİZ keçirdi        (açıq qadağan ifadə!)
«problemlərini» olan adi cümlə → BLOKLANIRDI  (yalan pozitiv)
```

Səbəb: kök üzrə tutuş ən uzun sözü seçirdi — «problemlərini». İndi `split_phrases()`
vergül/nöqtəli vergülə də bölür, kök üzrə tutuş isə YALNIZ 2 sözlük ifadələrə tətbiq olunur
(uzun təsvirlər tam uyğunluq tələb edir). Nəticə: 1 ifadə → 6 ifadə.

**B · Palitra yoxlamasının kalibrasiyası.** Model açıq fil sümüyünü «yumşaq ağ» adlandırdı
və düzgün çıxış `NEEDS_INPUT`-a düşdü. `ağ`/`qara` neytraldır və demək olar hər palitra
təsvirində olur; şikayətin mövzusu MAVİ idi. Neytrallar siyahıdan çıxarıldı, xromatik
rənglər və HEX yoxlaması qaldı.

**C · `confidence` məntiqi.** Yalnız forma sahəsinə baxırdı, ona görə Brand Kit-dəki
təsdiqlənmiş təkliflə yazılan material da «aşağı etibar» alırdı. İndi faktın OLMASINA baxır,
haradan gəldiyinə yox.

### Canlı nəticə (razılıq açıq, real model)

3 ardıcıl generasiya, **3-ü də uğurlu, hamısı `confidence: high`**:

```
başlıq : Barrier Restore Serum: Dəri bariyerinizi gücləndirin      ← «bariyer» düzgün
palitra: #F4EFE6 fil sümüyü, #D8C7AD isti bej, #3B2A22 tünd qəhvəyi, #B89A62 zəif qızılı
caption: «İlk 100 ön sifarişə 15 % endirim» — rədd EDİLMİR (Brand Kit faktdır)
needs_input: []
```

**Cəmi 216 test keçir.**

---

## Telefon satış agenti — ayrıca layihə, EYNİ CRM-ə yazır (2026-09-05)

**Qovluq:** `MainLessons/CallCenterAI` (ayrıca FastAPI tətbiqi, port 6060).
Bu, `app/voice_agent.py`-dən FƏRQLİ şeydir: voice_agent brauzerdə **gələn** danışıqdır,
bu isə real telefon xətti ilə **gedən** satış zəngidir.

**Nə edir:** `sales_leads`-dən lead götürür → Twilio ilə real zəng edir → OpenAI Realtime
API (`gpt-realtime`) azərbaycanca danışır → e-poçt ardıcıllığının (INITIAL/FOLLOW_UP)
davamı kimi özünü təqdim edir → məqsəd: 20 dəqiqəlik onlayn **görüş təyin etmək**.

**The Agency-yə toxunuşu — YALNIZ iki cədvəl** (`CallCenterAI/crm.py`, birbaşa SQLite):
- `sales_activities`-ə `activity_type='CALL'` sətri (mövzu = nəticə, məzmun = danışıq mətni)
- `sales_leads.status` → `MEETING` / `NOT_INTERESTED` / `CALLBACK` / `CONTACTED`
  və `notes`-a bir sətir (görüş vaxtı, geri zəng vaxtı, imtina səbəbi)

Status dəyərləri qəsdən `outbound.py`-dəki email axını ilə eynidir — bir lead-in email və
zəng tarixçəsi bir yerdə oxunur. **Backend-də (8800) heç bir dəyişiklik edilməyib**, yeni
endpoint və ya migrasiya yoxdur; The Agency işləmirsə də zəng agenti işləyir (SQLite faylı
birbaşa oxunur, WAL rejimi paralel girişə imkan verir).

**Bilinməli məhdudiyyətlər:**
- Twilio hesabı **trial**-dır: yalnız təsdiqlənmiş nömrəyə zəng gedir və zəngin əvvəlində
  Twilio-nun ingiliscə xəbərdarlığı oxunur. Real lead-lərə zəng üçün upgrade lazımdır.
- CRM-dəki nömrələrin bir hissəsi E.164 deyil (`+0709650324` kimi) — Twilio onları rədd edir,
  `/call` bunu 400 ilə aydın qaytarır.
- **Hüquqi:** lead-lər OpenStreetMap-dən yığılıb, razılıq verməyiblər. Razılığı olmayan
  nömrəyə avtomatik zəng bir çox yurisdiksiyada qadağandır — panel bu barədə xəbərdarlıq
  göstərir və hər zəng ayrıca təsdiq tələb edir.

## Telegram `/brief` işləmirdi — tək ngrok domeni iki xidmət arasında bölünür (2026-09-11)

**Simptom.** Telegram-da `demobot_bot`-a `/brief ...` yazılırdı, HEÇ NƏ olmurdu: nə cavab,
nə yeni layihə. n8n-də həmin workflow-un icra tarixçəsi TAMAM BOŞ idi.

**Kök səbəb (ngrok inspect jurnalı ilə sübut olundu).** Pulsuz ngrok planında bir statik
domen var — `cursor-eleven-preteen.ngrok-free.dev`. n8n-in Telegram trigger-i öz webhook-unu
Telegram-da MƏHZ bu domenlə qeydiyyatdan keçirib (`WEBHOOK_URL` konteyner dəyişəni). Lakin
Twilio səsli demosu üçün tunel 5678 (n8n) əvəzinə 8800 (bu FastAPI tətbiqi) portuna
yönəldilmişdi. Nəticədə:

```
23:46:34  POST /webhook/agency-telegram-webhook/webhook -> 404   (Telegram 8 dəfə təkrar etdi)
```

Telegram mesajı çatdırırdı, ngrok onu FastAPI-yə verirdi, FastAPI belə route tanımadığı üçün
404 qaytarırdı və n8n heç vaxt xəbər tutmurdu.

**Həll — `app/n8n_proxy.py` (yeni).** Tunel 8800-də QALIR (Twilio işləyir), tətbiq isə
`/webhook`, `/webhook-test`, `/webhook-waiting` ilə başlayan istəkləri olduğu kimi lokal
n8n-ə ötürür. Beləliklə tək domen hər iki xidmətə xidmət edir; n8n-i yenidən qurmaq və ya
Telegram webhook-unu yenidən qeydiyyatdan keçirmək lazım gəlmir.

- `N8N_INTERNAL_URL` (yeni parametr, `app/core.py`) boş qalsa proxy route-ları HEÇ
  qeydiyyatdan keçmir — bulud serverində n8n olmadığı üçün orada boş saxlanılır.
- n8n-in idarəetmə API-si (`/rest/...`) QƏSDƏN ötürülmür, yoxsa tunel n8n-i tam açardı.
- Hər prefiks üçün ayrıca route var; `/{prefix}/{path}` şəklində tutan tək route yazsaq,
  tətbiqin bütün digər səhifələrini kölgələyərdi.

**Yoxlama.** `POST https://cursor-eleven-preteen.ngrok-free.dev/webhook/agency-telegram-webhook/webhook`
əvvəl `404` qaytarırdı, indi `403` — yəni istək artıq n8n-ə çatır (403-ü n8n-in öz Telegram
trigger-i verir, çünki sınaq istəyində düzgün `secret_token` yoxdur; əsl Telegram istəkləri
onu göndərir). 244 test keçir.

**Diqqət: n8n-də TƏKRAR workflow-lar var.** Eyni adlı ikişər nüsxə mövcuddur və `active`
olanlar repo-dakı JSON-lardan FƏRQLİ ID-lərdir:

| Ad | Aktiv ID | Passiv (repo JSON) ID |
|---|---|---|
| The Agency — Approval Notify | `SA7ZRzGGVJ3PyfhJ` | `RGIOAck1FeRXfTkm` |
| The Agency — Telegram Commands | `Wam8MF7p8DRkbYI9` | `zx2ONbRIaantoWgF` |

Debug edərkən YANLIŞ nüsxəyə baxmaq asandır — əvvəlcə `docker exec n8n n8n list:workflow`
və `workflow_entity.active` yoxlanmalıdır.

**Hələ də açıq (kosmetik).** Aktiv "Approval Notify" hər dəqiqə xəta verir: təsdiq gözləyən
layihə olmayanda `/agency/pending-approval` `204 No Content` qaytarır, n8n-in HTTP node-u isə
boş gövdədə çökür (`Cannot read properties of undefined (reading 'data')`). Bildirişin özü
işləyir (gözləyən layihə olanda 200 + JSON gəlir) — bu sadəcə icra tarixçəsini qırmızı
xətalarla doldurur.

### Davamı: `/tesdiq` işləmirdi — Telegram əmr linkinə toxunanda ID İTİR (2026-09-12)

Webhook körpüsündən sonra `/brief` işlədi (layihə #39 yarandı), amma `/tesdiq` "Not Found"
xətası verdi. n8n icra məlumatında istəyin URL-i belə idi:

```
http://host.docker.internal:8800/agency//approve      <-- id boş!
```

**Səbəb.** Bildiriş mesajı `✅ Təsdiq: /tesdiq 38` şəklində göndərilirdi. Telegram `/tesdiq`
hissəsini klikilə bilən ƏMR linkinə çevirir, `38` isə ADİ MƏTN olaraq qalır — istifadəçi
əmrə toxunanda Telegram yalnız `/tesdiq` göndərir və rəqəm itir. Parser `parseInt('')` → `NaN`
alırdı, `NaN` JSON-da `null` olurdu, URL-də isə boş sətrə çevrilirdi.

**Həll (iki hissə).**
1. **Bildiriş mesajı** artıq `/tesdiq_39` və `/redd_39` yazır — alt xətt əmrin ÖZ hissəsidir,
   ona görə toxunanda ID də birlikdə göndərilir (Telegram-ın standart `/command_id` qaydası).
2. **Parser** (`Əmri təhlil et`) yenidən yazıldı: `/tesdiq_39`, `/tesdiq 39`, `/təsdiq_39`,
   `/tesdiq_39@demobot_bot`, `/redd_39 səbəb mətni` — hamısı işləyir. ID tapılmasa artıq
   qırmızı xəta vermir, səssiz dayanır. Boş `/brief` də məzmunsuz layihə yaratmır.

**Yoxlama.** Parser JS-i n8n konteynerinin `node`-u ilə 11 nümunə əmr üzərində ayrıca
sınaqdan keçirildi (icazəsiz chat ID daxil) — hamısı gözlənilən nəticəni verdi.

**Dəyişikliyi canlıya tətbiq etmək (CLI yolu, brauzer lazım deyil).**
```
docker exec n8n n8n export:workflow --id=<ID> --output=/tmp/wf.json
# JSON redaktə olunur, geri kopyalanır
docker exec n8n n8n import:workflow --input=/tmp/wf_new.json
docker exec n8n n8n update:workflow --id=<ID> --active=true
docker restart n8n            # TRIGGER-LƏR YALNIZ BUNDAN SONRA YENİ KODU İCRA EDİR
```
**DİQQƏT:** `import:workflow` workflow-u avtomatik DEAKTİV edir ("Deactivating workflow ...")
və n8n işləyərkən edilən dəyişikliklər canlı trigger-ə təsir etmir — `update:workflow
--active=true` + `docker restart n8n` MÜTLƏQDİR. (Bu, 2-ci sessiyada REST API ilə tapılan
eyni qüsurun CLI qarşılığıdır.)

`n8n_workflows/1_*.json` və `2_*.json` mənbə faylları da eyni dəyişikliklə sinxronlaşdırıldı.

## Control Room: tapılan lead-lər səhər hesabatında görünür (2026-09-12)

**İstək.** "Səhər hesabatları" paneli yalnız RƏQƏM deyirdi (`15 tapıldı, 0 yeni lead`).
Təqdimat zamanı biznesin ADI lazımdır və ondan birbaşa outreach bölməsinə keçmək istənilir.

**Nə edildi.** Panel 06 indi üç hissədən ibarətdir:
1. **Sayğaclar** — bazadakı ümumi lead, audit edilmiş lead, hazırlanmış mesaj draftı sayı.
2. **Tapılan bizneslər** — ən son 12 lead, hər biri `/sales/{id}`-ə bağlıdır (klikləyəndə
   audit + təklif + outreach səhifəsi açılır). Hər sətirdə bal, kateqoriya, şəhər və
   `AUDİT` / `OUTREACH` nişanları var.
3. **Gecə hesabatları** — əvvəlki mətn sətirləri (dəyişməyib).

Kod: `app/web.py` → `_night_lead_rows()`, `_lead_stats()`; `templates/control_room.html`
panel 06; `static/control-room-space.css` → `.cr-leads`, `.cr-lead*`, `.cr-reportbox`.

**Yol boyu düzəlmiş layout qüsuru.** `.cr-panel` iki sütunlu qriddir və BİRBAŞA uşaq
elementləri avtomatik yerləşdirir. Panel 06-nın bir neçə `.cr-log` uşağı olduğu üçün
hesabatlar sütunlar arasında ZİQZAQ düzülürdü (ekran görüntüsündə açıq görünürdü). İndi bütün
məzmun tək `.cr-reportbox` qutusundadır — 12 sətrin hamısı eyni `x` koordinatındadır (brauzerdə
ölçülüb yoxlanıldı), üfüqi sürüşmə yoxdur.

**Qeyd — "0 yeni lead" səhv deyil.** Hesabat `15 tapıldı, 0 yeni lead` yazırsa, deməli həmin
15 biznes artıq bazadadır (`uq_workspace_sales_lead_source` təkrarın qarşısını alır). Hazırda
bazada **158 lead** var; panel bunu açıq göstərir.

### Yan tapıntı: Veo günlük limiti gecə saat 00:00-04:00 arası İŞLƏMİRDİ

Test dəsti gecə yarısı keçəndən sonra qəflətən iki testdə uğursuz oldu (`test_veo_budget_reports_cost`,
`test_veo_stops_at_the_daily_limit`). Səbəb kodda idi, testdə yox:

`VeoUsage.created_at` bazaya `func.now()` ilə **UTC** yazılır, `used_today()` isə `date.today()`
(serverin **yerli** tarixi) ilə müqayisə edirdi. Bakı UTC+4 olduğuna görə gecə 00:00-04:00 arası
yerli tarix UTC-dən bir gün qabaqdadır — `start` gələcəkdə qalır, sayğac **sıfır** qaytarır.
Nəticə: həmin dörd saat ərzində günlük limit yoxlaması tamamilə keçərsiz idi və xərc az
göstərilirdi (Veo ödənişlidir — real pul riski).

Düzəliş (`app/veo.py`): Bakı gününün başlanğıcı hesablanıb UTC-yə çevrilir, müqayisə saxlanma
formatı ilə eyni zolaqda aparılır. 244 test yenidən keçir.

## Kampaniya videoları sıxıldı — 64 saniyədən 2 saniyəyə (2026-09-12)

**Problem.** `static/media/campaigns/scene-01.mp4` **4K (3840×2160), 16.4 Mbit/s, 20.5 MB** idi.
Serverin ötürmə sürəti ölçüldü: **~318 KB/s** — yəni hero videosu ~64 saniyəyə yüklənirdi və
"Kampaniyalar" bölməsində heç bir irəliləyiş görünmürdü. (Fayllarda `moov` atomu artıq öndə
idi, yəni faststart problemi YOX idi — sırf zolaq genişliyi.)

**Həll.** `imageio-ffmpeg` (venv-ə quraşdırıldı, sistem PATH-ına toxunulmadı) ilə yenidən
kodlaşdırma: 1920×1080, H.264 High, CRF 27, maxrate 2.2 Mbit/s, səssiz (`-an`), `+faststart`.

| Fayl | Əvvəl | İndi |
|---|---|---|
| scene-01.mp4 | 20.5 MB | 2.2 MB |
| scene-02.mp4 | 5.8 MB | 1.8 MB |
| scene-03.mp4 | 6.8 MB | 2.8 MB |

Orijinal 4K fayllar `media-source/campaigns/` qovluğunda saxlanılır (bu qovluq `static`-dən
KƏNARDIR, yəni web-ə verilmir və Docker image-ə düşmür).

**Əlavə: poster kadrı.** Hər səhnə üçün ≈30 KB JPEG çıxarıldı (`scene-0N.jpg`). `<video>`-nun
`poster=""` atributu BOŞ idi — indi doldurulub və `static/campaign-production.js` səhnə
dəyişəndə posteri də dəyişir. Nəticədə ekran heç vaxt boş qalmır.

**Ölçülmüş nəticə (buludda, canlı).**
```
scene-01.mp4  2 223 853 B   2.10 s   (1 057 KB/s)     <- əvvəl ~64 s
scene-01.jpg     28 059 B   0.41 s
```
### ƏSL SƏBƏB: DigitalOcean məhdudiyyəti DEYİL — tək TCP axını + uzaq məsafə

Əvvəlki ehtimal ("yeni DO hesabına egress limiti qoyulub") SƏHV ÇIXDI. Həlledici ölçmə:

| Ölçmə | Sürət |
|---|---|
| SCP (xam SSH, HTTP-dən tam kənar), 20 MB | 145 KB/s |
| HTTPS, tək axın | ~800 KB/s |
| **HTTPS, 4 paralel axın (cəmi)** | **2.9 MB/s** |
| Bu mühitin öz interneti (Cloudflare) | 9.2 MB/s |

4 paralel axın cəmdə 2.9 MB/s verirsə, serverdə **sərt egress limiti YOXDUR** — məhdudiyyət
HƏR BİR BAĞLANTIYA aiddir. Səbəb: droplet `fra1` (Frankfurt) regionundadır, RTT ≈ **96 ms**.
Belə uzun gecikmədə tək TCP bağlantısı pəncərə ölçüsü (bandwidth×delay product) ilə məhdudlaşır
və kiçik paket itkisinə çox həssasdır. Brauzer isə videonu **tək** HTTP bağlantısı ilə çəkir —
buna görə 20 MB-lıq fayl onlarla saniyə çəkirdi.

SCP-nin 145 KB/s göstərməsi də yanıldıcı idi: SSH-ın öz daxili kanal pəncərəsi var və yüksək
gecikmədə xüsusilə pis işləyir — bu sual üçün ƏN PİS ölçü aləti idi.

Serverdə yoxlanıldı: `tc` trafik formalaşdırması yoxdur (yalnız defolt `fq_codel`), interfeysdə
xəta/drop sıfırdır, yük ~0. Yəni DigitalOcean-ın şəbəkə hesabatına baxmağa ehtiyac yoxdur.

**Nəticə:** faylı kiçiltmək təkcə "köməkçi tədbir" deyil, məhz DÜZGÜN həll idi. Gələcəkdə
media daha da sürətli lazım olsa, düzgün addım CDN-dir (Bakıya yaxın edge), serveri böyütmək yox.

### Buluda yerləşdirmə qaydası (bu sessiyada istifadə olunan)
```
tar --exclude=.venv --exclude=media-source --exclude=__pycache__ --exclude=.env \
    --exclude='agency.db*' -czf /tmp/deploy.tar.gz app templates static main.py ...
scp -i ~/.ssh/aigency_deploy /tmp/deploy.tar.gz root@<DROPLET_IP>:/tmp/
ssh ... "cd /opt/aigency && tar -xzf /tmp/deploy.tar.gz -C /opt/aigency && docker build -t aigency:new .
         docker tag aigency:new aigency:latest && docker rm -f aigency
         docker run -d --name aigency --restart unless-stopped --env-file /opt/aigency/.env \
           -p 127.0.0.1:8800:8800 -v /opt/aigency/data:/app/data aigency:latest"
```
`.env` və `agency.db` QƏSDƏN köçürülmür — server öz `.env`-ini saxlayır, baza isə host-da
(`/opt/aigency/data`) bind mount ilə yaşayır, ona görə image yenilənəndə itmir.
