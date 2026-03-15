"""
CRAWL — Landscape.vc Adapter
Scrapes the filterable VC investor directory at landscape.vc/investors.
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


class LandscapeVCAdapter(BaseSiteAdapter):
    """Adapter for landscape.vc/investors — filterable VC directory."""

    ADAPTER_NAME = "landscape_vc"
    VERTICALS = ["vc"]
    RATE_LIMIT_RPM = 30
    REQUIRES_AUTH = False

    def parse_card(self, card: Tag) -> Optional[InvestorLead]:
        name = _first_text(
            card,
            ".name", "td:nth-child(1) a", "td:nth-child(1)", "h3",
            "[class*='name']", "[class*='Name']",
        )
        if not name or name == "N/A":
            return None

        role = _first_text(
            card,
            ".title", ".role", "td:nth-child(2)",
            "[class*='title']", "[class*='role']",
        )
        fund = _first_text(
            card,
            ".firm", ".fund", "td:nth-child(3)",
            "[class*='firm']", "[class*='fund']",
        )
        focus_areas = _first_list(
            card,
            ".sectors span", ".focus span", "td:nth-child(4) span",
            "[class*='sector']", "[class*='focus']",
        )
        # Fallback: single cell text split by comma
        if not focus_areas:
            raw = _first_text(card, ".sectors", ".focus", "td:nth-child(4)")
            if raw and raw != "N/A":
                focus_areas = [s.strip() for s in raw.split(",") if s.strip()]

        stage = _first_text(card, ".stage", "td:nth-child(5)", "[class*='stage']")
        check_size = _first_text(card, ".check", "td:nth-child(6)", "[class*='check']")
        location = _first_text(card, ".location", "td:nth-child(7)", "[class*='location']")

        linkedin = "N/A"
        li_tag = card.select_one("a[href*='linkedin.com/in/']")
        if li_tag:
            linkedin = li_tag.get("href", "N/A")

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
