"""
CRAWL — Hunter.io Domain Finder

Calls Hunter.io /v2/domain-search once per domain to:
  1. Discover the email pattern used by that domain (e.g. "first.last")
  2. Return any contacts Hunter already knows about

This is far more efficient than per-email SMTP verification:
  - 1 API call per *domain* instead of 1 per *email*
  - Returns the authoritative pattern, eliminating blind guessing
  - Enriches PatternStore so future guesses use the correct pattern

Free tier: 25 domain searches/month.
Starter ($49/mo): 500/month.

Usage:
    finder = HunterDomainFinder(api_key="xxx")
    results = await finder.enrich_leads(leads)
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# Hunter pattern tokens → our _PATTERNS template
_HUNTER_PATTERN_MAP = {
    "first.last":  "{first}.{last}@{domain}",
    "first_last":  "{first}_{last}@{domain}",
    "firstlast":   "{first}{last}@{domain}",
    "first":       "{first}@{domain}",
    "flast":       "{f}{last}@{domain}",
    "f.last":      "{f}.{last}@{domain}",
    "last":        "{last}@{domain}",
    "last.first":  "{last}.{first}@{domain}",
    "lastfirst":   "{last}{first}@{domain}",
}


def _extract_domain(website: str) -> Optional[str]:
    if not website or website == "N/A":
        return None
    try:
        parsed = urlparse(website if "://" in website else f"https://{website}")
        netloc = parsed.netloc.lower().lstrip("www.")
        return netloc or None
    except Exception:
        return None


class HunterDomainFinder:
    """
    Enriches leads using Hunter.io domain search.

    For each unique domain in the lead set:
    - Fetches Hunter's known email pattern for that domain
    - Collects any contacts Hunter already has
    - Updates PatternStore with the confirmed pattern
    - Directly sets email + email_status on matching leads
    """

    _BASE_URL = "https://api.hunter.io/v2/domain-search"

    def __init__(self, api_key: Optional[str] = None, pattern_store=None):
        self.api_key = api_key or os.environ.get("HUNTER_API_KEY", "")
        self.pattern_store = pattern_store  # enrichment.email_guesser.PatternStore
        self._domain_cache: Dict[str, dict] = {}
        self.calls_made = 0
        self.domains_with_pattern = 0
        self.leads_enriched = 0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def fetch_domain(
        self,
        session: aiohttp.ClientSession,
        domain: str,
        limit: int = 100,
    ) -> Optional[dict]:
        """
        Fetch Hunter domain-search result for one domain.
        Returns the parsed JSON data dict, or None on error/exhaustion.
        """
        if domain in self._domain_cache:
            return self._domain_cache[domain]

        params = {
            "domain": domain,
            "limit": limit,
            "api_key": self.api_key,
        }
        try:
            async with session.get(
                self._BASE_URL,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 429:
                    logger.debug("Hunter rate-limited on %s", domain)
                    return None
                if resp.status == 401:
                    logger.warning("Hunter API key invalid or quota exhausted")
                    return None
                if resp.status != 200:
                    logger.debug("Hunter %s → HTTP %d", domain, resp.status)
                    return None
                data = await resp.json()
                self.calls_made += 1
                result = data.get("data", {})
                self._domain_cache[domain] = result
                return result
        except Exception as exc:
            logger.debug("Hunter domain fetch %s → %s", domain, exc)
            return None

    async def enrich_leads(
        self,
        leads: list,
        concurrency: int = 5,
    ) -> list:
        """
        Enrich a lead list using Hunter domain search.

        For each unique domain:
        - Records the email pattern in PatternStore
        - Where Hunter has a known contact matching a lead's name,
          sets lead.email + lead.email_status = "verified"
        - Where Hunter has the pattern but not the contact,
          regenerates lead.email using the correct pattern

        Returns the same list with email fields updated in place.
        """
        if not self.enabled:
            logger.info("Hunter domain finder disabled (no HUNTER_API_KEY)")
            return leads

        # Group leads by domain
        by_domain: Dict[str, list] = {}
        for lead in leads:
            domain = _extract_domain(getattr(lead, "website", "") or "")
            if domain:
                by_domain.setdefault(domain, []).append(lead)

        if not by_domain:
            return leads

        logger.info(
            "  🔍  Hunter domain search: %d unique domains", len(by_domain)
        )

        sem = asyncio.Semaphore(concurrency)

        async def process_domain(domain: str, domain_leads: list):
            async with sem:
                async with aiohttp.ClientSession() as session:
                    data = await self.fetch_domain(session, domain)
                if not data:
                    return

                # Extract domain email pattern
                pattern_key = data.get("pattern", "")
                our_pattern = _HUNTER_PATTERN_MAP.get(pattern_key)
                if our_pattern and self.pattern_store:
                    # Record with high confidence (Hunter confirmed it)
                    for _ in range(5):  # weight = 5 observations
                        self.pattern_store.record(domain, our_pattern)
                    self.domains_with_pattern += 1
                    logger.debug(
                        "Hunter: %s uses pattern %s → %s",
                        domain, pattern_key, our_pattern,
                    )

                # Build name → email map from Hunter contacts
                hunter_emails: Dict[str, str] = {}
                for contact in data.get("emails", []):
                    first = (contact.get("first_name") or "").lower().strip()
                    last = (contact.get("last_name") or "").lower().strip()
                    email = (contact.get("value") or "").lower().strip()
                    conf = contact.get("confidence", 0)
                    if first and last and email and "@" in email and conf >= 70:
                        hunter_emails[f"{first} {last}"] = email
                    elif first and email and "@" in email and conf >= 70:
                        hunter_emails[first] = email

                for lead in domain_leads:
                    name = getattr(lead, "name", "") or ""
                    parts = name.lower().split()
                    if len(parts) < 2:
                        continue

                    first, last = parts[0], parts[-1]
                    full_key = f"{first} {last}"

                    if full_key in hunter_emails:
                        lead.email = hunter_emails[full_key]
                        lead.email_status = "verified"
                        self.leads_enriched += 1
                    elif our_pattern and lead.email_status not in ("verified", "scraped"):
                        # Apply the confirmed domain pattern
                        import unicodedata
                        import re as _re

                        def norm(s):
                            nfkd = unicodedata.normalize("NFKD", s)
                            return _re.sub(r"[^a-z]", "", nfkd.encode("ascii", "ignore").decode("ascii").lower())

                        fn = norm(first)
                        ln = norm(last)
                        if fn and ln:
                            lead.email = our_pattern.format(
                                first=fn, last=ln, f=fn[0], domain=domain
                            )
                            lead.email_status = "guessed"

        tasks = [
            process_domain(domain, domain_leads)
            for domain, domain_leads in by_domain.items()
        ]
        await asyncio.gather(*tasks)

        logger.info(
            "  ✉️  Hunter: %d API calls, %d domains with known pattern, "
            "%d leads directly verified",
            self.calls_made,
            self.domains_with_pattern,
            self.leads_enriched,
        )
        return leads
