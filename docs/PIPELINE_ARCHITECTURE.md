# Pipeline Architecture & Operations Guide

## Overview

The LeadFactory pipeline has been upgraded with a resilience-first architecture:
structured logging, retry logic, streaming database persistence, metrics
collection, centralized configuration, and a task-queue prototype for
decoupled stage execution.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     CrawlEngine (engine.py)                  │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Aggregator│→ │ Discovery│→ │Deep Crawl│→ │Enrichment│    │
│  └─────┬────┘  └─────┬────┘  └─────┬────┘  └─────┬────┘    │
│        │             │             │             │           │
│        ▼             ▼             ▼             ▼           │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              LeadStore (pipeline/lead_store.py)       │    │
│  │   Streaming writes → DB dedup → fallback to memory   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌──────────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │ PipelineMetrics│ │ Retry    │  │ Structured Logging │    │
│  │ (CSV+Prometheus)│ │ Decorator│  │ (JSON / Text)      │    │
│  └──────────────┘  └──────────┘  └────────────────────┘    │
└──────────────────────────────────────────────────────────────┘

        ┌────────────────────────────────────────┐
        │   Celery Task Queue (pipeline/tasks.py) │
        │   Independent stage execution & retry   │
        └────────────────────────────────────────┘
```

## Configuration

All settings are centralized in `config/settings.py` using Pydantic BaseSettings.
Every setting maps to an environment variable and has a sensible default.

### Key Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CONCURRENCY` | 10 | Max concurrent browser instances |
| `SMTP_CONCURRENCY` | 20 | Max concurrent SMTP connections |
| `SMTP_TIMEOUT` | 10 | SMTP connection timeout (seconds) |
| `MAX_RETRIES` | 3 | Retry attempts for transient errors |
| `RETRY_BASE_DELAY` | 1.0 | Base delay for exponential backoff |
| `STALE_DAYS` | 7 | Days before re-crawling a domain |
| `DATABASE_URL` | sqlite:///data/leadfactory.db | Database connection string |
| `LOG_LEVEL` | INFO | Logging level |
| `LOG_FORMAT` | json | Log format: `json` or `text` |
| `LOG_FILE` | (empty) | Optional log file path |
| `METRICS_ENABLED` | true | Enable metrics collection |
| `METRICS_PORT` | 9090 | Prometheus exporter port |
| `METRICS_FILE` | data/metrics/pipeline_metrics.csv | CSV metrics output |
| `CELERY_BROKER_URL` | redis://localhost:6379/0 | Celery broker |
| `LEAD_BATCH_SIZE` | 100 | DB write batch size |
| `TARGET_LEAD_COUNT` | 30000 | Target lead volume |

### Overriding Settings

```bash
# Via environment variable
export CONCURRENCY=20
export LOG_FORMAT=text
python engine.py --deep --discover

# Via .env file (auto-loaded)
echo "CONCURRENCY=20" >> .env

# Via CLI (some settings have CLI equivalents)
python engine.py --concurrency 20 --log-format text
```

## Structured Logging

Logs are JSON-formatted by default for easy aggregation (ELK, Datadog, etc.):

```json
{
  "ts": "2024-01-15T10:30:00+00:00",
  "level": "INFO",
  "logger": "crawl.engine",
  "msg": "Stage completed: discovery in 45.2s (leads=420, errors=0)",
  "phase": "discovery",
  "run_id": "20240115_103000",
  "duration_s": 45.2,
  "lead_count": 420,
  "error_count": 0
}
```

Switch to human-readable format:
```bash
python engine.py --log-format text
```

### Context Fields

All log records include contextual fields:
- `run_id` — unique pipeline execution ID
- `phase` — current pipeline stage
- `adapter` — site adapter name (during crawl)
- `domain` — domain being processed
- `lead_count`, `error_count`, `duration_s`

## Error Handling & Retries

### Per-Stage Isolation

Every pipeline stage is wrapped in try/except with:
- Structured error logging with context
- Error count tracking for metrics
- Graceful degradation (one stage failure doesn't kill the pipeline)

### Retry Decorator

The `@retry_async` decorator handles transient errors with exponential backoff:

```python
from pipeline.retry import retry_async

@retry_async(max_retries=3, base_delay=1.0)
async def fetch_page(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()
```

Retryable exceptions: `ConnectionError`, `TimeoutError`, `OSError`,
`aiohttp.ClientError`.

### Greyhat Module Isolation

Each of the 8 greyhat enrichment modules runs in its own try/except.
A DNS harvester failure won't prevent GitHub mining from running.

## Database Persistence

### Streaming Lead Store

Leads are persisted incrementally via `pipeline/lead_store.py` instead of
accumulating in memory:

1. Leads are written to `pipeline_leads` table as each stage produces them
2. Deduplication happens at the DB level via unique constraint on
   `(name_normalized, fund_normalized)`
3. Falls back to in-memory storage if DB is unavailable

### New Database Tables

**`pipeline_leads`** — Incremental lead storage
- Unique constraint: `(name_normalized, fund_normalized)`
- Indexes: `email`, `run_id`, `(email, fund_normalized)`

**`pipeline_runs`** — Run observability
- Tracks: run_id, status, duration, lead/email/error counts, stages completed

### Updated Constraints on `leads` Table

- New index: `(name, fund)` for fast dedup lookups
- New unique index: `(email, fund)` to prevent duplicate contacts per fund

## Metrics

### CSV Metrics (Always On)

Pipeline metrics are appended to `data/metrics/pipeline_metrics.csv`:

```csv
run_id,timestamp,stage,duration_s,lead_count,error_count
20240115_103000,2024-01-15T10:30:45,aggregation,12.3,1500,0
20240115_103000,2024-01-15T10:31:30,discovery,45.2,420,0
20240115_103000,2024-01-15T10:35:00,deep_crawl,210.5,3200,2
20240115_103000,2024-01-15T10:40:00,enrichment,300.1,4500,1
20240115_103000,2024-01-15T10:40:00,_run_total,567.8,4500,3
```

### Prometheus (Optional)

If `prometheus_client` is installed:

```bash
pip install prometheus_client
export METRICS_PORT=9090
python engine.py --deep --discover
# → Prometheus metrics at http://localhost:9090
```

Exposed metrics:
- `pipeline_stage_duration_seconds{stage}`
- `pipeline_stage_lead_count{stage}`
- `pipeline_stage_errors_total{stage}`
- `pipeline_total_leads`

## Task Queue (Celery)

### Setup

```bash
# Start Redis
docker run -d -p 6379:6379 redis

# Start Celery worker
celery -A pipeline.tasks worker --loglevel=info

# Trigger a full pipeline run
python -c "from pipeline.tasks import run_full_pipeline; run_full_pipeline.delay()"
```

### Individual Stage Execution

```python
from pipeline.tasks import (
    run_aggregation,
    run_discovery,
    run_deep_crawl,
    run_enrichment,
    run_portfolio_scrape,
)

# Run one stage
result = run_aggregation.delay()
print(result.get())  # {"stage": "aggregation", "lead_count": 1500, "status": "completed"}

# Chain stages
from celery import chain
workflow = chain(
    run_aggregation.si(),
    run_discovery.si(),
    run_deep_crawl.si(concurrency=20, headless=True),
    run_enrichment.si(),
)
workflow.apply_async()
```

### Task Configuration

- Soft time limit: 1 hour per task
- Hard time limit: 2 hours per task
- Max retries: 2-3 per task (with 60s delay)
- Late ACK: tasks acknowledged only after completion

## Troubleshooting

### Pipeline Fails Silently

1. Check logs: `tail -f pipeline.log` (if `--log-file` set)
2. Check metrics CSV: `cat data/metrics/pipeline_metrics.csv`
3. Check pipeline_runs table for error counts

### High Memory Usage

Ensure streaming persistence is active (DB available). If fallback to
in-memory, check `DATABASE_URL` and database connectivity.

### Slow Deep Crawl

- Increase `CONCURRENCY` (default: 10)
- Use `--incremental` to skip recently-crawled domains
- Check `data/metrics/pipeline_metrics.csv` for per-stage timings

### Enrichment Module Failures

Each greyhat module logs independently. Search logs by stage:
```bash
# JSON logs
cat pipeline.log | jq 'select(.phase == "greyhat" and .level == "ERROR")'

# Text logs
grep "greyhat.*ERROR" pipeline.log
```

### Resuming from Checkpoint

If the pipeline crashes mid-enrichment:
```bash
python engine.py --resume data/enriched/checkpoint_guesser.csv
```

This skips aggregation/crawl and resumes from the last checkpoint.
