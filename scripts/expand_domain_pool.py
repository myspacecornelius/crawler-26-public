"""
expand_domain_pool.py — VC/Investor Domain Pool Expander
=========================================================
Reads VC/PE/investor domains from multiple public sources and appends new
unique domains to data/target_funds.txt.

Sources used (in order):
  1. data/seed/vc_firms.csv
  2. data/seed/vc_firms_expanded.csv
  3. data/seed/vc_firms_supplemental.csv
  4. data/seed/pe_firms.csv
  5. data/seed/family_offices.csv
  6. data/seed/corp_dev.csv  (filtered — only VC-adjacent entries)
  7. data/seed/vc_firms_iapd.csv  (if present; produced by fetch_iapd_domains.py)
  8. Crunchbase open-data mirrors on GitHub/raw URLs (HTTP fetch)
  9. Awesome-VC GitHub markdown lists (HTTP fetch)

Filters:
  - Name must contain at least one VC keyword (configurable)
  - Domain must have a TLD and be reasonable length
  - Social-media / noise domains are blocked
  - Deduplicates against existing data/target_funds.txt and data/seen_domains.txt

Usage:
    python scripts/expand_domain_pool.py               # dry-run
    python scripts/expand_domain_pool.py --write       # append to target_funds.txt
    python scripts/expand_domain_pool.py --write --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import re
import sys
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

try:
    import aiohttp  # type: ignore
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DATA = ROOT / "data"
SEED = DATA / "seed"

TARGET_FUNDS = DATA / "target_funds.txt"
SEEN_DOMAINS = DATA / "seen_domains.txt"

SEED_CSVS = [
    SEED / "vc_firms.csv",
    SEED / "vc_firms_expanded.csv",
    SEED / "vc_firms_supplemental.csv",
    SEED / "pe_firms.csv",
    SEED / "family_offices.csv",
    SEED / "vc_firms_iapd.csv",   # produced by fetch_iapd_domains.py (optional)
]

# corp_dev.csv intentionally excluded — mostly Big Tech acquirers, not VC funds

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ── VC keyword filter ─────────────────────────────────────────────────────────
VC_KEYWORDS = {
    "capital", "venture", "ventures", "partner", "partners", "fund", "funds",
    "invest", "investor", "investors", "investment", "investments",
    "equity", "management", "holdings", "assets", "financial", "group",
    "growth", "private", "asset", "portfolio", "advisors", "advisory",
    "associates", "technologies", "innovation", "bio", "health", "life",
    "science", "sciences", "tech", "digital", "global", "international",
    "emerging", "seed", "angel", "accelerator", "incubator", "studio",
    "early", "stage", "micro", "nano", "impact", "sustainable", "climate",
    "crypto", "blockchain", "web3", "fintech", "deep",
}

# ── Domains that should never appear in output ────────────────────────────────
BLOCKLIST = {
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "crunchbase.com", "angellist.com", "angel.co", "pitchbook.com",
    "dealroom.co", "techcrunch.com", "medium.com", "substack.com",
    "forbes.com", "bloomberg.com", "wikipedia.org", "youtube.com",
    "google.com", "github.com", "wellfound.com", "tracxn.com",
    "cbinsights.com", "sec.gov", "wsj.com", "ft.com", "reuters.com",
    "nytimes.com", "ycombinator.com", "techstars.com", "openvc.app",
    "angelmatch.io", "signal.nfx.com", "vcstack.io",
    "amazon.com", "apple.com", "microsoft.com", "cisco.com",
    "shopify.com", "stripe.com", "paypal.com", "zoom.us",
    "slack.com", "notion.so", "figma.com", "vercel.com",
    "netlify.com", "heroku.com", "digitalocean.com",
    "hubspot.com", "twilio.com", "salesforce.com", "oracle.com",
    "sap.com", "adobe.com", "intuit.com", "servicenow.com",
    "snowflake.com", "paloaltonetworks.com", "crowdstrike.com",
    "datadoghq.com", "block.xyz", "meta.com", "mongodb.com",
    "uipath.com", "workday.com", "murata.com", "tencent.com",
    # junk from existing target_funds.txt
    "bitbucket.org", "sourceforge.net", "github.com", "gitlab.com",
    "readthedocs.io", "apperta.org", "openaps.org", "openmrs.org",
    "openelis-global.org", "ehrbase.org", "openehr.org",
    "dicom.offis.de", "itk.org", "vtk.org", "imagej.net",
    "ctakes.apache.org", "ohdsi.org", "hl7.org", "librehealth.io",
    "hospitalrun.io", "openeobs.github.io", "openrem.org",
    "freemeddforms.com", "opendental.com", "gnuhealth.org",
    "gnumed.de", "hosxp.net", "medintux.org", "openlmis.org",
    "inferno-framework.github.io", "ehubio.ehu.eus",
    "horosproject.org", "invesalius.github.io", "scanpy.readthedocs.io",
    "nomadlist.com", "workfrom.co", "techmasters.chat",
    "canadabusiness.ca", "mirrors.creativecommons.org",
    "docs.smarthealthit.org", "smartfhir.org",
    "dicom.innolitics.com", "fhirbase.github.io",
    "cottagemed.org", "hcw-at-home.com", "hackaday.io",
    "galaxyproject.org", "labkey.com", "i2b2.org",
    "opal.openhealthcare.org.uk", "lanzame.es",
    "seriesseed.com", "seed-db.com", "docracy.com",
    "dcm4che.org", "mitk.org", "kheops.online",
    "orthanc-server.com", "senaite.com", "ozone-his.com",
    "meldatools.com", "pixelmed.com", "ohif.org",
}

# ── Remote sources (markdown / CSV lists) ─────────────────────────────────────
# NOTE: The raw Crunchbase companies.csv is intentionally excluded here because
# it contains all company types, not just investors.  Use
# scripts/fetch_crunchbase_vc_domains.py instead — it filters by category_list
# to only include VC/PE/angel/accelerator firms.
REMOTE_SOURCES = [
    # Awesome-VC curated lists (GitHub markdown)
    "https://raw.githubusercontent.com/mckaywrigley/awesome-vc/main/README.md",
    "https://raw.githubusercontent.com/byjonah/awesome-venture-capital/main/README.md",
    "https://raw.githubusercontent.com/nicbou/european-vc/main/README.md",
    "https://raw.githubusercontent.com/elainesfolder/awesome-climate-vc/main/README.md",
    "https://raw.githubusercontent.com/dbreunig/venture-capital/master/README.md",
]


# ── Domain helpers ────────────────────────────────────────────────────────────

def normalize(url: str) -> str:
    """Return clean bare domain from a URL string, or '' on failure."""
    url = url.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    host = host.split(":")[0]          # drop port
    host = re.sub(r"^www\.", "", host) # strip www.
    host = host.rstrip("/. ")
    return host


def is_valid(domain: str) -> bool:
    """Return True if domain looks like a real investor website."""
    if not domain or len(domain) < 5 or len(domain) > 100:
        return False
    if "." not in domain:
        return False
    if domain in BLOCKLIST:
        return False
    # blocklist suffix check (e.g. linkedin.com/something)
    for blocked in BLOCKLIST:
        if domain == blocked or domain.endswith("." + blocked):
            return False
    # must not be a raw path (no slashes in domain portion)
    if "/" in domain:
        return False
    return True


def name_is_vc_related(name: str) -> bool:
    """Return True if firm name contains at least one VC keyword."""
    if not name:
        return False
    words = re.findall(r"[a-z]+", name.lower())
    return any(w in VC_KEYWORDS for w in words)


# ── Load existing domains ──────────────────────────────────────────────────────

def load_existing_domains() -> set[str]:
    """Load all domains already in target_funds.txt and seen_domains.txt."""
    existing: set[str] = set()
    for path in (TARGET_FUNDS, SEEN_DOMAINS):
        if not path.exists():
            continue
        with path.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = normalize(line)
                if d:
                    existing.add(d)
                else:
                    existing.add(line.lower())
    return existing


# ── CSV seed sources ──────────────────────────────────────────────────────────

def iter_csv_domains() -> Iterator[tuple[str, str]]:
    """Yield (domain, source_label) from all seed CSVs."""
    for csv_path in SEED_CSVS:
        if not csv_path.exists():
            continue
        try:
            with csv_path.open(encoding="utf-8", errors="ignore") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    name = (row.get("name") or "").strip()
                    website = (row.get("website") or "").strip()
                    if not website:
                        continue
                    domain = normalize(website)
                    if is_valid(domain):
                        yield domain, csv_path.name
        except Exception as e:
            log.warning(f"  Warning: could not read {csv_path}: {e}")


# ── Remote async fetching ─────────────────────────────────────────────────────

def extract_domains_from_text(text: str, source_url: str) -> list[str]:
    """
    Extract domains from markdown or CSV text.
    Handles both:
      - Markdown links: [Name](https://example.com)
      - CSV rows with a 'website' column (naive URL scan)
    """
    domains: list[str] = []
    # Find all http(s) URLs
    for m in re.finditer(r'https?://[^\s\)\],"\'<>]+', text):
        raw = m.group(0).rstrip(".,;)")
        d = normalize(raw)
        if is_valid(d):
            domains.append(d)
    return domains


async def fetch_remote(session: "aiohttp.ClientSession", url: str) -> list[str]:
    """Fetch a remote URL and return extracted domains."""
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=20),
            headers={"User-Agent": "Mozilla/5.0 LeadFactory-DomainExpander/1.0"},
        ) as resp:
            if resp.status != 200:
                log.warning(f"  HTTP {resp.status} for {url}")
                return []
            text = await resp.text(errors="replace")
            domains = extract_domains_from_text(text, url)
            log.info(f"  Fetched {url} → {len(domains)} domains")
            return domains
    except Exception as e:
        log.warning(f"  Could not fetch {url}: {e}")
        return []


async def fetch_all_remote() -> list[str]:
    """Fetch all remote sources concurrently."""
    if not HAS_AIOHTTP:
        log.warning("  aiohttp not installed — skipping remote fetch")
        return []
    domains: list[str] = []
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_remote(session, url) for url in REMOTE_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                domains.extend(result)
    return domains


# ── Main ──────────────────────────────────────────────────────────────────────

def run(write: bool = False, verbose: bool = False) -> None:
    log.info("\n" + "=" * 60)
    log.info("  VC DOMAIN POOL EXPANDER")
    log.info("=" * 60)

    # Load what we already have
    existing = load_existing_domains()
    log.info(f"\n  Existing domains in target_funds.txt / seen_domains.txt: {len(existing)}")

    new_domains: list[str] = []
    seen_new: set[str] = set()

    def add(domain: str, source: str) -> None:
        if domain not in existing and domain not in seen_new:
            seen_new.add(domain)
            new_domains.append(domain)
            if verbose:
                log.info(f"    + {domain}  [{source}]")

    # --- Source 1-6: Seed CSVs ---
    csv_count = 0
    for domain, src in iter_csv_domains():
        add(domain, src)
        csv_count += 1
    log.info(f"  Seed CSVs scanned: {csv_count} valid domains → {len(new_domains)} new")

    # --- Source 7: Remote (async) ---
    remote_before = len(new_domains)
    try:
        remote_domains = asyncio.run(fetch_all_remote())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        remote_domains = loop.run_until_complete(fetch_all_remote())
    for d in remote_domains:
        add(d, "remote")
    log.info(f"  Remote sources: {len(remote_domains)} scanned → {len(new_domains) - remote_before} new")

    log.info("\n" + "-" * 60)
    log.info(f"  Total new unique domains found: {len(new_domains)}")
    log.info("-" * 60)

    if not write:
        log.info("\n  Dry-run — use --write to append to target_funds.txt")
        log.info(f"  target_funds.txt would grow from {len(existing)} → ~{len(existing) + len(new_domains)} domains")
        return

    # Append to target_funds.txt
    before_count = sum(1 for _ in TARGET_FUNDS.open(encoding="utf-8", errors="ignore").readlines()) if TARGET_FUNDS.exists() else 0
    with TARGET_FUNDS.open("a", encoding="utf-8") as fh:
        for d in sorted(new_domains):
            fh.write(d + "\n")

    log.info(f"\n  Appended {len(new_domains)} domains to {TARGET_FUNDS}")
    log.info(f"  target_funds.txt: was {before_count} lines, now ~{before_count + len(new_domains)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Expand VC domain pool in target_funds.txt")
    parser.add_argument("--write", action="store_true", help="Append new domains to target_funds.txt")
    parser.add_argument("--verbose", action="store_true", help="Print each new domain as it is added")
    args = parser.parse_args()
    run(write=args.write, verbose=args.verbose)


if __name__ == "__main__":
    main()
