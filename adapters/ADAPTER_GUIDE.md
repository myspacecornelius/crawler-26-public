# Building New Adapters — Step-by-Step Guide

This guide walks you through creating a new site adapter for the CRAWL scraping framework.

## Overview

Adapters are plug-in modules that teach the crawler how to extract investor data from a specific website. The framework auto-discovers adapters from the `adapters/` directory — no changes to `engine.py` needed.

## Quick Start

### 1. Create Your Adapter File

Copy the template at `adapters/example_regional_vc.py` and rename it:

```bash
cp adapters/example_regional_vc.py adapters/my_site.py
```

### 2. Set Adapter Metadata

Every adapter needs class-level metadata for the registry:

```python
class MySiteAdapter(BaseSiteAdapter):
    ADAPTER_NAME = "my_site"          # Must match your sites.yaml entry
    VERTICALS = ["vc", "angel"]       # Investor types this site covers
    RATE_LIMIT_RPM = 20               # Max requests per minute
    REQUIRES_AUTH = False              # Does the site require login?
    REQUIRED_CREDENTIALS = []          # e.g., ["api_key", "session_cookie"]
```

### 3. Implement `parse_card()`

This is the only required method. It receives a BeautifulSoup Tag for each investor card and returns an `InvestorLead`:

```python
def parse_card(self, card) -> Optional[InvestorLead]:
    name = self._safe_text(card, self.selectors.get("name", "h3"))
    if not name or name == "N/A":
        return None

    return InvestorLead(
        name=name,
        email=self._extract_email(card),
        role=self._safe_text(card, self.selectors.get("role", "")),
        fund=self._safe_text(card, self.selectors.get("fund", "")),
        focus_areas=self._safe_list(card, self.selectors.get("focus_areas", "")),
        stage=self._safe_text(card, self.selectors.get("stage", "")),
        check_size=self._safe_text(card, self.selectors.get("check_size", "")),
        location=self._safe_text(card, self.selectors.get("location", "")),
        linkedin=self._safe_attr(card, self.selectors.get("linkedin", ""), "href"),
        website=self._safe_attr(card, self.selectors.get("website", ""), "href"),
    )
```

### 4. Add Site Configuration

Add an entry to `config/sites.yaml`:

```yaml
my_site:
  enabled: true
  url: "https://my-vc-directory.com/investors"
  adapter: "my_site"  # Must match ADAPTER_NAME
  description: "Description of the site"
  selectors:
    card: ".investor-card"        # CSS selector for each investor listing
    name: "h3.name"               # Name within the card
    email: "a[href^='mailto:']"   # Email link
    role: ".title"                # Job title
    fund: ".firm-name"            # Fund/firm name
    focus_areas: ".tag"           # Investment focus tags
    stage: ".stage"               # Investment stage
    check_size: ".check-size"     # Typical check size
    location: ".location"         # Geographic location
    linkedin: "a[href*='linkedin.com/in/']"
    website: "a[href*='http']:not([href*='linkedin'])"
  pagination:
    type: "load_more_button"      # or "infinite_scroll" or "numbered_pages"
    button_selector: "button.load-more"
    max_clicks: 50
    click_delay_ms: 2000
```

### 5. That's It!

The adapter registry auto-discovers your new adapter on startup. Run:

```bash
python engine.py --site my_site
```

## Helper Methods

`BaseSiteAdapter` provides these utilities for your `parse_card()`:

| Method | Description |
|--------|-------------|
| `_safe_text(card, selector)` | Extract text from a CSS selector, returns "N/A" if not found |
| `_safe_attr(card, selector, attr)` | Extract an attribute value from a CSS selector |
| `_safe_list(card, selector)` | Extract a list of text values from matching elements |
| `_extract_email(card)` | Multi-strategy email extraction (mailto links + regex) |

## Pagination Types

| Type | Description | Config Keys |
|------|-------------|-------------|
| `infinite_scroll` | Scroll down to load more content | `scroll_count`, `scroll_delay_ms`, `extract_interval` |
| `load_more_button` | Click a "Load More" button | `button_selector`, `max_clicks`, `click_delay_ms` |
| `numbered_pages` | Navigate numbered pages | `next_button`, `max_pages` |

## Authentication

For sites requiring login, set `REQUIRES_AUTH = True` and override the `run()` method to add authentication before scraping:

```python
class AuthSiteAdapter(BaseSiteAdapter):
    REQUIRES_AUTH = True
    REQUIRED_CREDENTIALS = ["username", "password"]

    async def run(self, page):
        # Authenticate first
        await page.goto("https://site.com/login")
        await page.fill("#email", self.config.get("username", ""))
        await page.fill("#password", self.config.get("password", ""))
        await page.click("button[type='submit']")
        await page.wait_for_load_state("networkidle")

        # Then run the standard pipeline
        return await super().run(page)
```

## Testing Your Adapter

Create a test file at `tests/test_my_site.py`:

```python
import pytest
from bs4 import BeautifulSoup
from adapters.my_site import MySiteAdapter

@pytest.fixture
def adapter():
    config = {
        "url": "https://example.com",
        "adapter": "my_site",
        "selectors": {"card": ".card", "name": "h3"},
        "pagination": {"type": "none"},
    }
    return MySiteAdapter(config)

def test_parse_card(adapter):
    html = '<div class="card"><h3>John Doe</h3></div>'
    card = BeautifulSoup(html, "html.parser").select_one(".card")
    lead = adapter.parse_card(card)
    assert lead is not None
    assert lead.name == "John Doe"

def test_parse_card_empty(adapter):
    html = '<div class="card"></div>'
    card = BeautifulSoup(html, "html.parser").select_one(".card")
    lead = adapter.parse_card(card)
    assert lead is None
```

## Adapter Discovery Mechanisms

The framework discovers adapters in three ways (in priority order):

1. **Auto-discovery**: Scans `adapters/*.py` for `BaseSiteAdapter` subclasses with `ADAPTER_NAME`
2. **Entry points**: Third-party packages can register via `[project.entry-points."crawl.adapters"]`
3. **Decorator**: Use `@register_adapter("name")` for explicit registration

For most cases, just setting `ADAPTER_NAME` on your class is sufficient.
