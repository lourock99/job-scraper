# Job Search Pipeline — Architecture & Process Flow

## Overview

Two companion repositories form an automated job search pipeline targeting SAM/compliance roles in Atlanta. The Python backend scrapes multiple job boards daily, scores each listing against a parsed resume using an LLM, and generates tailored PDF resumes for high-scoring matches. The Next.js frontend exposes the full dataset for browsing, filtering, and application tracking.

| Layer | Repo | Runtime |
|---|---|---|
| Backend pipeline | `job-scraper` | GitHub Actions (cloud) |
| Frontend | `jobs-scraper-web` | localhost:3000 (macOS launchd) |
| Storage | Supabase | PostgreSQL + object storage |
| Scheduling | Claude Code routines | Local machine → `gh workflow run` |

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      SCHEDULING LAYER                            │
│                    Claude Code Routines                          │
│                                                                  │
│  job-scraper-scrape  job-scraper-score  job-scraper-customize    │
│      6:00 AM              */4h                */6h               │
│                                        job-scraper-manage        │
│                                             1:00 PM              │
│            └──────────────────────────────┘                      │
│                       gh workflow run                            │
└──────────────────────────────┬───────────────────────────────────┘
                               │ workflow_dispatch
┌──────────────────────────────▼───────────────────────────────────┐
│                     EXECUTION LAYER                              │
│                   GitHub Actions (cloud)                         │
│                                                                  │
│  ┌──────────────┐ ┌─────────────┐ ┌──────────────┐ ┌─────────┐  │
│  │ scraper.py   │ │score_jobs   │ │custom_resume │ │job_mgr  │  │
│  │              │ │.py          │ │_generator.py │ │.py      │  │
│  │ LinkedIn     │ │             │ │              │ │         │  │
│  │ JSearch      │ │ LiteLLM     │ │ LiteLLM      │ │Expire   │  │
│  │ USAJobs      │ │ ↓           │ │ ↓            │ │Check    │  │
│  │ CareersFut.  │ │ Anthropic   │ │ Anthropic    │ │Soft-del │  │
│  └──────┬───────┘ │ Gemini      │ │ Gemini       │ └────┬────┘  │
│         │         │ OpenAI      │ │ OpenAI       │      │       │
│         │         └──────┬──────┘ │pdf_generator │      │       │
│         │                │        │.py           │      │       │
│         │                │        └──────┬───────┘      │       │
└─────────┼────────────────┼───────────────┼──────────────┼───────┘
          │ UPSERT         │ UPDATE        │ INSERT+UP    │ UPDATE
┌─────────▼────────────────▼───────────────▼──────────────▼───────┐
│                    DATA LAYER — Supabase                         │
│                                                                  │
│  PostgreSQL Tables             Object Storage Buckets            │
│  ┌────────────────────┐        ┌──────────────────────────────┐  │
│  │ jobs               │        │ resumes/                     │  │
│  │ customized_resumes │        │   resume.pdf  (base, manual) │  │
│  │ base_resume        │        │ personalized_resumes/        │  │
│  └────────────────────┘        │   resume_{job_id}.pdf        │  │
│                                └──────────────────────────────┘  │
└──────────────────────────────────────┬───────────────────────────┘
                                       │ Supabase JS client
┌──────────────────────────────────────▼───────────────────────────┐
│                  PRESENTATION LAYER                              │
│            jobs-scraper-web (Next.js 16 / React 19)              │
│                                                                  │
│  Dashboard → Browse → Filter → Detail → Resume → Apply          │
│               localhost:3000  (macOS launchd service)            │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Layer

### PostgreSQL Tables

#### `jobs`

Primary table. One row per job listing.

| Column | Type | Default | Description |
|---|---|---|---|
| `job_id` | text | PK | Unique ID from source (e.g. LinkedIn job ID) |
| `company` | text | — | Company name |
| `job_title` | text | — | Position title |
| `level` | text | — | Seniority level |
| `location` | text | — | City/state from listing |
| `country` | text | — | Inferred country |
| `description` | text | — | Full job description (Markdown) |
| `status` | text | `'new'` | Workflow state (see state machine below) |
| `is_active` | boolean | `true` | Whether listing is still live on source |
| `resume_score` | smallint | `NULL` | LLM match score 0–100 |
| `resume_score_stage` | text | `'initial'` | `initial` or `custom` |
| `is_interested` | boolean | `NULL` | User interest flag |
| `customized_resume_id` | uuid | `NULL` | FK → customized_resumes |
| `provider` | text | — | Source: `linkedin`, `jsearch`, `usajobs`, `careers_future` |
| `posted_at` | timestamp | — | When job was posted on source |
| `scraped_at` | timestamp | `NOW()` | When pipeline first saw it |
| `last_checked` | timestamp | — | Last LinkedIn activity check |
| `url` | text | — | Direct link to listing |
| `evaluation_report` | text | — | LLM legitimacy/evaluation notes |
| `legitimacy_tier` | text | — | `High Confidence`, `Proceed with Caution`, `Suspicious` |
| `notes` | text | — | User notes |

**Indexes:** `company`, `job_title`, `is_active`, `resume_score`, `status`, `scraped_at`, `last_checked`

#### `customized_resumes`

One row per generated resume. Linked from `jobs.customized_resume_id`.

| Column | Type | Description |
|---|---|---|
| `id` | uuid | PK (auto-generated) |
| `name`, `email`, `phone`, `location` | text | Contact fields |
| `summary` | text | LLM-tailored professional summary |
| `skills` | text[] | LLM-tailored skills list |
| `education` | jsonb | Education entries |
| `experience` | jsonb | LLM-tailored experience entries |
| `projects` | jsonb | LLM-tailored project entries |
| `certifications` | jsonb | Certification entries |
| `links` | jsonb | LinkedIn, GitHub, portfolio |
| `resume_link` | text | Path in `personalized_resumes/` bucket |
| `created_at` | timestamp | Auto-set on insert |
| `last_updated` | timestamp | Auto-updated via trigger |

#### `base_resume`

Single row. Stores the parsed JSON of the user's master resume.

| Column | Type | Description |
|---|---|---|
| `id` | uuid | PK |
| `resume_data` | jsonb | Full Resume object (see Pydantic models) |
| `created_at` | timestamp | — |
| `updated_at` | timestamp | Auto-updated via trigger |

### Object Storage Buckets

| Bucket | Contents | Who writes |
|---|---|---|
| `resumes` | `resume.pdf` — user's master resume | Manual upload |
| `personalized_resumes` | `resume_{job_id}.pdf` — tailored PDFs | `custom_resume_generator.py` |

### Job Status State Machine

```
                      ┌─────────┐
     scraper.py  ───▶ │   new   │
                      └────┬────┘
                           │ score_jobs.py scores it
                           ▼
                   ┌───────────────┐
                   │ new +         │
                   │ resume_score  │◀── re-scored with custom resume
                   └───────┬───────┘        (score_stage = 'custom')
                           │
                   score >= 50?
                   │              │
                  YES             NO → stays as new, user dismisses
                   │
                   ▼
            ┌──────────────────┐
            │ resume_generated │◀── custom_resume_generator.py
            └──────┬───────────┘
                   │ user applies
                   ▼
              ┌─────────┐
              │ applied │
              └────┬────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
   ┌─────────────┐   ┌───────────┐
   │ interviewing│   │ rejected  │
   └─────────────┘   └───────────┘

Parallel (job_manager.py):
  new/resume_generated + age > 30d  ──▶  expired
  expired + is_active=FALSE + age > 60d  ──▶  deleted (soft)
```

---

## Process Flows

### 0. Bootstrap — Parse Base Resume (manual, one-time)

```
1. Upload resume.pdf to Supabase Storage → resumes/ bucket
2. Trigger parse_resume workflow (manual dispatch)
3. resume_parser.py:
     a. Download resume.pdf from resumes/ bucket
     b. Extract text with pdfplumber
     c. Send to LLM with structured output schema (Resume Pydantic model)
     d. Return validated Resume object
4. UPSERT into base_resume table (resume_data = JSON)
5. Pipeline is now ready
```

### 1. Daily Scrape — 6:00 AM local

```
Claude Code routine: job-scraper-scrape
  └─▶ gh workflow run scrape_jobs.yml

scraper.py:
  1. Load existing job_ids (set) from jobs table [dedup check]
  2. Load existing (company|job_title) pairs (set) [dedup check]
  3. For each enabled source in SCRAPING_SOURCES:

     LinkedIn:
       ├─ Build search URL with LINKEDIN_SEARCH_QUERIES, location, geo_id
       ├─ HTTP GET with rotating user-agent + retry logic
       ├─ Parse HTML → extract job cards (id, title, company, location, url)
       ├─ For each job card not in existing sets:
       │    └─ Fetch job detail page → extract full description
       └─ Collect up to MAX_JOBS_PER_SEARCH['linkedin'] (default: 2)

     JSearch (RapidAPI):
       ├─ POST /search with query, date_posted, remote_only params
       ├─ Parse JSON response
       └─ Collect up to MAX_JOBS_PER_SEARCH['jsearch'] (default: 10)

     USAJobs (federal API):
       ├─ GET /search with keyword, location, radius, date params
       ├─ Auth: X-App-AuthKey + X-App-Email headers
       ├─ Parse JSON → extract MatchedObjectDescriptor fields
       └─ Collect up to MAX_JOBS_PER_SEARCH['usajobs'] (default: 10)

     CareersFuture (Singapore API):
       ├─ GET with search, categories, employment_type params
       └─ Collect up to MAX_JOBS_PER_SEARCH['careers_future'] (default: 10)

  4. UPSERT all collected jobs into jobs table:
       status='new', resume_score=NULL, is_active=TRUE
       (conflict on job_id → update metadata, preserve score/status)
```

### 2. Scoring — every 4 hours

```
Claude Code routine: job-scraper-score
  └─▶ gh workflow run score_jobs.yml

score_jobs.py Phase 1 — Initial scoring:
  1. Load base_resume from base_resume table
  2. Format resume to plain text (format_resume_to_text)
  3. If PRE_FILTER_ENABLED:
       a. Fetch JOBS_TO_SCORE × PRE_FILTER_FETCH_MULTIPLIER unscored jobs
       b. Send each to PRE_FILTER_MODEL (claude-haiku) for fast relevance check
       c. Mark irrelevant jobs as resume_score_stage='pre_filtered', score=0
       d. Keep relevant subset (up to JOBS_TO_SCORE_PER_RUN = 20)
     Else:
       a. Fetch up to 20 jobs WHERE status='new' AND resume_score IS NULL
  4. For each job → LLM prompt:
       Input:  resume text + job description
       Output: integer score 0–100
       Model:  LLM_MODEL (default: anthropic/claude-sonnet-4-5)
  5. UPDATE jobs SET resume_score=N, resume_score_stage='initial'

score_jobs.py Phase 2 — Re-score with custom resume:
  1. RPC get_jobs_for_rescore() →
       jobs WHERE customized_resume_id IS NOT NULL
            AND resume_score_stage='initial'
            AND is_interested != FALSE
  2. For each: load customized resume, re-score with tailored content
  3. UPDATE jobs SET resume_score=N, resume_score_stage='custom'
```

### 3. Resume Customization — every 6 hours

```
Claude Code routine: job-scraper-customize
  └─▶ gh workflow run hourly_resume_customization.yml

custom_resume_generator.py:
  1. RPC get_jobs_for_resume_generation_custom_sort() →
       jobs WHERE resume_score >= 50
            AND customized_resume_id IS NULL
            AND status = 'new'
       Limit: JOBS_TO_CUSTOMIZE_PER_RUN (default: 1)

  2. Load base_resume from Supabase → parse to Resume Pydantic model

  3. For the selected job, personalize each resume section:
     ┌─ summary:    LLM rewrites professional summary for this role
     ├─ skills:     LLM reorders/filters skills to match JD keywords
     ├─ experience: LLM rewrites each bullet to emphasize relevant work
     └─ projects:   LLM highlights projects most relevant to the role
     Each section uses structured output (SummaryOutput, SkillsOutput, etc.)

  4. Assemble updated Resume Pydantic object

  5. pdf_generator.py (ReportLab):
       ├─ Render contact header, summary, skills, experience, projects
       ├─ ATS-optimized layout (no tables, standard fonts)
       └─ Return PDF bytes

  6. Upload to personalized_resumes/resume_{job_id}.pdf in Supabase Storage

  7. INSERT into customized_resumes → returns uuid

  8. UPDATE jobs:
       customized_resume_id = uuid
       status = 'resume_generated'
```

### 4. Job Management — 1:00 PM daily

```
Claude Code routine: job-scraper-manage
  └─▶ gh workflow run job_manager.yml

job_manager.py:
  1. mark_expired_jobs()
       WHERE scraped_at < NOW() - JOB_EXPIRY_DAYS (30d)
       AND status NOT IN ('applied','interviewing','offer','rejected')
       → UPDATE status='expired'

  2. check_linkedin_job_activity()
       WHERE provider='linkedin' AND is_active=TRUE
       AND last_checked < NOW() - JOB_CHECK_DAYS (3d)
       Limit: JOB_CHECK_LIMIT (50 per run)
       For each:
         HTTP HEAD to LinkedIn job URL with timeout
         404 / redirect away → UPDATE is_active=FALSE
         200 → UPDATE last_checked=NOW()

  3. delete_old_inactive_jobs()
       WHERE is_active=FALSE
       AND scraped_at < NOW() - JOB_DELETION_DAYS (60d)
       → UPDATE status='deleted' (soft delete, row preserved)
```

---

## Tech Stack

### Backend (job-scraper)

| Component | Technology | Purpose |
|---|---|---|
| Language | Python 3.11.9 | Runtime |
| HTTP client | `requests`, `httpx` | Scraping and API calls |
| HTML parsing | `BeautifulSoup4` | LinkedIn HTML extraction |
| Browser automation | `Playwright` | JS-rendered pages |
| PDF extraction | `pdfplumber` | Parse base resume PDF |
| PDF generation | `ReportLab` | Generate tailored PDFs |
| LLM abstraction | `LiteLLM` | Route to any LLM provider |
| Data validation | `Pydantic v2` | Resume/job data models |
| Database | `supabase-py` | Supabase client |
| CI/CD | GitHub Actions | Workflow runner |
| Scheduling | Claude Code routines | Cron trigger layer |

### LLM Integration (LiteLLM)

All LLM calls route through `llm_client.py` which wraps LiteLLM with:
- Rate limiting: `LLM_MAX_RPM` (10 req/min)
- Exponential backoff: `LLM_MAX_RETRIES` (3), base delay 10s
- Request delay: 8s between calls
- Structured output: Pydantic models passed as response schema

| Task | Model | Notes |
|---|---|---|
| Pre-filtering | `anthropic/claude-haiku-4-5-20251001` | Fast, cheap relevance check |
| Scoring | `anthropic/claude-sonnet-4-5` (default) | Configurable via LLM_MODEL |
| Resume parsing | LLM_MODEL | Structured JSON extraction |
| Resume tailoring | LLM_MODEL | One section at a time |

Model names use LiteLLM provider prefix (e.g. `anthropic/`, `gemini/`, `openai/`). Swap providers by changing `LLM_MODEL` in `config.py`.

### Frontend (jobs-scraper-web)

| Component | Technology | Version |
|---|---|---|
| Framework | Next.js | 16.1.6 |
| UI library | React | 19.2.4 |
| Language | TypeScript | 5.9.3 |
| Styling | Tailwind CSS | 4.1.5 |
| Icons | Lucide React | 0.577.0 |
| PDF viewing | react-pdf | 10.4.1 |
| PDF generation | PDFKit (server-side) | 0.17.2 |
| Markdown | react-markdown + remark-gfm | 10.1.0 |
| DB client | @supabase/supabase-js | 2.99.0 |
| SSR auth | @supabase/ssr | 0.9.0 |
| HTTP | axios | 1.9.0 |

---

## Pydantic Models

All shared between `resume_parser.py`, `score_jobs.py`, and `custom_resume_generator.py`.

```
Resume
├── name, email, phone, location (str)
├── summary (str)
├── skills (list[str])
├── education (list[Education])
│     └── degree, field_of_study, institution, start_year, end_year
├── experience (list[Experience])
│     └── job_title, company, location, start_date, end_date, description
├── projects (list[Project])
│     └── name, description, technologies (list[str])
├── certifications (list[Certification])
│     └── name, issuer, year
├── languages (list[str])
└── links (Links)
      └── linkedin, github, portfolio

LLM structured output models:
  SummaryOutput         → summary: str
  SkillsOutput          → skills: list[str]
  ExperienceListOutput  → experience: list[Experience]
  SingleExperienceOutput→ experience: Experience
  ProjectListOutput     → projects: list[Project]
  SingleProjectOutput   → project: Project
  ValidationResponse    → is_valid: bool, reason: str
```

---

## Frontend Routes

| Route | Component | Purpose |
|---|---|---|
| `/` | Dashboard | Stats overview — job counts by state/provider |
| `/jobs/new` | — | Unscored/new listings |
| `/jobs/top-matches` | TopMatchesList | Filtered/sorted scored jobs |
| `/jobs/applied` | AppliedJobsList | Application history |
| `/jobs/[job_id]` | JobDetailsClient | Job detail + description |
| `/jobs/[job_id]/report` | — | Legitimacy and evaluation report |
| `/jobs/[job_id]/resumes/[id]` | — | View customized resume PDF |
| `/jobs/[job_id]/resumes/[id]/edit` | ResumeEditClient | Edit tailored resume |
| `/profile` | ProfileClient | Base resume management |

### API Routes

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/base-resume` | PATCH | Update base resume in Supabase |
| `/api/generate-resume` | POST | Server-side PDF generation (PDFKit) |
| `/api/customized_resumes/[id]` | GET | Fetch resume metadata |
| `/api/customized_resumes/[id]/signed-url` | GET | 1-hour signed download URL |
| `/api/jobs/[job_id]` | GET | Job details with related data |

---

## Configuration Reference

All settings live in `config.py`. Override via environment variables where noted.

### Supabase

| Setting | Default | Description |
|---|---|---|
| `SUPABASE_URL` | env | Project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | env | Admin key (bypasses RLS) |
| `SUPABASE_TABLE_NAME` | `jobs` | Primary table |
| `SUPABASE_STORAGE_BUCKET` | `personalized_resumes` | Custom resume PDFs |
| `SUPABASE_RESUME_STORAGE_BUCKET` | `resumes` | Base resume PDF |

### LLM

| Setting | Default | Description |
|---|---|---|
| `LLM_MODEL` | `anthropic/claude-sonnet-4-5` | Primary model (400+ via LiteLLM) |
| `PRE_FILTER_MODEL` | `anthropic/claude-haiku-4-5-20251001` | Fast pre-filter model |
| `PRE_FILTER_ENABLED` | `True` | Enable relevance pre-filtering |
| `PRE_FILTER_FETCH_MULTIPLIER` | `4` | Fetch 4× jobs, keep top fraction |
| `LLM_MAX_RPM` | `10` | Max requests per minute |
| `LLM_MAX_RETRIES` | `3` | Retry attempts on failure |
| `LLM_RETRY_BASE_DELAY` | `10` | Backoff base in seconds |
| `LLM_REQUEST_DELAY_SECONDS` | `8` | Delay between requests |

### Pipeline Volumes

| Setting | Default | Description |
|---|---|---|
| `JOBS_TO_SCORE_PER_RUN` | `20` | Max jobs scored per workflow run |
| `JOBS_TO_CUSTOMIZE_PER_RUN` | `1` | Max resumes generated per run |
| `MAX_JOBS_PER_SEARCH` | `{linkedin: 2, jsearch: 10, usajobs: 10, careers_future: 10}` | Per-source cap |

### Job Lifecycle

| Setting | Default | Description |
|---|---|---|
| `JOB_EXPIRY_DAYS` | `30` | Days before marking expired |
| `JOB_CHECK_DAYS` | `3` | Days between LinkedIn activity checks |
| `JOB_DELETION_DAYS` | `60` | Days inactive before soft-delete |
| `JOB_CHECK_LIMIT` | `50` | Max LinkedIn checks per job_manager run |

### Search (LinkedIn)

| Setting | Default | Description |
|---|---|---|
| `LINKEDIN_LOCATION` | `Atlanta Metropolitan Area` | Location string |
| `LINKEDIN_GEO_ID` | `90000539` | LinkedIn geo ID for Atlanta |
| `LINKEDIN_JOB_TYPE` | `F` | F=Full-time |
| `LINKEDIN_JOB_POSTING_DATE` | `r86400` | Past 24 hours |
| `LINKEDIN_F_WT` | `None` | `2` for remote-only |

---

## Secrets & Environment Variables

### GitHub Actions Secrets

| Secret | Required by | Purpose |
|---|---|---|
| `SUPABASE_URL` | all workflows | Database connection |
| `SUPABASE_SERVICE_ROLE_KEY` | all workflows | Admin DB access |
| `ANTHROPIC_API_KEY` | score, customize, parse | LLM calls via Anthropic |
| `LLM_API_KEY` | score, customize, parse | Primary LiteLLM key |
| `JSEARCH_API_KEY` | scrape | JSearch RapidAPI |
| `USAJOBS_API_KEY` | scrape | USAJobs API auth |
| `USAJOBS_API_EMAIL` | scrape | USAJobs user-agent header |

### Frontend (.env.local)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Public anon key (RLS-scoped) |
| `NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY` | Service role key (server-side only) |

---

## Scheduled Routines

All 4 routines live in `~/.claude/scheduled-tasks/` and run in the user's local timezone (EDT, UTC-4).

| Routine ID | Local Time | UTC Equivalent | Triggers |
|---|---|---|---|
| `job-scraper-scrape` | 6:00 AM daily | 10:00 UTC | `scrape_jobs.yml` |
| `job-scraper-score` | every 4 hours | every 4h UTC | `score_jobs.yml` |
| `job-scraper-customize` | every 6 hours | every 6h UTC | `hourly_resume_customization.yml` |
| `job-scraper-manage` | 1:00 PM daily | 17:00 UTC | `job_manager.yml` |

Each routine: `gh workflow run <name>.yml --repo lourock99/job-scraper --ref main`, then confirms the run started.

GitHub Actions workflows retain `workflow_dispatch` only — cron triggers removed after migrating to routines.

---

## Repository Structure

```
job-scraper/
├── .github/workflows/
│   ├── scrape_jobs.yml            # Daily scraping
│   ├── score_jobs.yml             # Quadrihourly scoring
│   ├── hourly_resume_customization.yml  # Six-hourly PDF generation
│   ├── job_manager.yml            # Daily cleanup
│   └── parse_resume.yml          # Manual resume parsing
├── supabase_setup/
│   └── init.sql                  # Full schema (tables, indexes, RPC functions)
├── docs/
│   └── ARCHITECTURE.md           # This file
├── config.py                     # All configuration and secrets
├── models.py                     # Pydantic data models
├── supabase_utils.py             # DB/storage CRUD layer
├── llm_client.py                 # LiteLLM wrapper with rate limiting
├── scraper.py                    # Multi-source job scraper
├── resume_parser.py              # PDF → structured JSON via LLM
├── score_jobs.py                 # LLM job scoring pipeline
├── custom_resume_generator.py    # LLM resume tailoring + PDF
├── pdf_generator.py              # ReportLab PDF renderer
├── job_manager.py                # Expiry / activity check / soft-delete
├── user_agents.py                # UA rotation for scraping
├── requirements.txt              # Python dependencies
└── README.md                     # Setup and usage guide

jobs-scraper-web/
├── src/
│   ├── app/
│   │   ├── page.tsx              # Dashboard
│   │   ├── layout.tsx            # Global layout + Navbar
│   │   ├── jobs/                 # Job browsing routes
│   │   │   ├── new/              # New listings
│   │   │   ├── top-matches/      # Scored + filtered view
│   │   │   ├── applied/          # Application history
│   │   │   └── [job_id]/         # Detail, report, resume views
│   │   ├── profile/              # Base resume management
│   │   └── api/                  # Server-side API routes
│   ├── components/
│   │   ├── Navbar.tsx
│   │   ├── CustomPdfViewer.tsx
│   │   ├── jobs/                 # Job list, filters, detail components
│   │   └── resume/               # Resume edit components
│   ├── lib/supabase/
│   │   ├── queries.ts            # All DB queries
│   │   └── storage.ts            # Signed URL generation
│   ├── utils/supabase/
│   │   ├── client.ts             # Browser Supabase client
│   │   └── server.ts             # Server Supabase client
│   └── types.ts                  # TypeScript types (Job, Resume, etc.)
└── .env.local                    # Supabase credentials
```
