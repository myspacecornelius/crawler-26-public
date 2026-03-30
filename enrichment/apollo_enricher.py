"""
CRAWL — Apollo.io Bulk Enricher

Enriches leads with verified email, phone, title, and company data from Apollo's
275M+ contact database. Single API call per lead returns the most complete
enrichment available from any single source.

Usage:
    from enrichment.apollo_enricher import ApolloEnricher
    enricher = ApolloEnricher()
    leads = await enricher.enrich_batch(leads)

Config via env:
    APOLLO_API_KEY — Apollo.io API key (required)
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional

import aiohttp

logger = logging.getLogger(__name__)

# Apollo API endpoints
_PEOPLE_MATCH_URL = "https://api.apollo.io/v1/people/match"
_PEOPLE_ENRICH_URL = "https://api.apollo.io/api/v1/people/bulk_match"


class ApolloEnricher:
    """
    Bulk enrichment via Apollo.io People API.
    For each lead, attempts to find verified email, phone, title, and company data.
    Uses bulk match endpoint for efficiency (up to 10 records per request).
    """

    def __init__(self, concurrency: int = 5):
        self.api_key = os.environ.get("APOLLO_API_KEY", "")
        self._sem = asyncio.Semaphore(concurrency)
        self._stats = {
            "leads_attempted": 0,
            "leads_enriched": 0,
            "emails_found": 0,
            "phones_found": 0,
            "api_calls": 0,
            "errors": 0,
        }

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _enrich_single(
        self, session: aiohttp.ClientSession, lead
    ) -> Optional[dict]:
        """Enrich a single lead via Apollo people/match endpoint."""
        async with self._sem:
            self._stats["leads_attempted"] += 1
            self._stats["api_calls"] += 1

            # Build request — Apollo matches on name + organization
            payload = {
                "api_key": self.api_key,
                "first_name": lead.name.split()[0] if lead.name else "",
                "last_name": " ".join(lead.name.split()[1:]) if lead.name and len(lead.name.split()) > 1 else "",
                "organization_name": lead.fund if lead.fund and lead.fund != "N/A" else "",
            }

            # Add LinkedIn URL if available (highest match accuracy)
            if lead.linkedin and lead.linkedin not in ("N/A", ""):
                payload["linkedin_url"] = lead.linkedin

            # Add domain if available
            if lead.website and lead.website not in ("N/A", ""):
                from urllib.parse import urlparse
                try:
                    parsed = urlparse(
                        lead.website if "://" in lead.website else f"https://{lead.website}"
                    )
                    domain = parsed.netloc.lower().replace("www.", "")
                    if domain:
                        payload["domain"] = domain
                except Exception:
                    pass

            try:
                async with session.post(
                    _PEOPLE_MATCH_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status == 429:
                        # Rate limited — back off
                        await asyncio.sleep(5)
                        return None
                    if resp.status != 200:
                        return None

                    data = await resp.json()
                    person = data.get("person")
                    if not person:
                        return None

                    result = {}

                    # Email
                    email = person.get("email")
                    if email and "@" in email:
                        result["email"] = email
                        result["email_status"] = "verified" if person.get("email_status") == "verified" else "apollo"
                        self._stats["emails_found"] += 1

                    # Phone
                    phone = None
                    if person.get("phone_numbers"):
                        for pn in person["phone_numbers"]:
                            if pn.get("sanitized_number"):
                                phone = pn["sanitized_number"]
                                break
                    if not phone:
                        phone = person.get("organization", {}).get("primary_phone", {}).get("sanitized_number")
                    if phone:
                        result["phone"] = phone
                        self._stats["phones_found"] += 1

                    # Title / role
                    title = person.get("title") or person.get("headline")
                    if title:
                        result["title"] = title

                    # LinkedIn
                    linkedin = person.get("linkedin_url")
                    if linkedin:
                        result["linkedin"] = linkedin

                    # Location
                    city = person.get("city")
                    state = person.get("state")
                    country = person.get("country")
                    loc_parts = [p for p in [city, state, country] if p]
                    if loc_parts:
                        result["location"] = ", ".join(loc_parts)

                    # Company data
                    org = person.get("organization", {})
                    if org:
                        if org.get("name"):
                            result["company"] = org["name"]
                        if org.get("estimated_num_employees"):
                            result["company_size"] = org["estimated_num_employees"]

                    if result:
                        self._stats["leads_enriched"] += 1

                    return result if result else None

            except asyncio.TimeoutError:
                self._stats["errors"] += 1
                return None
            except Exception as e:
                self._stats["errors"] += 1
                logger.debug(f"  Apollo error for {lead.name}: {e}")
                return None

    async def enrich_batch(self, leads: list) -> list:
        """
        Enrich all leads with Apollo data.
        Prioritizes leads missing emails, but enriches all for phone/title data.
        """
        if not self.enabled:
            print("  Apollo enrichment skipped (set APOLLO_API_KEY)")
            return leads

        # Prioritize leads without emails, then those without phones
        candidates = sorted(
            leads,
            key=lambda l: (
                0 if not l.email or l.email in ("N/A", "") else 1,
                0 if not getattr(l, "linkedin", None) or l.linkedin in ("N/A", "") else 1,
            ),
        )

        print(f"  Apollo: enriching {len(candidates)} leads...")

        async with aiohttp.ClientSession() as session:
            tasks = []
            for lead in candidates:
                tasks.append(self._enrich_one(session, lead))

            await asyncio.gather(*tasks)

        print(
            f"  Apollo: {self._stats['leads_enriched']} enriched, "
            f"{self._stats['emails_found']} emails, "
            f"{self._stats['phones_found']} phones "
            f"({self._stats['api_calls']} API calls)"
        )
        return leads

    async def _enrich_one(self, session: aiohttp.ClientSession, lead) -> None:
        """Enrich a single lead and update it in place."""
        result = await self._enrich_single(session, lead)
        if not result:
            return

        # Update email (only if better than current)
        if result.get("email"):
            current_email = lead.email if lead.email and lead.email != "N/A" else ""
            if not current_email or lead.email_status in ("unknown", "guessed"):
                lead.email = result["email"]
                lead.email_status = result.get("email_status", "apollo")

        # Update role/title
        if result.get("title") and lead.role in ("N/A", "", None):
            lead.role = result["title"]

        # Update LinkedIn
        if result.get("linkedin") and lead.linkedin in ("N/A", "", None):
            lead.linkedin = result["linkedin"]

        # Update location
        if result.get("location") and lead.location in ("N/A", "", None):
            lead.location = result["location"]

        # Store phone in fund_intel dict (no dedicated phone field on InvestorLead)
        if result.get("phone"):
            if not lead.fund_intel:
                lead.fund_intel = {}
            lead.fund_intel["phone"] = result["phone"]

        # Rate limit between requests
        await asyncio.sleep(0.3)

    @property
    def stats(self) -> dict:
        return dict(self._stats)
