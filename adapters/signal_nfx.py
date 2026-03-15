"""
CRAWL — Signal by NFX Adapter
Scrapes investor profiles from signal.nfx.com — one of the highest quality
VC directories with structured investor data.
"""

from typing import Optional
from .base import BaseSiteAdapter, InvestorLead


class SignalNFXAdapter(BaseSiteAdapter):
    """
    Adapter for Signal by NFX (https://signal.nfx.com/investor-lists)

    Signal provided structured investor cards with name, fund, role,
    location, focus areas, and LinkedIn. Uses load-more pagination.
    """

    ADAPTER_NAME = "signal_nfx"
    VERTICALS = ["vc"]
    RATE_LIMIT_RPM = 20
    REQUIRES_AUTH = False

    def parse_card(self, card) -> Optional[InvestorLead]:
        """Parse a Signal investor card into a lead."""

        name = self._safe_text(card, self.selectors.get("name", "h3.investor-name, .name, h3"))
        if not name or name == "N/A":
            return None

        # Extract fund name — often in a subtitle or org name element
        fund = self._safe_text(
            card, self.selectors.get("fund", ".org-name, .fund-name, .subtitle")
        )

        # Role/title
        role = self._safe_text(
            card, self.selectors.get("role", ".title, .role, .position")
        )

        # Focus areas (tags/chips)
        focus = self._safe_list(
            card, self.selectors.get("focus_areas", ".tag, .chip, .sector-tag")
        )

        # Stage preference
        stage = self._safe_text(
            card, self.selectors.get("stage", ".stage, .stage-tag")
        )

        # Location
        location = self._safe_text(
            card, self.selectors.get("location", ".location, .city")
        )

        # LinkedIn URL
        linkedin = self._safe_attr(
            card, self.selectors.get("linkedin", 'a[href*="linkedin.com/in"]'), "href"
        )

        # Fund website
        website = self._safe_attr(
            card, self.selectors.get("website", 'a[href*="http"]:not([href*="linkedin"])')
            , "href"
        )

        return InvestorLead(
            name=name,
            fund=fund,
            role=role,
            focus_areas=focus,
            stage=stage,
            location=location,
            linkedin=linkedin,
            website=website,
            source="signal_nfx",
        )
