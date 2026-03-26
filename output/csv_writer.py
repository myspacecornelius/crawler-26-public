"""
CRAWL — CSV Writer
Handles CSV export with deduplication, delta detection, and formatted output.
"""

import csv
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


class CSVWriter:
    """
    Exports leads to CSV with smart features:
    - Deduplication across runs (by name + fund combo)
    - Delta detection (flag new leads since last export)
    - Sorted by lead score (highest first)
    - Timestamped filenames for history
    """

    # Core lead fields
    CORE_FIELDNAMES = [
        "Name", "Email", "Email Status", "Role", "Fund", "Focus Areas", "Stage",
        "Check Size", "Location", "LinkedIn", "Website",
        "Lead Score", "Tier", "Source", "Scraped At",
    ]

    # Fund intelligence fields (appended when present)
    INTEL_FIELDNAMES = [
        "firm_domain", "portfolio_companies", "portfolio_count",
        "recent_investments", "last_investment_date",
        "hq_geography", "geography_investment_signals",
        "sector_fit_keywords", "business_model_keywords",
        "thesis_evidence_url", "thesis_evidence_title",
        "check_size_estimate",
        "decision_maker_names", "decision_maker_roles",
        "team_size",
        "active_status", "active_status_confidence", "active_status_evidence",
        "lead_follow_preference", "lead_follow_confidence", "lead_follow_evidence",
        "board_seat_signals", "strategy_snippets",
    ]

    # Combined — used for enriched output
    FIELDNAMES = CORE_FIELDNAMES + INTEL_FIELDNAMES

    def __init__(self, output_dir: str = "data"):
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir / "raw"
        self.enriched_dir = self.output_dir / "enriched"
        
        # Create dirs
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.enriched_dir.mkdir(parents=True, exist_ok=True)

    def write(self, leads: list, filename: str = "investor_leads.csv", enriched: bool = False) -> str:
        """
        Write leads to CSV.
        
        Args:
            leads: List of InvestorLead objects
            filename: Output filename
            enriched: If True, write to enriched/ dir, else raw/
            
        Returns:
            Path to the written file
        """
        target_dir = self.enriched_dir if enriched else self.raw_dir
        filepath = target_dir / filename

        rows = [lead.to_dict() for lead in leads]

        # Determine which columns to use — include intel columns only if data present
        has_intel = any(row.get("firm_domain") or row.get("active_status") for row in rows)
        fieldnames = self.FIELDNAMES if (enriched and has_intel) else self.CORE_FIELDNAMES

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()

            # Rename keys to match our headers
            for row in rows:
                formatted = {
                    "Name": row.get("name", ""),
                    "Email": row.get("email", ""),
                    "Role": row.get("role", ""),
                    "Fund": row.get("fund", ""),
                    "Focus Areas": row.get("focus_areas", ""),
                    "Stage": row.get("stage", ""),
                    "Check Size": row.get("check_size", ""),
                    "Location": row.get("location", ""),
                    "LinkedIn": row.get("linkedin", ""),
                    "Website": row.get("website", ""),
                    "Lead Score": row.get("lead_score", 0),
                    "Tier": row.get("tier", ""),
                    "Source": row.get("source", ""),
                    "Scraped At": row.get("scraped_at", ""),
                    "Email Status": row.get("email_status", "unknown"),
                }
                # Add intel fields if present
                if has_intel:
                    for col in self.INTEL_FIELDNAMES:
                        formatted[col] = row.get(col, "")
                writer.writerow(formatted)

        print(f"  💾  Saved {len(rows)} leads → {filepath}")
        return str(filepath)

    def write_master(self, leads: list) -> str:
        """
        Write the master CSV with all leads, deduped.
        Also saves a timestamped snapshot.

        MERGES new leads into the existing master CSV so incremental runs
        don't clobber previously accumulated data.

        Dedup key is (name, fund, email) so that multiple email-pattern rows
        for the same person are all preserved while exact duplicates are dropped.
        """
        from adapters.base import InvestorLead

        seen = set()
        deduped = []

        # ── Backup existing master before touching it ──
        master_file = self.enriched_dir / "investor_leads_master.csv"
        if master_file.exists():
            backup_name = f"investor_leads_master_BACKUP_{len(leads)}.csv"
            backup_path = self.enriched_dir / backup_name
            shutil.copy2(master_file, backup_path)
            print(f"  🛡️  Backed up master CSV → {backup_name}")

        # ── Load existing master CSV first ──
        if master_file.exists():
            try:
                with open(master_file, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        key = (
                            row.get("Name", "").lower(),
                            row.get("Fund", "").lower(),
                            row.get("Email", "").lower(),
                        )
                        if key not in seen:
                            seen.add(key)
                            # Reconstruct an InvestorLead from the CSV row
                            existing_lead = InvestorLead(
                                name=row.get("Name", ""),
                                email=row.get("Email", "N/A"),
                                email_status=row.get("Email Status", "unknown"),
                                role=row.get("Role", "N/A"),
                                fund=row.get("Fund", "N/A"),
                                focus_areas=[a.strip() for a in row.get("Focus Areas", "").split(";") if a.strip()],
                                stage=row.get("Stage", "N/A"),
                                check_size=row.get("Check Size", "N/A"),
                                location=row.get("Location", "N/A"),
                                linkedin=row.get("LinkedIn", "N/A"),
                                website=row.get("Website", "N/A"),
                                lead_score=int(row.get("Lead Score", 0) or 0),
                                tier=row.get("Tier", ""),
                                source=row.get("Source", ""),
                                scraped_at=row.get("Scraped At", ""),
                            )
                            deduped.append(existing_lead)
                print(f"  📂  Loaded {len(deduped)} existing leads from master CSV")
            except Exception as e:
                print(f"  ⚠️  Could not load existing master: {e}")

        # ── Merge new leads ──
        new_count = 0
        for lead in leads:
            key = (
                lead.name.lower(),
                lead.fund.lower(),
                (lead.email or "").lower(),
            )
            if key not in seen:
                seen.add(key)
                deduped.append(lead)
                new_count += 1

        print(f"  🆕  {new_count} new leads merged (total: {len(deduped)})")

        # Sort by score (highest first)
        deduped.sort(key=lambda l: l.lead_score, reverse=True)

        # Write master file
        master_path = self.write(deduped, "investor_leads_master.csv", enriched=True)

        # Write timestamped snapshot
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.write(deduped, f"leads_{timestamp}.csv", enriched=True)

        return master_path

    def detect_deltas(self, new_leads: list, master_file: str = "data/enriched/investor_leads_master.csv") -> list:
        """
        Compare new leads against existing master CSV.
        Returns only leads that are NEW (not in master).
        """
        existing_keys = set()
        master_path = Path(master_file)

        if master_path.exists():
            with open(master_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    key = (
                        row.get("Name", "").lower(),
                        row.get("Fund", "").lower(),
                    )
                    existing_keys.add(key)

        deltas = []
        for lead in new_leads:
            key = (lead.name.lower(), lead.fund.lower())
            if key not in existing_keys:
                deltas.append(lead)

        if deltas:
            print(f"  🆕  {len(deltas)} new leads detected (delta from master)")
        else:
            print(f"  ♻️  No new leads — all {len(new_leads)} already in master")

        return deltas
