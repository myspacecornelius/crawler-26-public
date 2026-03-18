"""
verify_fund_domains.py — DNS-verify derived fund domains and add to target_funds.txt.

Reads fund names from:
  - data/edgar_form_d.csv  (output of enrichment/edgar_bulk.py)
  - data/seed/*.csv        (Fund column)

For each unique fund name, generates multiple domain candidates using name
normalization patterns, then fires async DNS A-record lookups to verify which
domains actually exist. Only verified domains (with a real A record) are added
to data/target_funds.txt.

Why DNS over SMTP:
  - DNS A-record lookup: ~10ms, no rate-limit concerns, fully passive
  - SMTP check: ~2s, triggers spam filters, requires MX
  - For domain existence validation, A-record is fast and sufficient

Usage:
    python scripts/verify_fund_domains.py               # dry-run
    python scripts/verify_fund_domains.py --write       # append verified to target_funds.txt
    python scripts/verify_fund_domains.py --write --max 20000
    python scripts/verify_fund_domains.py --input data/edgar_form_d.csv --write

Target: 15,000-30,000 domain candidates → 20-40% DNS hit rate → 3,000-12,000 new domains
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import re
import socket
import sys
import time
from pathlib import Path
from typing import Iterator

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
TARGET_FUNDS = ROOT / "data" / "target_funds.txt"

# ── Name normalization ─────────────────────────────────────────────────────────

_LEGAL_SUFFIXES = re.compile(
    r"\b(llc|l\.l\.c\.|lp|l\.p\.|ltd|limited|inc|inc\.|corp|corp\.|co\.|co|"
    r"plc|pllc|llp|l\.l\.p\.|s\.a\.|n\.a\.|n\.v\.|ag|gmbh|bv|oy|"
    r"holdings?|management|mgmt|advisors?|advisory|associates?|services?|"
    r"solutions?|group|international|intl|global|worldwide)\b",
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

# Domain extensions to try beyond .com
_EXTENSIONS = [".com", ".vc", ".co", ".fund", ".capital", ".io"]
# Max extensions to check per candidate (limit to avoid too many lookups)
_MAX_EXTENSIONS = 2


def _base_slug(fund_name: str) -> str:
    """Produce a clean lowercase slug from a fund name."""
    s = _FUND_SERIES.sub(" ", fund_name)
    s = _LEGAL_SUFFIXES.sub(" ", s)
    s = _CLEAN_PUNCT.sub("", s)
    s = _MULTI_SPACE.sub(" ", s).strip()
    return s.lower().replace(" ", "")


def _slug_variants(fund_name: str) -> list[str]:
    """
    Generate ordered list of domain slug candidates for a fund name.
    Returns slugs WITHOUT extension (caller appends TLD).
    """
    full_slug = _base_slug(fund_name)
    if not full_slug or len(full_slug) < 3:
        return []

    variants: list[str] = []
    seen: set[str] = set()

    def add(s: str) -> None:
        s = s.strip("-").lower()
        if s and len(s) >= 3 and len(s) <= 40 and s not in seen:
            seen.add(s)
            variants.append(s)

    # Primary: full collapsed slug
    add(full_slug)

    # Without common investor words if they're in the name
    for word in ("capital", "ventures", "venture", "partners", "invest", "fund"):
        if full_slug.endswith(word) and len(full_slug) > len(word) + 2:
            add(full_slug[: -len(word)])
        if full_slug.startswith(word) and len(full_slug) > len(word) + 2:
            add(full_slug[len(word):])

    return variants


def domain_candidates(fund_name: str) -> list[str]:
    """
    Return a list of domain candidates (with TLD) for a fund name.
    Ordered from most to least likely.
    """
    if not fund_name or fund_name == "N/A" or _SKIP_PATTERNS.search(fund_name):
        return []
    # Skip individual person names (ALL CAPS FIRST LAST)
    if re.match(r"^[A-Z]+\s+[A-Z]+(\s+[A-Z]{1,3}\.?|\s+(?:JR|SR|II|III|IV)\.?)?$", fund_name.strip()):
        return []

    slugs = _slug_variants(fund_name)
    if not slugs:
        return []

    candidates: list[str] = []
    # Take up to 2 slugs × up to 2 extensions = 4 candidates per fund
    for slug in slugs[:2]:
        for ext in _EXTENSIONS[:_MAX_EXTENSIONS]:
            candidates.append(slug + ext)
    return candidates


# ── Domain existence check ─────────────────────────────────────────────────────

async def _dns_exists(domain: str, loop: asyncio.AbstractEventLoop) -> bool:
    """Return True if the domain resolves to at least one A record."""
    try:
        result = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(domain, None, socket.AF_INET, socket.SOCK_STREAM),
        )
        return bool(result)
    except (socket.gaierror, OSError):
        return False


async def _check_batch(
    domains: list[str],
    concurrency: int = 200,
) -> dict[str, bool]:
    """DNS-check a list of domains concurrently. Returns {domain: exists}."""
    sem = asyncio.Semaphore(concurrency)
    loop = asyncio.get_event_loop()

    async def check_one(domain: str) -> tuple[str, bool]:
        async with sem:
            exists = await _dns_exists(domain, loop)
            return domain, exists

    tasks = [check_one(d) for d in domains]
    results = await asyncio.gather(*tasks)
    return dict(results)


# ── Data readers ──────────────────────────────────────────────────────────────

def iter_fund_names(input_files: list[Path]) -> Iterator[str]:
    """Yield unique fund names from CSV files."""
    seen: set[str] = set()

    for path in input_files:
        if not path.exists():
            continue
        try:
            with path.open(encoding="utf-8", errors="ignore") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    # Accept 'Fund', 'fund', 'fund_name', 'firm_name', 'name', 'company'
                    for col in ("Fund", "fund", "fund_name", "firm_name", "name", "company", "Name"):
                        val = (row.get(col) or "").strip()
                        if val and val not in ("N/A", "Unknown", ""):
                            if val not in seen:
                                seen.add(val)
                                yield val
                            break
        except Exception as exc:
            log.warning(f"  Could not read {path}: {exc}")


def load_existing() -> set[str]:
    existing: set[str] = set()
    if TARGET_FUNDS.exists():
        for line in TARGET_FUNDS.read_text(encoding="utf-8", errors="ignore").splitlines():
            d = line.strip()
            if d:
                d = re.sub(r"^https?://(?:www\.)?", "", d).rstrip("/").lower()
                existing.add(d)
    return existing


# ── Main ──────────────────────────────────────────────────────────────────────

def run(
    input_files: list[Path],
    write: bool = False,
    max_candidates: int = 30000,
    dns_concurrency: int = 150,
    verbose: bool = False,
) -> None:
    log.info("\n" + "=" * 60)
    log.info("  FUND DOMAIN DNS VERIFIER")
    log.info("=" * 60)

    existing = load_existing()
    log.info(f"\n  Existing domains in target_funds.txt: {len(existing)}")

    # Collect fund names and generate candidates
    log.info("\n  Reading fund names from input files...")
    all_candidates: list[str] = []
    seen_candidates: set[str] = set()

    fund_count = 0
    for fund_name in iter_fund_names(input_files):
        fund_count += 1
        for candidate in domain_candidates(fund_name):
            if candidate not in existing and candidate not in seen_candidates:
                seen_candidates.add(candidate)
                all_candidates.append(candidate)

    log.info(f"  Fund names read: {fund_count}")
    log.info(f"  Domain candidates generated: {len(all_candidates)}")

    if len(all_candidates) > max_candidates:
        log.info(f"  Limiting to {max_candidates} candidates (use --max to increase)")
        all_candidates = all_candidates[:max_candidates]

    if not all_candidates:
        log.info("  No new candidates to check.")
        return

    # DNS verification
    log.info(f"\n  DNS-verifying {len(all_candidates)} candidates")
    log.info(f"  (concurrency={dns_concurrency}, estimated time: ~{len(all_candidates)//dns_concurrency + 5}s)...")
    t0 = time.monotonic()

    try:
        results = asyncio.run(_check_batch(all_candidates, concurrency=dns_concurrency))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        results = loop.run_until_complete(_check_batch(all_candidates, concurrency=dns_concurrency))

    elapsed = time.monotonic() - t0
    verified = [d for d, ok in results.items() if ok]

    log.info(f"  Verified in {elapsed:.1f}s: {len(verified)}/{len(all_candidates)} domains exist")
    log.info(f"  Hit rate: {100*len(verified)//max(1,len(all_candidates))}%")

    if verbose:
        for d in sorted(verified)[:50]:
            log.info(f"    ✓ {d}")
        if len(verified) > 50:
            log.info(f"    ... and {len(verified)-50} more")

    if not write:
        log.info(f"\n  Dry-run — use --write to append to target_funds.txt")
        log.info(f"  target_funds.txt would grow from {len(existing)} → ~{len(existing) + len(verified)}")
        return

    with TARGET_FUNDS.open("a", encoding="utf-8") as fh:
        for d in sorted(verified):
            fh.write(d + "\n")

    log.info(f"\n  Appended {len(verified)} verified domains to {TARGET_FUNDS}")
    log.info(f"  target_funds.txt now has ~{len(existing) + len(verified)} domains")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DNS-verify fund domain candidates and add to target_funds.txt"
    )
    parser.add_argument(
        "--input", nargs="+", type=Path,
        default=[
            ROOT / "data" / "edgar_form_d.csv",
            ROOT / "data" / "seed" / "vc_firms.csv",
            ROOT / "data" / "seed" / "vc_firms_expanded.csv",
            ROOT / "data" / "seed" / "vc_firms_supplemental.csv",
            ROOT / "data" / "seed" / "vc_firms_tier2.csv",
            ROOT / "data" / "seed" / "pe_firms.csv",
            ROOT / "data" / "seed" / "family_offices.csv",
            ROOT / "data" / "seed" / "vc_firms_iapd.csv",
        ],
        help="CSV files containing fund names to process",
    )
    parser.add_argument("--write", action="store_true", help="Append verified domains to target_funds.txt")
    parser.add_argument("--max", type=int, default=30000, dest="max_candidates",
                        help="Max domain candidates to DNS-check (default: 30000)")
    parser.add_argument("--concurrency", type=int, default=150,
                        help="DNS lookup concurrency (default: 150)")
    parser.add_argument("--verbose", action="store_true", help="Print verified domains")
    args = parser.parse_args()
    run(
        input_files=args.input,
        write=args.write,
        max_candidates=args.max_candidates,
        dns_concurrency=args.concurrency,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
