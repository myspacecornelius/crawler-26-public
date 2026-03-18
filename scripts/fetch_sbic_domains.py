"""
fetch_sbic_domains.py — Extract investment firm domains from SBA SBIC list.

The SBA (Small Business Administration) maintains a public registry of
licensed Small Business Investment Companies (SBICs) — VC-like private
equity funds that receive government leverage.  This script fetches the
licensee list, extracts company names, derives probable .com domain
candidates via name normalization, DNS-verifies them, and appends verified
domains to data/target_funds.txt.

Sources tried in order:
  1. Excel spreadsheet at known SBA CDN URLs (openpyxl / xlrd)
  2. SBA API endpoint (JSON)
  3. HTML directory page at https://www.sba.gov/sbic/sbic-directory

No API key required.  All SBA data is public.

Usage:
    python scripts/fetch_sbic_domains.py           # dry-run
    python scripts/fetch_sbic_domains.py --write   # append to target_funds.txt
    python scripts/fetch_sbic_domains.py --write --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import re
import socket
import time
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
TARGET_FUNDS = ROOT / "data" / "target_funds.txt"

DNS_CONCURRENCY = 150
REQUEST_TIMEOUT = 30

# SBA CDN paths to try (most recent first; script tries all until one works)
_SBA_CDN = "https://www.sba.gov/sites/default/files"
EXCEL_URLS = [
    # Versioned paths seen in the wild
    _SBA_CDN + "/2024-01/SBIC_Licensees.xlsx",
    _SBA_CDN + "/2023-10/SBIC_Licensees.xlsx",
    _SBA_CDN + "/2023-07/SBIC_Licensees.xlsx",
    _SBA_CDN + "/2023-01/SBIC_Licensees.xlsx",
    _SBA_CDN + "/2022-10/SBIC_Licensees.xlsx",
    # Unversioned canonical path
    _SBA_CDN + "/SBIC_Licensees.xlsx",
]

# Unofficial / speculative API endpoints
API_URLS = [
    "https://www.sba.gov/api/content/search/sbics",
    "https://www.sba.gov/sbic/sbic-directory.json",
]

HTML_URL = "https://www.sba.gov/sbic/sbic-directory"

UA = "Mozilla/5.0 (compatible; LeadFactory/1.0; +https://github.com)"

# ── Name normalization ────────────────────────────────────────────────────────

_STRIP_PATTERNS = re.compile(
    r"""\b(
        llc | l\.l\.c\. | lp | l\.p\. | ltd | limited |
        inc | inc\. | corp | corp\. | co\. | co | plc |
        pllc | llp | l\.l\.p\. | s\.a\. | n\.a\. | n\.v\. |
        ag | gmbh | bv | oy |
        holdings? | holding | group | management | mgmt |
        fund\s+(?:i{1,3}|iv|v?i{0,3}|[0-9]+) |
        (?:series|class)\s+[a-z0-9]+ |
        international | intl | global | worldwide |
        advisors? | advisory | services? | associates? | partners? |
        capital | ventures? | equity | investments? |
        sbic | sba |
        \/[a-z]{2,4}\/ |
        \(.*?\)
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

_SKIP_PATTERNS = re.compile(
    r"""\b(
        mutual\s+fund | etf | bank | bancorp | bancshares |
        insurance | annuity | mortgage | lending |
        trust\s+bank | savings | thrift | reit |
        federal\s+reserve | university | college | school |
        foundation | endowment | nonprofit |
        department | government | agency |
        loan\s+trust | securit | pass.through |
        note[s]?\s+trust | certificate
    )\b""",
    re.IGNORECASE | re.VERBOSE,
)

_PERSON_PATTERN = re.compile(
    r"^[A-Z][A-Z]+\s+[A-Z][A-Z]+"
    r"(\s+[A-Z]{1,3}\.?|\s+[IVX]+|,?\s+JR\.?|,?\s+SR\.?)?$"
)

_BLOCKLIST = {
    "sba.gov", "sec.gov", "finra.org", "linkedin.com",
    "twitter.com", "x.com", "bloomberg.com", "crunchbase.com",
    "pitchbook.com", "angellist.com",
}


def name_to_slug(name: str) -> str:
    """Derive a lowercase slug from a company name."""
    slug = _STRIP_PATTERNS.sub(" ", name)
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", slug)
    slug = re.sub(r"\s+", "", slug).lower().strip("-")
    return slug


def name_to_domain(name: str) -> str:
    """Return a probable .com domain, or '' if the name is unusable."""
    if not name or _SKIP_PATTERNS.search(name):
        return ""
    if _PERSON_PATTERN.match(name.strip()):
        return ""
    slug = name_to_slug(name)
    if len(slug) < 3 or len(slug) > 40:
        return ""
    # Skip securitization-style slugs (digits + hyphens)
    if re.search(r"\d{4}", slug) and "-" in slug:
        return ""
    return slug + ".com"


def load_existing() -> set[str]:
    """Return the set of domains already in target_funds.txt."""
    existing: set[str] = set()
    if TARGET_FUNDS.exists():
        text = TARGET_FUNDS.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            d = line.strip()
            if d:
                d = re.sub(
                    r"^https?://(?:www\.)?", "", d
                ).rstrip("/").lower()
                existing.add(d)
    return existing


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(url: str, timeout: int = REQUEST_TIMEOUT) -> bytes | None:
    """Fetch URL bytes; return None on any error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                return resp.read()
    except Exception as exc:  # pylint: disable=broad-except
        log.debug("  GET %s failed: %s", url, exc)
    return None


# ── Source 1: Excel spreadsheet ───────────────────────────────────────────────

def _parse_excel(data: bytes) -> list[str]:
    """
    Parse an SBIC licensee Excel workbook and return company names.
    Tries openpyxl first, then xlrd as fallback.
    """
    names: list[str] = []

    # --- openpyxl (xlsx) ---
    try:
        import openpyxl  # type: ignore[import-untyped]
        wb = openpyxl.load_workbook(
            io.BytesIO(data), read_only=True, data_only=True
        )
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                if not row:
                    continue
                for cell in row:
                    val = str(cell).strip() if cell is not None else ""
                    if (
                        len(val) > 3
                        and not val.replace(".", "").replace("-", "").isdigit()
                        and val.lower() not in ("none", "nan", "n/a", "name")
                    ):
                        names.append(val)
                        break  # first non-empty text cell per row = company
            break  # only first sheet
        wb.close()
        return names
    except ImportError:
        pass
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("  openpyxl parse error: %s", exc)

    # --- xlrd (xls fallback) ---
    try:
        import xlrd  # type: ignore[import-untyped]
        wb = xlrd.open_workbook(file_contents=data)
        ws = wb.sheet_by_index(0)
        for rx in range(ws.nrows):
            for cx in range(ws.ncols):
                val = str(ws.cell_value(rx, cx)).strip()
                if (
                    len(val) > 3
                    and not val.replace(".", "").replace("-", "").isdigit()
                    and val.lower() not in ("none", "nan", "n/a", "name")
                ):
                    names.append(val)
                    break
        return names
    except ImportError:
        pass
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("  xlrd parse error: %s", exc)

    log.warning(
        "  Neither openpyxl nor xlrd available — cannot parse Excel."
        "  Install with: pip install openpyxl"
    )
    return []


def fetch_from_excel() -> list[str]:
    """Try each known Excel URL; return company names from the first success."""
    for url in EXCEL_URLS:
        log.info("  Trying Excel URL: %s", url)
        data = _get(url)
        if data and len(data) > 1024:
            log.info("  Downloaded %d bytes", len(data))
            names = _parse_excel(data)
            if names:
                log.info("  Parsed %d rows from Excel", len(names))
                return names
            log.warning("  Excel parsed but yielded no names")
        else:
            log.debug("  No data or too small")
    return []


# ── Source 2: JSON API ────────────────────────────────────────────────────────

def _extract_names_from_json(obj: object, depth: int = 0) -> list[str]:
    """Recursively search a JSON object for string values that look like names."""
    if depth > 8:
        return []
    names: list[str] = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            k = str(key).lower()
            if k in ("name", "company", "company_name", "licensee",
                      "firm", "fund", "fund_name", "title"):
                if isinstance(val, str) and len(val) > 3:
                    names.append(val.strip())
            else:
                names.extend(
                    _extract_names_from_json(val, depth + 1)
                )
    elif isinstance(obj, list):
        for item in obj:
            names.extend(_extract_names_from_json(item, depth + 1))
    return names


def fetch_from_api() -> list[str]:
    """Try SBA API endpoints; return company names."""
    import json

    for url in API_URLS:
        log.info("  Trying API URL: %s", url)
        data = _get(url)
        if not data:
            continue
        try:
            parsed = json.loads(data.decode("utf-8", errors="replace"))
            names = _extract_names_from_json(parsed)
            if names:
                log.info("  API returned %d name candidates", len(names))
                return names
        except Exception as exc:  # pylint: disable=broad-except
            log.debug("  JSON parse failed for %s: %s", url, exc)
    return []


# ── Source 3: HTML scrape ─────────────────────────────────────────────────────

def fetch_from_html() -> list[str]:
    """Scrape company names from the SBA SBIC HTML directory."""
    log.info("  Trying HTML page: %s", HTML_URL)
    data = _get(HTML_URL)
    if not data:
        log.warning("  HTML fetch failed")
        return []

    html = data.decode("utf-8", errors="replace")

    # Try to find names in table cells, list items, or heading tags
    names: list[str] = []

    # Table cells that look like company names (capital first letter, 5+ chars)
    for match in re.finditer(
        r"<td[^>]*>\s*([A-Z][A-Za-z0-9 ,\.&\-']{4,80})\s*</td>",
        html,
    ):
        candidate = match.group(1).strip()
        # Filter out headers/dates/numbers
        if (
            not re.match(r"^\d", candidate)
            and len(candidate.split()) >= 2
        ):
            names.append(candidate)

    # List items
    for match in re.finditer(
        r"<li[^>]*>\s*([A-Z][A-Za-z0-9 ,\.&\-']{4,80})\s*</li>",
        html,
    ):
        candidate = match.group(1).strip()
        if len(candidate.split()) >= 2:
            names.append(candidate)

    log.info("  Scraped %d candidate strings from HTML", len(names))
    return names


# ── DNS verification ──────────────────────────────────────────────────────────

async def _dns_exists(
    domain: str,
    loop: asyncio.AbstractEventLoop,
) -> bool:
    """Return True if domain resolves to at least one A record."""
    try:
        result = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(
                domain, None, socket.AF_INET, socket.SOCK_STREAM
            ),
        )
        return bool(result)
    except (socket.gaierror, OSError):
        return False


async def _check_batch(
    domains: list[str],
    concurrency: int = DNS_CONCURRENCY,
) -> dict[str, bool]:
    """DNS-check domains concurrently. Returns {domain: resolves}."""
    sem = asyncio.Semaphore(concurrency)
    loop = asyncio.get_event_loop()

    async def check_one(domain: str) -> tuple[str, bool]:
        async with sem:
            exists = await _dns_exists(domain, loop)
            return domain, exists

    tasks = [check_one(d) for d in domains]
    results = await asyncio.gather(*tasks)
    return dict(results)


def dns_verify(
    domains: list[str],
    concurrency: int = DNS_CONCURRENCY,
) -> list[str]:
    """Return only the domains that actually resolve."""
    if not domains:
        return []
    try:
        result_map = asyncio.run(
            _check_batch(domains, concurrency=concurrency)
        )
    except RuntimeError:
        evloop = asyncio.new_event_loop()
        result_map = evloop.run_until_complete(
            _check_batch(domains, concurrency=concurrency)
        )
    return [d for d, ok in result_map.items() if ok]


# ── Orchestration ─────────────────────────────────────────────────────────────

def collect_names() -> list[str]:
    """
    Try all sources in priority order and return a deduplicated list of
    raw company name strings.
    """
    all_names: list[str] = []

    log.info("\n  [Source 1] SBA Excel spreadsheet")
    names = fetch_from_excel()
    if names:
        all_names.extend(names)
        log.info("  Excel yielded %d raw names", len(names))

    if not all_names:
        log.info("\n  [Source 2] SBA JSON API")
        names = fetch_from_api()
        if names:
            all_names.extend(names)
            log.info("  API yielded %d raw names", len(names))

    if not all_names:
        log.info("\n  [Source 3] SBA HTML directory")
        names = fetch_from_html()
        if names:
            all_names.extend(names)
            log.info("  HTML scrape yielded %d raw names", len(names))

    if not all_names:
        log.warning(
            "\n  All sources failed. "
            "Check network access or install openpyxl."
        )

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for n in all_names:
        key = n.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(n.strip())
    return unique


def derive_domains(
    names: list[str],
    existing: set[str],
    verbose: bool = False,
) -> list[str]:
    """Convert raw company names to new, non-duplicate domain candidates."""
    new_domains: list[str] = []
    seen: set[str] = set()
    skipped_no_slug = 0
    skipped_existing = 0

    for name in names:
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
            log.info("    candidate: %s  [%s]", domain, name)

    log.info("  Domains derived: %d", len(new_domains))
    log.info(
        "  Skipped (no slug / blocked): %d", skipped_no_slug
    )
    log.info(
        "  Skipped (already in pool): %d", skipped_existing
    )
    return new_domains


# ── Main ──────────────────────────────────────────────────────────────────────

def run(
    write: bool = False,
    dns_concurrency: int = DNS_CONCURRENCY,
    verbose: bool = False,
) -> None:
    """Full pipeline: fetch → parse → normalize → DNS verify → write."""
    log.info("\n" + "=" * 60)
    log.info("  SBA SBIC DOMAIN FETCHER")
    log.info("=" * 60)

    existing = load_existing()
    log.info(
        "\n  Existing domains in target_funds.txt: %d", len(existing)
    )

    # Collect company names from all sources
    names = collect_names()
    log.info("\n  Total unique company names collected: %d", len(names))

    if not names:
        log.warning("  No names collected — aborting.")
        return

    # Derive domain candidates
    log.info("\n  Deriving domain candidates...")
    candidates = derive_domains(names, existing, verbose=verbose)

    if not candidates:
        log.info("  No new domain candidates.")
        return

    # DNS verification
    log.info(
        "\n  DNS-verifying %d candidates "
        "(concurrency=%d)...",
        len(candidates),
        dns_concurrency,
    )
    t0 = time.monotonic()
    verified = dns_verify(candidates, concurrency=dns_concurrency)
    elapsed = time.monotonic() - t0

    log.info(
        "  Verified in %.1fs: %d/%d domains resolve",
        elapsed, len(verified), len(candidates),
    )
    hit_pct = 100 * len(verified) // max(1, len(candidates))
    log.info("  Hit rate: %d%%", hit_pct)

    if verbose:
        for d in sorted(verified)[:50]:
            log.info("    + %s", d)
        if len(verified) > 50:
            log.info("    ... and %d more", len(verified) - 50)

    if not write:
        log.info(
            "\n  Dry-run — use --write to append to target_funds.txt"
        )
        log.info(
            "  target_funds.txt would grow from %d to ~%d",
            len(existing),
            len(existing) + len(verified),
        )
        return

    TARGET_FUNDS.parent.mkdir(parents=True, exist_ok=True)
    with TARGET_FUNDS.open("a", encoding="utf-8") as fh:
        for d in sorted(verified):
            fh.write(d + "\n")

    log.info(
        "\n  Appended %d verified domains to %s",
        len(verified),
        TARGET_FUNDS,
    )
    log.info(
        "  target_funds.txt now has ~%d domains",
        len(existing) + len(verified),
    )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch SBA SBIC licensee list and append verified domains"
            " to data/target_funds.txt"
        )
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Append verified domains to target_funds.txt (default: dry-run)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=DNS_CONCURRENCY,
        help=f"DNS lookup concurrency (default: {DNS_CONCURRENCY})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print each candidate / verified domain",
    )
    args = parser.parse_args()
    run(
        write=args.write,
        dns_concurrency=args.concurrency,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
