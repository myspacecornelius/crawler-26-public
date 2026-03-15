"""
CRAWL — AngelMatch Adapter
Scrapes investor profiles from angelmatch.io
"""

from typing import Optional
from .base import BaseSiteAdapter, InvestorLead


class AngelMatchAdapter(BaseSiteAdapter):
    """
    Adapter for AngelMatch (https://angelmatch.io/investors)

    AngelMatch is a freemium angel investor matching platform.
    Uses 'Load More' button pagination.
    """

    ADAPTER_NAME = "angelmatch"
    VERTICALS = ["angel", "vc"]
    RATE_LIMIT_RPM = 20
    REQUIRES_AUTH = False

    def parse_card(self, card) -> Optional[InvestorLead]:
        """Parse an AngelMatch investor listing into a lead."""
        
        name = self._safe_text(card, self.selectors.get("name", ".investor-name"))
        if not name or name == "N/A":
            return None

        # AngelMatch sometimes puts check size as a range like "$25K - $100K"
        check_size_raw = self._safe_text(card, self.selectors.get("check_size", ""))

        return InvestorLead(
            name=name,
            email=self._extract_email(card),
            role=self._safe_text(card, self.selectors.get("role", "")),
            fund=self._safe_text(card, self.selectors.get("fund", "")),
            focus_areas=self._safe_list(card, self.selectors.get("focus_areas", "")),
            stage=self._safe_text(card, self.selectors.get("stage", "")),
            check_size=check_size_raw,
            location=self._safe_text(card, self.selectors.get("location", "")),
            linkedin=self._safe_attr(
                card, self.selectors.get("linkedin", ""), "href"
            ),
            website=self._safe_attr(
                card, self.selectors.get("website", ""), "href"
            ),
        )
