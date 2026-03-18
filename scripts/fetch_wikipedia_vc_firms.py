"""
fetch_wikipedia_vc_firms.py — Scrape public Wikipedia pages and curated
GitHub lists to extract investor firm website domains, then append them
to data/target_funds.txt.

Sources:
  1. Wikipedia "List of venture capital firms"
  2. Wikipedia "List of private equity firms"
  3. Wikipedia "List of the largest private equity firms"
  4. Wikipedia "List of early-stage venture capital firms"
  5. Wikipedia "Corporate venture capital"
  6. GitHub markdown / JSON lists (awesome-vc, invest-tracker, etc.)

Usage:
    python scripts/fetch_wikipedia_vc_firms.py
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
TARGET_FUNDS = ROOT / "data" / "target_funds.txt"

# ---------------------------------------------------------------------------
# Blocklist — domains we never want to add (social, news, wikis, directories, etc.)
# ---------------------------------------------------------------------------
BLOCKLIST_SUFFIXES = {
    "wikipedia.org", "wikimedia.org", "wikidata.org", "wikiquote.org",
    "wikisource.org", "wiktionary.org", "mediawiki.org",
    "twitter.com", "x.com", "facebook.com", "linkedin.com",
    "instagram.com", "youtube.com", "youtu.be", "tiktok.com",
    "pinterest.com", "reddit.com", "tumblr.com", "snapchat.com",
    "whatsapp.com", "telegram.org",
    "bloomberg.com", "reuters.com", "wsj.com", "ft.com", "cnbc.com",
    "techcrunch.com", "crunchbase.com", "pitchbook.com", "axios.com",
    "forbes.com", "fortune.com", "businessinsider.com", "inc.com",
    "nytimes.com", "washingtonpost.com", "economist.com",
    "theguardian.com", "medium.com", "substack.com",
    "wordpress.com", "blogspot.com",
    "github.com", "github.io", "gitlab.com", "bitbucket.org",
    "google.com", "google.co.uk", "google.co.in", "maps.google.com",
    "apple.com", "microsoft.com", "amazon.com", "amazonaws.com",
    "sec.gov", "finra.org", "irs.gov", "ftc.gov", "justice.gov",
    "archive.org", "web.archive.org", "waybackmachine.org",
    "doi.org", "nih.gov", "pubmed.ncbi.nlm.nih.gov",
    "creativecommons.org", "opensource.org",
    "angelist.com", "angel.co",  # not investor firm sites
    "producthunt.com", "ycombinator.com", "hbr.org",
    "investopedia.com", "thebalance.com", "fool.com",
    "marketwatch.com", "stackexchange.com", "stackoverflow.com",
    "quora.com", "eventbrite.com", "meetup.com",
    "stripe.com", "paypal.com", "visa.com", "mastercard.com",
    "amazon.co.uk", "ebay.com", "shopify.com",
}

# Blocklist for domain fragments that are never investor sites
BLOCKLIST_FRAGMENTS = {
    "news", "blog", "press", "media", "photo", "image", "cdn",
    "shop", "store", "ecommerce", "jobs", "careers",
}

# Allowed TLDs increase confidence this is a real firm website
# (not strictly required, just used for scoring)
INVESTOR_TLDS = {".com", ".co", ".vc", ".io", ".fund", ".capital",
                 ".investments", ".partners", ".ventures", ".group",
                 ".net", ".org", ".co.uk", ".de", ".sg", ".hk", ".jp",
                 ".fr", ".nl", ".se", ".ch", ".au", ".nz", ".ca"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; LeadFactory-WikiScraper/1.0; "
        "+https://github.com/myspacecornelius/crawler-26-public)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    ),
}


def fetch_url(url: str, timeout: int = 20) -> str | None:
    """Fetch a URL and return body text, or None on error."""
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=timeout) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read().decode(charset, errors="replace")
    except HTTPError as e:
        log.warning("  HTTP %s for %s", e.code, url)
    except URLError as e:
        log.warning("  URL error for %s: %s", url, e.reason)
    except Exception as e:  # pylint: disable=broad-except
        log.warning("  Error fetching %s: %s", url, e)
    return None


def normalize_domain(url: str) -> str | None:
    """
    Parse a URL, strip www., return bare domain (lowercase).
    Returns None if the URL doesn't look like a useful investor domain.
    """
    url = url.strip()
    if not url:
        return None
    # Ensure scheme
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        parsed = urlparse(url)
    except Exception:  # pylint: disable=broad-except
        return None

    host = parsed.netloc.lower()
    if not host:
        return None

    # Strip port
    if ":" in host:
        host = host.split(":")[0]

    # Strip www.
    if host.startswith("www."):
        host = host[4:]

    if not host or "." not in host:
        return None

    # Reject IP addresses
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", host):
        return None

    # Blocklist suffix check
    for blocked in BLOCKLIST_SUFFIXES:
        if host == blocked or host.endswith("." + blocked):
            return None

    # Reject very short domains that look like internal wiki links or junk
    parts = host.split(".")
    if len(parts[0]) < 2:
        return None

    return host


def is_plausible_investor_domain(domain: str) -> bool:
    """Return True if this domain could plausibly be an investor firm."""
    # Must have at least one dot
    if "." not in domain:
        return False
    # Not in blocklist fragments (e.g. "news.vc.com" — unlikely)
    first_label = domain.split(".")[0]
    if first_label in BLOCKLIST_FRAGMENTS:
        return False
    return True


# ---------------------------------------------------------------------------
# Wikipedia HTML parser
# ---------------------------------------------------------------------------

class ExternalLinkParser(HTMLParser):
    """Collect all hrefs in <a> tags that look like external websites."""

    def __init__(self, base_url: str = ""):
        super().__init__()
        self.base_url = base_url
        self.links: list[str] = []
        self._in_body = False
        self._skip_depth = 0  # track navbox / footer sections to skip

    def handle_starttag(self, tag: str, attrs):
        attr_dict = dict(attrs)

        # Skip navigation/footer sections
        cls = attr_dict.get("class", "") or ""
        role = attr_dict.get("role", "") or ""
        skip_cls = ("navbox", "reflist", "mw-references", "footer",
                    "catlinks", "sistersitebox", "hatnote")
        if any(x in cls for x in skip_cls):
            self._skip_depth += 1
            return
        if role in ("navigation", "contentinfo"):
            self._skip_depth += 1
            return

        if self._skip_depth > 0:
            return

        if tag == "a":
            href = attr_dict.get("href", "")
            if href and href.startswith("http"):
                self.links.append(href)

    def handle_endtag(self, tag: str):
        if self._skip_depth > 0:
            self._skip_depth -= 1


def extract_wikipedia_external_links(html: str, page_url: str) -> list[str]:
    """Parse Wikipedia HTML and return external domain links."""
    parser = ExternalLinkParser(base_url=page_url)
    parser.feed(html)
    domains = []
    for link in parser.links:
        domain = normalize_domain(link)
        if domain and is_plausible_investor_domain(domain):
            domains.append(domain)
    return domains


# ---------------------------------------------------------------------------
# GitHub Markdown / JSON extractors
# ---------------------------------------------------------------------------

MD_LINK_RE = re.compile(r'\[([^\]]+)\]\((https?://[^\)]+)\)')
BARE_URL_RE = re.compile(r'(?<!\()https?://[^\s\)\]<>"\']+')


def extract_from_markdown(text: str) -> list[str]:
    """Extract all URLs from markdown text."""
    urls = []
    for m in MD_LINK_RE.finditer(text):
        urls.append(m.group(2))
    for m in BARE_URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;)")
        urls.append(url)
    domains = []
    for url in urls:
        domain = normalize_domain(url)
        if domain and is_plausible_investor_domain(domain):
            domains.append(domain)
    return domains


def extract_from_json_firms(text: str) -> list[str]:
    """
    Try to parse a JSON array of firm objects and pull out website fields.
    Handles arrays like [{"name": "...", "website": "..."}, ...]
    """
    domains: list[str] = []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("  Could not parse JSON")
        return domains

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Try common wrapper keys
        for key in ("firms", "vcs", "investors", "data", "results", "items"):
            if key in data and isinstance(data[key], list):
                items = data[key]
                break
        else:
            items = []
    else:
        return domains

    url_keys = ("website", "url", "homepage", "site", "web", "domain")
    for item in items:
        if not isinstance(item, dict):
            # Could be a plain URL string
            if isinstance(item, str):
                d = normalize_domain(item)
                if d and is_plausible_investor_domain(d):
                    domains.append(d)
            continue
        for key in url_keys:
            val = item.get(key) or item.get(key.upper()) or item.get(key.capitalize())
            if val and isinstance(val, str):
                d = normalize_domain(val)
                if d and is_plausible_investor_domain(d):
                    domains.append(d)
                break

    return domains


# ---------------------------------------------------------------------------
# Source definitions
# ---------------------------------------------------------------------------

WIKIPEDIA_SOURCES = [
    ("Wikipedia: List of venture capital firms",
     "https://en.wikipedia.org/wiki/List_of_venture_capital_firms"),
    ("Wikipedia: List of private equity firms",
     "https://en.wikipedia.org/wiki/List_of_private_equity_firms"),
    ("Wikipedia: List of the largest private equity firms",
     "https://en.wikipedia.org/wiki/List_of_the_largest_private_equity_firms"),
    ("Wikipedia: List of early-stage venture capital firms",
     "https://en.wikipedia.org/wiki/List_of_early-stage_venture_capital_firms"),
    ("Wikipedia: Corporate venture capital",
     "https://en.wikipedia.org/wiki/Corporate_venture_capital"),
]

_GH = "https://raw.githubusercontent.com"
GITHUB_MARKDOWN_SOURCES = [
    ("GitHub: invest-tracker README",
     f"{_GH}/adrianmoisey/invest-tracker/main/README.md"),
    ("GitHub: awesome-venture-capital README",
     f"{_GH}/0x2b3bfa0/awesome-venture-capital/main/README.md"),
    ("GitHub: awesome-crypto-vc README",
     f"{_GH}/Vcoincheck/awesome-crypto-vc/main/README.md"),
]

GITHUB_JSON_SOURCES = [
    ("GitHub: vc-list firms.json",
     f"{_GH}/bengladwell/vc-list/main/firms.json"),
]

# OpenVC public JSON endpoints to probe
OPENVC_CANDIDATES = [
    ("OpenVC public API /vcs", "https://openvc.app/api/vcs"),
    ("OpenVC public API /investors", "https://openvc.app/api/investors"),
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def load_existing_domains() -> set[str]:
    """Load all existing entries from target_funds.txt, normalised."""
    existing: set[str] = set()
    if not TARGET_FUNDS.exists():
        return existing
    for line in TARGET_FUNDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        d = normalize_domain(line)
        if d:
            existing.add(d)
        else:
            # Keep the raw value so we don't re-add weird lines
            existing.add(line.lower())
    return existing


def append_domains(new_domains: list[str]) -> int:
    """Append new domains to target_funds.txt. Returns count written."""
    if not new_domains:
        return 0
    with TARGET_FUNDS.open("a", encoding="utf-8") as fh:
        for d in sorted(new_domains):
            fh.write(f"https://{d}\n")
    return len(new_domains)


def main() -> None:
    log.info("Loading existing domains from %s …", TARGET_FUNDS)
    existing = load_existing_domains()
    log.info("  %d existing entries", len(existing))

    all_new: list[str] = []
    source_summary: list[tuple[str, int]] = []

    # ---- Wikipedia sources ----
    for label, url in WIKIPEDIA_SOURCES:
        log.info("\nFetching %s …", label)
        html = fetch_url(url)
        if not html:
            source_summary.append((label, 0))
            continue
        time.sleep(1)  # be polite to Wikipedia
        candidates = extract_wikipedia_external_links(html, url)
        # deduplicate within source
        new_here = [d for d in dict.fromkeys(candidates)
                    if d not in existing]
        log.info("  Found %d unique domains, %d new",
                 len(set(candidates)), len(new_here))
        for d in new_here:
            existing.add(d)
            all_new.append(d)
        source_summary.append((label, len(new_here)))

    # ---- GitHub Markdown sources ----
    for label, url in GITHUB_MARKDOWN_SOURCES:
        log.info("\nFetching %s …", label)
        text = fetch_url(url)
        if not text:
            source_summary.append((label, 0))
            continue
        candidates = extract_from_markdown(text)
        new_here = [d for d in dict.fromkeys(candidates) if d not in existing]
        log.info("  Found %d unique domains, %d new",
                 len(set(candidates)), len(new_here))
        for d in new_here:
            existing.add(d)
            all_new.append(d)
        source_summary.append((label, len(new_here)))

    # ---- GitHub JSON sources ----
    for label, url in GITHUB_JSON_SOURCES:
        log.info("\nFetching %s …", label)
        text = fetch_url(url)
        if not text:
            source_summary.append((label, 0))
            continue
        candidates = extract_from_json_firms(text)
        new_here = [d for d in dict.fromkeys(candidates) if d not in existing]
        log.info("  Found %d unique domains, %d new",
                 len(set(candidates)), len(new_here))
        for d in new_here:
            existing.add(d)
            all_new.append(d)
        source_summary.append((label, len(new_here)))

    # ---- OpenVC probes ----
    for label, url in OPENVC_CANDIDATES:
        log.info("\nProbing %s …", url)
        text = fetch_url(url)
        if not text:
            log.info("  Not available (HTTP error or timeout) — skipping")
            source_summary.append((label, 0))
            continue
        # Try JSON first
        candidates = extract_from_json_firms(text)
        if not candidates:
            # Maybe it returned HTML — try markdown extractor
            candidates = extract_from_markdown(text)
        new_here = [d for d in dict.fromkeys(candidates) if d not in existing]
        log.info("  Found %d unique domains, %d new",
                 len(set(candidates)), len(new_here))
        for d in new_here:
            existing.add(d)
            all_new.append(d)
        source_summary.append((label, len(new_here)))

    # ---- Write results ----
    log.info("\n" + "=" * 60)
    written = append_domains(all_new)

    # Count final lines
    final_lines = TARGET_FUNDS.read_text(encoding="utf-8").count("\n")

    log.info("SUMMARY")
    log.info("-" * 60)
    for label, count in source_summary:
        log.info("  %-52s %4d", label, count)
    log.info("-" * 60)
    log.info("  Total new domains added:                         %4d", written)
    log.info("  Final line count of target_funds.txt:           %5d", final_lines)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
