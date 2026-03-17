"""
CRAWL — Landscape.vc Adapter
Scrapes investor data from landscape.vc.

STATUS (2026-03): landscape.vc/investors returns a 404 — the /investors path
no longer exists. The site is currently a VC news and analysis publication.
config/sites.yaml has been updated with enabled: false and url: "https://landscape.vc"
until a valid investor directory path is identified.

When re-enabling: verify the correct URL path first (e.g. /directory, /database)
and update both the url field in config/sites.yaml and the selectors below.
The parse_card() logic uses multi-selector fallback chains that should work
against most table-row or card-grid layouts common to VC directories.
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
    """
    Adapter for landscape.vc — VC news/analysis site.

    NOTE: The /investors directory path returned 404 as of 2026-03.
    This adapter is kept for when the path is rediscovered or restored.
    Selectors use broad fallback chains to handle both table-row and
    card-grid layouts.
    """

    ADAPTER_NAME = "landscape_vc"
    VERTICALS = ["vc"]
    RATE_LIMIT_RPM = 30
    REQUIRES_AUTH = False

    def parse_card(self, card: Tag) -> Optional[InvestorLead]:
        # Name — try config selector, then broad fallbacks
        name_sel = self.selectors.get("name", "")
        name = self._safe_text(card, name_sel) if name_sel else "N/A"
        if not name or name == "N/A":
            name = _first_text(
                card,
                "h2", "h3", "h4",
                ".name", "[class*='name']", "[class*='Name']",
                "td:nth-child(1) a", "td:nth-child(1)",
            )
        if not name or name == "N/A":
            return None

        role = _first_text(
            card,
            ".title", ".role",
            "[class*='title']", "[class*='Title']",
            "[class*='role']", "[class*='Role']",
            "td:nth-child(2)",
        )
        fund = _first_text(
            card,
            ".firm", ".fund", ".organization",
            "[class*='firm']", "[class*='Firm']",
            "[class*='fund']", "[class*='Fund']",
            "td:nth-child(3)",
        )

        focus_areas = _first_list(
            card,
            ".sectors span", ".focus span",
            "[class*='sector']", "[class*='Sector']",
            "[class*='focus']", "[class*='Focus']",
            "[class*='tag']", "[class*='Tag']",
            "td:nth-child(4) span",
        )
        # Fallback: single-cell text split by comma
        if not focus_areas:
            raw = _first_text(card, ".sectors", ".focus", "td:nth-child(4)")
            if raw and raw != "N/A":
                focus_areas = [s.strip() for s in raw.split(",") if s.strip()]

        stage = _first_text(
            card,
            ".stage", "[class*='stage']", "[class*='Stage']", "td:nth-child(5)",
        )
        check_size = _first_text(
            card,
            ".check", "[class*='check']", "[class*='Check']", "td:nth-child(6)",
        )
        location = _first_text(
            card,
            ".location", "[class*='location']", "[class*='Location']",
            "[class*='city']", "[class*='City']",
            "td:nth-child(7)",
        )

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
