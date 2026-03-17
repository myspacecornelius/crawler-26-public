"""
CRAWL — SEC EDGAR Form D Bulk Extractor
Pulls fund officer names and contact info at massive scale by consuming
EDGAR's quarterly full-text index files and parsing Form D XML filings.

Design:
- Downloads quarterly company.idx files to enumerate all Form D accessions
- Fetches each filing's primary XML document and parses officer records
- Rate-limited to 10 req/sec (SEC fair-use policy); uses asyncio.Semaphore
- Outputs InvestorLead-compatible dicts and writes a master CSV

Usage (standalone):
    python -m enrichment.edgar_bulk --years 2023 2024 --max 50000 --output data/edgar_form_d.csv
    python -m enrichment.edgar_bulk --years 2022 2023 2024 --output data/edgar_form_d.csv

Environment:
    No API keys required. SEC EDGAR is fully public.
    User-Agent header must identify the caller (SEC requirement).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import gzip
import logging
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import aiohttp

# Import the shared data model so leads slot straight into the pipeline.
from adapters.base import InvestorLead

logger = logging.getLogger(__name__)

# ── SEC connection constants ──────────────────────────────────────────────────

# SEC fair-use: max 10 req/sec.  We honour this strictly via a semaphore.
_MAX_RPS = 10
_SEC_DELAY = 1.0 / _MAX_RPS          # 0.1 s between acquires at full speed

# SEC requires a descriptive User-Agent with a contact address.
_USER_AGENT = "CRAWL FormDExtractor/1.0 (contact@example.com)"

_EDGAR_BASE = "https://www.sec.gov"
_INDEX_URL = _EDGAR_BASE + "/Archives/edgar/full-index/{year}/QTR{qtr}/company.idx"
_INDEX_GZ_URL = _EDGAR_BASE + "/Archives/edgar/full-index/{year}/QTR{qtr}/company.gz"
_FILING_BASE = _EDGAR_BASE + "/Archives/edgar/data"

# Form D types we care about (D and D/A = amendment)
_FORM_D_TYPES = {"D", "D/A"}

# CSV header matching the master investor_leads format
_CSV_FIELDNAMES = [
    "Name", "Email", "Email Status", "Role", "Fund", "Focus Areas",
    "Stage", "Check Size", "Location", "LinkedIn", "Website",
    "Lead Score", "Tier", "Source", "Scraped At",
]

# Officer title field names across different Form D schema versions
_TITLE_FIELDS = [
    "relationshipCoveredPersonsTitle",
    "title",
    "titleOfRelationship",
    "personTitle",
]

# ── Rate limiter ──────────────────────────────────────────────────────────────

class _RateLimiter:
    """Token-bucket rate limiter backed by asyncio.Semaphore + sleep."""

    def __init__(self, max_rps: float = _MAX_RPS):
        self._sem = asyncio.Semaphore(int(max_rps))
        self._delay = 1.0 / max_rps
        self._last = 0.0

    async def acquire(self):
        await self._sem.acquire()
        now = time.monotonic()
        wait = self._delay - (now - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()

    def release(self):
        self._sem.release()


# ── Index parsing ─────────────────────────────────────────────────────────────

def _parse_company_idx(raw: str) -> list[dict]:
    """
    Parse an EDGAR company.idx file and return Form D filing records.

    The fixed-width text format looks like:
        Company Name          Form Type  CIK       Date Filed  Filename
        ─────────────────────────────────────────────────────────────────
        SOME FUND LP          D          1234567   2024-01-15  edgar/data/1234567/0001234567-24-000001.txt

    We only keep rows whose Form Type is 'D' or 'D/A'.
    """
    records: list[dict] = []

    lines = raw.splitlines()
    # Skip the two header lines (company name header + dashes line)
    data_lines = []
    header_found = False
    for line in lines:
        if re.match(r"-{10,}", line.strip()):
            header_found = True
            continue
        if header_found and line.strip():
            data_lines.append(line)

    for line in data_lines:
        # The format is fixed-width but the most reliable split is on the CIK
        # column (10-char right-padded after form type). We use a regex.
        m = re.match(
            r"^(.{62})(.{12})(\d{10})\s+(\d{4}-\d{2}-\d{2})\s+(\S+)",
            line,
        )
        if not m:
            # Try a looser split for lines with varying whitespace
            parts = line.split()
            if len(parts) < 4:
                continue
            # Detect form type — it's typically the second-to-last word before cik
            # Fall through to regex-only for cleanliness.
            continue

        company_name = m.group(1).strip()
        form_type = m.group(2).strip()
        cik = m.group(3).strip().lstrip("0") or "0"
        date_filed = m.group(4).strip()
        filename = m.group(5).strip()

        if form_type not in _FORM_D_TYPES:
            continue

        records.append({
            "company": company_name,
            "form_type": form_type,
            "cik": cik,
            "date_filed": date_filed,
            "filename": filename,
        })

    return records


def _accession_from_filename(filename: str) -> Optional[str]:
    """
    Convert an EDGAR index filename to an accession number string.
    e.g.  'edgar/data/1234567/0001234567-24-000001.txt'
          -> '0001234567-24-000001'
    """
    stem = Path(filename).stem          # strips .txt/.htm etc.
    # accession numbers look like XXXXXXXXXX-YY-ZZZZZZ
    m = re.search(r"(\d{10}-\d{2}-\d{6})", stem)
    return m.group(1) if m else None


def _xml_url_from_record(record: dict) -> str:
    """
    Build the URL to the primary Form D XML filing document.
    EDGAR stores Form D as primary-document.xml inside the accession directory.
    """
    cik = record["cik"]
    filename = record["filename"]
    accession = _accession_from_filename(filename)
    if not accession:
        return ""

    # Accession directory name: dashes removed
    acc_dir = accession.replace("-", "")
    return f"{_FILING_BASE}/{cik}/{acc_dir}/primary-document.xml"


# ── XML parsing ───────────────────────────────────────────────────────────────


def _find_all_ns(root: ET.Element, local_name: str) -> list[ET.Element]:
    """Find all elements with a given local name, regardless of namespace."""
    results = []
    for el in root.iter():
        tag = el.tag
        # Strip namespace like {http://...}localName
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        if tag == local_name:
            results.append(el)
    return results


def _find_ns(root: ET.Element, local_name: str) -> Optional[ET.Element]:
    """Find first element with a given local name, regardless of namespace."""
    for el in root.iter():
        tag = el.tag
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        if tag == local_name:
            return el
    return None


def _text_of(element: Optional[ET.Element]) -> str:
    if element is None:
        return ""
    return (element.text or "").strip()


def parse_form_d_xml(xml_text: str, record: dict) -> list[dict]:
    """
    Parse a Form D XML filing and return one dict per officer found.

    Returns a list of dicts compatible with InvestorLead field names:
        name, email, role, fund, focus_areas, stage, check_size,
        location, linkedin, website, source, scraped_at,
        lead_score, tier, email_status
    """
    results: list[dict] = []

    try:
        root = ET.fromstring(xml_text.encode("utf-8", errors="replace"))
    except ET.ParseError as exc:
        logger.debug("XML parse error for %s: %s", record.get("filename", "?"), exc)
        return results

    # ── Issuer (fund) metadata ────────────────────────────────────────────────
    issuer_name = _text_of(_find_ns(root, "issuerName")) or record.get("company", "N/A")
    state_el = _find_ns(root, "issuerStateOrCountryDescription")
    state = _text_of(state_el)
    if not state:
        state = _text_of(_find_ns(root, "issuerStateOrCountry"))

    entity_type = _text_of(_find_ns(root, "entityType")) or "N/A"
    date_filed = record.get("date_filed", datetime.utcnow().strftime("%Y-%m-%d"))

    # ── Officers ──────────────────────────────────────────────────────────────
    # Form D XML has <relatedPersonsList><relatedPersonInfo>...</relatedPersonInfo>...
    # Each relatedPersonInfo contains:
    #   <relatedPersonName><firstName> <lastName>
    #   <relatedPersonRelationshipList><relationship> (one or more)
    #   <relationshipCoveredPersonsInfo> or <relatedPersonTitle>

    person_infos = _find_all_ns(root, "relatedPersonInfo")

    # Fallback: older filings use <officers><officer> structure
    if not person_infos:
        person_infos = _find_all_ns(root, "officer")

    for person in person_infos:
        first = _text_of(_find_ns(person, "firstName"))
        last = _text_of(_find_ns(person, "lastName"))

        if not first and not last:
            # Try combined name fields
            full = _text_of(_find_ns(person, "name"))
            if not full:
                continue
            parts = full.strip().split(None, 1)
            first = parts[0] if parts else ""
            last = parts[1] if len(parts) > 1 else ""

        full_name = f"{first} {last}".strip()
        if not full_name or full_name in ("-", "N/A"):
            continue

        # Role / title — try multiple field paths
        role = ""
        for field_name in _TITLE_FIELDS:
            role = _text_of(_find_ns(person, field_name))
            if role:
                break

        if not role:
            # Collect relationship type tags
            rel_els = _find_all_ns(person, "relationship")
            role_parts = [_text_of(r) for r in rel_els if _text_of(r)]
            role = "; ".join(role_parts) if role_parts else "Officer/Director"

        # Skip clearly non-officer relationships if we have enough signal
        role_lower = role.lower()
        if "investor" in role_lower and "director" not in role_lower and "officer" not in role_lower:
            continue

        results.append({
            "name": full_name,
            "email": "N/A",
            "email_status": "unknown",
            "role": role or "Officer/Director",
            "fund": issuer_name,
            "focus_areas": [],
            "stage": "N/A",
            "check_size": "N/A",
            "location": state or "N/A",
            "linkedin": "N/A",
            "website": "",
            "source": "SEC EDGAR Form D",
            "scraped_at": datetime.utcnow().isoformat(),
            "lead_score": 0,
            "tier": "",
            # Extra metadata for downstream enrichment
            "_entity_type": entity_type,
            "_date_filed": date_filed,
            "_cik": record.get("cik", ""),
        })

    return results


# ── Network fetching ──────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "User-Agent": _USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "*/*",
    }


async def _fetch_text(
    url: str,
    session: aiohttp.ClientSession,
    limiter: _RateLimiter,
    timeout: int = 30,
    retries: int = 3,
) -> Optional[str]:
    """Fetch a URL respecting the rate limiter; returns text or None on failure."""
    for attempt in range(retries):
        await limiter.acquire()
        try:
            async with session.get(
                url,
                headers=_headers(),
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as resp:
                if resp.status == 200:
                    content_type = resp.headers.get("Content-Type", "")
                    if "gzip" in content_type or url.endswith(".gz"):
                        raw = await resp.read()
                        return gzip.decompress(raw).decode("utf-8", errors="replace")
                    return await resp.text(errors="replace")
                if resp.status == 429:
                    wait = 60 * (attempt + 1)
                    logger.warning("Rate-limited by SEC (429); waiting %ds", wait)
                    await asyncio.sleep(wait)
                    continue
                if resp.status in (403, 404):
                    logger.debug("HTTP %d for %s", resp.status, url)
                    return None
                logger.debug("HTTP %d for %s (attempt %d)", resp.status, url, attempt + 1)
        except asyncio.TimeoutError:
            logger.debug("Timeout fetching %s (attempt %d)", url, attempt + 1)
        except aiohttp.ClientError as exc:
            logger.debug("Client error for %s: %s", url, exc)
        finally:
            limiter.release()

        if attempt < retries - 1:
            await asyncio.sleep(2 ** attempt)

    return None


async def _fetch_bytes(
    url: str,
    session: aiohttp.ClientSession,
    limiter: _RateLimiter,
    timeout: int = 60,
) -> Optional[bytes]:
    """Fetch raw bytes (for gzip index files)."""
    await limiter.acquire()
    try:
        async with session.get(
            url,
            headers=_headers(),
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status == 200:
                return await resp.read()
            logger.debug("HTTP %d fetching bytes from %s", resp.status, url)
            return None
    except Exception as exc:
        logger.debug("Error fetching bytes from %s: %s", url, exc)
        return None
    finally:
        limiter.release()


# ── Index downloading ─────────────────────────────────────────────────────────

async def _fetch_quarter_index(
    year: int,
    qtr: int,
    session: aiohttp.ClientSession,
    limiter: _RateLimiter,
) -> list[dict]:
    """
    Download and parse one quarter's company.idx from EDGAR.
    Tries the gzipped version first (faster), falls back to plain text.
    """
    gz_url = _INDEX_GZ_URL.format(year=year, qtr=qtr)
    plain_url = _INDEX_URL.format(year=year, qtr=qtr)

    logger.info("Fetching EDGAR index: %d QTR%d", year, qtr)

    # Try gzipped first
    raw_bytes = await _fetch_bytes(gz_url, session, limiter, timeout=120)
    if raw_bytes:
        try:
            text = gzip.decompress(raw_bytes).decode("latin-1", errors="replace")
            records = _parse_company_idx(text)
            logger.info("  QTR%d %d: %d Form D filings from gzip index", qtr, year, len(records))
            return records
        except Exception as exc:
            logger.warning("Failed to decompress %s: %s", gz_url, exc)

    # Fall back to plain text
    text = await _fetch_text(plain_url, session, limiter, timeout=120)
    if not text:
        logger.warning("Could not download index for %d QTR%d", year, qtr)
        return []

    records = _parse_company_idx(text)
    logger.info("  QTR%d %d: %d Form D filings from plain index", qtr, year, len(records))
    return records


# ── Filing worker ─────────────────────────────────────────────────────────────

async def _process_filing(
    record: dict,
    session: aiohttp.ClientSession,
    limiter: _RateLimiter,
) -> list[dict]:
    """
    Fetch one Form D XML filing and extract officer records.
    Returns a (possibly empty) list of officer dicts.
    """
    xml_url = _xml_url_from_record(record)
    if not xml_url:
        return []

    xml_text = await _fetch_text(xml_url, session, limiter)
    if not xml_text:
        return []

    return parse_form_d_xml(xml_text, record)


# ── CSV output ────────────────────────────────────────────────────────────────

def _write_csv(officers: list[dict], output_file: str) -> int:
    """
    Write officer dicts to a CSV matching the master investor_leads format.
    Returns the number of rows written.
    """
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for officer in officers:
            focus = officer.get("focus_areas", [])
            row = {
                "Name": officer.get("name", ""),
                "Email": officer.get("email", "N/A"),
                "Email Status": officer.get("email_status", "unknown"),
                "Role": officer.get("role", "N/A"),
                "Fund": officer.get("fund", "N/A"),
                "Focus Areas": "; ".join(focus) if isinstance(focus, list) else (focus or "N/A"),
                "Stage": officer.get("stage", "N/A"),
                "Check Size": officer.get("check_size", "N/A"),
                "Location": officer.get("location", "N/A"),
                "LinkedIn": officer.get("linkedin", "N/A"),
                "Website": officer.get("website", ""),
                "Lead Score": officer.get("lead_score", 0),
                "Tier": officer.get("tier", ""),
                "Source": officer.get("source", "SEC EDGAR Form D"),
                "Scraped At": officer.get("scraped_at", ""),
            }
            writer.writerow(row)
            written += 1

    return written


# ── Main extraction function ──────────────────────────────────────────────────

async def bulk_extract_form_d_officers(
    output_file: str,
    years: list[int] = None,
    max_filings: int = 50000,
    concurrency: int = 8,
    quarters: list[int] = None,
) -> list[dict]:
    """
    Bulk-extract fund officer records from SEC EDGAR Form D filings.

    Args:
        output_file:  Path to write the output CSV.
        years:        List of years to pull (default: [2022, 2023, 2024]).
        max_filings:  Maximum number of filings to process (across all quarters).
        concurrency:  Number of concurrent HTTP workers (max 10 recommended).
        quarters:     Quarters to pull per year (default: [1, 2, 3, 4]).

    Returns:
        List of officer dicts (also written to output_file as CSV).
    """
    if years is None:
        years = [2022, 2023, 2024]
    if quarters is None:
        quarters = [1, 2, 3, 4]

    # Cap concurrency to stay under SEC's 10 req/sec limit
    concurrency = min(concurrency, _MAX_RPS)

    limiter = _RateLimiter(max_rps=_MAX_RPS)

    connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency)
    timeout = aiohttp.ClientTimeout(total=60, connect=10)

    all_officers: list[dict] = []
    seen_names: set[tuple] = set()   # (name_lower, fund_lower) dedup
    filings_processed = 0
    filings_errored = 0

    start_ts = time.monotonic()

    logger.info(
        "Starting EDGAR bulk Form D extraction: years=%s, max_filings=%d, concurrency=%d",
        years, max_filings, concurrency,
    )

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:

        # ── Step 1: collect filing index entries ──────────────────────────────
        all_records: list[dict] = []
        for year in sorted(years):
            for qtr in quarters:
                # Skip future quarters
                now = datetime.utcnow()
                if year > now.year:
                    continue
                if year == now.year and qtr > (now.month - 1) // 3 + 1:
                    continue

                records = await _fetch_quarter_index(year, qtr, session, limiter)
                all_records.extend(records)
                await asyncio.sleep(0.2)  # be polite between index downloads

        logger.info("Total Form D filings found in index: %d", len(all_records))

        if not all_records:
            logger.warning("No filing records found — check network and year range.")
            return []

        # Cap to max_filings
        if len(all_records) > max_filings:
            logger.info("Capping to %d filings (from %d total)", max_filings, len(all_records))
            # Sort newest-first so we get recent data
            all_records.sort(key=lambda r: r.get("date_filed", ""), reverse=True)
            all_records = all_records[:max_filings]

        total = len(all_records)
        logger.info("Processing %d Form D filings...", total)

        # ── Step 2: fetch + parse filings concurrently ────────────────────────
        sem = asyncio.Semaphore(concurrency)

        async def bounded_process(record: dict) -> list[dict]:
            nonlocal filings_processed, filings_errored
            async with sem:
                try:
                    officers = await _process_filing(record, session, limiter)
                    filings_processed += 1
                    return officers
                except Exception as exc:
                    filings_errored += 1
                    logger.debug("Error processing %s: %s", record.get("filename", "?"), exc)
                    return []

        tasks = [asyncio.create_task(bounded_process(r)) for r in all_records]

        log_interval = max(1, total // 20)   # log at every 5% milestone

        for i, coro in enumerate(asyncio.as_completed(tasks)):
            batch = await coro

            for officer in batch:
                key = (
                    officer.get("name", "").lower().strip(),
                    officer.get("fund", "").lower().strip(),
                )
                if key[0] and key not in seen_names:
                    seen_names.add(key)
                    all_officers.append(officer)

            if (i + 1) % log_interval == 0 or i == total - 1:
                elapsed = time.monotonic() - start_ts
                rps = (i + 1) / elapsed if elapsed > 0 else 0
                logger.info(
                    "  [%d/%d] filings processed | %d officers collected | %.1f fil/s",
                    i + 1, total, len(all_officers), rps,
                )

    # ── Step 3: write CSV ─────────────────────────────────────────────────────
    written = _write_csv(all_officers, output_file)

    elapsed = time.monotonic() - start_ts
    logger.info(
        "EDGAR bulk extraction complete: %d officers from %d filings "
        "(%d errors) in %.0fs → %s",
        written, filings_processed, filings_errored, elapsed, output_file,
    )

    print(
        f"\n  SEC EDGAR Form D extraction complete:\n"
        f"    Filings processed : {filings_processed:,}\n"
        f"    Filings errored   : {filings_errored:,}\n"
        f"    Unique officers   : {len(all_officers):,}\n"
        f"    Written to CSV    : {written:,}\n"
        f"    Output file       : {output_file}\n"
        f"    Elapsed           : {elapsed:.0f}s\n"
    )

    return all_officers


# ── InvestorLead conversion ───────────────────────────────────────────────────

def officers_to_leads(officers: list[dict]) -> list[InvestorLead]:
    """
    Convert raw officer dicts to InvestorLead objects for pipeline ingestion.
    Filters out records with no usable name.
    """
    leads = []
    for o in officers:
        name = o.get("name", "").strip()
        if not name or name in ("N/A", ""):
            continue
        lead = InvestorLead(
            name=name,
            email=o.get("email", "N/A"),
            email_status=o.get("email_status", "unknown"),
            role=o.get("role", "N/A"),
            fund=o.get("fund", "N/A"),
            focus_areas=o.get("focus_areas", []),
            stage=o.get("stage", "N/A"),
            check_size=o.get("check_size", "N/A"),
            location=o.get("location", "N/A"),
            linkedin=o.get("linkedin", "N/A"),
            website=o.get("website", ""),
            source=o.get("source", "SEC EDGAR Form D"),
            scraped_at=o.get("scraped_at", datetime.utcnow().isoformat()),
            lead_score=o.get("lead_score", 0),
            tier=o.get("tier", ""),
        )
        leads.append(lead)
    return leads


# ── Pipeline integration helper ───────────────────────────────────────────────

async def run_edgar_bulk_discovery(
    output_file: str = "data/edgar_form_d.csv",
    years: list[int] = None,
    max_filings: int = 50000,
    concurrency: int = 8,
) -> list[InvestorLead]:
    """
    Top-level helper for engine.py to call.  Downloads Form D filings,
    extracts officers, writes CSV, and returns InvestorLead objects ready
    for the enrichment pipeline.

    Example usage in engine.py:
        from enrichment.edgar_bulk import run_edgar_bulk_discovery
        edgar_leads = await run_edgar_bulk_discovery(years=[2023, 2024])
        self.all_leads.extend(edgar_leads)
    """
    officers = await bulk_extract_form_d_officers(
        output_file=output_file,
        years=years or [2022, 2023, 2024],
        max_filings=max_filings,
        concurrency=concurrency,
    )
    return officers_to_leads(officers)


# ── CLI entrypoint ────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="edgar_bulk",
        description="Bulk-extract fund officer names from SEC EDGAR Form D filings.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=[2022, 2023, 2024],
        metavar="YEAR",
        help="Calendar years to pull filings for (e.g. --years 2022 2023 2024).",
    )
    parser.add_argument(
        "--quarters",
        nargs="+",
        type=int,
        default=[1, 2, 3, 4],
        choices=[1, 2, 3, 4],
        metavar="QTR",
        help="Quarters to pull per year (default: all four).",
    )
    parser.add_argument(
        "--max",
        type=int,
        default=50000,
        dest="max_filings",
        metavar="N",
        help="Maximum number of Form D filings to process.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/edgar_form_d.csv",
        metavar="FILE",
        help="Output CSV file path.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        metavar="N",
        help="Number of concurrent HTTP workers (max 10).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    return parser


if __name__ == "__main__":
    parser = _build_parser()
    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        asyncio.run(
            bulk_extract_form_d_officers(
                output_file=args.output,
                years=args.years,
                max_filings=args.max_filings,
                concurrency=args.concurrency,
                quarters=args.quarters,
            )
        )
    except KeyboardInterrupt:
        print("\nInterrupted — partial results may have been written.")
        sys.exit(130)
