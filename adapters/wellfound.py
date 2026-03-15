"""
CRAWL — Wellfound (AngelList) Adapter
Scrapes the public investor directory at wellfound.com/investors.
Uses data-test attributes where available with CSS class fallbacks.
"""

from bs4 import Tag
from typing import Optional

from adapters.base import BaseSiteAdapter, InvestorLead


def _first_text(card: Tag, *selectors: str, default: str = "N/A") -> str:
    for sel in selectors:
        el = card.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    return default


def _first_list(card: Tag, *selectors: str) -> list:
    for sel in selectors:
        items = card.select(sel)
        texts = [el.get_text(strip=True) for el in items if el.get_text(strip=True)]
        if texts:
            return texts
    return []


class WellfoundAdapter(BaseSiteAdapter):
    """Adapter for wellfound.com/investors — large angel/VC investor database."""

    ADAPTER_NAME = "wellfound"
    VERTICALS = ["vc", "angel"]
    RATE_LIMIT_RPM = 15
    REQUIRES_AUTH = True
    REQUIRED_CREDENTIALS = ["wellfound_session"]

    def parse_card(self, card: Tag) -> Optional[InvestorLead]:
        name = _first_text(
            card,
            "[data-test='InvestorName']",
            ".investor-name",
            "h3", "h2",
            "[class*='name']", "[class*='Name']",
        )
        if not name or name == "N/A":
            return None

        role = _first_text(
            card,
            "[data-test='InvestorTitle']",
            ".investor-title",
            "[class*='title']", "[class*='Title']",
        )
        fund = _first_text(
            card,
            "[data-test='InvestorFirm']",
            ".investor-firm",
            "[class*='firm']", "[class*='Firm']",
        )
        focus_areas = _first_list(
            card,
            "[data-test='InvestorMarkets'] span",
            ".market-tags .tag",
            "[class*='market'] span",
            "[class*='tag']",
        )
        stage = _first_text(
            card,
            "[data-test='InvestorStage']",
            ".stage-tag",
            "[class*='stage']",
        )
        check_size = _first_text(
            card,
            "[data-test='InvestorCheckSize']",
            ".check-size",
            "[class*='check']",
        )
        location = _first_text(
            card,
            "[data-test='InvestorLocation']",
            ".location",
            "[class*='location']",
        )

        linkedin = "N/A"
        li_tag = card.select_one("a[href*='linkedin.com/in/']")
        if li_tag:
            linkedin = li_tag.get("href", "N/A")

        # Wellfound rarely exposes emails directly; guesser will fill these in
        email = self._extract_email(card)

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
        )
