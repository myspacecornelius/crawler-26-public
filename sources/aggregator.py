"""
CRAWL — Source Aggregator
Orchestrates multiple lead sources into a unified pipeline.
Sources: seed database, GitHub VC lists, HTTP-based discovery,
pension LP disclosures, conference speakers, content mining.
This is the primary lead generation engine — deterministic and reliable.
"""

import asyncio
import logging
from difflib import SequenceMatcher
from typing import List, Tuple
from datetime import datetime

from adapters.base import InvestorLead
from sources.seed_db import load_seed_leads

logger = logging.getLogger(__name__)

# Fuzzy dedup threshold: 0.95 means 95% similarity treats entries as duplicates.
# Catches typos like "Andreessen Horowitz" vs "Andreessen Horowiz".
_FUZZY_THRESHOLD = 0.95


class SourceAggregator:
    """
    Aggregates investor leads from multiple deterministic sources.
    Unlike browser-based scraping, these sources are reliable and fast.
    """

    def __init__(self):
        self.all_leads: List[InvestorLead] = []
        self._seen_keys: List[Tuple[str, str]] = []  # ordered list for fuzzy matching
        self._seen_key_set: set = set()  # exact-match fast path
        self._lead_index: dict = {}  # key -> index in all_leads for merging
        self._stats = {
            "seed_db": 0,
            "github_lists": 0,
            "http_directories": 0,
            "pension_lp": 0,
            "conferences": 0,
            "content_mining": 0,
            "total_deduped": 0,
            "fuzzy_merges": 0,
        }

    def _find_fuzzy_match(self, key: Tuple[str, str]) -> int:
        """
        Check if a (name, fund) key is a fuzzy duplicate of any existing entry.
        Returns the index of the matching lead in self.all_leads, or -1 if no match.
        Uses difflib.SequenceMatcher on the concatenated name+fund string.
        """
        candidate = f"{key[0]} | {key[1]}"
        for existing_key in self._seen_keys:
            existing = f"{existing_key[0]} | {existing_key[1]}"
            ratio = SequenceMatcher(None, candidate, existing).ratio()
            if ratio >= _FUZZY_THRESHOLD:
                return self._lead_index[existing_key]
        return -1

    def _merge_lead(self, existing: InvestorLead, new: InvestorLead):
        """Merge fields from a new lead into an existing one (fill blanks only)."""
        for field_name in ("email", "role", "linkedin", "website", "location", "stage", "check_size"):
            existing_val = getattr(existing, field_name, "N/A")
            new_val = getattr(new, field_name, "N/A")
            if existing_val in ("N/A", "", None) and new_val not in ("N/A", "", None):
                setattr(existing, field_name, new_val)
        # Merge focus areas
        if new.focus_areas:
            existing_areas = set(existing.focus_areas or [])
            for area in new.focus_areas:
                if area not in existing_areas:
                    existing.focus_areas.append(area)

    def _dedup_add(self, leads: List[InvestorLead], source_label: str) -> int:
        """
        Add leads, deduplicating by name+fund composite key.
        Uses exact match as fast path, then fuzzy matching (>=95% similarity)
        to catch typos like 'Andreessen Horowitz' vs 'Andreessen Horowiz'.
        Fuzzy matches are merged instead of added.
        """
        added = 0
        for lead in leads:
            key = (lead.name.strip().lower(), lead.fund.strip().lower())
            if not key[0]:
                continue

            # Fast path: exact match
            if key in self._seen_key_set:
                # Merge into existing
                idx = self._lead_index[key]
                self._merge_lead(self.all_leads[idx], lead)
                continue

            # Slow path: fuzzy match against all existing keys
            fuzzy_idx = self._find_fuzzy_match(key)
            if fuzzy_idx >= 0:
                self._merge_lead(self.all_leads[fuzzy_idx], lead)
                self._stats["fuzzy_merges"] += 1
                logger.debug(
                    f"Fuzzy dedup merge: '{lead.name} @ {lead.fund}' matched existing "
                    f"'{self.all_leads[fuzzy_idx].name} @ {self.all_leads[fuzzy_idx].fund}'"
                )
                continue

            # No match — add as new
            idx = len(self.all_leads)
            self._seen_key_set.add(key)
            self._seen_keys.append(key)
            self._lead_index[key] = idx
            self.all_leads.append(lead)
            added += 1

        self._stats[source_label] = added
        return added

    async def aggregate(self) -> List[InvestorLead]:
        """
        Run all source collectors and return deduplicated leads.
        """
        print(f"\n{'='*60}")
        print("  SOURCE AGGREGATOR")
        print(f"{'='*60}\n")

        # ── Source 1: Curated seed database ──
        seed_leads = load_seed_leads()
        seed_count = self._dedup_add(seed_leads, "seed_db")
        print(f"  Seed database: {seed_count} firms")

        # ── Source 2: GitHub VC lists (HTTP-based, no browser) ──
        try:
            from sources.github_lists import fetch_github_vc_lists
            github_leads = await fetch_github_vc_lists()
            gh_count = self._dedup_add(github_leads, "github_lists")
            print(f"  GitHub lists: {gh_count} new firms")
        except Exception as e:
            logger.warning(f"  GitHub lists failed: {e}")

        # ── Source 3: HTTP directory fetchers (public VC directories) ──
        try:
            from sources.directory_fetchers import fetch_all_directories
            dir_leads = await fetch_all_directories()
            dir_count = self._dedup_add(dir_leads, "http_directories")
            print(f"  HTTP directories: {dir_count} new firms")
        except Exception as e:
            logger.warning(f"  HTTP directories failed: {e}")

        # ── Source 4: Pension fund LP disclosures ──
        try:
            from sources.pension_lp_scraper import PensionLPScraper
            pension_scraper = PensionLPScraper()
            pension_leads = await pension_scraper.discover()
            pension_count = self._dedup_add(pension_leads, "pension_lp")
            print(f"  Pension LP disclosures: {pension_count} new firms")
        except Exception as e:
            logger.warning(f"  Pension LP scraper failed: {e}")

        # ── Source 5: Conference speaker directories ──
        try:
            from sources.conference_scraper import ConferenceSpeakerScraper
            conf_scraper = ConferenceSpeakerScraper()
            conf_leads = await conf_scraper.discover()
            conf_count = self._dedup_add(conf_leads, "conferences")
            print(f"  Conference speakers: {conf_count} new contacts")
        except Exception as e:
            logger.warning(f"  Conference scraper failed: {e}")

        # ── Source 6: Content mining (Substack/Medium/podcasts) ──
        try:
            from sources.content_miner import InvestorContentMiner
            content_miner = InvestorContentMiner()
            content_leads = await content_miner.discover()
            content_count = self._dedup_add(content_leads, "content_mining")
            print(f"  Content mining: {content_count} new contacts")
        except Exception as e:
            logger.warning(f"  Content miner failed: {e}")

        self._stats["total_deduped"] = len(self.all_leads)

        print(f"\n  Aggregator complete: {len(self.all_leads)} unique target firms")
        print(
            f"      Seed: {self._stats['seed_db']} | GitHub: {self._stats['github_lists']} | "
            f"Directories: {self._stats['http_directories']} | "
            f"Pension: {self._stats['pension_lp']} | "
            f"Conferences: {self._stats['conferences']} | "
            f"Content: {self._stats['content_mining']}"
        )

        return self.all_leads

    @property
    def stats(self) -> dict:
        return dict(self._stats)


async def generate_target_funds(leads: List[InvestorLead], output_path: str = "data/target_funds.txt"):
    """
    Extract fund websites from aggregated leads and write to target_funds.txt
    for the deep_crawl module to process.
    Deduplicates by domain so we don't crawl the same site multiple times.
    """
    from pathlib import Path
    from urllib.parse import urlparse

    websites = set()
    seen_domains = set()
    skipped = 0

    for lead in leads:
        url = lead.website
        if not url or url in ("N/A", "", "/pricing"):
            continue
        # Normalize and deduplicate by domain
        try:
            parsed = urlparse(url if url.startswith("http") else f"https://{url}")
            domain = parsed.netloc.lower().replace("www.", "")
        except Exception:
            continue
        if not domain or domain in seen_domains:
            skipped += 1
            continue
        seen_domains.add(domain)
        websites.add(url)

    target_path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_path, "w") as f:
        for site in sorted(websites):
            f.write(site + "\n")

    logger.info(f"  🎯  Generated {len(websites)} target fund URLs → {target_path} (skipped {skipped} duplicate domains)")
    return websites
