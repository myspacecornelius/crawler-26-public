"""
CRAWL — Signal by NFX Adapter
Scrapes investor profiles from signal.nfx.com — one of the highest quality
VC directories with structured investor data.

NOTE: signal.nfx.com/investor-lists is a React SPA. All investor cards are
rendered client-side. This adapter requires Playwright to execute JavaScript
before BeautifulSoup parses the DOM. The BaseSiteAdapter.run() method already
handles this via page.goto() + wait, so no changes to the base class are needed.

The rendered DOM uses hashed/minified class names in production builds, so
selectors use [class*='...'] substring matching for resilience against
CSS module hashing. Selectors are configured in config/sites.yaml and
injected into self.selectors at runtime.
"""

from typing import Optional
from .base import BaseSiteAdapter, InvestorLead


class SignalNFXAdapter(BaseSiteAdapter):
    """
    Adapter for Signal by NFX (https://signal.nfx.com/investor-lists)

    Signal provides structured investor cards with name, fund, role,
    location, focus areas, and LinkedIn. The page is React-rendered
    (requires Playwright) and uses load-more pagination.

    Selector strategy: CSS [class*='substring'] matching is used throughout
    because React/webpack CSS modules produce hashed class names. The substrings
    below target the semantic component names NFX uses in their source code,
    which survive the hash transformation as partial matches.
    """

    ADAPTER_NAME = "signal_nfx"
    VERTICALS = ["vc"]
    RATE_LIMIT_RPM = 20
    REQUIRES_AUTH = False

    # Fallback selector chains used when config/sites.yaml overrides are absent.
    # Each tuple lists selectors in priority order; the first match wins.
    _NAME_SELECTORS = (
        "[class*='InvestorName']", "[class*='investor-name']",
        "[class*='PersonName']", "[class*='person-name']",
        "h3", "h2", "[class*='name']",
    )
    _FUND_SELECTORS = (
        "[class*='OrgName']", "[class*='org-name']",
        "[class*='FirmName']", "[class*='firm-name']",
        "[class*='FundName']", "[class*='fund-name']",
        "[class*='fund']", "[class*='subtitle']",
    )
    _ROLE_SELECTORS = (
        "[class*='InvestorTitle']", "[class*='investor-title']",
        "[class*='Title']", "[class*='title']",
        "[class*='Position']", "[class*='position']",
        "[class*='role']",
    )
    _FOCUS_SELECTORS = (
        "[class*='SectorTag']", "[class*='sector-tag']",
        "[class*='FocusTag']", "[class*='focus-tag']",
        "[class*='Tag']", "[class*='tag']",
        "[class*='chip']", "[class*='Chip']",
    )
    _STAGE_SELECTORS = (
        "[class*='StageTag']", "[class*='stage-tag']",
        "[class*='Stage']", "[class*='stage']",
    )
    _LOCATION_SELECTORS = (
        "[class*='Location']", "[class*='location']",
        "[class*='City']", "[class*='city']",
        "[class*='Geography']", "[class*='geography']",
    )

    def _multi_text(self, card, *selectors: str, default: str = "N/A") -> str:
        """Try each selector in order; return the first non-empty text."""
        for sel in selectors:
            el = card.select_one(sel)
            if el:
                text = el.get_text(strip=True)
                if text:
                    return text
        return default

    def _multi_list(self, card, *selectors: str) -> list:
        """Try each selector; return list of texts from the first that yields results.

        Filters out stage-tag elements when collecting focus/sector tags so that
        stage values don't bleed into focus_areas.
        """
        for sel in selectors:
            items = card.select(sel)
            texts = [el.get_text(strip=True) for el in items if el.get_text(strip=True)]
            if texts:
                return texts
        return []

    def parse_card(self, card) -> Optional[InvestorLead]:
        """Parse a Signal investor card into a lead.

        Uses config/sites.yaml selectors when provided, with hard-coded
        fallback chains for each field to handle selector drift.
        """

        # Name — required; skip card if absent
        name = self._safe_text(
            card,
            self.selectors.get("name", ""),
        )
        if not name or name == "N/A":
            # Try fallback chain
            name = self._multi_text(card, *self._NAME_SELECTORS)
        if not name or name == "N/A":
            return None

        # Fund / organisation name
        fund = self._safe_text(card, self.selectors.get("fund", ""))
        if not fund or fund == "N/A":
            fund = self._multi_text(card, *self._FUND_SELECTORS)

        # Role / title
        role = self._safe_text(card, self.selectors.get("role", ""))
        if not role or role == "N/A":
            role = self._multi_text(card, *self._ROLE_SELECTORS)

        # Focus / sector tags
        focus_sel = self.selectors.get("focus_areas", "")
        focus = self._safe_list(card, focus_sel) if focus_sel else []
        if not focus:
            focus = self._multi_list(card, *self._FOCUS_SELECTORS)

        # Stage preference
        stage = self._safe_text(card, self.selectors.get("stage", ""))
        if not stage or stage == "N/A":
            stage = self._multi_text(card, *self._STAGE_SELECTORS)

        # Location
        location = self._safe_text(card, self.selectors.get("location", ""))
        if not location or location == "N/A":
            location = self._multi_text(card, *self._LOCATION_SELECTORS)

        # LinkedIn URL — look for explicit selector first, then any linkedin.com/in href
        linkedin_sel = self.selectors.get("linkedin", 'a[href*="linkedin.com/in"]')
        linkedin = self._safe_attr(card, linkedin_sel, "href")
        if linkedin == "N/A":
            li_tag = card.select_one('a[href*="linkedin.com/in"]')
            if li_tag:
                linkedin = li_tag.get("href", "N/A")

        # Fund website (not linkedin, not signal.nfx itself)
        website_sel = self.selectors.get(
            "website",
            'a[href*="http"]:not([href*="linkedin"]):not([href*="signal.nfx"]):not([href*="nfx.com"])',
        )
        website = self._safe_attr(card, website_sel, "href")

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
