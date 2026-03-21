"""
CRAWL — Base Site Adapter
Abstract base class that all site-specific adapters extend.
Handles common operations: page loading, pagination, data extraction.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from playwright.async_api import Page

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────
#  Data Models
# ──────────────────────────────────────────────────

@dataclass
class InvestorLead:
    """A single investor lead extracted from a directory."""
    name: str
    email: str = "N/A"
    role: str = "N/A"
    fund: str = "N/A"
    focus_areas: list = field(default_factory=list)
    stage: str = "N/A"
    check_size: str = "N/A"
    location: str = "N/A"
    linkedin: str = "N/A"
    website: str = "N/A"
    source: str = ""
    scraped_at: str = ""
    lead_score: int = 0
    tier: str = ""
    email_status: str = "unknown"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["focus_areas"] = "; ".join(self.focus_areas) if self.focus_areas else "N/A"
        return d


# ──────────────────────────────────────────────────
#  Base Adapter
# ──────────────────────────────────────────────────

class BaseSiteAdapter(ABC):
    """
    Abstract base for all site scrapers.
    Subclasses implement parse_cards() with site-specific logic.
    The base class handles pagination, retries, and data collection.
    """

    def __init__(self, site_config: dict, stealth_module=None):
        self.config = site_config
        self.url = site_config["url"]
        self.selectors = site_config.get("selectors", {})
        self.pagination = site_config.get("pagination", {})
        self.stealth = stealth_module
        self.leads: list[InvestorLead] = []
        self._seen_names: set[str] = set()  # O(1) dedup within adapter

    @property
    def name(self) -> str:
        return self.config.get("adapter", self.__class__.__name__)

    async def run(self, page: Page) -> list[InvestorLead]:
        """
        Full scraping pipeline for this site:
        1. Navigate to target URL
        2. Apply stealth behaviors
        3. Handle pagination
        4. Extract leads from each page state
        """
        print(f"\n{'='*60}")
        print(f"  🕷️  CRAWLING: {self.name.upper()}")
        print(f"  📍  {self.url}")
        print(f"{'='*60}\n")

        await page.goto(self.url, timeout=60000)

        # Let page settle + apply human-like behavior
        if self.stealth:
            await self.stealth.human_wait(page)
            await self.stealth.random_mouse_movement(page)
        else:
            await page.wait_for_timeout(3000)

        # Handle pagination and extract across all pages
        await self._paginate_and_extract(page)

        print(f"\n  ✅  {self.name}: Extracted {len(self.leads)} leads\n")
        return self.leads

    async def _paginate_and_extract(self, page: Page):
        """Route to the correct pagination handler."""
        ptype = self.pagination.get("type", "none")

        if ptype == "infinite_scroll":
            await self._handle_infinite_scroll(page)
        elif ptype == "load_more_button":
            await self._handle_load_more(page)
        elif ptype == "numbered_pages":
            await self._handle_numbered_pages(page)
        else:
            # Single page, just extract
            await self._extract_from_page(page)

    async def _handle_infinite_scroll(self, page: Page):
        """Scroll down repeatedly to trigger lazy-loading content.
        Extracts after EVERY scroll to capture virtual-DOM pages that only
        render currently-visible rows (e.g. OpenVC).
        """
        scroll_count = self.pagination.get("scroll_count", 10)
        scroll_delay = self.pagination.get("scroll_delay_ms", 1500)
        load_indicator = self.pagination.get("load_indicator", "")
        extract_interval = self.pagination.get("extract_interval", 5)
        stale_rounds = 0  # stop early if no new leads for N rounds

        for i in range(scroll_count):
            if (i + 1) % 20 == 0 or i == 0:
                print(f"  📜  Scrolling... ({i+1}/{scroll_count})  [{len(self.leads)} leads so far]")

            if self.stealth:
                await self.stealth.human_scroll(page)
            else:
                await page.mouse.wheel(0, 800)

            if load_indicator:
                try:
                    await page.wait_for_selector(load_indicator, state="visible", timeout=2000)
                    await page.wait_for_selector(load_indicator, state="hidden", timeout=10000)
                except Exception:
                    pass

            await page.wait_for_timeout(scroll_delay)

            # Extract periodically to catch virtual-DOM rendered rows
            if (i + 1) % extract_interval == 0:
                before = len(self.leads)
                await self._extract_from_page(page, silent=True)
                gained = len(self.leads) - before
                if gained == 0:
                    stale_rounds += 1
                else:
                    stale_rounds = 0
                # Stop early if 3 consecutive extractions yield nothing new
                if stale_rounds >= 3 and len(self.leads) > 0:
                    print(f"  🏁  No new leads for {stale_rounds} rounds, stopping scroll at {i+1}/{scroll_count}")
                    break

        # Final extraction to catch anything remaining
        await self._extract_from_page(page)

    async def _handle_load_more(self, page: Page):
        """Click 'Load More' button until exhausted or max reached."""
        button = self.pagination.get("button_selector", "")
        max_clicks = self.pagination.get("max_clicks", 20)
        click_delay = self.pagination.get("click_delay_ms", 2000)

        for i in range(max_clicks):
            try:
                btn = page.locator(button)
                if await btn.count() == 0 or not await btn.is_visible():
                    print(f"  🏁  No more 'Load More' button found after {i} clicks")
                    break

                print(f"  🖱️  Clicking 'Load More'... ({i+1}/{max_clicks})")

                if self.stealth:
                    await self.stealth.human_click(page, button)
                else:
                    await btn.click()

                await page.wait_for_timeout(click_delay)

            except Exception as e:
                logger.debug("load_more stopped for %s: %s", self.name, e)
                break

        await self._extract_from_page(page)

    async def _handle_numbered_pages(self, page: Page):
        """Navigate through numbered pagination pages."""
        next_button = self.pagination.get("next_button", "")
        max_pages = self.pagination.get("max_pages", 20)

        for i in range(max_pages):
            print(f"  📄  Page {i+1}/{max_pages}")
            await self._extract_from_page(page)

            try:
                btn = page.locator(next_button)
                if await btn.count() == 0 or not await btn.is_visible():
                    print(f"  🏁  No more pages after page {i+1}")
                    break

                if self.stealth:
                    await self.stealth.human_click(page, next_button)
                else:
                    await btn.click()

                await page.wait_for_load_state("networkidle", timeout=10000)

                if self.stealth:
                    await self.stealth.human_wait(page, short=True)
                else:
                    await page.wait_for_timeout(1500)

            except Exception as e:
                logger.debug("pagination stopped for %s at page %d: %s", self.name, i + 1, e)
                break

    async def _extract_from_page(self, page: Page, silent: bool = False):
        """Get page HTML, parse it with BeautifulSoup, and extract leads."""
        content = await page.content()
        soup = BeautifulSoup(content, "html.parser")
        card_selector = self.selectors.get("card", "div")
        cards = soup.select(card_selector)

        if not silent:
            print(f"  🔍  Found {len(cards)} cards on current page state")

        # Diagnostic: when 0 cards found on a non-silent pass, dump structure hints
        if len(cards) == 0 and not silent:
            print(f"  ⚠️  DIAGNOSTIC: selector '{card_selector}' matched nothing.")
            # Try common fallbacks and report what exists
            for fallback in ["table tr", "div[class]", "[data-testid]", "article", "li"]:
                count = len(soup.select(fallback))
                if count > 0:
                    print(f"       → '{fallback}' matched {count} elements")

        new_leads = 0
        for card in cards:
            try:
                lead = self.parse_card(card)
                if lead and lead.name and lead.name != "N/A":
                    lead.source = self.url
                    lead.scraped_at = datetime.now().isoformat()
                    if lead.name not in self._seen_names:
                        self._seen_names.add(lead.name)
                        self.leads.append(lead)
                        new_leads += 1
            except Exception as e:
                logger.debug("parse_card failed for %s: %s", self.name, e)

        if not silent:
            print(f"  ➕  {new_leads} new unique leads extracted")

    @abstractmethod
    def parse_card(self, card) -> Optional[InvestorLead]:
        """
        Parse a single investor card from the page HTML.
        Must be implemented by each site adapter.

        Args:
            card: A BeautifulSoup Tag representing one investor card

        Returns:
            InvestorLead or None if card couldn't be parsed
        """
        pass

    # ── Utility helpers for subclasses ──

    def _safe_text(self, card, selector: str, default: str = "N/A") -> str:
        """Safely extract text from a CSS selector within a card."""
        el = card.select_one(selector) if selector else None
        return el.get_text(strip=True) if el else default

    def _safe_attr(self, card, selector: str, attr: str, default: str = "N/A") -> str:
        """Safely extract an attribute from a CSS selector within a card."""
        el = card.select_one(selector) if selector else None
        return el.get(attr, default) if el else default

    def _safe_list(self, card, selector: str) -> list:
        """Extract a list of text values from matching elements."""
        elements = card.select(selector) if selector else []
        return [el.get_text(strip=True) for el in elements if el.get_text(strip=True)]

    def _extract_email(self, card) -> str:
        """
        Multi-strategy email extraction:
        1. Look for mailto: links
        2. Scan text for @ patterns
        """
        email_sel = self.selectors.get("email", "")

        # Strategy 1: mailto link
        if email_sel:
            tag = card.select_one(email_sel)
            if tag:
                href = tag.get("href", "")
                if href.startswith("mailto:"):
                    return href.replace("mailto:", "").split("?")[0].strip()

        # Strategy 2: scan for email-like text
        text = card.get_text()
        if "@" in text:
            matches = re.findall(r'[\w.+-]+@[\w-]+\.[\w.-]+', text)
            if matches:
                return matches[0]

        return "N/A"
