"""
CRAWL — Visible.vc Adapter
Scrapes the investor database at connect.visible.vc/investors.

STATUS (2026-03): visible.vc/investors now permanently redirects to
visible.vc/monitor/ (a product marketing page). The actual investor database
is at connect.visible.vc/investors and appears to require login.

config/sites.yaml has been updated:
  - url: "https://connect.visible.vc/investors"
  - enabled: false (login wall not bypassed)

Re-enable this adapter only if connect.visible.vc/investors is confirmed
publicly accessible without authentication. The selectors below use
[class*='...'] substring matching because connect.visible.vc is a
React/Next.js app with CSS module hashing.
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
    """
    Adapter for connect.visible.vc/investors — investor database.

    NOTE: visible.vc/investors redirects to the marketing site as of 2026-03.
    The database lives at connect.visible.vc/investors and may require auth.
    Selectors use data-testid attributes (where available) and [class*='...']
    substring matching for the React CSS modules used on the connect subdomain.
    """

    ADAPTER_NAME = "visible_vc"
    VERTICALS = ["vc"]
    RATE_LIMIT_RPM = 30
    REQUIRES_AUTH = False  # May need to change to True if login is enforced

    def parse_card(self, card: Tag) -> Optional[InvestorLead]:
        name = _first_text(
            card,
            # data-testid attributes (React test ids survive minification)
            "[data-testid='investor-name']",
            # class substring matches for CSS modules
            "[class*='InvestorName']", "[class*='investor-name']",
            "[class*='PersonName']", "[class*='person-name']",
            # Generic semantic fallbacks
            "h3", "h2", "[class*='name']", "[class*='Name']",
        )
        if not name or name == "N/A":
            return None

        role = _first_text(
            card,
            "[data-testid='investor-title']",
            "[class*='InvestorTitle']", "[class*='investor-title']",
            "[class*='Title']", "[class*='title']",
            "[class*='role']", "[class*='Role']",
        )
        fund = _first_text(
            card,
            "[data-testid='fund-name']",
            "[class*='FundName']", "[class*='fund-name']",
            "[class*='FirmName']", "[class*='firm-name']",
            "[class*='OrgName']", "[class*='org-name']",
            "[class*='organization']",
        )
        focus_areas = _first_list(
            card,
            "[data-testid='focus-area']",
            "[class*='FocusTag']", "[class*='focus-tag']",
            "[class*='SectorTag']", "[class*='sector-tag']",
            "[class*='tag']", "[class*='Tag']",
        )
        stage = _first_text(
            card,
            "[data-testid='stage']",
            "[class*='Stage']", "[class*='stage']",
            "[class*='InvestmentStage']",
        )
        check_size = _first_text(
            card,
            "[data-testid='check-size']",
            "[class*='CheckSize']", "[class*='check-size']",
            "[class*='TicketSize']", "[class*='ticket-size']",
        )
        location = _first_text(
            card,
            "[data-testid='location']",
            "[class*='Location']", "[class*='location']",
            "[class*='City']", "[class*='city']",
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
