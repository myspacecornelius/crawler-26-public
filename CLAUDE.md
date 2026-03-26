# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

LeadFactory — a full-stack VC lead generation and outreach platform. Discovers investor contacts across fund websites, enriches them through a multi-layer email pipeline, scores/deduplicates leads, and delivers them through a dashboard with campaign management, outreach integrations, and CRM push.

## Commands

### Python pipeline

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
playwright install chromium

# Run full pipeline
python engine.py --deep --headless --force-recrawl

# Tests
python -m pytest tests/ -x -q
python -m pytest tests/test_dedup.py -v          # single file
python -m pytest tests/test_dedup.py::test_name   # single test

# Lint (CI runs this on every push, must score ≥7.0)
pylint $(git ls-files '*.py') --fail-under=7.0

# Database migrations
alembic upgrade head
```

### API server (FastAPI)

```bash
LEADFACTORY_SECRET_KEY=dev-secret uvicorn api.main:app --reload --port 8000
# Docs at http://localhost:8000/api/docs
```

### Dashboard (Next.js)

```bash
cd dashboard && npm install && npm run dev    # localhost:3000
npm run build
npm run lint
```

### Landing page (Next.js)

```bash
cd landing && npm install && npm run dev      # localhost:3001
npm run build
```

## Code Style

Python: black (line-length 120), isort (black profile), flake8 (120 chars, ignores E203/W503/E501). Config in `pyproject.toml`. Target Python 3.11–3.12.

TypeScript/React: Next.js defaults, Tailwind CSS, no custom ESLint overrides beyond Next.js built-in.

## Architecture

### Pipeline (4 stages, orchestrated by `engine.py`)

```
Discovery → Deep Crawl → Enrichment → Scoring/Dedup → CSV + DB
```

1. **Discovery** (`sources/aggregator.py`, `discovery/`) — aggregates fund URLs from seed CSVs, GitHub lists, HTTP directory scrapers, and search engines
2. **Deep Crawl** (`deep_crawl.py`) — Playwright-based crawler that detects team pages via keyword matching, renders JS, extracts names/roles. Uses circuit breaker (`scraping/circuit_breaker.py`) and domain rate limiting (`scraping/domain_limiter.py`)
3. **Enrichment** (`enrichment/`) — 12+ enrichers (DNS harvest, Google dorking, GitHub mining, SEC EDGAR, Wayback, PGP keyserver, Gravatar, etc.) feed into email guesser (8 pattern generators with per-domain learning) → validator (format + MX + SMTP RCPT TO) → waterfall (Hunter → ZeroBounce → MillionVerifier)
4. **Scoring/Dedup** (`enrichment/scoring.py`, `enrichment/dedup.py`) — weighted scoring (stage 30%, sector 25%, check-size 20%, portfolio 15%, recency 10%) → tier assignment (HOT ≥80, WARM ≥60, COOL ≥40, COLD <40). Two-pass dedup: name+fund merge, then email-based. Weights configured in `config/scoring.yaml`

### Core data model

`InvestorLead` dataclass in `adapters/base.py` — flows through the entire pipeline. All site adapters extend `BaseSiteAdapter` (same file) and implement `parse_card()`.

### Adapter plugin system

Adapters in `adapters/` are auto-discovered via `ADAPTER_NAME` class attribute — no manual registry. Site-specific CSS selectors and pagination rules live in `config/sites.yaml`. See `adapters/ADAPTER_GUIDE.md` for the template.

### API layer (`api/`)

FastAPI with async SQLAlchemy. SQLite for dev (`data/leadfactory.db`), PostgreSQL for prod (set `DATABASE_URL`). JWT auth, Stripe billing, SlowAPI rate limiting. 12 routers mounted in `api/main.py` covering users, campaigns, leads, outreach (Instantly/SmartLead), CRM (HubSpot/Salesforce), billing, portfolio, verticals, config, metrics, notifications, analytics.

### Dashboard (`dashboard/`)

Next.js + React 18 + Tailwind + Radix UI + Recharts + Framer Motion. Typed API client in `dashboard/lib/api.ts` stores JWT in localStorage, auto-redirects to `/login` on 401. Dashboard pages are under `app/dashboard/` with sidebar layout.

### Landing page (`landing/`)

Next.js 14 marketing site ("Honeypot"). Design direction documented in `.claude/LAYOUT.MD` — honeycomb motif used sparingly, warm editorial palette, interactive product demos. Key design tokens and motion specs are in that file.

### Pipeline resilience (`pipeline/`)

- `pipeline/retry.py` — exponential backoff decorator
- `pipeline/lead_store.py` — streaming DB persistence with memory fallback
- `pipeline/logging.py` — structured JSON logging with PipelineContext
- `pipeline/metrics.py` — Prometheus/StatsD metrics
- `pipeline/tasks.py` — optional Celery/Redis async workers (degrades to threading)

### Stealth layer (`stealth/`)

Browser fingerprint rotation, human-like browsing patterns, proxy pool management. Configured via `config/proxies.yaml`.

## Key Configuration Files

- `config/scoring.yaml` — lead scoring weights, tiers, role modifiers
- `config/sites.yaml` — per-site CSS selectors, pagination rules, enabled/disabled flags
- `config/settings.py` — Pydantic BaseSettings, all env vars with defaults
- `.env.example` — environment variable template (copy to `.env`)

## Database

Migrations via Alembic (`alembic/versions/`). Core tables: users, campaigns, leads, api_keys, credit_transactions. Schema defined in `api/models.py` with cross-DB UUID compatibility.

## CI

GitHub Actions (`.github/workflows/pylint.yml`): runs `pylint --fail-under=7.0` on every push with Python 3.12.
