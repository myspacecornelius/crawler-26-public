"""
CRAWL — Investor Content Miner

Discovers active investors from their published content:
- Substack newsletters (finance/VC category)
- Medium articles (venture-capital, startups, investing tags)
- Podcast guest appearances (via ListenNotes-style search)
- Twitter/X VC lists

Active investors who publish are high-signal: they're building a brand,
which means they're actively deploying or fundraising.
"""

import asyncio
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from adapters.base import InvestorLead

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0"

# VC/investor bio patterns
_BIO_INVESTOR_RE = re.compile(
    r'(?:partner|managing director|gp|general partner|principal|investor|founder|ceo|'
    r'venture partner|operating partner)\s+(?:at|@|of|,)\s+'
    r'([A-Z][A-Za-z\s&\-]+(?:Capital|Ventures|Partners|Fund|VC|Equity|Growth|'
    r'Management|Advisors|Holdings|Associates|Group))',
    re.IGNORECASE,
)

# Substack discovery URLs
_SUBSTACK_FINANCE_URLS = [
    "https://substack.com/discover/category/finance/paid",
    "https://substack.com/discover/category/finance/free",
    "https://substack.com/discover/category/business/paid",
    "https://substack.com/discover/category/technology/paid",
]

# Medium tag URLs for investor content
_MEDIUM_TAG_URLS = [
    "https://medium.com/tag/venture-capital/recommended",
    "https://medium.com/tag/startups/recommended",
    "https://medium.com/tag/investing/recommended",
    "https://medium.com/tag/angel-investing/recommended",
    "https://medium.com/tag/fundraising/recommended",
]

# Known curated VC Twitter/X lists (public lists of VCs)
_TWITTER_VC_LISTS = [
    "https://twitter.com/i/lists/1271513507838840833",  # VC investors
    "https://twitter.com/i/lists/217437023",             # Venture capitalists
]

_VC_INDICATORS = {
    "capital", "ventures", "partners", "vc", "fund", "equity", "growth",
    "investment", "holdings", "advisors", "management", "associates",
}


def _is_investor_bio(text: str) -> bool:
    """Check if a bio/description suggests an investor."""
    lower = text.lower()
    investor_terms = [
        "venture", "investor", "vc", "capital", "portfolio",
        "fund", "partner at", "investing in", "seed stage",
        "series a", "angel", "limited partner", "general partner",
    ]
    return any(term in lower for term in investor_terms)


def _extract_fund_from_bio(bio: str) -> str:
    """Try to extract a fund name from a bio string."""
    match = _BIO_INVESTOR_RE.search(bio)
    if match:
        return match.group(1).strip()
    return ""


def _fund_to_domain(fund_name: str) -> str:
    """Derive probable website domain from a fund name."""
    name = re.sub(
        r'\b(llc|lp|l\.p\.|ltd|inc|corp)\b', '', fund_name, flags=re.IGNORECASE
    ).strip()
    name = re.sub(r'[,.\'"!?()&@\-]', '', name).strip()
    slug = re.sub(r'\s+', '', name).lower().strip('-')
    if len(slug) < 4:
        return ''
    return slug + '.com'


class InvestorContentMiner:
    """
    Discovers active investors from their published content on
    Substack, Medium, and podcast platforms.
    """

    def __init__(self, concurrency: int = 5):
        self._sem = asyncio.Semaphore(concurrency)
        self._stats = {
            "substack_authors": 0,
            "medium_authors": 0,
            "podcast_guests": 0,
            "total_investor_authors": 0,
            "leads_generated": 0,
            "errors": 0,
        }

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str:
        """Fetch a URL with error handling."""
        try:
            async with session.get(
                url,
                headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
                timeout=aiohttp.ClientTimeout(total=15),
                allow_redirects=True,
            ) as resp:
                if resp.status != 200:
                    return ""
                return await resp.text()
        except Exception as e:
            self._stats["errors"] += 1
            logger.debug(f"  Content miner fetch error {url}: {e}")
            return ""

    async def _mine_substack(self, session: aiohttp.ClientSession) -> List[dict]:
        """Discover investor authors from Substack category pages."""
        authors = []
        seen = set()

        for url in _SUBSTACK_FINANCE_URLS:
            html = await self._fetch(session, url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Substack renders newsletter cards with author info
            for card in soup.select("[class*='publication'], [class*='newsletter'], article"):
                name_el = card.select_one("h2, h3, [class*='name'], [class*='title']")
                desc_el = card.select_one("p, [class*='description'], [class*='subtitle']")
                author_el = card.select_one("[class*='author'], [class*='byline']")

                name = ""
                description = ""
                author_name = ""
                newsletter_url = ""

                if name_el:
                    name = name_el.get_text(strip=True)
                if desc_el:
                    description = desc_el.get_text(strip=True)
                if author_el:
                    author_name = author_el.get_text(strip=True)

                # Get the newsletter URL
                link = card.find("a", href=True)
                if link:
                    newsletter_url = link["href"]

                # Check if the author/description suggests an investor
                combined_text = f"{name} {description} {author_name}"
                if _is_investor_bio(combined_text):
                    fund = _extract_fund_from_bio(combined_text)
                    person_name = author_name if author_name else name
                    key = person_name.lower().strip()
                    if key and key not in seen and len(person_name.split()) >= 2:
                        seen.add(key)
                        authors.append({
                            "name": person_name,
                            "fund": fund,
                            "bio": description[:200],
                            "source_url": newsletter_url,
                            "platform": "substack",
                        })
                        self._stats["substack_authors"] += 1

            await asyncio.sleep(2.0)

        return authors

    async def _mine_medium(self, session: aiohttp.ClientSession) -> List[dict]:
        """Discover investor authors from Medium tag pages."""
        authors = []
        seen = set()

        for url in _MEDIUM_TAG_URLS:
            html = await self._fetch(session, url)
            if not html:
                continue

            soup = BeautifulSoup(html, "html.parser")

            # Medium article cards contain author info
            for article in soup.select("article, [class*='postPreview'], [class*='streamItem']"):
                # Find author name
                author_el = article.select_one(
                    "[class*='author'], [data-testid*='author'], "
                    "a[href*='/@'], [class*='creator']"
                )
                # Find author description/bio
                desc_el = article.select_one(
                    "[class*='bio'], [class*='description'], "
                    "[class*='subtitle']"
                )

                if not author_el:
                    continue

                author_name = author_el.get_text(strip=True)
                description = desc_el.get_text(strip=True) if desc_el else ""

                # Get author profile URL
                author_url = ""
                if author_el.name == "a":
                    author_url = author_el.get("href", "")
                else:
                    link = author_el.find("a", href=True)
                    if link:
                        author_url = link["href"]

                combined = f"{author_name} {description}"
                if _is_investor_bio(combined):
                    fund = _extract_fund_from_bio(combined)
                    key = author_name.lower().strip()
                    if key and key not in seen and len(author_name.split()) >= 2:
                        seen.add(key)
                        authors.append({
                            "name": author_name,
                            "fund": fund,
                            "bio": description[:200],
                            "source_url": author_url,
                            "platform": "medium",
                        })
                        self._stats["medium_authors"] += 1

            await asyncio.sleep(2.0)

        return authors

    async def _mine_podcast_guests(self, session: aiohttp.ClientSession) -> List[dict]:
        """
        Search for VC podcast guests via search engine queries.
        Uses DuckDuckGo to find podcast episode pages featuring investors.
        """
        guests = []
        seen = set()

        queries = [
            '"venture capital" podcast guest investor site:podcasts.apple.com',
            '"venture partner" podcast episode site:open.spotify.com',
            '"general partner" "capital" podcast interview site:youtube.com',
            'VC investor podcast "managing partner" site:listennotes.com',
        ]

        for query in queries:
            try:
                async with self._sem:
                    async with session.get(
                        "https://html.duckduckgo.com/html/",
                        params={"q": query},
                        headers={"User-Agent": _UA},
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()

                    soup = BeautifulSoup(html, "html.parser")

                    # Extract results
                    for result in soup.select(".result, .links_main, [class*='result']"):
                        title = result.select_one("a, h2, h3")
                        snippet = result.select_one(
                            ".result__snippet, .snippet, [class*='snippet']"
                        )
                        if not title:
                            continue

                        title_text = title.get_text(strip=True)
                        snippet_text = snippet.get_text(strip=True) if snippet else ""
                        combined = f"{title_text} {snippet_text}"

                        # Look for investor names in podcast titles/snippets
                        for match in _BIO_INVESTOR_RE.finditer(combined):
                            fund = match.group(1).strip()
                            # Try to extract the person name from surrounding text
                            # Pattern: "Name, Role at Fund"
                            name_match = re.search(
                                r'([A-Z][a-z]+\s+[A-Z][a-z]+)(?:,|\s+[-–—]\s+|\s+of\s+|\s+from\s+)',
                                combined[:match.start() + 50],
                            )
                            if name_match:
                                person_name = name_match.group(1)
                                key = person_name.lower()
                                if key not in seen:
                                    seen.add(key)
                                    guests.append({
                                        "name": person_name,
                                        "fund": fund,
                                        "bio": "",
                                        "source_url": title.get("href", ""),
                                        "platform": "podcast",
                                    })
                                    self._stats["podcast_guests"] += 1

            except Exception as e:
                self._stats["errors"] += 1
                logger.debug(f"  Podcast search error: {e}")

            await asyncio.sleep(3.0)

        return guests

    async def discover(self) -> List[InvestorLead]:
        """
        Mine all content platforms for investor contacts.
        Returns InvestorLead objects for discovered investors.
        """
        print("  Content miner: scanning Substack, Medium, podcasts...")

        async with aiohttp.ClientSession() as session:
            substack_task = self._mine_substack(session)
            medium_task = self._mine_medium(session)
            podcast_task = self._mine_podcast_guests(session)

            substack, medium, podcasts = await asyncio.gather(
                substack_task, medium_task, podcast_task,
                return_exceptions=True,
            )

        # Combine all authors
        all_authors = []
        if isinstance(substack, list):
            all_authors.extend(substack)
        if isinstance(medium, list):
            all_authors.extend(medium)
        if isinstance(podcasts, list):
            all_authors.extend(podcasts)

        self._stats["total_investor_authors"] = len(all_authors)

        # Deduplicate and generate leads
        leads = []
        seen_names = set()

        for author in all_authors:
            name = author.get("name", "").strip()
            fund = author.get("fund", "")
            platform = author.get("platform", "")
            source_url = author.get("source_url", "")

            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())

            domain = _fund_to_domain(fund) if fund else ""

            lead = InvestorLead(
                name=name,
                fund=fund if fund else "N/A",
                website=domain if domain else "N/A",
                source=f"content:{platform}",
                scraped_at=datetime.now().isoformat(),
            )
            leads.append(lead)

        self._stats["leads_generated"] = len(leads)

        print(
            f"  Content miner: {self._stats['total_investor_authors']} investor authors "
            f"(Substack: {self._stats['substack_authors']}, "
            f"Medium: {self._stats['medium_authors']}, "
            f"Podcasts: {self._stats['podcast_guests']}) → "
            f"{self._stats['leads_generated']} leads"
        )

        return leads

    @property
    def stats(self) -> dict:
        return dict(self._stats)
