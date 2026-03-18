"""
CRAWL — CSV Writer
Handles CSV export with deduplication, delta detection, and formatted output.
"""

import csv
import os
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

    FIELDNAMES = [
        "Name", "Email", "Email Status", "Role", "Fund", "Focus Areas", "Stage",
        "Check Size", "Location", "LinkedIn", "Website",
        "Lead Score", "Tier", "Source", "Scraped At",
    ]

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

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDNAMES, extrasaction="ignore")
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
                writer.writerow(formatted)

        print(f"  💾  Saved {len(rows)} leads → {filepath}")
        return str(filepath)

    def write_master(self, leads: list) -> str:
        """
        Write the master CSV with all leads, deduped.
        Also saves a timestamped snapshot.

        Dedup key is (name, fund, email) so that multiple email-pattern rows
        for the same person are all preserved while exact duplicates are dropped.
        """
        seen = set()
        deduped = []
        for lead in leads:
            key = (
                lead.name.lower(),
                lead.fund.lower(),
                (lead.email or "").lower(),
            )
            if key not in seen:
                seen.add(key)
                deduped.append(lead)

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
