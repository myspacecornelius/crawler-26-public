"""
verify_emails.py — SMTP-verify the expanded email list.

Strategy per domain:
  1. MX check — skip any domain with no MX record
  2. Catch-all probe — send RCPT TO a random address; if 250, domain accepts everything
     → for catch-all domains keep only the best-pattern row per person (first.last@)
  3. SMTP RCPT TO — for non-catch-all domains, test every candidate
     → keep only rows that get a 250 response

Output:
  data/enriched/investor_leads_verified.csv   — confirmed deliverable (or best catch-all guess)
  data/enriched/investor_leads_unverified.csv — inconclusive (timeout, greylist, etc.)

Usage:
    python3 scripts/verify_emails.py
    python3 scripts/verify_emails.py --input data/enriched/investor_leads_expanded.csv
    python3 scripts/verify_emails.py --concurrency 30
"""

import argparse
import asyncio
import csv
import random
import smtplib
import socket
import string
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

EXPANDED   = ROOT / "data" / "enriched" / "investor_leads_expanded.csv"
OUT_GOOD   = ROOT / "data" / "enriched" / "investor_leads_verified.csv"
OUT_UNSURE = ROOT / "data" / "enriched" / "investor_leads_unverified.csv"

FIELDNAMES = [
    "Name", "Email", "Email Status", "Role", "Fund", "Focus Areas", "Stage",
    "Check Size", "Location", "LinkedIn", "Website",
    "Lead Score", "Tier", "Source", "Scraped At",
]

HELO = "leadfactory.io"
TIMEOUT = 10


# ── DNS / MX ──────────────────────────────────────────────────────────────────

def _resolve_mx(domain: str) -> Optional[str]:
    """Return best MX host for domain, or None."""
    try:
        import dns.resolver
        records = dns.resolver.resolve(domain, "MX", lifetime=8)
        return str(sorted(records, key=lambda r: r.preference)[0].exchange).rstrip(".")
    except Exception:
        pass
    # Fallback: try A record
    try:
        socket.getaddrinfo(domain, 25, socket.AF_INET)
        return domain
    except Exception:
        return None


_mx_cache: dict[str, Optional[str]] = {}

def mx_host(domain: str) -> Optional[str]:
    if domain not in _mx_cache:
        _mx_cache[domain] = _resolve_mx(domain)
    return _mx_cache[domain]


# ── SMTP helpers ──────────────────────────────────────────────────────────────

def _smtp_rcpt(host: str, email: str) -> int:
    """Return SMTP response code for RCPT TO, or 0 on error, -1 on timeout."""
    for port in [25, 587]:
        try:
            smtp = smtplib.SMTP(timeout=TIMEOUT)
            smtp.connect(host, port)
            smtp.ehlo(HELO)
            smtp.mail(f"probe@{HELO}")
            code, _ = smtp.rcpt(email)
            try:
                smtp.quit()
            except Exception:
                pass
            return code
        except (TimeoutError, socket.timeout, OSError):
            return -1
        except smtplib.SMTPServerDisconnected:
            continue
        except Exception:
            continue
    return 0


def _is_catch_all(mx: str, domain: str) -> bool:
    rand = "".join(random.choices(string.ascii_lowercase, k=16))
    fake = f"{rand}@{domain}"
    code = _smtp_rcpt(mx, fake)
    return code == 250


# ── Async worker ──────────────────────────────────────────────────────────────

async def _check_domain(
    domain: str,
    rows_by_person: dict[str, list[dict]],
    sem: asyncio.Semaphore,
    results_good: list,
    results_unsure: list,
    counters: dict,
):
    async with sem:
        loop = asyncio.get_event_loop()

        # MX lookup
        host = await loop.run_in_executor(None, mx_host, domain)
        if not host:
            counters["no_mx"] += 1
            return

        # Catch-all probe
        is_ca = await loop.run_in_executor(None, _is_catch_all, host, domain)

        if is_ca:
            counters["catch_all_domains"] += 1
            # Keep only best pattern per person (first.last@ is index 0)
            for person_key, person_rows in rows_by_person.items():
                # Sort by email pattern preference (first.last first)
                best = sorted(person_rows, key=lambda r: (
                    0 if "." in (r["Email"].split("@")[0]) and "_" not in r["Email"].split("@")[0] else 1
                ))[0]
                best = dict(best)
                best["Email Status"] = "catch_all"
                results_unsure.append(best)
                counters["catch_all_leads"] += 1
            return

        # Non-catch-all: SMTP test each candidate
        for person_key, person_rows in rows_by_person.items():
            found_one = False
            for row in person_rows:
                email = row["Email"]
                if not email or "@" not in email:
                    continue
                code = await loop.run_in_executor(None, _smtp_rcpt, host, email)
                counters["smtp_checks"] += 1

                if code == 250:
                    good = dict(row)
                    good["Email Status"] = "verified"
                    results_good.append(good)
                    counters["verified"] += 1
                    found_one = True
                    # Don't break — test all patterns so we capture every real alias
                elif code == -1:
                    # Timeout — inconclusive
                    unsure = dict(row)
                    unsure["Email Status"] = "timeout"
                    results_unsure.append(unsure)
                    counters["timeouts"] += 1
                # 550/551 etc → silently drop (undeliverable)
                else:
                    counters["rejected"] += 1

            if not found_one:
                counters["persons_no_valid_email"] += 1

        progress = counters["verified"] + counters["catch_all_leads"]
        if progress % 500 == 0 and progress > 0:
            print(
                f"  progress: {progress} good emails | "
                f"{counters['smtp_checks']} SMTP checks | "
                f"{counters['catch_all_domains']} catch-all domains"
            )


# ── Main ──────────────────────────────────────────────────────────────────────

def smtp_available() -> bool:
    """Quick check: can we reach port 25 on a well-known MX?"""
    try:
        smtp = smtplib.SMTP(timeout=8)
        smtp.connect("gmail-smtp-in.l.google.com", 25)
        smtp.quit()
        return True
    except Exception:
        pass
    try:
        smtp = smtplib.SMTP(timeout=8)
        smtp.connect("gmail-smtp-in.l.google.com", 587)
        smtp.quit()
        return True
    except Exception:
        return False


async def run(input_path: Path, concurrency: int):
    rows = []
    with open(input_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    print(f"  Loaded {len(rows)} rows from {input_path.name}")

    # Only process guessed rows — keep verified/scraped as-is
    to_verify = [r for r in rows if r.get("Email Status", "").lower() == "guessed"
                 and r.get("Email", "") not in ("", "N/A") and "@" in r.get("Email", "")]
    already_good = [r for r in rows if r.get("Email Status", "").lower() in ("verified", "scraped")
                    and r.get("Email", "") not in ("", "N/A") and "@" in r.get("Email", "")]

    print(f"  Already verified/scraped: {len(already_good)}")
    print(f"  To SMTP-verify: {len(to_verify)}")

    # Group by domain → person
    domain_persons: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in to_verify:
        email = row["Email"]
        domain = email.split("@")[1].lower()
        name = row.get("Name", "").lower().strip()
        domain_persons[domain][name].append(row)

    print(f"  Unique domains: {len(domain_persons)}")
    print(f"  Checking SMTP availability...")

    if not smtp_available():
        print("\n  ⚠️  Port 25/587 blocked on this network.")
        print("  Cannot SMTP-verify. Options:")
        print("    • Run on a VPS/cloud instance where port 25 is open")
        print("    • Set SMTP_PROXY_HOST env var to route through a proxy")
        print("    • Use Hunter/ZeroBounce/MillionVerifier API keys for paid verification")
        sys.exit(1)

    print(f"  SMTP available. Starting verification (concurrency={concurrency})...")
    t0 = time.monotonic()

    results_good: list[dict] = list(already_good)
    results_unsure: list[dict] = []
    counters = {
        "no_mx": 0, "catch_all_domains": 0, "catch_all_leads": 0,
        "verified": 0, "rejected": 0, "timeouts": 0,
        "smtp_checks": 0, "persons_no_valid_email": 0,
    }

    sem = asyncio.Semaphore(concurrency)
    tasks = [
        _check_domain(domain, dict(persons), sem, results_good, results_unsure, counters)
        for domain, persons in domain_persons.items()
    ]
    await asyncio.gather(*tasks)

    elapsed = time.monotonic() - t0

    # Write outputs
    def write_csv(path: Path, data: list[dict]):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(data)

    write_csv(OUT_GOOD, results_good)
    write_csv(OUT_UNSURE, results_unsure)

    print(f"\n  Done in {elapsed:.0f}s")
    print(f"  Verified deliverable: {len(results_good)} → {OUT_GOOD.name}")
    print(f"    (includes {len(already_good)} pre-existing scraped/verified)")
    print(f"  Inconclusive (catch-all/timeout): {len(results_unsure)} → {OUT_UNSURE.name}")
    print(f"\n  SMTP checks run: {counters['smtp_checks']}")
    print(f"  Confirmed 250:   {counters['verified']}")
    print(f"  Rejected 5xx:    {counters['rejected']}")
    print(f"  Timeouts:        {counters['timeouts']}")
    print(f"  No MX record:    {counters['no_mx']} domains")
    print(f"  Catch-all:       {counters['catch_all_domains']} domains "
          f"({counters['catch_all_leads']} leads kept as best-guess)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(EXPANDED))
    parser.add_argument(
        "--concurrency", type=int, default=25,
        help="Concurrent SMTP connections (default: 25)",
    )
    args = parser.parse_args()
    asyncio.run(run(Path(args.input), args.concurrency))


if __name__ == "__main__":
    main()
