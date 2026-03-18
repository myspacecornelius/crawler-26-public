"""
smtp_sample_test.py — SMTP hit-rate sampling on top-ranked email candidates.

Takes a random sample from HIGH/MEDIUM confidence rows, attempts SMTP RCPT TO,
and reports the estimated deliverability rate by confidence tier and MX provider.

Skips Google/Microsoft hosted domains (they block RCPT probing universally).
Short timeout (4s) to fail fast on blocked ports.

Usage:
    python3 scripts/smtp_sample_test.py --n 200
    python3 scripts/smtp_sample_test.py --n 500 --tier HIGH
"""

import argparse
import asyncio
import csv
import random
import re
import smtplib
import socket
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RANKED = ROOT / "data" / "enriched" / "investor_leads_ranked.csv"
TIMEOUT = 4  # seconds — fail fast
HELO = "leadfactory.io"

# MX providers that accept everything (catch-all gateways) — skip RCPT probing
# Google Workspace and Microsoft 365 DO respond correctly, so keep them testable
_BLOCKED_MX_PATTERNS = re.compile(
    r"(mimecast|proofpoint|barracuda|messagelabs|symantec"
    r"|spamhero|pphosted|mailchimp|sendgrid|amazonses|spamexperts"
    r"|hornetsecurity|trendmicro|sophos)",
    re.IGNORECASE,
)


def resolve_mx(domain: str):
    try:
        import dns.resolver
        records = dns.resolver.resolve(domain, "MX", lifetime=4)
        host = str(sorted(records, key=lambda r: r.preference)[0].exchange).rstrip(".")
        return host
    except Exception:
        pass
    try:
        socket.getaddrinfo(domain, 25, socket.AF_INET)
        return domain
    except Exception:
        return None


def smtp_probe(mx_host: str, email: str) -> str:
    """Returns: '250' | '5xx' | 'blocked' | 'timeout' | 'error'"""
    for port in [25, 587]:
        try:
            smtp = smtplib.SMTP(timeout=TIMEOUT)
            smtp.connect(mx_host, port)
            smtp.ehlo(HELO)
            smtp.mail(f"probe@{HELO}")
            code, _ = smtp.rcpt(email)
            try:
                smtp.quit()
            except Exception:
                pass
            if code == 250:
                return "250"
            elif str(code).startswith("5"):
                return "5xx"
            return f"other_{code}"
        except (TimeoutError, socket.timeout):
            return "timeout"
        except ConnectionRefusedError:
            return "refused"
        except smtplib.SMTPServerDisconnected:
            continue
        except OSError as e:
            if "Connection refused" in str(e):
                return "refused"
            if "timed out" in str(e).lower() or "errno 60" in str(e).lower():
                return "timeout"
            return f"os_error"
        except Exception:
            continue
    return "error"


async def probe_one(
    row: dict,
    sem: asyncio.Semaphore,
    results: list,
    counters: Counter,
):
    domain = row["Email"].split("@")[1].lower()
    async with sem:
        loop = asyncio.get_event_loop()
        mx = await loop.run_in_executor(None, resolve_mx, domain)
        if not mx:
            counters["no_mx"] += 1
            return

        if _BLOCKED_MX_PATTERNS.search(mx):
            counters["skipped_blocked_mx"] += 1
            mx_provider = re.search(r"(google|microsoft|outlook|mimecast|proofpoint|barracuda|pphosted)", mx, re.I)
            results.append({**row, "mx_host": mx, "smtp_result": "skipped_bulk_provider",
                            "mx_provider": mx_provider.group(1).lower() if mx_provider else "known_bulk"})
            return

        result = await loop.run_in_executor(None, smtp_probe, mx, row["Email"])
        counters[result] += 1
        results.append({**row, "mx_host": mx, "smtp_result": result, "mx_provider": "custom"})

        done = sum(counters.values())
        if done % 25 == 0:
            hit = counters["250"]
            rej = counters["5xx"]
            tot = hit + rej
            rate = f"{100*hit//tot}%" if tot else "?"
            print(f"  {done} probed | 250: {hit} | 5xx: {rej} | timeout: {counters['timeout']} "
                  f"| hit rate (excl timeout): {rate}", flush=True)


async def run(n: int, tier_filter: str, seed: int):
    rows = list(csv.DictReader(open(RANKED, encoding="utf-8")))
    print(f"  Loaded {len(rows)} ranked rows")

    # Filter to requested tier + guessed only (not scraped)
    pool = [
        r for r in rows
        if (tier_filter == "ALL" or r.get("Confidence Tier", "").strip() == tier_filter)
        and r.get("Email Status", "") == "guessed"
        and r.get("Email", "") not in ("", "N/A")
        and "@" in r.get("Email", "")
    ]
    print(f"  Pool after filter (tier={tier_filter}, status=guessed): {len(pool)}")

    random.seed(seed)
    sample = random.sample(pool, min(n, len(pool)))
    print(f"  Sample size: {len(sample)}")
    print(f"  SMTP timeout: {TIMEOUT}s | HELO: {HELO}")
    print(f"  Skipping Google/Microsoft/Mimecast/Proofpoint MX (block RCPT probing)")
    print()

    sem = asyncio.Semaphore(20)
    results = []
    counters: Counter = Counter()

    t0 = time.monotonic()
    await asyncio.gather(*[probe_one(r, sem, results, counters) for r in sample])
    elapsed = time.monotonic() - t0

    # Stats
    tested = counters["250"] + counters["5xx"] + counters["timeout"] + counters["refused"] + counters.get("error", 0)
    definitive = counters["250"] + counters["5xx"]
    hit_rate = counters["250"] / definitive if definitive else 0

    print(f"\n  {'='*55}")
    print(f"  RESULTS  ({elapsed:.0f}s)")
    print(f"  {'='*55}")
    print(f"  Sample:                    {len(sample)}")
    print(f"  Skipped (bulk MX):         {counters['skipped_blocked_mx']}")
    print(f"  No MX:                     {counters['no_mx']}")
    print(f"  Tested (custom MX only):   {tested}")
    print(f"")
    print(f"  250 deliverable:           {counters['250']}")
    print(f"  5xx rejected:              {counters['5xx']}")
    print(f"  Timeout:                   {counters['timeout']}")
    print(f"  Refused (port blocked):    {counters['refused']}")
    print(f"")
    print(f"  Hit rate (250 / definitive responses): {hit_rate:.1%}  (n={definitive})")

    if definitive < 20:
        print(f"  ⚠️  Too few definitive responses to estimate — port 25 likely blocked outbound")
    else:
        # Extrapolate to full 12k
        total_guessed = len([r for r in rows if r.get("Email Status") == "guessed"])
        custom_mx_fraction = tested / max(1, len(sample) - counters["skipped_blocked_mx"] - counters["no_mx"])
        est_testable = int(total_guessed * custom_mx_fraction)
        est_deliverable = int(est_testable * hit_rate)
        print(f"\n  Extrapolation to full {total_guessed} guessed leads:")
        print(f"    ~{est_testable} on custom MX (testable)")
        print(f"    ~{est_deliverable} estimated deliverable")

    # Pattern breakdown of hits
    hit_patterns = Counter(r["Pattern"] for r in results if r.get("smtp_result") == "250")
    if hit_patterns:
        print(f"\n  Pattern breakdown of 250 hits:")
        for pat, cnt in hit_patterns.most_common():
            print(f"    {pat}: {cnt}")

    # Provider breakdown
    provider_hits = defaultdict(Counter)
    for r in results:
        provider_hits[r.get("mx_provider","?")][r.get("smtp_result","?")] += 1
    print(f"\n  MX provider breakdown:")
    for prov, counts in sorted(provider_hits.items()):
        print(f"    {prov}: {dict(counts)}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200, help="Sample size (default 200)")
    p.add_argument("--tier", default="HIGH", choices=["HIGH","MEDIUM","LOW","ALL"])
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()
    asyncio.run(run(args.n, args.tier, args.seed))


if __name__ == "__main__":
    main()
