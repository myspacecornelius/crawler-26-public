"""
CRAWL — Cross-Run Lead Deduplication

Persistent dedup across crawl runs. Prevents duplicate contacts from
accumulating in the master CSV by maintaining a dedup index and merging
new data into existing records instead of creating duplicates.

Dedup key: normalized (name, fund_domain) composite.
When a duplicate is found, the existing record is MERGED (not replaced):
  - Empty fields are filled from the new record
  - Email is updated only if the new one is higher quality (verified > guessed > N/A)
  - Score is recalculated using the merged data
  - last_seen timestamp is updated

Usage:
    from enrichment.dedup import LeadDeduplicator
    dedup = LeadDeduplicator()
    clean_leads = dedup.deduplicate(new_leads)  # returns deduped + merged list
"""

import csv
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Email status priority (higher = better)
EMAIL_PRIORITY = {
    "verified": 5,
    "scraped": 4,
    "catch_all": 3,
    "guessed": 2,
    "unknown": 1,
    "undeliverable": 0,
}


def _normalize_name(name: str) -> str:
    """Normalize a name for dedup: lowercase, strip whitespace, remove middle initials."""
    if not name:
        return ""
    name = name.lower().strip()
    # Remove common titles
    for prefix in ["dr.", "dr ", "mr.", "mr ", "mrs.", "mrs ", "ms.", "ms ", "prof."]:
        if name.startswith(prefix):
            name = name[len(prefix):].strip()
    # Remove middle initials (single letter, optionally followed by period)
    parts = name.split()
    if len(parts) > 2:
        parts = [p for p in parts if not (len(p) <= 2 and p.rstrip(".").isalpha() and len(p.rstrip(".")) == 1)]
    return " ".join(parts)


def _normalize_fund(fund: str) -> str:
    """Normalize fund name for dedup: lowercase, strip common suffixes."""
    if not fund:
        return ""
    fund = fund.lower().strip()
    for suffix in [" ventures", " capital", " partners", " fund", " management",
                   " advisors", " group", " co.", " llc", " lp", " inc."]:
        if fund.endswith(suffix):
            fund = fund[:-len(suffix)].strip()
    return fund


def _dedup_key(name: str, fund: str) -> str:
    """Generate a stable merge key from name + fund."""
    norm_name = _normalize_name(name)
    norm_fund = _normalize_fund(fund)
    return hashlib.md5(f"{norm_name}|{norm_fund}".encode()).hexdigest()


class LeadDeduplicator:
    """
    Cross-run deduplcation engine.
    Maintains a persistent index at data/dedup_index.json.
    """

    def __init__(self, index_path: str = "data/dedup_index.json"):
        self.index_path = Path(index_path)
        self.index: Dict[str, dict] = {}
        self._load_index()

    def _load_index(self):
        """Load the dedup index from disk."""
        if self.index_path.exists():
            try:
                with open(self.index_path, "r", encoding="utf-8") as f:
                    self.index = json.load(f)
                logger.info(f"  📋 Loaded dedup index: {len(self.index)} entries")
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"  ⚠️ Dedup index corrupted, starting fresh: {e}")
                self.index = {}
        else:
            self.index = {}

    def _save_index(self):
        """Persist the dedup index to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, indent=2, default=str)
        logger.info(f"  💾 Saved dedup index: {len(self.index)} entries")

    def _merge_lead(self, existing: dict, new_lead) -> dict:
        """
        Merge a new lead into an existing record.
        - Fill empty fields from the new lead
        - Use higher quality email if available
        - Update timestamps
        """
        merged = dict(existing)

        # Fill empty fields
        for field in ["role", "linkedin", "location", "stage", "check_size"]:
            existing_val = merged.get(field, "")
            new_val = getattr(new_lead, field, "") or ""
            if existing_val in ("N/A", "", None) and new_val not in ("N/A", "", None):
                merged[field] = new_val

        # Merge focus areas (union)
        existing_areas = set(merged.get("focus_areas", []) or [])
        new_areas = set(getattr(new_lead, "focus_areas", []) or [])
        merged["focus_areas"] = list(existing_areas | new_areas)

        # Email: keep the higher quality one
        existing_email = merged.get("email", "N/A")
        new_email = getattr(new_lead, "email", "N/A") or "N/A"
        existing_status = merged.get("email_status", "unknown")
        new_status = getattr(new_lead, "email_status", "unknown") or "unknown"

        existing_priority = EMAIL_PRIORITY.get(existing_status, 1)
        new_priority = EMAIL_PRIORITY.get(new_status, 1)

        if new_email not in ("N/A", "", None):
            if existing_email in ("N/A", "", None) or new_priority > existing_priority:
                merged["email"] = new_email
                merged["email_status"] = new_status

        # Update timestamps
        merged["last_seen"] = datetime.now().isoformat()
        merged["times_seen"] = merged.get("times_seen", 1) + 1

        return merged

    def deduplicate(self, leads: list) -> list:
        """
        Deduplicate leads against the persistent index.
        Returns the merged/deduped list and updates the index.
        """
        new_count = 0
        merged_count = 0
        duplicate_count = 0

        for lead in leads:
            key = _dedup_key(lead.name, lead.fund)

            if key in self.index:
                # Merge new data into existing record
                self.index[key] = self._merge_lead(self.index[key], lead)
                merged_count += 1
            else:
                # New lead — add to index
                self.index[key] = {
                    "name": lead.name,
                    "fund": lead.fund,
                    "role": getattr(lead, "role", "N/A"),
                    "email": getattr(lead, "email", "N/A"),
                    "email_status": getattr(lead, "email_status", "unknown"),
                    "linkedin": getattr(lead, "linkedin", "N/A"),
                    "website": getattr(lead, "website", ""),
                    "location": getattr(lead, "location", ""),
                    "stage": getattr(lead, "stage", ""),
                    "check_size": getattr(lead, "check_size", ""),
                    "focus_areas": getattr(lead, "focus_areas", []),
                    "lead_score": getattr(lead, "lead_score", 0),
                    "tier": getattr(lead, "tier", ""),
                    "source": getattr(lead, "source", ""),
                    "first_seen": datetime.now().isoformat(),
                    "last_seen": datetime.now().isoformat(),
                    "times_seen": 1,
                }
                new_count += 1

        # Now deduplicate within the current batch too
        seen_keys: Set[str] = set()
        seen_emails: Set[str] = set()
        deduped_leads = []
        for lead in leads:
            key = _dedup_key(lead.name, lead.fund)
            if key not in seen_keys:
                seen_keys.add(key)
                # Update lead attributes from merged index
                idx = self.index.get(key, {})
                if idx.get("email") and idx["email"] not in ("N/A", ""):
                    lead.email = idx["email"]
                if idx.get("email_status"):
                    lead.email_status = idx["email_status"]
                if idx.get("linkedin") and idx["linkedin"] not in ("N/A", ""):
                    lead.linkedin = idx["linkedin"]
                if idx.get("role") and idx["role"] not in ("N/A", ""):
                    lead.role = idx["role"]

                # Secondary dedup: if two name+fund-distinct leads share an email
                # (e.g. same person listed at two funds, or name variation), keep
                # only the first. This prevents duplicate outreach to the same address.
                clean_email = (lead.email or "").strip().lower()
                if clean_email and clean_email not in ("n/a", "unknown", ""):
                    if clean_email in seen_emails:
                        duplicate_count += 1
                        continue
                    seen_emails.add(clean_email)

                deduped_leads.append(lead)
            else:
                duplicate_count += 1

        # Persist updated index
        self._save_index()

        logger.info(
            "Dedup: %d new, %d merged, %d duplicates removed. Index total: %d unique leads",
            new_count, merged_count, duplicate_count, len(self.index),
        )

        return deduped_leads

    def get_stats(self) -> dict:
        """Return dedup index statistics."""
        total = len(self.index)
        with_email = sum(1 for v in self.index.values()
                        if v.get("email") and v["email"] not in ("N/A", ""))
        multi_seen = sum(1 for v in self.index.values()
                        if v.get("times_seen", 1) > 1)
        return {
            "total_unique_leads": total,
            "with_email": with_email,
            "seen_multiple_times": multi_seen,
        }
