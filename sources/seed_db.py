"""
CRAWL — Seed Database Loader
Loads curated VC firm data from CSV and converts to InvestorLead objects.
This provides a deterministic, high-volume lead source that doesn't depend on scraping.
"""

import csv
import logging
from pathlib import Path
from typing import List
from datetime import datetime

from adapters.base import InvestorLead

logger = logging.getLogger(__name__)

SEED_DIR = Path("data/seed")

# All seed CSV files to load, with column mapping for non-standard schemas
SEED_FILES = [
    {"file": "vc_firms.csv",             "focus_col": "focus_areas", "location_col": "location"},
    {"file": "vc_firms_supplemental.csv", "focus_col": "focus_areas", "location_col": "location"},
    {"file": "vc_firms_expanded.csv",    "focus_col": "focus_areas", "location_col": "location"},
    {"file": "vc_firms_tier2.csv",       "focus_col": "focus_areas", "location_col": "location"},
    {"file": "pe_firms.csv",             "focus_col": "sectors",     "location_col": "hq"},
    {"file": "family_offices.csv",       "focus_col": "sectors",     "location_col": "hq"},
    {"file": "corp_dev.csv",             "focus_col": "sectors",     "location_col": "hq"},
]


def _load_single_seed(seed_path: Path, focus_col: str, location_col: str,
                       seen_names: set) -> List[InvestorLead]:
    """Load one seed CSV, handling column name differences across files."""
    if not seed_path.exists():
        logger.warning(f"Seed file not found: {seed_path}")
        return []

    leads = []
    with open(seed_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            website = (row.get("website") or "").strip()
            stage = (row.get("stage") or "N/A").strip()
            # Handle pipe-delimited sectors vs space-delimited focus_areas
            focus_raw = (row.get(focus_col) or "").strip()
            if "|" in focus_raw:
                focus_areas = [s.strip() for s in focus_raw.split("|") if s.strip()]
            else:
                focus_areas = [s.strip() for s in focus_raw.split() if s.strip()]
            location = (row.get(location_col) or "N/A").strip()
            check_size = (row.get("check_size") or "N/A").strip()

            lead = InvestorLead(
                name=name,
                fund=name,
                website=website if website else "N/A",
                stage=stage,
                focus_areas=focus_areas,
                location=location,
                check_size=check_size if check_size else "N/A",
                source=f"seed:{seed_path.stem}",
                scraped_at=datetime.now().isoformat(),
            )
            leads.append(lead)

    return leads


def load_seed_leads() -> List[InvestorLead]:
    """Load ALL seed CSVs from data/seed/ and return deduplicated InvestorLead list."""
    all_leads = []
    seen_names: set = set()

    for spec in SEED_FILES:
        path = SEED_DIR / spec["file"]
        batch = _load_single_seed(path, spec["focus_col"], spec["location_col"], seen_names)
        all_leads.extend(batch)
        logger.info(f"  📂  {spec['file']}: {len(batch)} firms loaded")

    logger.info(f"  📂  Seed database total: {len(all_leads)} firms from {len(SEED_FILES)} files")
    return all_leads
