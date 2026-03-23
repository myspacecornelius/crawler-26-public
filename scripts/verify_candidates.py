import asyncio
import csv
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from enrichment.email_validator import EmailValidator

INPUT_CSV = ROOT / "data" / "enriched" / "investor_leads_top_candidates.csv"
OUTPUT_CSV = ROOT / "data" / "enriched" / "investor_leads_smtp_verified.csv"

FIELDNAMES = [
    "Name", "Email", "Email Status", "Confidence", "Confidence Tier",
    "Pattern", "Pattern Source",
    "Role", "Fund", "Focus Areas", "Stage", "Check Size",
    "Location", "LinkedIn", "Website",
    "Lead Score", "Tier", "Source", "Scraped At",
]

async def main():
    if not INPUT_CSV.exists():
        print(f"Error: {INPUT_CSV} not found")
        return

    print(f"Loading {INPUT_CSV.name}...")
    with open(INPUT_CSV, "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"Loaded {len(rows)} candidates.")

    # Unique emails to verify
    emails = list(set(r.get("Email", "") for r in rows if "@" in r.get("Email", "")))
    print(f"Starting SMTP validation on {len(emails)} unique emails...")

    validator = EmailValidator()
    # verify_smtp_batch uses concurrency internally
    results = await validator.verify_smtp_batch(emails, concurrency=50)

    verified_count = 0
    undeliverable_count = 0
    catchall_count = 0
    unknown_count = 0

    # Group rows by person (Name + Fund)
    persons = defaultdict(list)

    for row in rows:
        email = row.get("Email", "")
        res = results.get(email)

        status = "unknown"
        if not res:
            unknown_count += 1
        else:
            if res.get("deliverable") is True:
                if res.get("catch_all"):
                    status = "catch_all"
                    catchall_count += 1
                else:
                    status = "verified"
                    verified_count += 1
            elif res.get("deliverable") is False:
                status = "undeliverable"
                undeliverable_count += 1
            else:
                unknown_count += 1

        # Preserve "scraped" status if it was already known ground truth
        if row.get("Email Status") not in ("scraped", "verified") or status == "undeliverable":
            row["Email Status"] = status
        
        # We assume the input CSV is already sorted by rank/confidence per person
        key = (row.get("Name", "").strip().lower(), row.get("Fund", "").strip().lower())
        persons[key].append(row)

    print(f"\nSMTP Results: {verified_count} verified, {catchall_count} catch-all, {undeliverable_count} undeliverable, {unknown_count} unknown/timeout")

    # Pick the best email per person
    best_rows = []
    for key, candidates in persons.items():
        # Preference: 1. verified/scraped, 2. catch_all/unknown, 3. undeliverable
        def rank_status(r):
            st = r.get("Email Status", "")
            if st in ("verified", "scraped"): return 0
            if st == "catch_all": return 1
            if st == "unknown": return 2
            return 3 # undeliverable

        candidates.sort(key=rank_status)
        best_rows.append(candidates[0])

    print(f"Filtered down to {len(best_rows)} unique persons (best valid email).")

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(best_rows)

    print(f"Saved deduplicated & verified leads to {OUTPUT_CSV.name}")

if __name__ == "__main__":
    asyncio.run(main())
