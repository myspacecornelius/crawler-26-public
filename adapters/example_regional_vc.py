"""
CRAWL — Example Regional VC Directory Adapter

This is a template adapter demonstrating how to build a new adapter for
the scraping framework. It targets a hypothetical regional VC directory
and shows all the patterns you need.

To create your own adapter:
1. Copy this file and rename it (e.g., my_site.py)
2. Set ADAPTER_NAME to a unique slug matching your sites.yaml entry
3. Implement parse_card() with your site's HTML structure
4. Add a sites.yaml entry with selectors and pagination config
5. The registry auto-discovers your adapter — no engine.py changes needed

See adapters/base.py for the full BaseSiteAdapter interface.
"""

from typing import Optional
from .base import BaseSiteAdapter, InvestorLead


class ExampleRegionalVCAdapter(BaseSiteAdapter):
    """
    Adapter for a hypothetical European VC directory.

    Demonstrates:
    - ADAPTER_NAME for auto-registration
    - VERTICALS for filtering by investor type
    - RATE_LIMIT_RPM to declare respectful request rates
    - REQUIRES_AUTH / REQUIRED_CREDENTIALS for auth-gated sites
    - parse_card() for extracting structured data from HTML cards
    """

    # ── Adapter Metadata (used by the registry) ──
    ADAPTER_NAME = "example_regional_vc"
    VERTICALS = ["vc", "growth_equity"]
    RATE_LIMIT_RPM = 20
    REQUIRES_AUTH = False
    REQUIRED_CREDENTIALS = []  # e.g., ["api_key"] if login needed

    def parse_card(self, card) -> Optional[InvestorLead]:
        """
        Parse a single investor card from the directory HTML.

        Args:
            card: A BeautifulSoup Tag representing one investor listing.
                  The tag is selected using the 'card' selector from sites.yaml.

        Returns:
            InvestorLead with extracted fields, or None to skip this card.
        """
        # Extract the investor's name using the configured selector
        name = self._safe_text(card, self.selectors.get("name", "h3"))
        if not name or name == "N/A":
            return None

        # Extract role/title
        role = self._safe_text(card, self.selectors.get("role", ".role"))

        # Extract fund/firm name
        fund = self._safe_text(card, self.selectors.get("fund", ".firm-name"))

        # Extract focus areas as a list
        focus_areas = self._safe_list(card, self.selectors.get("focus_areas", ".tag"))

        # Extract investment stage preference
        stage = self._safe_text(card, self.selectors.get("stage", ".stage"))

        # Extract check size / ticket size
        check_size = self._safe_text(card, self.selectors.get("check_size", ".check-size"))

        # Extract location
        location = self._safe_text(card, self.selectors.get("location", ".location"))

        # Extract email using the multi-strategy helper from BaseSiteAdapter
        email = self._extract_email(card)

        # Extract LinkedIn URL from an anchor tag
        linkedin = self._safe_attr(
            card, self.selectors.get("linkedin", "a[href*='linkedin.com/in/']"), "href"
        )

        # Extract fund website URL
        website = self._safe_attr(
            card,
            self.selectors.get("website", "a[href*='http']:not([href*='linkedin'])"),
            "href",
        )

        return InvestorLead(
            name=name,
            email=email,
            role=role,
            fund=fund,
            focus_areas=focus_areas,
            stage=stage,
            check_size=check_size,
            location=location,
            linkedin=linkedin,
            website=website,
        )
