"""
CRAWL — LinkedIn Profile Enricher

Enriches leads with LinkedIn profile data using proxy-based public profile
scraping. Extracts current title, company, headline, connections count,
and recent activity signals.

Uses aiohttp with configurable proxy support to avoid rate limiting.

Usage:
    from enrichment.linkedin_enricher import LinkedInEnricher
    enricher = LinkedInEnricher()
    leads = await enricher.enrich_batch(leads)

Config via env:
    LINKEDIN_PROXY_URL — SOCKS5/HTTP proxy for LinkedIn requests
    PROXYCURL_API_KEY — Optional: use Proxycurl API for reliable data
"""

import asyncio
import logging
import os
import re
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)


class LinkedInEnricher:
    """
    Enriches leads with LinkedIn profile data.
    Strategy: Proxycurl API (paid, reliable) → public profile scraping (free, fragile).
    """

    def __init__(self):
        self.proxycurl_key = os.environ.get("PROXYCURL_API_KEY")
        self.proxy_url = os.environ.get("LINKEDIN_PROXY_URL")
        self.enriched_count = 0
        self.skipped_count = 0
        self.failed_count = 0

    async def _enrich_via_proxycurl(
        self, session: aiohttp.ClientSession, linkedin_url: str
    ) -> Optional[dict]:
        """Enrich via Proxycurl API (paid, $0.01/profile)."""
        if not self.proxycurl_key:
            return None
        try:
            async with session.get(
                "https://nubela.co/proxycurl/api/v2/linkedin",
                params={"url": linkedin_url},
                headers={"Authorization": f"Bearer {self.proxycurl_key}"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                return {
                    "current_title": data.get("headline", ""),
                    "current_company": data.get("company", ""),
                    "connections": data.get("connections", 0),
                    "summary": data.get("summary", ""),
                    "location": data.get("city", "") or data.get("country_full_name", ""),
                    "experience_count": len(data.get("experiences", [])),
                    "education": ", ".join(
                        e.get("school", "") for e in data.get("education", [])[:2]
                    ),
                }
        except Exception:
            return None

    async def _enrich_via_scrape(
        self, session: aiohttp.ClientSession, linkedin_url: str
    ) -> Optional[dict]:
        """Scrape public LinkedIn profile (fragile, may be blocked)."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            async with session.get(
                linkedin_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
                proxy=self.proxy_url,
            ) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text()

                # Extract basic info from meta tags and public HTML
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
                headline = ""
                if title_match:
                    # LinkedIn titles: "Name - Title - Company | LinkedIn"
                    parts = title_match.group(1).split(" - ")
                    if len(parts) >= 2:
                        headline = parts[1].strip()

                # Extract location from meta
                location = ""
                loc_match = re.search(r'"addressLocality"\s*:\s*"([^"]+)"', html)
                if loc_match:
                    location = loc_match.group(1)

                return {
                    "current_title": headline,
                    "location": location,
                }
        except Exception:
            return None

    async def enrich_single(
        self, session: aiohttp.ClientSession, linkedin_url: str
    ) -> Optional[dict]:
        """Enrich a single LinkedIn profile using the best available method."""
        # Try Proxycurl first (most reliable)
        result = await self._enrich_via_proxycurl(session, linkedin_url)
        if result:
            return result

        # Fallback to scraping
        return await self._enrich_via_scrape(session, linkedin_url)

    async def enrich_batch(
        self, leads: list, max_concurrent: int = 3
    ) -> list:
        """
        Enrich leads that have LinkedIn URLs but incomplete data.
        Updates leads in place.
        """
        candidates = [
            lead for lead in leads
            if getattr(lead, "linkedin", "N/A") not in ("N/A", "", None)
            and "linkedin.com/in/" in getattr(lead, "linkedin", "")
        ]

        if not candidates:
            print("  ⚠️  No LinkedIn URLs to enrich")
            return leads

        if not self.proxycurl_key and not self.proxy_url:
            print("  ⚠️  LinkedIn enrichment skipped (set PROXYCURL_API_KEY or LINKEDIN_PROXY_URL)")
            return leads

        print(f"  🔗  Enriching {len(candidates)} LinkedIn profiles...")
        sem = asyncio.Semaphore(max_concurrent)

        async with aiohttp.ClientSession() as session:
            async def _enrich_lead(lead):
                async with sem:
                    data = await self.enrich_single(session, lead.linkedin)
                    if data:
                        if data.get("current_title") and lead.role in ("N/A", "", None):
                            lead.role = data["current_title"]
                        if data.get("location") and lead.location in ("N/A", "", None):
                            lead.location = data["location"]
                        self.enriched_count += 1
                    else:
                        self.failed_count += 1
                    await asyncio.sleep(1.5)  # Rate limit

            tasks = [_enrich_lead(lead) for lead in candidates]
            await asyncio.gather(*tasks)

        print(f"  🔗  LinkedIn: {self.enriched_count} enriched, {self.failed_count} failed")
        return leads
