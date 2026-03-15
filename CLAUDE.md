# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LeadFactory is an autonomous investor lead generation platform that discovers, enriches, and activates investor contacts (VCs, PE, family offices) from public web sources. It combines a Python crawling/enrichment pipeline with a Next.js dashboard and FastAPI backend.

## Commands

### Python pipeline
```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
playwright install chromium

# Run full pipeline
python engine.py --deep --headless --force-recrawl

# Run tests
python -m pytest tests/ -x -q
python -m pytest tests/test_adapter_registry.py -v   # single test file

# Lint (matches CI)
pylint $(git ls-files '*.py')

# Start API server
LEADFACTORY_SECRET_KEY=dev-secret uvicorn api.main:app --reload
```

### Dashboard (Next.js)
```bash
cd dashboard && npm install && npm run dev    # localhost:3000
npm run build
npm run lint
```

### Landing page
```bash
cd landing && npm install && npm run dev      # localhost:3001
```

## Architecture

The system is a 4-stage pipeline orchestrated by `engine.py`:

```
Discovery → Enrichment → Scoring/Dedup → Platform (API + Dashboard + Outreach + CRM)
```

### Core pipeline (Python, root level)

- **engine.py** — Main orchestrator (~2000 lines). Wires discovery, deep crawl, enrichment, scoring, and output. CLI flags: `--discover`, `--deep`, `--headless`, `--dry-run`, `--force-recrawl`, `--skip-smtp`, `--portfolio`, `--incremental`, `--stale-days`.
- **deep_crawl.py** — Playwright-based website crawler (~1800 lines). Finds team pages via keyword detection, extracts names/roles/emails with JS rendering. Uses circuit breaker and domain concurrency limiting.

### Key modules

- **adapters/** — Site-specific extractors (OpenVC, AngelMatch, Crunchbase, etc.). Each adapter extends `BaseSiteAdapter` from `adapters/base.py`. The `InvestorLead` dataclass in `base.py` is the core data model that flows through the entire pipeline. New adapters follow `adapters/ADAPTER_GUIDE.md`.
- **adapters/registry.py** — Plugin auto-discovery via `ADAPTER_NAME` class attribute.
- **enrichment/** — Multi-layer email discovery and validation:
  - `email_guesser.py` — 8 pattern-based generators
  - `email_validator.py` — MX lookup + SMTP verification
  - `email_waterfall.py` — Multi-provider fallback (Hunter → ZeroBounce → MillionVerifier)
  - `scoring.py` — Weighted lead ranking (stage 30%, sector 25%, check_size 20%, portfolio 15%, recency 10%). Config in `config/scoring.yaml`.
  - `dedup.py` — Cross-run deduplication with email quality hierarchy. State in `data/dedup_index.json`.
  - Additional enrichers: `dns_harvester`, `google_dorker`, `github_miner`, `sec_edgar`, `wayback_enricher`, `gravatar_oracle`, `pgp_keyserver`, `catchall_detector`, `portfolio_scraper`
- **discovery/** — Search-based lead finding via `multi_searcher.py` (Google, Bing, DuckDuckGo)
- **sources/** — Lead aggregation from seed DB, GitHub lists, directory scrapers
- **scraping/** — Resilience layer: `circuit_breaker.py`, `domain_limiter.py`, `metrics.py`
- **stealth/** — Anti-detection: browser fingerprint rotation, human-like behavior simulation, proxy management
- **output/** — CSV export with checkpoints, Discord/Slack webhooks

### API (FastAPI)

- **api/main.py** — Entry point. CORS allows localhost:3000 and :5173.
- **api/models.py** — SQLAlchemy async ORM. PostgreSQL (prod) or SQLite (dev). Core tables: User, Campaign, Lead, ApiKey, CreditTransaction.
- **api/routers/** — REST endpoints: users, campaigns, leads, outreach, crm, billing (Stripe), portfolio, verticals.

### Dashboard (Next.js 14 + TypeScript)

Located in `dashboard/`. Uses Tailwind CSS, Recharts for charts, Radix UI primitives. Pages under `app/dashboard/` for campaigns, outreach, CRM, portfolio, settings, verticals.

### Configuration

- **config/sites.yaml** — Per-site scraping rules with CSS selectors and pagination config
- **config/scoring.yaml** — Lead scoring weights and tier thresholds
- **config/proxies.yaml** — Proxy rotation pool
- **config/search.yaml** — Search engine query templates

## Environment Variables

Required: `LEADFACTORY_SECRET_KEY` (JWT signing)

Optional: `DATABASE_URL` (defaults to SQLite), `STRIPE_SECRET_KEY`, `INSTANTLY_API_KEY`, `SMARTLEAD_API_KEY`, `SERPAPI_KEY`, `GITHUB_TOKEN`

## CI

GitHub Actions runs `pylint` on all Python files on every push (`.github/workflows/pylint.yml`, Python 3.14).
