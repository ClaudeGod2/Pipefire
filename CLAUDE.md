# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## State of the repo

This repo is in transition. Three legacy scripts exist (`bygg_ringlista_v4 (1).py`, `mail_generator_v2.py`, `lead_tracker.py`) and a full production app plan is in `PLAN.md`. The task is to build the app described in `PLAN.md` — the scripts are reference implementations to port from, not code to extend.

## Running the app (once built)

```bash
cp .env.example .env   # fill in ABPI_API_KEY, Gmail credentials
pip install -r requirements.txt
python run.py           # → http://localhost:8000
```

Database migrations:
```bash
alembic upgrade head          # apply all migrations
alembic revision --autogenerate -m "description"  # create new migration
```

## Architecture (target — see PLAN.md for full detail)

**FastAPI + Jinja2 + HTMX.** No JS framework. Server renders HTML partials; HTMX handles all dynamic updates via `hx-target` / `hx-swap="outerHTML"`. Alpine.js only for local UI state (collapse/expand, loading spinners).

**Three pipeline phases map to three routers:**
1. `routers/campaigns.py` — create campaign, trigger background enrichment, SSE progress stream
2. `routers/drafts.py` — preview generated emails, approve, push to Gmail as drafts
3. `routers/tracking.py` — sync Gmail replies, generate followup drafts

**Background jobs** run via FastAPI `BackgroundTasks`. Progress is emitted over SSE at `/campaigns/{id}/progress` and consumed by HTMX SSE extension in the template. No Celery or Redis.

**Services are the core logic:**
- `services/scb.py` — downloads/caches SCB bulk file (~30–60 MB zip, latin-1 encoded, tab-separated)
- `services/abpi.py` — ABPI REST API client for company detail (revenue, contacts, email)
- `services/enrichment.py` — MX validation via `dnspython` (never subprocess); LinkedIn search URL generation
- `services/pipeline.py` — orchestrates scb → abpi → enrichment → DB per campaign
- `services/gmail_client.py` — Gmail API wrapper (create_draft, search_sent_threads, read_thread)

**SQLite via SQLAlchemy.** Three main models: `Campaign`, `Lead`, `EmailDraft`. State lives in DB, not files.

## Domain context

- **ImBox** is a Swedish B2B SaaS for customer communications (live chat, chatbot, ticketing, telephony).
- **SCB bulk file** is a zip from Bolagsverket containing all Swedish registered companies, filtered by SNI industry code and size class.
- **ABPI** is a Swedish company data API that enriches org numbers with financials, contacts, and email.
- **MX status** determines whether an email address is safe to contact: `ok` = send, `catch_all` = manual check, `no_mx` = never send.
- **Emails are always drafts** — pushed to Gmail, reviewed and sent manually by the SDR. Auto-send must never be implemented.

## Key constraints

- All user-facing text in the UI is Swedish.
- Email copy is Swedish (personalized per lead using company name, industry, contact name).
- The `data/` directory (SQLite db, SCB cache, Gmail token, Excel exports) is gitignored and must be created on first run.
- Gmail OAuth uses a local redirect URI (`http://localhost:8000/auth/gmail/callback`) — app is not deployed remotely.
