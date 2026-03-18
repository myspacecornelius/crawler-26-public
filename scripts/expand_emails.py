"""
expand_emails.py — Apply all 8 email patterns to existing master CSV.

Reads data/enriched/investor_leads_master.csv, expands each person-level
row into up to 8 email-pattern candidates, writes:
  data/enriched/investor_leads_expanded.csv

Skips rows that already have verified/scraped emails (keeps them as-is).
Deduplicates by (name, fund, email) so no exact duplicates.

Usage:
    python3 scripts/expand_emails.py
    python3 scripts/expand_emails.py --input data/enriched/investor_leads_master.csv
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from enrichment.email_guesser import generate_candidates, _is_person_name, _extract_domain

MASTER = ROOT / "data" / "enriched" / "investor_leads_master.csv"
OUT    = ROOT / "data" / "enriched" / "investor_leads_expanded.csv"

FIELDNAMES = [
    "Name", "Email", "Email Status", "Role", "Fund", "Focus Areas", "Stage",
    "Check Size", "Location", "LinkedIn", "Website",
    "Lead Score", "Tier", "Source", "Scraped At",
]


def expand_row(row: dict) -> list[dict]:
    """Return 1–8 rows for a single input row."""
    name   = row.get("Name", "").strip()
    email  = row.get("Email", "").strip()
    status = row.get("Email Status", "").strip().lower()
    website = row.get("Website", "").strip()

    # Already confirmed — keep as-is
    if status in ("verified", "scraped") and email and email != "N/A" and "@" in email:
        return [row]

    domain = _extract_domain(website)
    if not domain or not _is_person_name(name):
        return [row]

    candidates = generate_candidates(name, domain)
    if not candidates:
        return [row]

    expanded = []
    for candidate in candidates:
        new_row = dict(row)
        new_row["Email"] = candidate
        new_row["Email Status"] = "guessed"
        expanded.append(new_row)
    return expanded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=str(MASTER))
    parser.add_argument("--output", default=str(OUT))
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)

    if not src.exists():
        print(f"Input not found: {src}")
        sys.exit(1)

    rows = []
    with open(src, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"  Input: {len(rows)} rows from {src.name}")

    expanded = []
    for row in rows:
        expanded.extend(expand_row(row))

    # Deduplicate by (name, fund, email)
    seen: set = set()
    deduped = []
    for row in expanded:
        key = (
            row.get("Name", "").lower(),
            row.get("Fund", "").lower(),
            row.get("Email", "").lower(),
        )
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    with open(dst, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(deduped)

    # Stats
    verified = sum(1 for r in deduped if r.get("Email Status", "").lower() == "verified")
    scraped  = sum(1 for r in deduped if r.get("Email Status", "").lower() == "scraped")
    guessed  = sum(1 for r in deduped if r.get("Email Status", "").lower() == "guessed")
    with_email = sum(
        1 for r in deduped
        if r.get("Email", "") not in ("", "N/A") and "@" in r.get("Email", "")
    )

    print(f"  Output: {len(deduped)} rows → {dst.name}")
    print(f"  Emails: {with_email} total")
    print(f"    verified: {verified}")
    print(f"    scraped:  {scraped}")
    print(f"    guessed:  {guessed}")
    print(f"  Expansion: {len(rows)} → {len(deduped)} ({len(deduped)//max(1,len(rows))}x)")


if __name__ == "__main__":
    main()
