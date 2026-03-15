# CI, Testing & Analytics — Developer Guide

## 1. CI Pipeline (`.github/workflows/ci.yml`)

The CI pipeline runs on every push and pull request to `main`, `master`, `develop`, and `claude/*` branches.

### Jobs

| Job | What it does | Matrix |
|-----|-------------|--------|
| **lint** | `black --check` + `flake8` | Python 3.11, 3.12 |
| **typecheck** | `mypy` on `enrichment/`, `api/`, `adapters/` | Python 3.12 |
| **test** | `pytest` with coverage (XML + terminal) | Python 3.11, 3.12 |
| **security** | `pip-audit --strict` | Python 3.12 |
| **frontend** | `next lint` + `tsc --noEmit` + `jest` | Node 20 |

### Running Locally

```bash
# Install dev dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run tests with coverage
pytest tests/ --cov=enrichment --cov=api --cov=adapters --cov-report=term-missing

# Check formatting
black --check .

# Lint
flake8 .

# Type check
mypy enrichment/ api/ adapters/ --ignore-missing-imports

# Security scan
pip-audit --strict --desc
```

### Dependabot

Automated dependency updates are configured in `.github/dependabot.yml` for both `pip` and `npm` (dashboard).

---

## 2. Testing Strategy

### Test Organisation

All tests live in `tests/` and follow the naming convention `test_*.py`.

| File | Coverage Area |
|------|--------------|
| `test_email_validation_v2.py` | EmailValidator cascading checks (format, disposable, role, MX) |
| `test_email_validator_v2.py` | EmailValidator SMTP, batch, and deep validation |
| `test_email_guesser_v2.py` | EmailGuesser pattern learning, detection, and statistics |
| `test_scoring_v2.py` | LeadScorer and MLLeadScorer scoring logic |
| `test_adapters_v2.py` | Adapter base class, deduplication, helpers |
| `test_analytics.py` | PipelineAnalytics stage/run tracking |
| `test_api_analytics.py` | Analytics API endpoint responses |
| `test_crm.py` | CRM integration (HubSpot, Salesforce) |
| `test_dedup.py` | Deduplication logic |
| `test_email_discovery.py` | Email pattern matching |
| `test_email_waterfall.py` | Multi-provider email fallback |
| `test_engine_integration.py` | Full pipeline integration |

### Fixtures (conftest.py)

- `sample_lead` — single `MockInvestorLead` with defaults
- `sample_leads` — batch of 5 leads with varying attributes
- `email_validator` — fresh `EmailValidator` instance

### Running Tests

```bash
# All tests
pytest tests/ -v

# Specific module
pytest tests/test_email_validation_v2.py -v

# With coverage
pytest tests/ --cov=enrichment --cov-report=html

# Parallel execution
pytest tests/ -n auto  # requires pytest-xdist
```

---

## 3. Email Validation Architecture

### Cascading Validation Strategy

```
Email input
  │
  ├── 1. Format check (regex) ──→ invalid? STOP → quality="invalid"
  │
  ├── 2. Disposable domain check ──→ disposable? STOP → quality="low"
  │      (config/email_validation.yaml)
  │
  ├── 3. Role-based prefix check ──→ role-based? STOP → quality="medium"
  │      (config/email_validation.yaml)
  │
  ├── 4. MX record check (DNS) ──→ no MX? → quality="low"
  │      (cached per domain)     ──→ DNS error? → quality="medium" + retry flag
  │
  └── 5. All passed → quality="high"
```

### Configuration

Disposable domains and role prefixes are centralised in `config/email_validation.yaml`. Update the lists there without code changes.

### Pattern Learning (EmailGuesser)

The EmailGuesser v3 uses a `PatternStore` that:
1. Records all observed email patterns per domain with frequency counts
2. Persists patterns to `data/email_patterns.json`
3. Selects the most frequent pattern for future guesses
4. Exposes statistics via `guesser.pattern_statistics`

---

## 4. ML Lead Scoring

### Overview

The ML scorer uses scikit-learn gradient boosting to rank leads. It falls back to the rule-based `LeadScorer` when the model is not available or confidence is below threshold.

### Features

| Feature | Type | Source |
|---------|------|--------|
| `stage_encoded` | int | Stage → ordinal (pre-seed=0 .. late-stage=5) |
| `sector_count` | int | Number of focus areas |
| `sector_*` | binary | Presence of specific sector keywords |
| `has_email` | binary | Email available |
| `email_verified` | binary | Email status = verified |
| `has_linkedin` | binary | LinkedIn URL present |
| `role_encoded` | ordinal | Role seniority (intern=0 .. partner=4) |
| `check_size_*` | float | Normalised check size range |
| `times_seen` | int | Cross-run observation count |
| `days_since_scraped` | int | Lead freshness |

### Training

```bash
pip install scikit-learn pandas joblib

python scripts/train_ml_scorer.py \
  --input data/enriched/investor_leads_master.csv \
  --output models/lead_scorer.joblib \
  --model-type gradient_boosting
```

Options for `--model-type`: `gradient_boosting`, `logistic_regression`, `random_forest`.

The script outputs:
- `models/lead_scorer.joblib` — serialised model pipeline
- `models/lead_scorer.json` — training metadata (accuracy, features, etc.)

### Integration

The ML scorer is integrated into the enrichment pipeline:
1. Try ML prediction first
2. If confidence < threshold (default 0.3) or model unavailable → fall back to rule-based scorer
3. Both scores are available via the API

### Retraining

1. Export fresh leads: `GET /api/leads/export`
2. Run training script with new data
3. Replace `models/lead_scorer.joblib`
4. Restart the API (model is loaded on init)

---

## 5. Analytics & Metrics

### Pipeline Analytics

The `PipelineAnalytics` class in `enrichment/analytics.py` tracks:
- Run-level metrics (duration, leads discovered, emails generated)
- Stage-level metrics (duration, success/failure counts, errors)
- Email bounce rates
- Global counters across all runs

### API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/analytics/pipeline` | Aggregate summary across all runs |
| `GET /api/analytics/pipeline/current` | Current in-progress run |
| `GET /api/analytics/pipeline/history?limit=N` | Recent completed runs |
| `GET /api/analytics/email-patterns` | Email pattern learning statistics |
| `GET /api/analytics/ml-scorer` | ML model status and prediction counts |
| `GET /api/analytics/email-validation` | Validator cache statistics |

### Usage in Pipeline

```python
from enrichment.analytics import pipeline_analytics

pipeline_analytics.start_run("run-001")
pipeline_analytics.start_stage("discovery")
# ... do work ...
pipeline_analytics.record_success("discovery", count=50)
pipeline_analytics.end_stage("discovery")
pipeline_analytics.end_run()

summary = pipeline_analytics.get_summary()
```

### Extending with Prometheus

The analytics data can be exported to Prometheus by creating a `/metrics` endpoint that formats the data as Prometheus text exposition format. The `get_summary()` method returns all the data needed.

---

## 6. File Reference

```
.github/
  workflows/ci.yml        # CI pipeline
  dependabot.yml           # Automated dependency updates
config/
  email_validation.yaml    # Disposable domains, role prefixes, validation settings
  scoring.yaml             # Rule-based scoring weights and tiers
enrichment/
  email_validator.py       # Cascading email validator with MX integration
  email_guesser.py         # Pattern-learning email guesser (v3)
  scoring.py               # Rule-based lead scorer
  ml_scorer.py             # ML lead scorer with fallback
  analytics.py             # Pipeline analytics collector
api/routers/
  analytics.py             # Analytics API endpoints
models/                    # Trained ML model storage
scripts/
  train_ml_scorer.py       # ML model training script
tests/
  conftest.py              # Shared fixtures
  test_email_validation_v2.py  # Validator tests
  test_email_guesser_v2.py     # Guesser pattern tests
  test_scoring_v2.py           # Scoring tests
  test_adapters_v2.py          # Adapter tests
  test_analytics.py            # Analytics tests
  test_api_analytics.py        # API endpoint tests
pyproject.toml             # Tool configuration (black, mypy, etc.)
requirements-dev.txt       # Dev/CI dependencies
```
