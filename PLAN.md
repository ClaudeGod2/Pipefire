# Pipefire — Production App Plan

## Goal

Transform the existing three Python scripts into a locally-runnable web app that a non-technical SDR can use without Claude Code. The app manages the full outbound sales pipeline: prospecting → email drafts → reply tracking.

**Non-negotiables:**
- Python throughout
- Runs locally (`python run.py` → open browser)
- Never auto-sends email — always push to Gmail as drafts, SDR sends manually
- Preview + approve step before any Gmail action

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Backend | FastAPI + Uvicorn | Modern Python, async, great DX |
| Database | SQLite + SQLAlchemy + Alembic | Zero infrastructure, local, migratable |
| Frontend | HTMX + Alpine.js + Tailwind (CDN) | No build step, Jinja2-native, no React |
| Templating | Jinja2 | Server-side, integrates with HTMX |
| Background jobs | FastAPI BackgroundTasks + SSE | No Redis/Celery needed at this scale |
| Gmail | google-api-python-client + google-auth-oauthlib | Official, OAuth2 local flow |
| MX validation | dnspython | Cross-platform, reliable, replaces subprocess hack |
| Excel export | openpyxl | Already in use |
| Config | pydantic-settings + python-dotenv | Type-safe env vars |

---

## File Structure

```
pipefire/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, mounts routers, serves templates
│   ├── config.py                # Pydantic Settings (reads .env)
│   ├── database.py              # SQLAlchemy engine, session factory, Base
│   ├── models.py                # ORM models: Campaign, Lead, EmailDraft, Followup
│   ├── schemas.py               # Pydantic schemas for request/response validation
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── campaigns.py         # Create, list, get campaigns; trigger pipeline
│   │   ├── leads.py             # List leads, update call status/comment
│   │   ├── drafts.py            # Preview drafts, approve, push to Gmail
│   │   ├── tracking.py          # Check Gmail replies, show followup queue
│   │   └── gmail_auth.py        # OAuth2 flow: /auth/gmail + /auth/gmail/callback
│   ├── services/
│   │   ├── __init__.py
│   │   ├── scb.py               # Download + parse SCB bulk file (with 7-day cache)
│   │   ├── abpi.py              # ABPI API client: fetch company detail
│   │   ├── enrichment.py        # MX check (dnspython), LinkedIn URL generation
│   │   ├── pipeline.py          # Orchestrator: scb → abpi → enrichment → DB
│   │   ├── mail_generator.py    # Generate personalized email subject + body
│   │   └── gmail_client.py      # Gmail API: create_draft, search_threads, read_thread
│   ├── templates/
│   │   ├── base.html            # Layout: nav, flash messages, Tailwind/HTMX/Alpine CDN
│   │   ├── dashboard.html       # Campaign list + summary stats
│   │   ├── campaign_new.html    # New campaign form (SNI, size, revenue, count)
│   │   ├── campaign_detail.html # Lead table with MX colors, status dropdown, LinkedIn
│   │   ├── drafts.html          # Draft preview cards, approve/reject, push to Gmail
│   │   └── tracking.html        # Reply status, followup queue, generate followup draft
│   └── static/
│       └── app.css              # Minimal overrides (Tailwind via CDN handles the rest)
├── data/
│   ├── pipefire.db              # SQLite database (gitignored)
│   ├── scb_cache.txt            # SCB bulk file cache (gitignored)
│   ├── token.json               # Gmail OAuth token (gitignored)
│   └── exports/                 # Generated Excel files (gitignored)
├── alembic/
│   ├── env.py
│   └── versions/                # Migration files
├── alembic.ini
├── .env.example                 # Template for env vars (committed)
├── .env                         # Actual secrets (gitignored)
├── .gitignore
├── requirements.txt
└── run.py                       # Entry point: starts uvicorn
```

---

## Database Schema

### `campaigns`
```python
class Campaign(Base):
    __tablename__ = "campaigns"
    id          = Column(Integer, primary_key=True)
    name        = Column(String, nullable=False)       # e.g. "Gym-bolag maj 2025"
    sni_prefix  = Column(String, nullable=False)       # e.g. "9313"
    min_klass   = Column(Integer, default=3)           # SCB size class min
    max_klass   = Column(Integer, default=9)           # SCB size class max
    min_msek    = Column(Integer, default=0)           # Min revenue filter
    max_bolag   = Column(Integer, default=50)          # Max leads to fetch
    status      = Column(String, default="pending")   # pending | running | done | error
    progress    = Column(Integer, default=0)           # 0-100
    error_msg   = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=func.now())
    leads       = relationship("Lead", back_populates="campaign")
```

### `leads`
```python
class Lead(Base):
    __tablename__ = "leads"
    id               = Column(Integer, primary_key=True)
    campaign_id      = Column(Integer, ForeignKey("campaigns.id"))
    company_name     = Column(String)
    org_nr           = Column(String)
    revenue          = Column(String)           # e.g. "450 MSEK"
    employees        = Column(String)
    industry         = Column(String)
    sni              = Column(String)
    city             = Column(String)
    website          = Column(String)
    phone            = Column(String)
    email            = Column(String)
    mx_status        = Column(String)           # ok | catch_all | no_mx | invalid | error
    mx_detail        = Column(String)
    contact_name     = Column(String)
    contact_role     = Column(String)
    linkedin_url     = Column(String)
    call_status      = Column(String, default="Ej kontaktad")
    call_date        = Column(Date, nullable=True)
    comment          = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=func.now())
    campaign         = relationship("Campaign", back_populates="leads")
    drafts           = relationship("EmailDraft", back_populates="lead")
```

### `email_drafts`
```python
class EmailDraft(Base):
    __tablename__ = "email_drafts"
    id              = Column(Integer, primary_key=True)
    lead_id         = Column(Integer, ForeignKey("leads.id"))
    subject         = Column(String)
    body            = Column(Text)
    gmail_draft_id  = Column(String, nullable=True)   # Set after pushing to Gmail
    gmail_thread_id = Column(String, nullable=True)   # Set after SDR sends it
    status          = Column(String, default="pending")  # pending | approved | sent | replied | cold
    attempt         = Column(Integer, default=1)         # 1=initial, 2=followup1, 3=followup2
    created_at      = Column(DateTime, default=func.now())
    sent_at         = Column(DateTime, nullable=True)
    replied_at      = Column(DateTime, nullable=True)
    lead            = relationship("Lead", back_populates="drafts")
```

---

## Environment Variables (`.env.example`)

```env
# ABPI API
ABPI_API_KEY=your_key_here
ABPI_BASE_URL=https://abpi.se/api

# App
OUTPUT_DIR=./data/exports
SCB_CACHE_PATH=./data/scb_cache.txt
DATABASE_URL=sqlite:///./data/pipefire.db
SECRET_KEY=change_me_to_random_string

# Gmail OAuth — get from Google Cloud Console
GMAIL_CLIENT_ID=
GMAIL_CLIENT_SECRET=
GMAIL_REDIRECT_URI=http://localhost:8000/auth/gmail/callback
GMAIL_TOKEN_PATH=./data/token.json

# Sender identity (shown in email drafts)
SENDER_NAME=Adam
GMAIL_SEND_AS=adam@imbox.io

# Pipeline tuning
ABPI_REQUEST_DELAY=0.15     # seconds between ABPI calls
ABPI_TIMEOUT=10             # seconds
SCB_CACHE_TTL=604800        # 7 days in seconds
FOLLOWUP_DAY_1=5            # days before first followup
FOLLOWUP_DAY_2=10           # days before second followup
FOLLOWUP_COLD=15            # days before marking cold
```

---

## Services

### `app/services/scb.py`
Responsibility: Download and parse the Bolagsverket/SCB bulk file.

```python
def get_candidates(sni_prefix: str, min_klass: int, max_klass: int) -> list[dict]:
    """
    Downloads (or reads from cache) the SCB bulk zip.
    Returns list of {orgnr, namn, sni} matching the filters.
    Cache TTL = SCB_CACHE_TTL from config.
    """
```

Key details:
- Cache file at `config.SCB_CACHE_PATH`
- Check file age vs `config.SCB_CACHE_TTL`
- Decode as `latin-1` (SCB file encoding)
- Strip `16` prefix from org numbers, format as `XXXXXX-XXXX`

### `app/services/abpi.py`
Responsibility: Fetch company detail from ABPI API.

```python
def fetch_company(orgnr: str) -> dict | None:
    """
    GET {ABPI_BASE_URL}/{orgnr}/data
    Returns parsed JSON or None on failure.
    Retries once on timeout, skips on other errors.
    Adds Bearer token if ABPI_API_KEY is set.
    """

def extract_contact(data: dict) -> tuple[str, str]:
    """Returns (name, role) for best matching contact. Priority: Marketing > Customer Service > IT."""

def extract_revenue(data: dict) -> tuple[int | None, str]:
    """Returns (revenue_kr, display_text) e.g. (450000000, '450 MSEK')"""

def extract_email(data: dict) -> str:
    """Returns email if found, falls back to info@{domain}"""
```

### `app/services/enrichment.py`
Responsibility: MX validation and LinkedIn URL generation.

```python
def check_mx(email: str, cache: dict = {}) -> tuple[str, str]:
    """
    Uses dnspython (dns.resolver.resolve(domain, 'MX')).
    Returns (status, detail):
      "ok"        — MX records found
      "catch_all" — MX ok but address starts with info@
      "no_mx"     — No MX records (NXDOMAIN or empty)
      "invalid"   — No @ or empty email
      "error"     — DNS timeout or other error
    In-memory cache per domain within a pipeline run.
    """

def generate_linkedin_url(name: str, company: str) -> str:
    """
    Returns LinkedIn people search URL.
    Strips legal suffixes (AB, HB, KB, Inc, Ltd) from company name.
    """
```

### `app/services/pipeline.py`
Responsibility: Orchestrate the full enrichment run for a campaign.

```python
async def run_pipeline(campaign_id: int, db: Session):
    """
    1. Update campaign status = 'running'
    2. Load candidates from SCB (scb.get_candidates)
    3. For each candidate (up to max_bolag * 6 attempts):
       a. fetch_company via ABPI
       b. Filter by min_msek
       c. check_mx on extracted email
       d. generate_linkedin_url
       e. Save Lead to DB
       f. Update campaign.progress (0-100)
       g. Sleep config.ABPI_REQUEST_DELAY
    4. Update campaign status = 'done'
    5. On any unhandled exception: status = 'error', save error_msg
    """
```

Progress formula: `int((leads_found / max_bolag) * 100)` capped at 99 until done.

### `app/services/mail_generator.py`
Responsibility: Generate personalized email subject and body.

```python
def generate_subject(lead: Lead) -> str:
    return f"Kundkommunikation hos {lead.company_name} — en tanke"

def generate_body(lead: Lead, sender_name: str) -> str:
    """
    Personalize based on: company_name, contact_name, industry, city.
    Uses lead.industry for context line.
    Never hardcode ImBox marketing claims — keep them factual.
    Returns plain text body (Gmail draft handles formatting).
    """

def generate_followup_body(lead: Lead, attempt: int, sender_name: str) -> str:
    """
    attempt=2: Short reminder, reference previous email
    attempt=3: Final attempt, soft close
    """
```

### `app/services/gmail_client.py`
Responsibility: All Gmail API interactions.

```python
def get_credentials() -> Credentials:
    """
    Loads token from config.GMAIL_TOKEN_PATH.
    Refreshes if expired.
    Raises GmailNotAuthorizedError if no token exists.
    """

def create_draft(to: str, subject: str, body: str, thread_id: str = None) -> str:
    """
    Creates Gmail draft. Returns gmail_draft_id.
    If thread_id given: creates as reply in that thread.
    """

def search_sent_threads(query: str = "from:me label:sent") -> list[dict]:
    """
    Returns list of {thread_id, to, subject, sent_date, has_reply}
    Checks each thread for replies from non-self senders.
    """

def is_authorized() -> bool:
    """Returns True if valid token exists."""
```

---

## Routers

### `app/routers/campaigns.py`

| Method | Path | Description |
|---|---|---|
| GET | `/` | Dashboard: list all campaigns with stats |
| GET | `/campaigns/new` | New campaign form |
| POST | `/campaigns` | Create campaign + trigger pipeline in background |
| GET | `/campaigns/{id}` | Campaign detail with lead table |
| GET | `/campaigns/{id}/progress` | SSE stream: `{"progress": 45, "done": false, "leads": 12}` |
| GET | `/campaigns/{id}/export` | Download Excel file (regenerated on request) |
| DELETE | `/campaigns/{id}` | Delete campaign + all leads |

### `app/routers/leads.py`

| Method | Path | Description |
|---|---|---|
| PATCH | `/leads/{id}/status` | Update call_status (HTMX partial) |
| PATCH | `/leads/{id}/comment` | Update comment (HTMX partial) |
| GET | `/campaigns/{id}/leads` | Filtered/sorted lead table partial (HTMX) |

### `app/routers/drafts.py`

| Method | Path | Description |
|---|---|---|
| GET | `/campaigns/{id}/drafts` | Draft preview page |
| POST | `/campaigns/{id}/drafts/generate` | Generate drafts for all eligible leads (MX ok, not contacted) |
| POST | `/drafts/{id}/approve` | Mark draft approved |
| POST | `/drafts/{id}/reject` | Mark draft rejected |
| POST | `/campaigns/{id}/drafts/push` | Push all approved drafts to Gmail |

### `app/routers/tracking.py`

| Method | Path | Description |
|---|---|---|
| GET | `/campaigns/{id}/tracking` | Tracking page |
| POST | `/campaigns/{id}/tracking/sync` | Pull Gmail reply status, update draft statuses |
| POST | `/drafts/{id}/followup` | Generate + push followup draft to Gmail |

### `app/routers/gmail_auth.py`

| Method | Path | Description |
|---|---|---|
| GET | `/auth/gmail` | Redirect to Google OAuth consent screen |
| GET | `/auth/gmail/callback` | Exchange code for token, save to token.json |
| GET | `/auth/gmail/status` | Returns `{"authorized": true/false}` (HTMX partial) |
| POST | `/auth/gmail/disconnect` | Delete token.json |

---

## UI Pages

### Dashboard (`/`)
- Header with app name + Gmail connection status badge (green/red)
- Table of campaigns: Name | SNI | Leads | MX OK | Drafted | Sent | Replied | Date
- "New Campaign" button
- Empty state if no campaigns

### New Campaign (`/campaigns/new`)
Clean form with 5 fields:
1. Campaign name (text)
2. Industry / SNI code — text input with a helper accordion showing common SNI codes (47=Retail, 62=IT, 9313=Gym, 561=Restaurant, etc.)
3. Company size — slider or select (SCB classes 0–9 with labels: "10–19 anst", "20–49 anst" etc.)
4. Min revenue (MSEK) — number input
5. Max leads — number input (default 50)

On submit: POST → redirect to campaign detail page with progress bar active.

### Campaign Detail (`/campaigns/{id}`)
Two sections:

**Header bar:** Campaign name | Status badge | Lead count | Export Excel button

**Progress bar** (shown while status=running, hidden when done):
Uses HTMX SSE to update in real time. Shows "Hämtar bolagsdata... 34/50"

**Lead table** (shown when done):
Columns: # | Bolagsnamn | Omsättning | Ort | E-post | MX | Kontaktperson | LinkedIn | Telefon | Status | Kommentar

- MX column: color-coded badge (green ✓ OK / yellow ~ info@ / red ✗ Ingen MX / grey ?)
- LinkedIn column: "Kolla →" link (opens LinkedIn search in new tab)
- Status column: dropdown (HTMX PATCH on change)
- Comment: inline edit (click to edit, blur to save)
- Row sort: MX OK first, then alphabetical
- Filter bar: filter by MX status, call status

"Gå till mailutkast →" button at bottom.

### Drafts (`/campaigns/{id}/drafts`)
**Step 1:** "Generera utkast" button — POST to generate, shows count of eligible leads.

**Draft cards** (one per lead):
```
┌─────────────────────────────────────────────┐
│ Företag AB  ·  anna@foretag.se  ·  ✓ MX OK │
│ Kontakt: Anna Svensson (Marknadschef)       │
│                                             │
│ Ämne: Kundkommunikation hos Företag AB...   │
│                                             │
│ Hej Anna,                                   │
│ Jag kontaktar er på Företag AB...           │
│ [full preview collapsed, click to expand]   │
│                                             │
│  [✓ Godkänn]  [✗ Hoppa över]              │
└─────────────────────────────────────────────┘
```

Bottom bar: "X av Y godkända — Skicka till Gmail →" button.
Pushing shows a progress indicator, then success count.

### Tracking (`/campaigns/{id}/tracking`)
**Sync button** — "Kolla Gmail efter svar" → POST /tracking/sync

**Stats row:** Skickade | Fått svar | Inväntar svar | Behöver uppföljning | Kalla

**Followup queue table:**
| Bolag | Dagar sedan | Försök | Åtgärd |
|---|---|---|---|
| Företag AB | 7 | #1 | [Skapa uppföljning →] |

Clicking "Skapa uppföljning" generates a followup draft and pushes to Gmail. Shows preview first.

**Replied table:**
| Bolag | Svarade | Tråd |
|---|---|---|
| Annat AB | 3 dagar sedan | [Öppna i Gmail →] |

---

## Key Implementation Details

### SSE Progress (pipeline running)

```python
# In campaign_detail.html
<div hx-ext="sse" sse-connect="/campaigns/{{ campaign.id }}/progress">
  <div sse-swap="message">
    <!-- Progress bar updated via SSE -->
  </div>
</div>
```

```python
# In campaigns.py router
@router.get("/{id}/progress")
async def campaign_progress(id: int, db: Session = Depends(get_db)):
    async def generate():
        while True:
            campaign = db.get(Campaign, id)
            data = {"progress": campaign.progress, "done": campaign.status == "done",
                    "leads": len(campaign.leads), "status": campaign.status}
            yield f"data: {json.dumps(data)}\n\n"
            if campaign.status in ("done", "error"):
                break
            await asyncio.sleep(1)
    return StreamingResponse(generate(), media_type="text/event-stream")
```

### Gmail OAuth (local flow)

```python
# In gmail_auth.py
@router.get("/auth/gmail")
def gmail_auth():
    flow = Flow.from_client_config(
        {"web": {"client_id": config.GMAIL_CLIENT_ID, ...}},
        scopes=["https://www.googleapis.com/auth/gmail.compose",
                "https://www.googleapis.com/auth/gmail.readonly"]
    )
    flow.redirect_uri = config.GMAIL_REDIRECT_URI
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)

@router.get("/auth/gmail/callback")
def gmail_callback(code: str):
    flow.fetch_token(code=code)
    with open(config.GMAIL_TOKEN_PATH, "w") as f:
        f.write(flow.credentials.to_json())
    return RedirectResponse("/")
```

### MX Check with dnspython

```python
import dns.resolver
import dns.exception

def check_mx(email: str, cache: dict = {}) -> tuple[str, str]:
    if not email or "@" not in email:
        return "invalid", "Ingen giltig e-post"
    domain = email.split("@")[1].lower()
    if domain in cache:
        status, detail = cache[domain]
        if status == "ok" and email.lower().startswith("info@"):
            return "catch_all", f"Generisk info@"
        return status, detail
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        servers = sorted(answers, key=lambda r: r.preference)
        detail = str(servers[0].exchange).rstrip(".")
        cache[domain] = ("ok", detail)
        if email.lower().startswith("info@"):
            return "catch_all", "Generisk info@"
        return "ok", detail
    except dns.resolver.NXDOMAIN:
        cache[domain] = ("no_mx", f"Domänen {domain} finns inte")
        return "no_mx", f"Domänen {domain} finns inte"
    except dns.resolver.NoAnswer:
        cache[domain] = ("no_mx", f"Ingen MX för {domain}")
        return "no_mx", f"Ingen MX för {domain}"
    except dns.exception.Timeout:
        cache[domain] = ("error", "DNS timeout")
        return "error", "DNS timeout"
    except Exception as e:
        cache[domain] = ("error", str(e))
        return "error", str(e)
```

### Excel Export

Generate on-demand in `campaigns.py`:

```python
@router.get("/{id}/export")
def export_excel(id: int, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, id)
    leads = campaign.leads
    # Build openpyxl workbook with same formatting as original script
    # MX color coding, status dropdown, LinkedIn hyperlinks
    # Return as StreamingResponse with application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
```

---

## `requirements.txt`

```
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
sqlalchemy>=2.0.0
alembic>=1.13.0
jinja2>=3.1.0
python-dotenv>=1.0.0
pydantic-settings>=2.0.0
dnspython>=2.6.0
openpyxl>=3.1.0
google-api-python-client>=2.0.0
google-auth-oauthlib>=1.0.0
google-auth-httplib2>=0.2.0
python-multipart>=0.0.9
httpx>=0.27.0
```

---

## `run.py`

```python
import uvicorn
from app.main import app
from app.database import init_db

if __name__ == "__main__":
    init_db()
    print("Pipefire körs på http://localhost:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
```

---

## `app/main.py`

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routers import campaigns, leads, drafts, tracking, gmail_auth
from app.config import settings

app = FastAPI(title="Pipefire")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(campaigns.router)
app.include_router(leads.router)
app.include_router(drafts.router)
app.include_router(tracking.router)
app.include_router(gmail_auth.router)
```

---

## `app/config.py`

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    abpi_api_key: str = ""
    abpi_base_url: str = "https://abpi.se/api"
    database_url: str = "sqlite:///./data/pipefire.db"
    output_dir: str = "./data/exports"
    scb_cache_path: str = "./data/scb_cache.txt"
    scb_cache_ttl: int = 604800
    secret_key: str = "change_me"
    gmail_client_id: str = ""
    gmail_client_secret: str = ""
    gmail_redirect_uri: str = "http://localhost:8000/auth/gmail/callback"
    gmail_token_path: str = "./data/token.json"
    sender_name: str = "Adam"
    gmail_send_as: str = ""
    abpi_request_delay: float = 0.15
    abpi_timeout: int = 10
    followup_day_1: int = 5
    followup_day_2: int = 10
    followup_cold: int = 15

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## Implementation Order

Execute in this order — each stage is independently runnable/testable.

### Stage 1 — Skeleton (Day 1)
1. Create full directory structure
2. Write `requirements.txt`
3. Write `.env.example` and `.gitignore`
4. Write `app/config.py` and `app/database.py`
5. Write `app/models.py` (all 3 models)
6. Write `app/main.py` (bare app, no routes yet)
7. Write `run.py`
8. Run `alembic init alembic` and write first migration
9. Verify: `python run.py` starts without errors

### Stage 2 — Pipeline Core (Day 1–2)
10. Port `bygg_ringlista_v4.py` → `app/services/scb.py` (clean function, no globals)
11. Port ABPI logic → `app/services/abpi.py` (proper retry, logging)
12. Write `app/services/enrichment.py` using dnspython
13. Write `app/services/pipeline.py` orchestrator
14. Write minimal test: run pipeline for SNI "9313", 5 leads, print to console

### Stage 3 — Campaigns UI (Day 2)
15. Write `app/routers/campaigns.py` (all endpoints)
16. Write `app/templates/base.html` (Tailwind CDN, HTMX CDN, Alpine CDN, nav)
17. Write `app/templates/dashboard.html`
18. Write `app/templates/campaign_new.html`
19. Write `app/templates/campaign_detail.html` (table + SSE progress bar)
20. Verify: Can create a campaign, watch it run, see leads appear

### Stage 4 — Leads & Export (Day 2–3)
21. Write `app/routers/leads.py` (status/comment update via HTMX)
22. Add inline status dropdown with HTMX PATCH in campaign_detail.html
23. Add Excel export endpoint (port Excel generation from original script)
24. Verify: Can update statuses, download Excel

### Stage 5 — Gmail Auth (Day 3)
25. Set up Google Cloud project: enable Gmail API, create OAuth2 credentials (Web app), add `http://localhost:8000/auth/gmail/callback` as redirect URI
26. Write `app/services/gmail_client.py`
27. Write `app/routers/gmail_auth.py`
28. Add Gmail status badge to base.html (green/red, links to /auth/gmail)
29. Verify: OAuth flow completes, token.json saved, badge turns green

### Stage 6 — Drafts (Day 3–4)
30. Port `mail_generator_v2.py` → `app/services/mail_generator.py` (Lead model input)
31. Write `app/routers/drafts.py`
32. Write `app/templates/drafts.html`
33. Implement draft card: preview collapsed by default (Alpine toggle)
34. Implement approve/reject (HTMX PATCH, optimistic UI)
35. Implement "Push to Gmail" button with progress
36. Verify: Drafts appear in Gmail inbox as drafts

### Stage 7 — Tracking (Day 4)
37. Implement `gmail_client.search_sent_threads()` and `gmail_client.read_thread()`
38. Write `app/routers/tracking.py`
39. Write `app/templates/tracking.html`
40. Implement sync button → updates draft statuses in DB
41. Implement followup generation + push
42. Verify: Send a test email manually, reply to it, sync shows reply

### Stage 8 — Polish (Day 5)
43. Error handling: wrap all service calls in try/except with user-visible flash messages
44. Add loading spinners (Alpine.js) on all async actions
45. Mobile-responsive check (Tailwind breakpoints)
46. Empty states for all tables
47. Add SNI reference accordion to campaign_new.html
48. Final QA: full pipeline run end-to-end

---

## Google Cloud Setup (one-time, for Gmail)

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create new project: "Pipefire"
3. Enable API: Gmail API
4. Create credentials: OAuth 2.0 Client ID → Web Application
5. Add authorized redirect URI: `http://localhost:8000/auth/gmail/callback`
6. Download credentials → copy Client ID + Client Secret to `.env`
7. OAuth consent screen: set to "External", add your Gmail as test user

---

## What to Keep from Existing Scripts

| Old file | What to keep | What to rewrite |
|---|---|---|
| `bygg_ringlista_v4.py` | SCB parsing logic (lines 163–186), ABPI field extraction helpers (lines 210–248), LinkedIn URL generation, MX status labels | Replace subprocess MX with dnspython, remove globals, remove Excel generation |
| `mail_generator_v2.py` | `generate_subject()`, `generate_body()` logic | Adapt to take `Lead` model instead of dict |
| `lead_tracker.py` | `generate_report()` structure, `generate_followup_body()` | Adapt to read from DB instead of Excel + JSON |
| `SKILL_v4.md` | SNI prefix reference table, status value list, MX status definitions | Removed — replaced by the web app |

---

## Notes for Next Claude Session

- **Start with Stage 1** — get the skeleton running before touching any service logic
- **The ABPI API key is empty** — pipeline will still run but all enrichment calls will fail/return None. The skeleton + SCB parsing can be tested without it.
- **MX caching** — the `cache` dict in `enrichment.py` is intentionally in-memory per process. Do not persist it to DB; the SCB cache is enough.
- **HTMX patterns** — use `hx-target`, `hx-swap="outerHTML"` for partial updates. Each row in the lead table should be its own `<tr id="lead-{id}">` so HTMX can swap it independently.
- **No JavaScript framework** — Alpine.js only for toggling (expand/collapse draft preview, loading states). HTMX handles all server communication.
- **Tailwind via CDN** — use `https://cdn.tailwindcss.com` in base.html. No build step.
- **The data/ directory** must exist before first run — create it in `run.py` startup or `init_db()`.
