"""
edgar_fund_names_to_domains.py — Fast EDGAR Form D fund-name domain extractor.

Downloads only the quarterly EDGAR company index files (one per quarter) to
extract all Form D company names, then DNS-verifies derived domain candidates
and appends verified domains to data/target_funds.txt.

Much faster than edgar_bulk.py (which fetches individual XML files) because
company names are present directly in the company.gz index.

Usage:
    python scripts/edgar_fund_names_to_domains.py          # dry-run
    python scripts/edgar_fund_names_to_domains.py --write  # append domains
    python scripts/edgar_fund_names_to_domains.py --write --years 2022 2023 2024 2025
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import logging
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterator

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
TARGET_FUNDS = ROOT / "data" / "target_funds.txt"

_EDGAR_BASE = "https://www.sec.gov"
_INDEX_GZ = _EDGAR_BASE + "/Archives/edgar/full-index/{year}/QTR{qtr}/company.gz"
_INDEX_IDX = _EDGAR_BASE + "/Archives/edgar/full-index/{year}/QTR{qtr}/company.idx"
_FORM_D = {"D", "D/A"}
_UA = "LeadFactory/1.0 (contact@leadfactory.io)"

# Name normalization — mirrors scripts/verify_fund_domains.py logic
_LEGAL_SUFFIXES = re.compile(
    r"\b(llc|l\.l\.c\.|lp|l\.p\.|ltd|limited|inc|inc\.|corp|corp\."
    r"|co\.|co|plc|pllc|llp|l\.l\.p\.|s\.a\.|n\.a\.|n\.v\.|ag|gmbh"
    r"|bv|oy|holdings?|management|mgmt|advisors?|advisory|associates?"
    r"|services?|solutions?|group|international|intl|global|worldwide)\b",
    re.IGNORECASE,
)
_FUND_SERIES = re.compile(
    r"\b(fund\s*(?:i{1,3}|iv|v?i{0,3}|\d+)|series\s*\w+|"
    r"class\s+[a-z0-9]+|tranche\s+\w+)\b",
    re.IGNORECASE,
)
_CLEAN_PUNCT = re.compile(r"[^a-zA-Z0-9\s-]")
_MULTI_SPACE = re.compile(r"\s+")
_SKIP_PATTERNS = re.compile(
    r"\b(mortgage|loan\s+trust|securit|pass.through|note.*trust|"
    r"certificate.*trust|asset.backed|abs\s*trust|collateral|"
    r"bank|bancorp|savings|thrift|insurance|annuity|reit|"
    r"school|university|college|foundation|government|agency|"
    r"federal\s+reserve|municipal|pension|401k|retirement)\b",
    re.IGNORECASE,
)
_EXTENSIONS = [".com", ".vc"]


def _base_slug(fund_name: str) -> str:
    s = _FUND_SERIES.sub(" ", fund_name)
    s = _LEGAL_SUFFIXES.sub(" ", s)
    s = _CLEAN_PUNCT.sub("", s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s.lower().replace(" ", "")


def domain_candidates(fund_name: str) -> list[str]:
    """Return domain candidates for a fund name."""
    if not fund_name or _SKIP_PATTERNS.search(fund_name):
        return []
    if re.match(
        r"^[A-Z]+\s+[A-Z]+(\s+[A-Z]{1,3}\.?|\s+(?:JR|SR|II|III|IV)\.?)?$",
        fund_name.strip(),
    ):
        return []
    slug = _base_slug(fund_name)
    if not slug or len(slug) < 3:
        return []
    candidates: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s = s.strip("-").lower()
        if s and 3 <= len(s) <= 40 and s not in seen:
            seen.add(s)
            candidates.append(s)

    add(slug)
    for word in ("capital", "ventures", "venture", "partners", "invest", "fund"):
        if slug.endswith(word) and len(slug) > len(word) + 2:
            add(slug[: -len(word)])

    domains: list[str] = []
    for s in candidates[:2]:
        for ext in _EXTENSIONS:
            domains.append(s + ext)
    return domains


# ── Index fetching ────────────────────────────────────────────────────────────

def _fetch_index(year: int, qtr: int, max_attempts: int = 5) -> str | None:
    """Download and decompress quarterly company.gz (or .idx) index.

    Retries on 429 with exponential backoff.
    """
    headers = {"User-Agent": _UA}
    for url in [_INDEX_GZ.format(year=year, qtr=qtr),
                _INDEX_IDX.format(year=year, qtr=qtr)]:
        for attempt in range(max_attempts):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read()
                if url.endswith(".gz"):
                    return gzip.decompress(raw).decode("latin-1", errors="replace")
                return raw.decode("latin-1", errors="replace")
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    wait = 30 * (2 ** attempt)
                    log.info(
                        "    Rate-limited (429); waiting %ds...", wait
                    )
                    time.sleep(wait)
                elif exc.code == 404:
                    break  # Quarter doesn't exist yet — try next URL
                else:
                    log.debug("  HTTP %d for %s", exc.code, url)
                    break
            except Exception as exc:
                log.debug("  %s: %s", url, exc)
                break
    return None


def _parse_form_d_names(raw: str) -> Iterator[str]:
    """Yield company names from a raw company.idx text."""
    in_data = False
    for line in raw.splitlines():
        if re.match(r"-{10,}", line.strip()):
            in_data = True
            continue
        if not in_data or not line.strip():
            continue
        m = re.match(
            r"^(.{62})\s*(\S+)\s+(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\S+)",
            line,
        )
        if not m:
            continue
        if m.group(2).strip() in _FORM_D:
            yield m.group(1).strip()


# ── DNS verification ──────────────────────────────────────────────────────────

async def _dns_exists(domain: str, loop: asyncio.AbstractEventLoop) -> bool:
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
    concurrency: int = 150,
) -> dict[str, bool]:
    sem = asyncio.Semaphore(concurrency)
    loop = asyncio.get_event_loop()

    async def check_one(domain: str) -> tuple[str, bool]:
        async with sem:
            exists = await _dns_exists(domain, loop)
            return domain, exists

    results = await asyncio.gather(*[check_one(d) for d in domains])
    return dict(results)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_existing() -> set[str]:
    existing: set[str] = set()
    if TARGET_FUNDS.exists():
        for line in TARGET_FUNDS.read_text(
            encoding="utf-8", errors="ignore"
        ).splitlines():
            d = line.strip()
            if d:
                d = re.sub(r"^https?://(?:www\.)?", "", d).rstrip("/").lower()
                existing.add(d)
    return existing


# ── Main ──────────────────────────────────────────────────────────────────────

def run(
    years: list[int],
    write: bool = False,
    max_candidates: int = 40000,
    dns_concurrency: int = 150,
) -> None:
    log.info("\n" + "=" * 60)
    log.info("  EDGAR FORM D → DOMAIN DNS VERIFIER")
    log.info("=" * 60)

    existing = load_existing()
    log.info("\n  Existing domains: %d", len(existing))

    # Collect company names from quarterly indices
    all_names: list[str] = []
    name_seen: set[str] = set()

    quarters = [(y, q) for y in years for q in [1, 2, 3, 4]]
    for year, qtr in quarters:
        log.info("  Fetching QTR%d %d ...", qtr, year)
        raw = _fetch_index(year, qtr)
        if not raw:
            log.info("    → not available")
            continue
        n = 0
        for name in _parse_form_d_names(raw):
            if name and name not in name_seen:
                name_seen.add(name)
                all_names.append(name)
                n += 1
        log.info("    → %d unique Form D company names", n)
        time.sleep(0.5)

    log.info("\n  Total unique fund names: %d", len(all_names))

    # Generate domain candidates
    all_candidates: list[str] = []
    cand_seen: set[str] = set()
    for name in all_names:
        for cand in domain_candidates(name):
            if cand not in existing and cand not in cand_seen:
                cand_seen.add(cand)
                all_candidates.append(cand)

    log.info("  Domain candidates: %d", len(all_candidates))

    if len(all_candidates) > max_candidates:
        log.info("  Limiting to %d candidates (use --max to increase)", max_candidates)
        all_candidates = all_candidates[:max_candidates]

    if not all_candidates:
        log.info("  No new candidates to check.")
        return

    # DNS verification
    log.info("\n  DNS-verifying %d candidates ...", len(all_candidates))
    t0 = time.monotonic()
    try:
        results = asyncio.run(_check_batch(all_candidates, concurrency=dns_concurrency))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        results = loop.run_until_complete(
            _check_batch(all_candidates, concurrency=dns_concurrency)
        )
    elapsed = time.monotonic() - t0
    verified = [d for d, ok in results.items() if ok]

    log.info("  Verified in %.1fs: %d/%d domains exist",
             elapsed, len(verified), len(all_candidates))
    log.info("  Hit rate: %d%%",
             100 * len(verified) // max(1, len(all_candidates)))

    if not write:
        log.info(
            "\n  Dry-run — use --write to append to target_funds.txt"
        )
        log.info(
            "  target_funds.txt: %d → ~%d",
            len(existing), len(existing) + len(verified),
        )
        return

    with TARGET_FUNDS.open("a", encoding="utf-8") as fh:
        for d in sorted(verified):
            fh.write(d + "\n")

    log.info("\n  Appended %d domains to %s", len(verified), TARGET_FUNDS)
    log.info("  target_funds.txt: %d → %d",
             len(existing), len(existing) + len(verified))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract Form D fund domains from EDGAR quarterly indices"
    )
    parser.add_argument(
        "--years", nargs="+", type=int,
        default=[2022, 2023, 2024, 2025],
        help="Calendar years to process (default: 2022-2025)",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Append verified domains to target_funds.txt",
    )
    parser.add_argument(
        "--max", type=int, default=40000, dest="max_candidates",
        help="Max domain candidates to DNS-check (default: 40000)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=150,
        help="DNS lookup concurrency (default: 150)",
    )
    args = parser.parse_args()
    run(
        years=args.years,
        write=args.write,
        max_candidates=args.max_candidates,
        dns_concurrency=args.concurrency,
    )


if __name__ == "__main__":
    main()
