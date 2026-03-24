"""
Fund Site Discovery — locates relevant pages on a VC fund website.

Given a fund domain, discovers and classifies pages by type:
team, portfolio, thesis/blog, news, about, contact.

Uses sitemap.xml, internal link crawling, and keyword-based URL ranking.
Falls back to well-known path guessing.
"""

import asyncio
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Page types we classify
PAGE_TYPES = ["team", "portfolio", "thesis", "news", "about", "contact"]

# Default keyword → page type mapping
DEFAULT_PAGE_KEYWORDS: Dict[str, List[str]] = {
    "team": [
        "team", "people", "partners", "our-team", "who-we-are",
        "leadership", "investment-team", "professionals", "bios",
        "our-people", "meet-the-team", "founders", "staff",
        "managing-directors", "general-partners",
    ],
    "portfolio": [
        "portfolio", "companies", "investments", "portfolio-companies",
        "our-portfolio", "startups", "founders", "our-companies",
    ],
    "thesis": [
        "thesis", "insights", "blog", "what-we-do", "approach",
        "strategy", "philosophy", "focus", "perspectives",
        "thinking", "views", "ideas",
    ],
    "news": [
        "news", "press", "media", "announcements", "in-the-news",
        "press-releases", "newsroom",
    ],
    "about": [
        "about", "about-us", "who-we-are", "our-story", "firm",
        "overview", "mission", "values",
    ],
    "contact": [
        "contact", "connect", "get-in-touch", "reach-out",
    ],
}

# Well-known fallback paths per page type
FALLBACK_PATHS: Dict[str, List[str]] = {
    "team": ["/team", "/people", "/about/team", "/our-team", "/leadership",
             "/about/people", "/partners", "/investment-team"],
    "portfolio": ["/portfolio", "/companies", "/investments",
                  "/portfolio-companies", "/our-portfolio", "/startups"],
    "thesis": ["/blog", "/insights", "/thesis", "/perspectives",
               "/what-we-do", "/approach", "/strategy"],
    "news": ["/news", "/press", "/media", "/announcements", "/in-the-news"],
    "about": ["/about", "/about-us", "/firm", "/overview"],
    "contact": ["/contact", "/connect", "/get-in-touch"],
}


@dataclass
class DiscoveredPage:
    """A page discovered on a fund website with classification."""
    url: str
    page_type: str
    confidence: float  # 0.0–1.0
    source: str  # "sitemap", "link", "fallback"
    anchor_text: str = ""
    path: str = ""


@dataclass
class SiteDiscoveryResult:
    """Complete discovery result for a fund website."""
    domain: str
    homepage_url: str
    pages: Dict[str, List[DiscoveredPage]] = field(default_factory=lambda: {t: [] for t in PAGE_TYPES})
    all_internal_links: Set[str] = field(default_factory=set)
    sitemap_urls: List[str] = field(default_factory=list)

    def best_page(self, page_type: str) -> Optional[DiscoveredPage]:
        """Return highest-confidence page of a given type."""
        candidates = self.pages.get(page_type, [])
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.confidence)

    def best_url(self, page_type: str) -> Optional[str]:
        """Return URL of highest-confidence page of a given type."""
        p = self.best_page(page_type)
        return p.url if p else None

    def summary(self) -> dict:
        """Summary dict for logging."""
        return {
            page_type: len(pages)
            for page_type, pages in self.pages.items()
            if pages
        }


class SiteDiscoverer:
    """
    Discovers and classifies pages on a fund website.

    Strategy (in order):
    1. Parse sitemap.xml for all URLs
    2. Crawl homepage for internal links (depth 1)
    3. Classify found URLs by keyword matching
    4. Add fallback guessed paths for missing types
    """

    def __init__(
        self,
        page_keywords: Optional[Dict[str, List[str]]] = None,
        request_timeout: float = 10.0,
        crawl_delay: float = 0.3,
        max_internal_pages: int = 30,
        user_agent: str = "Mozilla/5.0 (compatible)",
    ):
        self.page_keywords = page_keywords or DEFAULT_PAGE_KEYWORDS
        self.timeout = aiohttp.ClientTimeout(total=request_timeout)
        self.crawl_delay = crawl_delay
        self.max_internal_pages = max_internal_pages
        self.user_agent = user_agent

    async def discover(self, fund_url: str) -> SiteDiscoveryResult:
        """Run full discovery for a fund URL."""
        parsed = urlparse(fund_url)
        domain = parsed.netloc.lower().replace("www.", "")
        base = f"{parsed.scheme}://{parsed.netloc}"

        result = SiteDiscoveryResult(domain=domain, homepage_url=fund_url)

        async with aiohttp.ClientSession(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
        ) as session:
            # Step 1: Sitemap
            sitemap_urls = await self._fetch_sitemap(session, base)
            result.sitemap_urls = sitemap_urls

            # Step 2: Homepage links
            homepage_links = await self._fetch_homepage_links(session, fund_url)
            result.all_internal_links = homepage_links | set(sitemap_urls)

            # Step 3: Classify all found URLs
            all_urls = list(result.all_internal_links)
            for url in all_urls[:self.max_internal_pages]:
                classifications = self._classify_url(url, fund_url)
                for page_type, confidence in classifications:
                    source = "sitemap" if url in sitemap_urls else "link"
                    page = DiscoveredPage(
                        url=url,
                        page_type=page_type,
                        confidence=confidence,
                        source=source,
                        path=urlparse(url).path,
                    )
                    result.pages[page_type].append(page)

            # Step 4: Fallback paths for missing types
            for page_type in PAGE_TYPES:
                if not result.pages[page_type]:
                    for path in FALLBACK_PATHS.get(page_type, []):
                        fallback_url = urljoin(fund_url, path)
                        page = DiscoveredPage(
                            url=fallback_url,
                            page_type=page_type,
                            confidence=0.3,
                            source="fallback",
                            path=path,
                        )
                        result.pages[page_type].append(page)

            # Sort each type by confidence
            for page_type in PAGE_TYPES:
                result.pages[page_type].sort(key=lambda p: p.confidence, reverse=True)

        return result

    async def _fetch_sitemap(self, session: aiohttp.ClientSession, base_url: str) -> List[str]:
        """Parse sitemap.xml and return all URLs."""
        urls = []
        for path in ["/sitemap.xml", "/sitemap_index.xml"]:
            try:
                async with session.get(base_url + path) as resp:
                    if resp.status != 200:
                        continue
                    text = await resp.text()
                    root = ET.fromstring(text)
                    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                    for loc in root.findall(".//sm:loc", ns):
                        if loc.text:
                            urls.append(loc.text.strip())
                    # Also try without namespace
                    for loc in root.iter():
                        if loc.tag.endswith("loc") and loc.text:
                            url = loc.text.strip()
                            if url not in urls:
                                urls.append(url)
            except Exception:
                continue
        return urls

    async def _fetch_homepage_links(
        self, session: aiohttp.ClientSession, homepage_url: str
    ) -> Set[str]:
        """Fetch homepage and extract internal links."""
        links = set()
        try:
            async with session.get(homepage_url) as resp:
                if resp.status != 200:
                    return links
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                base_domain = urlparse(homepage_url).netloc.lower()

                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    full = urljoin(homepage_url, href)
                    parsed = urlparse(full)
                    if parsed.netloc.lower().replace("www.", "") == base_domain.replace("www.", ""):
                        # Normalize
                        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                        if clean.endswith("/"):
                            clean = clean[:-1]
                        links.add(clean)
        except Exception as e:
            logger.debug(f"Homepage link fetch failed for {homepage_url}: {e}")
        return links

    def _classify_url(self, url: str, base_url: str) -> List[tuple]:
        """
        Classify a URL into page types based on path keywords.
        Returns list of (page_type, confidence) tuples.
        """
        path = urlparse(url).path.lower().strip("/")
        if not path:
            return []

        classifications = []
        segments = path.split("/")

        for page_type, keywords in self.page_keywords.items():
            best_score = 0.0
            for keyword in keywords:
                kw_lower = keyword.lower()
                # Exact segment match → high confidence
                if kw_lower in segments:
                    best_score = max(best_score, 0.9)
                # Path contains keyword → medium confidence
                elif kw_lower in path:
                    best_score = max(best_score, 0.7)
                # Partial match → lower confidence
                elif any(kw_lower in seg for seg in segments):
                    best_score = max(best_score, 0.5)

            # Depth penalty: deeper pages are less likely to be the canonical page
            depth = len(segments)
            if depth > 2:
                best_score *= 0.8

            if best_score > 0.0:
                classifications.append((page_type, best_score))

        return classifications
