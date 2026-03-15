"""
CRAWL — Crunchbase Free-Tier Adapter
Scrapes publicly accessible organization pages from crunchbase.com.
Uses the free tier (no API key) — parses public org pages for team members.
"""

from typing import Optional
from .base import BaseSiteAdapter, InvestorLead


class CrunchbaseAdapter(BaseSiteAdapter):
    """
    Adapter for Crunchbase (https://www.crunchbase.com)

    Crunchbase org pages list key people with roles, and often include
    LinkedIn URLs. Uses numbered page pagination for search results.
    Note: Respects robots.txt and rate limits. Some data may require
    the paid tier — this adapter focuses on freely accessible profiles.
    """

    ADAPTER_NAME = "crunchbase"
    VERTICALS = ["vc", "pe", "angel"]
    RATE_LIMIT_RPM = 10
    REQUIRES_AUTH = False

    def parse_card(self, card) -> Optional[InvestorLead]:
        """Parse a Crunchbase person card into a lead."""

        # Name — usually in a prominent heading or link
        name = self._safe_text(
            card, self.selectors.get("name", ".person-name, .identifier-label, h3")
        )
        if not name or name == "N/A":
            return None

        # Fund name
        fund = self._safe_text(
            card, self.selectors.get("fund", ".organization-name, .org-link, .company")
        )

        # Role/title
        role = self._safe_text(
            card, self.selectors.get("role", ".person-title, .role, .title")
        )

        # Location
        location = self._safe_text(
            card, self.selectors.get("location", ".location, .headquarters")
        )

        # Focus areas from category labels
        focus = self._safe_list(
            card, self.selectors.get("focus_areas", ".category-tag, .industry-tag")
        )

        # LinkedIn
        linkedin = self._safe_attr(
            card, self.selectors.get("linkedin", 'a[href*="linkedin.com/in"]'), "href"
        )

        # Fund website
        website = self._safe_attr(
            card, self.selectors.get("website", 'a.homepage-link, a[href*="http"]:not([href*="crunchbase"]):not([href*="linkedin"])'),
            "href",
        )

        return InvestorLead(
            name=name,
            fund=fund,
            role=role,
            focus_areas=focus,
            location=location,
            linkedin=linkedin,
            website=website,
            source="crunchbase",
        )
