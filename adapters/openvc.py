"""
CRAWL — OpenVC Adapter
Scrapes investor profiles from openvc.app
"""

from typing import Optional
from .base import BaseSiteAdapter, InvestorLead


class OpenVCAdapter(BaseSiteAdapter):
    """
    Adapter for OpenVC (https://openvc.app/investors)

    OpenVC is an open investor directory with no login required.
    Uses infinite scroll pagination and card-based layouts.
    """

    ADAPTER_NAME = "openvc"
    VERTICALS = ["vc", "angel"]
    RATE_LIMIT_RPM = 30
    REQUIRES_AUTH = False

    def parse_card(self, card) -> Optional[InvestorLead]:
        """Parse an OpenVC investor card into a lead."""
        
        name = self._safe_text(card, self.selectors.get("name", "h3"))
        if not name or name == "N/A":
            return None

        return InvestorLead(
            name=name,
            email=self._extract_email(card),
            role=self._safe_text(card, self.selectors.get("role", "")),
            fund=self._safe_text(card, self.selectors.get("fund", "")),
            focus_areas=self._safe_list(card, self.selectors.get("focus_areas", "")),
            stage=self._safe_text(card, self.selectors.get("stage", "")),
            check_size=self._safe_text(card, self.selectors.get("check_size", "")),
            location=self._safe_text(card, self.selectors.get("location", "")),
            linkedin=self._safe_attr(
                card, self.selectors.get("linkedin", ""), "href"
            ),
            website=self._safe_attr(
                card, self.selectors.get("website", ""), "href"
            ),
        )
