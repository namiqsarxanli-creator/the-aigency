# The Aigency

**An autonomous AI creative agency: a text brief spawns a simulated company of AI agents that plan,
write, design, build, sell and review the work, live on screen, with a human approving the result.**

🇦🇿 [Azərbaycan dilində](README.az.md)

Give it a brief, for example *"launch campaign for an eco-friendly coffee brand"*:

1. A **CEO agent** splits the brief into tasks.
2. The **creative department runs in sequence:** Strategist → Copywriter → Designer → Developer.
3. **Support departments run in parallel:** Sales, Outreach, Marketing, Analytics.
4. A **QA / Critic agent** gates every output: it approves it, or sends it back for revision.
5. The whole process streams to a live **WebSocket Kanban board**.
6. The final deliverable, a landing page or a social post, waits for **human approval**.

## What's inside

### Agent orchestration
- **State machine:** `BRIEF → IN_PROGRESS → REVIEW → AWAITING_APPROVAL → APPROVED/REJECTED`.
- **Bounded revision loop:** at most 2 revisions, so there's no infinite critic loop.
- **Autonomous background loop:** projects created from Telegram or the voice agent finish without
  anyone pressing "run".
- **Per-project async locks:** these fixed a real race between manual runs and the background loop.
- **Partial re-runs:** a single department can be regenerated, and previous versions are archived.
- **3-provider LLM failover:** Groq → Gemini → Hugging Face, all through the OpenAI-compatible API. On
  a 429 it switches immediately, because waiting doesn't reset per-minute quotas.
- **Token and cost telemetry** per provider and per role (`/usage`), answering *"which department is
  eating the quota?"*

### Voice AI
- **Browser voice receptionist** that speaks Azerbaijani:
  - it explains the service, takes a brief and creates a project, or captures a lead for a callback
  - its action space is deliberately narrow (`create_brief`, `capture_lead`, `handoff`) and contains
    nothing irreversible
- **Outbound sales calls** via **Twilio + OpenAI Realtime**:
  - a persona-driven pitch
  - context taken from the CRM lead record
  - a one-click call from the Control Room

### Sales engine
- **Lead discovery** from public map data (OpenStreetMap), with deterministic lead scoring.
- **Automated website audit** of each lead, then a proposal, an outreach sequence and a meeting brief.
- **Night-shift worker** that produces leads on a schedule.
- **Human-approved e-mail outbox:** without SMTP credentials, it runs in a safe no-send mode.

### Content & publishing
- **Campaign generator** built on a persuasion arc: attention → value → trust → offer → close. Longer
  campaigns *stretch* the arc instead of repeating it.
- **Content Studio:** structured drafts for posts, stories and carousels.
- **Media generation:** images with OpenAI; video with Sora / Veo, which is **off by default**
  because it's paid.
- **Publishing:** Instagram Graph API (posts + Reels), TikTok Content Posting API (per-user OAuth),
  Buffer.
- **Brand Kit with a shared compliance checker:** banned phrases and terminology are checked in every
  generation path. Brand updates from project output are *proposed for approval*, never written
  silently.
- **Client hand-off package:** a print-ready PDF report and a ZIP export.

### Platform
- **Multi-tenant workspaces:** owner/admin/presenter roles, server-side sessions, workspace
  isolation tests.
- **Automation key:** n8n-facing routes are protected by an API key, and n8n handles Telegram
  notifications and commands (`/brief`, `/tesdiq <id>`, `/redd <id>`).
- **Production profile:**
  - FastAPI web + **Celery** worker + beat + **PostgreSQL** + **Redis**, with Docker Compose
  - the app refuses to start with an unsafe production config
- **Local mode:** SQLite + an embedded worker, with an online-backup script.

## Tests

```bash
pytest
```

**244 tests**, all **network-mocked** (LLM, image search and telephony), so they burn no quota and pass
offline. They cover:

- workspace isolation and the security boundary
- the pipeline state machine
- regeneration and versioning
- usage tracking
- export
- prompt hygiene
- voice-agent scheduling
- lead finding and sales audits
- campaigns, social add-ons and regressions

## Run it

```bash
python -m venv .venv
```

```bash
.venv\Scripts\activate
```

```bash
pip install -r requirements.txt
```

```bash
uvicorn main:app --reload --port 8800
```

Then open http://localhost:8800. Copy `.env.example` to `.env` and set at least a free Groq key. Without
any key the pipeline still runs on fallback text. For the production stack, see
[PRODUCTION.md](PRODUCTION.md).

## Structure

```
app/
  agency.py            agent roles, state machine, LLM failover chain
  scheduler.py         autonomous background loop
  factory.py           durable job primitives, night_shift.py: scheduled lead production
  voice_agent.py       browser voice receptionist
  voice_demo_api.py    Twilio + OpenAI Realtime calls
  telephony.py         Twilio dialing
  lead_finder.py       lead discovery and scoring
  sales_intelligence.py  lead audits, proposals, outreach
  outbound.py          human-approved e-mail outbox
  campaigns.py         campaign generation
  content_studio.py    post / story / carousel drafts
  compliance.py        brand compliance checker
  brand_sync.py        brand-kit proposals
  instagram.py / tiktok.py / buffer_publish.py   publishing
  sora.py / veo.py / openai_images.py            media generation
  auth.py              workspaces, roles, sessions
  usage_report.py      token and cost reporting
  export.py            PDF and ZIP hand-off
  celery_app.py / worker_tasks.py                production workers
  api.py / web.py / ws.py                        HTTP, pages, WebSocket
templates/, static/    dashboard UI
tests/                 244 network-mocked tests
```

## Stack

Python · FastAPI · SQLAlchemy · Celery · Redis · PostgreSQL · WebSockets · Docker · Groq / Gemini /
Hugging Face / OpenAI · OpenAI Realtime · Twilio · n8n · Telegram · Instagram & TikTok APIs

## License

MIT
