"""
CRAWL — Visible.vc Adapter
Scrapes the public investor directory at visible.vc/investors.
Uses multi-selector fallback since the site's CSS classes vary by build.
"""

from bs4 import Tag
from typing import Optional

from adapters.base import BaseSiteAdapter, InvestorLead


def _first_text(card: Tag, *selectors: str, default: str = "N/A") -> str:
    """Try each CSS selector in order; return first non-empty text found."""
    for sel in selectors:
        el = card.select_one(sel)
        if el:
            text = el.get_text(strip=True)
            if text:
                return text
    return default


def _first_list(card: Tag, *selectors: str) -> list:
    """Try each selector; return list of texts from first that yields results."""
    for sel in selectors:
        items = card.select(sel)
        texts = [el.get_text(strip=True) for el in items if el.get_text(strip=True)]
        if texts:
            return texts
    return []


def _first_attr(card: Tag, attr: str, *selectors: str, default: str = "N/A") -> str:
    for sel in selectors:
        el = card.select_one(sel)
        if el and el.get(attr):
            return el[attr]
    return default


class VisibleVCAdapter(BaseSiteAdapter):
    """Adapter for visible.vc/investors — public investor directory."""

    ADAPTER_NAME = "visible_vc"
    VERTICALS = ["vc"]
    RATE_LIMIT_RPM = 30
    REQUIRES_AUTH = False

    def parse_card(self, card: Tag) -> Optional[InvestorLead]:
        name = _first_text(
            card,
            ".investor-name", "h3", "h2", "[class*='name']", "[class*='Name']",
        )
        if not name or name == "N/A":
            return None

        role = _first_text(
            card,
            ".investor-title", ".title", ".role",
            "[class*='title']", "[class*='Title']", "[class*='role']",
        )
        fund = _first_text(
            card,
            ".fund-name", ".firm-name", ".organization",
            "[class*='firm']", "[class*='Firm']", "[class*='fund']",
        )
        focus_areas = _first_list(
            card,
            ".tags .tag", ".sectors .sector", ".focus-areas span",
            "[class*='tag']", "[class*='sector']",
        )
        stage = _first_text(
            card,
            ".stage", ".investment-stage", "[class*='stage']",
        )
        check_size = _first_text(
            card,
            ".check-size", ".ticket-size", "[class*='check']", "[class*='ticket']",
        )
        location = _first_text(
            card,
            ".location", ".city", "[class*='location']", "[class*='city']",
        )
        linkedin = _first_attr(
            card, "href",
            "a[href*='linkedin.com/in/']",
        )
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
