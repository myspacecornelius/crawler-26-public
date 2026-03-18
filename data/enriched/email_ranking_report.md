# Email Ranking Report
Generated: 2026-03-17 23:02

## Methodology

Email candidates are ranked using deterministic evidence only — no SMTP, no paid APIs.

### Evidence hierarchy (highest trust first)

| Source | Description | Confidence |
|--------|-------------|------------|
| `scraped` | Email directly scraped from company website | 0.90–0.98 |
| `domain_lock` | 2+ scraped emails from same domain confirm pattern | 0.70–0.92 |
| `domain_hint` | 1 scraped email establishes pattern for domain | 0.50–0.75 |
| `base_rate` | Global VC corpus statistics (n=361 scraped emails) | 0.02–0.41 |

### Global VC email pattern base rates
Derived from 12510 real scraped emails in this corpus:

| Pattern | Rate |
|---------|------|
| `{first}@domain` | 41% |
| `{f}{last}@domain` | 26% |
| `{last}@domain` | 14% |
| `{first}.{last}@domain` | 5% |
| other | 14% |

> **Note:** The default guesser pattern `first.last@` is only 5% of real VC emails.
> The most common is `first@` (41%). Rankings correct for this.

### MX penalty
Domains with no MX record receive a 0.3x confidence multiplier (can't receive email).

### Collapse strategy
Each person is reduced to their top-1 candidate in `investor_leads_ranked.csv`
and top-2 in `investor_leads_top_candidates.csv`.

---

## Results

### Totals

| Metric | Count |
|--------|-------|
| Total people | 12523 |
| Domains with observed pattern | 58 |
| Domains with MX record | 531 / 546 |
| Domains without MX (penalised) | 15 |

### Confidence tiers (top-1 per person)

| Tier | Count | Criteria |
|------|-------|---------|
| HIGH | 1183 | Score ≥ 0.75 — domain pattern confirmed |
| MEDIUM | 11214 | Score 0.40–0.74 — single observation or strong base rate |
| LOW | 113 | Score < 0.40 — base rate only, no domain signal |

### Pattern source breakdown

| Source | Count |
|--------|-------|
| Scraped ground truth | 367 |
| Domain lock (2+ obs.) | 882 |
| Domain hint (1 obs.) | 763 |
| Base rate only | 10498 |

### Pattern distribution in output

| Pattern | Assigned |
|---------|---------|
| `{first}@{domain}` | 11066 |
| `{f}{last}@{domain}` | 1035 |
| `{first}.{last}@{domain}` | 136 |
| `{last}@{domain}` | 121 |
| `{first}{last}@{domain}` | 83 |
| `other` | 69 |


---

## Files

| File | Description |
|------|-------------|
| `investor_leads_ranked.csv` | Top-1 email per person, with confidence score |
| `investor_leads_top_candidates.csv` | Top-2 emails per person |
| `email_ranking_report.md` | This report |
