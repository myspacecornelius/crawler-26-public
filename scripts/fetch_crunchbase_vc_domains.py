"""
fetch_crunchbase_vc_domains.py — Extract investor firm domains from Crunchbase open data.

Filters the public Crunchbase companies CSV (via notpeter/crunchbase-data on GitHub)
to only rows whose category_list contains investor-related categories, then appends
their homepage domains to data/target_funds.txt.

Usage:
    python scripts/fetch_crunchbase_vc_domains.py               # dry-run
    python scripts/fetch_crunchbase_vc_domains.py --write       # append to target_funds.txt
    python scripts/fetch_crunchbase_vc_domains.py --write --verbose
"""

from __future__ import annotations

import argparse
import csv
import io
import logging
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen, Request

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
TARGET_FUNDS = ROOT / "data" / "target_funds.txt"

CRUNCHBASE_CSV_URL = (
    "https://raw.githubusercontent.com/notpeter/crunchbase-data/master/companies.csv"
)

# Categories in the Crunchbase CSV that indicate investor/fund entities.
INVESTOR_CATEGORIES = {
    "venture capital",
    "private equity",
    "angel investors",
    "investment management",
    "financial services",
    "asset management",
    "hedge funds",
    "family offices",
    "impact investing",
    "micro vc",
    "corporate venture capital",
    "seed funding",
    "accelerator",
    "incubator",
    "fund of funds",
}

BLOCKLIST = {
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "crunchbase.com", "angellist.com", "angel.co", "pitchbook.com",
    "techcrunch.com", "medium.com", "substack.com", "bloomberg.com",
    "wikipedia.org", "youtube.com", "google.com", "github.com",
    "amazon.com", "apple.com", "microsoft.com",
}


def normalize(url: str) -> str:
    if not url:
        return ""
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    host = host.split(":")[0]
    host = re.sub(r"^www\.", "", host)
    return host.rstrip("/. ")


def is_valid(domain: str) -> bool:
    if not domain or len(domain) < 5 or len(domain) > 100:
        return False
    if "." not in domain or "/" in domain:
        return False
    if domain in BLOCKLIST:
        return False
    for blocked in BLOCKLIST:
        if domain.endswith("." + blocked):
            return False
    return True


def is_investor(category_list: str) -> bool:
    cats = {c.strip().lower() for c in category_list.split("|") if c.strip()}
    return bool(cats & INVESTOR_CATEGORIES)


def load_existing() -> set[str]:
    existing: set[str] = set()
    if TARGET_FUNDS.exists():
        with TARGET_FUNDS.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                d = normalize(line.strip())
                if d:
                    existing.add(d)
                else:
                    existing.add(line.strip().lower())
    return existing


def fetch_and_filter() -> list[str]:
    log.info(f"  Fetching {CRUNCHBASE_CSV_URL} ...")
    req = Request(
        CRUNCHBASE_CSV_URL,
        headers={"User-Agent": "LeadFactory-DomainExpander/1.0"},
    )
    with urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(raw))
    domains: list[str] = []
    rows_checked = 0
    for row in reader:
        rows_checked += 1
        category_list = row.get("category_list", "")
        if not is_investor(category_list):
            continue
        url = row.get("homepage_url", "").strip()
        if not url:
            continue
        domain = normalize(url)
        if is_valid(domain):
            domains.append(domain)

    log.info(f"  Scanned {rows_checked} rows → {len(domains)} investor domains found")
    return domains


def run(write: bool = False, verbose: bool = False) -> None:
    log.info("\n" + "=" * 60)
    log.info("  CRUNCHBASE VC DOMAIN FETCHER")
    log.info("=" * 60)

    existing = load_existing()
    log.info(f"\n  Existing domains in target_funds.txt: {len(existing)}")

    try:
        investor_domains = fetch_and_filter()
    except Exception as e:
        log.error(f"  Failed to fetch Crunchbase data: {e}")
        sys.exit(1)

    new_domains: list[str] = []
    seen: set[str] = set()
    for d in investor_domains:
        if d not in existing and d not in seen:
            seen.add(d)
            new_domains.append(d)
            if verbose:
                log.info(f"    + {d}")

    log.info(f"\n  New investor domains: {len(new_domains)}")

    if not write:
        log.info("  Dry-run — use --write to append to target_funds.txt")
        log.info(f"  target_funds.txt would grow from {len(existing)} → ~{len(existing) + len(new_domains)}")
        return

    with TARGET_FUNDS.open("a", encoding="utf-8") as f:
        for d in sorted(new_domains):
            f.write(d + "\n")

    log.info(f"\n  Appended {len(new_domains)} investor domains to {TARGET_FUNDS}")
    log.info(f"  target_funds.txt: was {len(existing)} → now ~{len(existing) + len(new_domains)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch VC/investor domains from Crunchbase open data")
    parser.add_argument("--write", action="store_true", help="Append new domains to target_funds.txt")
    parser.add_argument("--verbose", action="store_true", help="Print each new domain as it is added")
    args = parser.parse_args()
    run(write=args.write, verbose=args.verbose)


if __name__ == "__main__":
    main()
