import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENRICHED_DIR = ROOT / "data" / "enriched"
OUT_MASTER = ENRICHED_DIR / "investor_leads_master_rebuilt.csv"

FIELDNAMES = [
    "Name", "Email", "Email Status", "Role", "Fund", "Focus Areas", "Stage",
    "Check Size", "Location", "LinkedIn", "Website",
    "Lead Score", "Tier", "Source", "Scraped At",
    "Confidence", "Confidence Tier", "Pattern", "Pattern Source"
]

def main():
    seen = set()
    all_leads = []

    # Read all leads_YYYYMMDD_HHMMSS.csv files
    # Also read the top_candidates and ranked if needed
    files_to_read = list(ENRICHED_DIR.glob("leads_*.csv"))
    files_to_read.append(ENRICHED_DIR / "investor_leads_top_candidates.csv")
    files_to_read.append(ENRICHED_DIR / "investor_leads_expanded.csv")

    for file in files_to_read:
        if not file.exists():
            continue
        print(f"Reading {file.name}...")
        try:
            with open(file, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Dedup key: name, fund, email
                    name = row.get("Name", "").strip().lower()
                    fund = row.get("Fund", "").strip().lower()
                    email = row.get("Email", "").strip().lower()
                    
                    if not name or not fund:
                        continue
                        
                    key = (name, fund, email)
                    if key not in seen:
                        seen.add(key)
                        all_leads.append(row)
        except Exception as e:
            print(f"Error reading {file.name}: {e}")

    # Re-normalize keys to match fieldnames, adding missing keys as blanks
    normalized_leads = []
    for row in all_leads:
        norm = {f: row.get(f, "") for f in FIELDNAMES}
        normalized_leads.append(norm)

    print(f"\nTotal unique rows (Name, Fund, Email) combined: {len(normalized_leads)}")

    # Let's also see how many unique persons we have
    persons = set()
    for row in normalized_leads:
        persons.add((row["Name"].lower(), row["Fund"].lower()))
        
    print(f"Total unique PERSONS (Name, Fund): {len(persons)}")

    with open(OUT_MASTER, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(normalized_leads)
        
    print(f"\nRebuilt master saved to {OUT_MASTER.name}")

if __name__ == "__main__":
    main()
