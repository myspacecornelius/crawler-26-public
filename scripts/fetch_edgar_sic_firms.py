"""
fetch_edgar_sic_firms.py — Extract investment firm domains from SEC EDGAR by SIC code.

Queries the SEC EDGAR company search for all companies under investor-related
SIC codes, extracts company names, derives probable website domains using name
normalization, then appends unique domains to data/target_funds.txt.

SIC codes targeted:
  6282 — Investment Advice (registered investment advisers, asset managers)
  6726 — Investment Offices, NEC (VC funds, PE funds, hedge funds)
  6770 — Blank Checks (SPACs, blank-check holding companies)
  6371 — Pension/Health/Welfare Funds
  6199 — Finance Services

No API key required. SEC EDGAR is fully public.
Rate limit: max 10 req/sec (SEC fair-use policy).

Usage:
    python scripts/fetch_edgar_sic_firms.py               # dry-run
    python scripts/fetch_edgar_sic_firms.py --write       # append to target_funds.txt
    python scripts/fetch_edgar_sic_firms.py --write --sic 6282 6726
    python scripts/fetch_edgar_sic_firms.py --write --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import re
import time
from pathlib import Path
from urllib.parse import urlencode
from typing import Iterator

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    import urllib.request
    HAS_AIOHTTP = False

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
TARGET_FUNDS = ROOT / "data" / "target_funds.txt"
EDGAR_BASE = "https://www.sec.gov/cgi-bin/browse-edgar"
PAGE_SIZE = 100       # Max allowed by EDGAR
RATE_LIMIT = 8.0      # Requests per second (SEC allows 10)
MIN_DELAY = 1.0 / RATE_LIMIT

# SIC codes that map to investor/fund entities
DEFAULT_SIC_CODES = [6282, 6726, 6770, 6371]

# ── Name normalization ─────────────────────────────────────────────────────────

# Patterns to strip from company names before generating a domain slug
_STRIP_PATTERNS = re.compile(
    r"""\b(
        llc | l\.l\.c\. | lp | l\.p\. | ltd | limited | inc | inc\. |
        corp | corp\. | co\. | co | plc | pllc | llp | l\.l\.p\. |
        s\.a\. | n\.a\. | n\.v\. | ag | gmbh | bv | oy |
        holdings? | holding | group | management | mgmt |
        fund\s+(?:i{1,3}|iv|v?i{0,3}|[0-9]+) |  # Fund I, II, III, IV, 1, 2 …
        (?:series|class)\s+[a-z0-9]+ |
        international | intl | global | worldwide |
        advisors? | advisory | services? | associates? | partners? |
        capital | ventures? | equity | investments? |
        \/[a-z]{2,4}\/ |    # /NY/ /DE/ country suffixes
        \(.*?\)             # parenthetical suffixes
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

# Domains that are clearly NOT investor websites
_BLOCKLIST = {
    "sec.gov", "finra.org", "linkedin.com", "twitter.com", "x.com",
    "bloomberg.com", "reuters.com", "wsj.com", "ft.com", "forbes.com",
    "google.com", "microsoft.com", "amazon.com", "apple.com",
    "crunchbase.com", "pitchbook.com", "angellist.com",
}

# Names that indicate non-VC entities (mutual fund families, banks, mortgage trusts, etc.)
_NAME_SKIP_PATTERNS = re.compile(
    r"\b(mutual\s+fund|etf|bank|bancorp|bancshares|insurance|annuity|"
    r"mortgage|lending|trust\s+bank|savings|thrift|reit|federal\s+reserve|"
    r"university|college|school|foundation|endowment|nonprofit|"
    r"department|government|agency|loan\s+trust|securit|"
    r"pass-through|pass\s+through|note[s]?\s+trust|certificate)\b",
    re.IGNORECASE,
)

# Skip entries that look like individual person names (e.g. "SMITH JOHN A")
_PERSON_NAME_PATTERN = re.compile(
    r"^[A-Z][A-Z]+\s+[A-Z][A-Z]+(\s+[A-Z]{1,3}\.?|\s+[IVX]+|,?\s+JR\.?|,?\s+SR\.?)?$"
)


def name_to_slug(name: str) -> str:
    """
    Derive a lowercase slug from a company name.
    Strips legal suffixes, punctuation, and normalizes whitespace.
    """
    # Strip legal / fund-series suffixes
    slug = _STRIP_PATTERNS.sub(" ", name)
    # Remove remaining punctuation except hyphens and spaces
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", slug)
    # Collapse whitespace
    slug = re.sub(r"\s+", "", slug).lower().strip("-")
    return slug


def name_to_domain(name: str) -> str:
    """Return a probable .com domain, or '' if the name is unusable."""
    if not name or _NAME_SKIP_PATTERNS.search(name):
        return ""
    # Skip individual person names in ALL-CAPS format
    if _PERSON_NAME_PATTERN.match(name.strip()):
        return ""
    slug = name_to_slug(name)
    if len(slug) < 3 or len(slug) > 40:
        return ""
    # Skip slugs that look like mortgage/securitization garbage (numbers + hyphens)
    if re.search(r'\d{4}', slug) and '-' in slug:
        return ""
    return slug + ".com"


def load_existing() -> set[str]:
    existing: set[str] = set()
    if TARGET_FUNDS.exists():
        for line in TARGET_FUNDS.read_text(encoding="utf-8", errors="ignore").splitlines():
            d = line.strip()
            if d:
                # Normalize — strip scheme and www.
                d = re.sub(r"^https?://(?:www\.)?", "", d).rstrip("/")
                existing.add(d.lower())
    return existing


# ── EDGAR scraping ─────────────────────────────────────────────────────────────

def _build_url(sic: int, start: int = 0) -> str:
    params = {
        "action": "getcompany",
        "State": "0",
        "SIC": str(sic),
        "dateb": "",
        "owner": "include",
        "count": str(PAGE_SIZE),
        "search_text": "",
        "start": str(start),
    }
    return EDGAR_BASE + "?" + urlencode(params)


def _parse_page(html: str) -> list[tuple[str, str]]:
    """
    Parse the EDGAR company search HTML table.
    Returns list of (cik, company_name) tuples.
    """
    results: list[tuple[str, str]] = []
    # Table rows: <td>CIK</td><td>Company Name</td><td>State</td>
    # Pattern derived from the actual HTML structure
    rows = re.findall(
        r'CIK=(\d+)[^>]+>\d+</a>\s*</td>\s*<td[^>]*>([^<]+)</td>',
        html,
        re.DOTALL,
    )
    for cik, name in rows:
        name = name.strip()
        if name:
            results.append((cik, name))
    return results


def _has_next(html: str) -> bool:
    # EDGAR uses: value="Next100" with onClick for pagination
    return bool(re.search(r'value="Next\d*"', html, re.IGNORECASE))


async def _fetch_page_async(
    session: "aiohttp.ClientSession",
    sic: int,
    start: int,
    semaphore: asyncio.Semaphore,
    last_req: list,  # mutable list holding [timestamp]
) -> tuple[list[tuple[str, str]], bool]:
    """Fetch one page; returns (entries, has_next)."""
    url = _build_url(sic, start)
    async with semaphore:
        # Respect rate limit
        elapsed = time.monotonic() - last_req[0]
        if elapsed < MIN_DELAY:
            await asyncio.sleep(MIN_DELAY - elapsed)
        last_req[0] = time.monotonic()

        try:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "CRAWL LeadFactory/1.0 (contact@example.com)"},
            ) as resp:
                if resp.status != 200:
                    log.warning(f"  HTTP {resp.status} for SIC={sic} start={start}")
                    return [], False
                html = await resp.text(errors="replace")
        except Exception as exc:
            log.warning(f"  Error fetching SIC={sic} start={start}: {exc}")
            return [], False

    entries = _parse_page(html)
    has_next = _has_next(html)
    return entries, has_next


async def fetch_sic_companies_async(
    sic_codes: list[int],
) -> list[tuple[str, str]]:
    """Fetch all companies for the given SIC codes. Returns (cik, name) pairs."""
    semaphore = asyncio.Semaphore(4)   # max 4 concurrent requests
    last_req = [0.0]
    all_entries: list[tuple[str, str]] = []

    async with aiohttp.ClientSession() as session:
        for sic in sic_codes:
            log.info(f"\n  Fetching SIC {sic}...")
            start = 0
            sic_count = 0

            while True:
                entries, has_next = await _fetch_page_async(
                    session, sic, start, semaphore, last_req
                )
                all_entries.extend(entries)
                sic_count += len(entries)

                if not entries or not has_next:
                    break
                start += PAGE_SIZE

                # Progress
                if sic_count % 1000 == 0:
                    log.info(f"    SIC {sic}: {sic_count} so far (start={start})...")

            log.info(f"  SIC {sic}: {sic_count} companies found")

    return all_entries


def fetch_sic_companies_sync(sic_codes: list[int]) -> list[tuple[str, str]]:
    """Synchronous fallback using urllib."""
    import urllib.request

    all_entries: list[tuple[str, str]] = []
    for sic in sic_codes:
        log.info(f"\n  Fetching SIC {sic} (sync)...")
        start = 0
        sic_count = 0
        while True:
            url = _build_url(sic, start)
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "CRAWL LeadFactory/1.0 (contact@example.com)"},
                )
                with urllib.request.urlopen(req, timeout=30) as r:
                    html = r.read().decode("utf-8", errors="replace")
            except Exception as exc:
                log.warning(f"  Error: {exc}")
                break

            entries = _parse_page(html)
            all_entries.extend(entries)
            sic_count += len(entries)

            if not entries or not _has_next(html):
                break
            start += PAGE_SIZE
            time.sleep(MIN_DELAY)

            if sic_count % 500 == 0:
                log.info(f"    SIC {sic}: {sic_count} so far...")

        log.info(f"  SIC {sic}: {sic_count} companies found")

    return all_entries


# ── Main ──────────────────────────────────────────────────────────────────────

def run(
    sic_codes: list[int],
    write: bool = False,
    verbose: bool = False,
) -> None:
    log.info("\n" + "=" * 60)
    log.info("  SEC EDGAR SIC FIRM SCRAPER")
    log.info("=" * 60)

    existing = load_existing()
    log.info(f"\n  Existing domains in target_funds.txt: {len(existing)}")
    log.info(f"  SIC codes to query: {sic_codes}")

    # Fetch companies
    if HAS_AIOHTTP:
        try:
            entries = asyncio.run(fetch_sic_companies_async(sic_codes))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            entries = loop.run_until_complete(fetch_sic_companies_async(sic_codes))
    else:
        log.warning("  aiohttp not available — using slower sync fetch")
        entries = fetch_sic_companies_sync(sic_codes)

    log.info(f"\n  Total companies fetched: {len(entries)}")

    # Derive domains
    new_domains: list[str] = []
    seen: set[str] = set()
    skipped_no_slug = 0
    skipped_existing = 0

    for cik, name in entries:
        domain = name_to_domain(name)
        if not domain:
            skipped_no_slug += 1
            continue
        if domain in _BLOCKLIST:
            skipped_no_slug += 1
            continue
        if domain in existing or domain in seen:
            skipped_existing += 1
            continue
        seen.add(domain)
        new_domains.append(domain)
        if verbose:
            log.info(f"    + {domain}  [{name}]")

    log.info(f"\n  New domains derived: {len(new_domains)}")
    log.info(f"  Skipped (no slug / blocked): {skipped_no_slug}")
    log.info(f"  Skipped (already in pool): {skipped_existing}")

    if not write:
        log.info(f"\n  Dry-run — use --write to append to target_funds.txt")
        log.info(f"  target_funds.txt would grow from {len(existing)} → ~{len(existing) + len(new_domains)}")
        return

    with TARGET_FUNDS.open("a", encoding="utf-8") as fh:
        for d in sorted(new_domains):
            fh.write(d + "\n")

    log.info(f"\n  Appended {len(new_domains)} domains to {TARGET_FUNDS}")
    log.info(f"  target_funds.txt now has ~{len(existing) + len(new_domains)} domains")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract investment firm domains from SEC EDGAR SIC codes"
    )
    parser.add_argument(
        "--sic", nargs="+", type=int, default=DEFAULT_SIC_CODES,
        help=f"SIC codes to query (default: {DEFAULT_SIC_CODES})",
    )
    parser.add_argument("--write", action="store_true", help="Append new domains to target_funds.txt")
    parser.add_argument("--verbose", action="store_true", help="Print each domain as it is added")
    args = parser.parse_args()
    run(sic_codes=args.sic, write=args.write, verbose=args.verbose)


if __name__ == "__main__":
    main()
