"""
CRAWL — Source Aggregator
Orchestrates multiple lead sources into a unified pipeline.
Sources: seed database, GitHub VC lists, HTTP-based discovery.
This is the primary lead generation engine — deterministic and reliable.
"""

import asyncio
import logging
from typing import List
from datetime import datetime

from adapters.base import InvestorLead
from sources.seed_db import load_seed_leads

logger = logging.getLogger(__name__)


class SourceAggregator:
    """
    Aggregates investor leads from multiple deterministic sources.
    Unlike browser-based scraping, these sources are reliable and fast.
    """

    def __init__(self):
        self.all_leads: List[InvestorLead] = []
        self._seen_names: set = set()
        self._stats = {
            "seed_db": 0,
            "github_lists": 0,
            "http_directories": 0,
            "total_deduped": 0,
        }

    def _dedup_add(self, leads: List[InvestorLead], source_label: str) -> int:
        """Add leads, deduplicating by name+fund composite key to avoid collisions."""
        added = 0
        for lead in leads:
            key = (lead.name.strip().lower(), lead.fund.strip().lower())
            if key[0] and key not in self._seen_names:
                self._seen_names.add(key)
                self.all_leads.append(lead)
                added += 1
        self._stats[source_label] = added
        return added

    async def aggregate(self) -> List[InvestorLead]:
        """
        Run all source collectors and return deduplicated leads.
        """
        print(f"\n{'='*60}")
        print("  📡  SOURCE AGGREGATOR")
        print(f"{'='*60}\n")

        # ── Source 1: Curated seed database ──
        seed_leads = load_seed_leads()
        seed_count = self._dedup_add(seed_leads, "seed_db")
        print(f"  📂  Seed database: {seed_count} firms")

        # ── Source 2: GitHub VC lists (HTTP-based, no browser) ──
        try:
            from sources.github_lists import fetch_github_vc_lists
            github_leads = await fetch_github_vc_lists()
            gh_count = self._dedup_add(github_leads, "github_lists")
            print(f"  🐙  GitHub lists: {gh_count} new firms")
        except Exception as e:
            logger.warning(f"  ⚠️  GitHub lists failed: {e}")

        # ── Source 3: HTTP directory fetchers (public VC directories) ──
        try:
            from sources.directory_fetchers import fetch_all_directories
            dir_leads = await fetch_all_directories()
            dir_count = self._dedup_add(dir_leads, "http_directories")
            print(f"  🌐  HTTP directories: {dir_count} new firms")
        except Exception as e:
            logger.warning(f"  ⚠️  HTTP directories failed: {e}")

        self._stats["total_deduped"] = len(self.all_leads)

        print(f"\n  ✅  Aggregator complete: {len(self.all_leads)} unique target firms")
        print(f"      Seed: {self._stats['seed_db']} | GitHub: {self._stats['github_lists']} | Directories: {self._stats['http_directories']}")

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
