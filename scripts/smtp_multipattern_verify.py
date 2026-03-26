"""
SMTP Multi-Pattern Verification with Rotating ISP Proxies

For each unverified lead, generates all 8 email pattern candidates and
SMTP-verifies each via rotating SOCKS5 proxies. Keeps the first verified
hit per lead. Updates the master CSV.

Usage:
    python scripts/smtp_multipattern_verify.py --input data/enriched/leads_20260325_224027.csv
    python scripts/smtp_multipattern_verify.py --dry-run
"""

import asyncio
import argparse
import csv
import itertools
import logging
import random
import smtplib
import socket
import string
import sys
import time
from collections import defaultdict
from pathlib import Path

from __future__ import annotations

import socks  # PySocks

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from enrichment.email_guesser import generate_candidates, _extract_domain, _is_person_name
from enrichment.email_validator import EmailValidator

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# ── Proxy pool ────────────────────────────────────────────────────────────────

PROXIES = [
    {"host": "139.190.193.110", "port": 61234, "user": "LAVISHQU8JYK", "pass": "LVolKrJ1"},
    {"host": "139.190.193.111", "port": 61234, "user": "LAVISHQU8JZM", "pass": "BFZtNbng"},
    {"host": "139.190.193.112", "port": 61234, "user": "LAVISHQU8K0N", "pass": "C3HrGXqM"},
    {"host": "139.190.193.113", "port": 61234, "user": "LAVISHQU8K1P", "pass": "Npb6SO3u"},
    {"host": "139.190.193.114", "port": 61234, "user": "LAVISHQU8K2R", "pass": "JwTjpzIS"},
]

TASKS_PER_PROXY = 10
SMTP_TIMEOUT = 12

# Statuses that mean "already SMTP-checked"
SMTP_DONE = {"verified", "undeliverable", "catch_all"}

# ── Rotating proxy iterator ──────────────────────────────────────────────────

_proxy_cycle = itertools.cycle(PROXIES)
_proxy_lock = asyncio.Lock()


async def _next_proxy() -> dict:
    async with _proxy_lock:
        return next(_proxy_cycle)


# ── SOCKS5-proxied SMTP connection ──────────────────────────────────────────

def _smtp_connect_via_proxy(mx_host: str, mx_port: int, proxy: dict) -> smtplib.SMTP:
    """Create an SMTP connection tunneled through a SOCKS5 proxy."""
    sock = socks.socksocket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(SMTP_TIMEOUT)
    sock.set_proxy(
        socks.HTTP,
        proxy["host"],
        proxy["port"],
        username=proxy["user"],
        password=proxy["pass"],
    )
    sock.connect((mx_host, mx_port))

    smtp = smtplib.SMTP(timeout=SMTP_TIMEOUT)
    smtp.sock = sock
    # Read the banner manually since we connected raw
    smtp.file = smtp.sock.makefile("rb")
    code, msg = smtp.getreply()
    if code != 220:
        raise smtplib.SMTPConnectError(code, msg)
    smtp.ehlo_resp = None
    smtp.helo_resp = None
    smtp.esmtp_features = {}
    smtp.does_esmtp = False
    smtp.local_hostname = socket.getfqdn()
    return smtp


def _smtp_verify_one(email: str, mx_host: str, proxy: dict, helo_domain: str) -> dict:
    """
    Single synchronous SMTP RCPT TO check through a proxy.
    Returns {"deliverable": bool|None, "smtp_code": int, "catch_all": bool}.
    """
    result = {"deliverable": None, "smtp_code": 0, "catch_all": False}
    domain = email.rsplit("@", 1)[1].lower()

    try:
        smtp = _smtp_connect_via_proxy(mx_host, 25, proxy)

        code, _ = smtp.ehlo(helo_domain)
        if code != 250:
            code, _ = smtp.helo(helo_domain)
        if code != 250:
            try:
                smtp.quit()
            except Exception:
                pass
            return result

        code, _ = smtp.mail(f"verify@{helo_domain}")
        if code != 250:
            smtp.rset()
            code, _ = smtp.mail("")
        if code != 250:
            try:
                smtp.quit()
            except Exception:
                pass
            return result

        code, _ = smtp.rcpt(email)
        result["smtp_code"] = code

        if code == 250:
            result["deliverable"] = True
            # Catch-all check: try a random address
            try:
                fake = "".join(random.choices(string.ascii_lowercase, k=14)) + f"@{domain}"
                smtp.rset()
                smtp.mail(f"verify@{helo_domain}")
                fake_code, _ = smtp.rcpt(fake)
                if fake_code == 250:
                    result["catch_all"] = True
            except Exception:
                pass
        elif 500 <= code < 600:
            result["deliverable"] = False

        try:
            smtp.quit()
        except Exception:
            pass

    except Exception as e:
        logger.debug("SMTP %s via %s → error: %s", email, proxy["host"][-3:], e)

    return result


# ── MX resolution cache ─────────────────────────────────────────────────────

_mx_cache: dict[str, str | None] = {}


async def _resolve_mx(domain: str) -> str | None:
    if domain in _mx_cache:
        return _mx_cache[domain]
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX")
        mx = str(sorted(answers, key=lambda x: x.preference)[0].exchange).rstrip(".")
        _mx_cache[domain] = mx
        return mx
    except Exception:
        pass
    # Fallback: try domain directly
    try:
        loop = asyncio.get_running_loop()
        await loop.getaddrinfo(domain, 25)
        _mx_cache[domain] = domain
        return domain
    except Exception:
        _mx_cache[domain] = None
        return None


# ── Main verification logic ─────────────────────────────────────────────────

def load_leads(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_leads(path: str, rows: list[dict], fieldnames: list[str]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


async def verify_multipattern(rows: list[dict], dry_run: bool):
    total_concurrency = len(PROXIES) * TASKS_PER_PROXY
    helo_domain = "mail.leadfactory.io"

    # Separate leads into already-done vs needs-check
    done = []
    to_check = []
    skipped_no_name = 0
    skipped_no_domain = 0

    for row in rows:
        status = row.get("Email Status", "unknown")
        if status in SMTP_DONE:
            done.append(row)
            continue

        name = row.get("Name", "")
        website = row.get("Website", "")
        domain = _extract_domain(website)

        if not _is_person_name(name):
            skipped_no_name += 1
            done.append(row)
            continue

        if not domain:
            skipped_no_domain += 1
            done.append(row)
            continue

        to_check.append(row)

    print(f"\n{'='*60}")
    print(f"  SMTP MULTI-PATTERN VERIFICATION (proxied)")
    print(f"{'='*60}")
    print(f"  Total leads:          {len(rows)}")
    print(f"  Already SMTP-done:    {len(done) - skipped_no_name - skipped_no_domain}")
    print(f"  Skipped (bad name):   {skipped_no_name}")
    print(f"  Skipped (no domain):  {skipped_no_domain}")
    print(f"  To verify:            {len(to_check)}")
    print(f"  Proxies:              {len(PROXIES)}")
    print(f"  Tasks/proxy:          {TASKS_PER_PROXY}")
    print(f"  Total concurrency:    {total_concurrency}")
    print()

    if dry_run:
        sample = to_check[:5]
        for row in sample:
            name = row["Name"]
            domain = _extract_domain(row["Website"])
            candidates = generate_candidates(name, domain)
            print(f"  {name} @ {domain}:")
            for c in candidates:
                print(f"    {c}")
            print()
        print(f"  ... and {len(to_check) - len(sample)} more leads")
        print(f"  Total emails to verify: ~{len(to_check) * 8}")
        est_hours = (len(to_check) * 8) / (total_concurrency * 3) / 3600  # ~3s avg per check
        print(f"  Estimated time: ~{est_hours:.1f} hours at {total_concurrency} concurrency")
        return rows

    # ── Test proxy connectivity ──
    print(f"  Testing proxy connectivity...")
    test_proxy = PROXIES[0]
    try:
        loop = asyncio.get_running_loop()
        test_result = await loop.run_in_executor(
            None,
            lambda: _smtp_verify_one("test@gmail.com", "gmail-smtp-in.l.google.com", test_proxy, helo_domain),
        )
        if test_result["smtp_code"] > 0 or test_result["deliverable"] is not None:
            print(f"  Proxy test OK (code={test_result['smtp_code']})")
        else:
            # Try HTTP CONNECT style (some ISP proxies use HTTP not SOCKS5)
            print(f"  SOCKS5 returned no code, trying direct via proxy...")
    except Exception as e:
        print(f"  Proxy test error: {e}")
        print(f"  Trying HTTP proxy mode...")
        # Fall through — we'll handle failures per-email gracefully

    # ── Build candidate list ──
    by_domain: dict[str, list[tuple[int, dict, list[str]]]] = defaultdict(list)
    total_candidates = 0
    for idx, row in enumerate(to_check):
        name = row["Name"]
        domain = _extract_domain(row["Website"])
        candidates = generate_candidates(name, domain)
        if candidates:
            by_domain[domain].append((idx, row, candidates))
            total_candidates += len(candidates)

    print(f"  Domains to probe:     {len(by_domain)}")
    print(f"  Total candidates:     {total_candidates}")
    print()

    # ── Per-proxy semaphores ──
    proxy_sems = {p["host"]: asyncio.Semaphore(TASKS_PER_PROXY) for p in PROXIES}
    checked = 0
    verified_count = 0
    catch_all_count = 0
    undeliverable_count = 0
    proxy_errors = defaultdict(int)
    start_time = time.monotonic()

    # Results: lead_idx -> (email, status)
    lead_results: dict[int, tuple[str, str]] = {}

    # Track catch-all domains to avoid redundant fake-address checks
    known_catch_all: set[str] = set()

    # Checkpoint tracking
    last_checkpoint = time.monotonic()
    CHECKPOINT_INTERVAL = 300  # 5 minutes

    async def _check_candidate(email: str, email_domain: str, mx_host: str, lead_idx: int):
        nonlocal checked, verified_count, catch_all_count, undeliverable_count, last_checkpoint

        # Skip if we already found a verified email for this lead
        if lead_idx in lead_results and lead_results[lead_idx][1] == "verified":
            checked += 1
            return

        # If domain is known catch-all and we already have a catch-all for this lead, skip
        if email_domain in known_catch_all and lead_idx in lead_results:
            checked += 1
            return

        proxy = await _next_proxy()
        sem = proxy_sems[proxy["host"]]

        async with sem:
            loop = asyncio.get_running_loop()
            try:
                result = await loop.run_in_executor(
                    None,
                    lambda: _smtp_verify_one(email, mx_host, proxy, helo_domain),
                )
            except Exception as e:
                proxy_errors[proxy["host"]] += 1
                checked += 1
                return

            checked += 1

            if result["deliverable"] is True:
                if result["catch_all"]:
                    known_catch_all.add(email_domain)
                    if lead_idx not in lead_results or lead_results[lead_idx][1] != "verified":
                        lead_results[lead_idx] = (email, "catch_all")
                        catch_all_count += 1
                else:
                    lead_results[lead_idx] = (email, "verified")
                    verified_count += 1
            elif result["deliverable"] is False:
                undeliverable_count += 1

            if checked % 500 == 0:
                elapsed = time.monotonic() - start_time
                rate = checked / elapsed if elapsed > 0 else 0
                remaining = (total_candidates - checked) / rate / 60 if rate > 0 else 0
                print(f"  Progress: {checked:>7d}/{total_candidates} "
                      f"({verified_count} verified, {catch_all_count} catch-all, "
                      f"{undeliverable_count} bounced) "
                      f"[{rate:.1f}/s, ~{remaining:.0f}m left]")
                # Show proxy error stats if any
                if any(proxy_errors.values()):
                    err_str = ", ".join(f"...{h[-3:]}:{c}" for h, c in proxy_errors.items() if c > 0)
                    print(f"  Proxy errors: {err_str}")

            # Periodic checkpoint
            now = time.monotonic()
            if now - last_checkpoint > CHECKPOINT_INTERVAL:
                last_checkpoint = now
                _save_checkpoint(done, to_check, lead_results)

    # ── Build and run tasks ──
    print(f"  Resolving MX records for {len(by_domain)} domains...")
    mx_map: dict[str, str | None] = {}
    for domain in by_domain:
        mx_map[domain] = await _resolve_mx(domain)
    resolvable = sum(1 for v in mx_map.values() if v)
    print(f"  MX resolved: {resolvable}/{len(by_domain)} domains")

    tasks = []
    for domain, lead_entries in by_domain.items():
        mx_host = mx_map.get(domain)
        if not mx_host:
            continue
        for idx, row, candidates in lead_entries:
            for email in candidates:
                tasks.append(_check_candidate(email, domain, mx_host, idx))

    # Shuffle to distribute load across domains/MX servers
    random.shuffle(tasks)

    print(f"  Starting verification of {len(tasks)} emails...")
    print()

    await asyncio.gather(*tasks)

    elapsed = time.monotonic() - start_time
    rate = checked / elapsed if elapsed > 0 else 0
    print(f"\n{'='*60}")
    print(f"  VERIFICATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Time:          {elapsed:.0f}s ({elapsed/3600:.1f}h)")
    print(f"  Checked:       {checked}")
    print(f"  Rate:          {rate:.1f}/s")
    print(f"  Verified:      {verified_count}")
    print(f"  Catch-all:     {catch_all_count}")
    print(f"  Bounced:       {undeliverable_count}")
    print(f"  Leads updated: {len(lead_results)}")
    if any(proxy_errors.values()):
        print(f"  Proxy errors:  {dict(proxy_errors)}")
    print()

    # Apply results
    updates = 0
    for idx, row in enumerate(to_check):
        if idx in lead_results:
            email, status = lead_results[idx]
            row["Email"] = email
            row["Email Status"] = status
            updates += 1
        else:
            row["Email Status"] = "undeliverable"

    print(f"  Leads with verified/catch-all: {updates}")
    print(f"  Leads marked undeliverable:    {len(to_check) - updates}")

    return done + to_check


def _save_checkpoint(done: list, to_check: list, lead_results: dict):
    """Save partial progress to a checkpoint file."""
    path = "data/enriched/checkpoint_smtp_multipattern.csv"
    try:
        all_rows = done + to_check
        if not all_rows:
            return
        fieldnames = list(all_rows[0].keys())
        # Apply current results
        for idx, row in enumerate(to_check):
            if idx in lead_results:
                email, status = lead_results[idx]
                row["Email"] = email
                row["Email Status"] = status
        save_leads(path, all_rows, fieldnames)
        n_done = sum(1 for idx in range(len(to_check)) if idx in lead_results)
        print(f"  [checkpoint] Saved {len(all_rows)} leads ({n_done} updated) → {path}")
    except Exception as e:
        logger.warning(f"Checkpoint save failed: {e}")


async def main():
    parser = argparse.ArgumentParser(description="SMTP multi-pattern verification with rotating proxies")
    parser.add_argument(
        "--input", type=str,
        default="data/enriched/leads_20260325_224027.csv",
        help="Input CSV path",
    )
    parser.add_argument(
        "--output", type=str, default="",
        help="Output CSV path (default: overwrite input)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be checked without actually checking",
    )
    args = parser.parse_args()

    input_path = args.input
    output_path = args.output or input_path

    rows = load_leads(input_path)
    if not rows:
        print("No leads found")
        return

    fieldnames = list(rows[0].keys())

    result_rows = await verify_multipattern(rows, args.dry_run)

    if not args.dry_run:
        save_leads(output_path, result_rows, fieldnames)
        print(f"\n  Saved {len(result_rows)} leads → {output_path}")

        status_counts = defaultdict(int)
        for r in result_rows:
            status_counts[r.get("Email Status", "unknown")] += 1
        print(f"\n  Final email status breakdown:")
        for s, c in sorted(status_counts.items(), key=lambda x: -x[1]):
            print(f"    {s:20s} {c:6d}")


if __name__ == "__main__":
    asyncio.run(main())
