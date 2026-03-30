"""
CRAWL — Reverse Portfolio Lookup

The snowball discovery engine. Takes portfolio companies already scraped from
known funds and searches for OTHER investors in those companies. Every funding
round announcement names participating investors — many of which are NOT in
our seed list. This creates a self-reinforcing discovery loop:

    known funds → portfolio companies → funding round press → NEW funds → repeat

Data sources:
1. Google search: "company raised" / "company funding" / "company investors"
2. Crunchbase/TechCrunch press mentions
3. SEC Form D co-filers (funds that co-invested in the same entity)
"""

import asyncio
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple
from urllib.parse import urlparse

import aiohttp

from adapters.base import InvestorLead

logger = logging.getLogger(__name__)

# Regex to extract fund/VC names from funding announcements
_FUND_NAME_RE = re.compile(
    r'(?:led by|with participation from|joined by|co-led by|backed by|investors? include)\s+'
    r'([A-Z][A-Za-z\s&,]+(?:Capital|Ventures|Partners|Fund|VC|Holdings|Group|Advisors|Investment[s]?))',
    re.IGNORECASE,
)

# Secondary: extract names after "investors:" or "backers:" lists
_INVESTOR_LIST_RE = re.compile(
    r'(?:investors?|backers?|participants?)[\s:]+([A-Z][A-Za-z\s&,]+)',
    re.IGNORECASE,
)

# Known VC suffixes for splitting comma-separated lists
_VC_SUFFIXES = {
    "capital", "ventures", "partners", "fund", "vc", "holdings", "group",
    "advisors", "investments", "management", "equity", "labs",
}

# User agents for rotation
_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/121.0.0.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0",
]


def _split_fund_names(raw: str) -> List[str]:
    """Split a comma/and-separated string of fund names into individual names."""
    # Replace "and" with comma for splitting
    raw = re.sub(r'\band\b', ',', raw, flags=re.IGNORECASE)
    parts = [p.strip().rstrip('.') for p in raw.split(',')]

    funds = []
    for part in parts:
        part = part.strip()
        if not part or len(part) < 3:
            continue
        # Keep if it contains a known VC suffix or is capitalized multi-word
        words = part.split()
        has_suffix = any(w.lower() in _VC_SUFFIXES for w in words)
        is_proper = len(words) >= 2 and all(w[0].isupper() for w in words if len(w) > 2)
        if has_suffix or is_proper:
            funds.append(part)

    return funds


def _fund_to_domain(fund_name: str) -> str:
    """Heuristically derive a domain from a fund name."""
    name = re.sub(
        r'\b(llc|lp|l\.p\.|ltd|inc|corp)\b', '', fund_name, flags=re.IGNORECASE
    ).strip()
    name = re.sub(r'[,.\'"!?()&@]', '', name).strip()
    slug = re.sub(r'\s+', '', name).lower().strip('-')
    if len(slug) < 4:
        return ''
    return slug + '.com'


class ReversePortfolioLookup:
    """
    Discovers new fund domains by searching for investors in known portfolio companies.
    """

    def __init__(self, concurrency: int = 10, max_companies: int = 200):
        self._sem = asyncio.Semaphore(concurrency)
        self._max_companies = max_companies
        self._discovered_funds: Dict[str, str] = {}  # fund_name → source_company
        self._known_domains: Set[str] = set()
        self._stats = {
            "companies_searched": 0,
            "queries_made": 0,
            "funds_discovered": 0,
            "domains_generated": 0,
            "errors": 0,
        }

    def _load_known_domains(self) -> Set[str]:
        """Load existing fund domains from target_funds.txt."""
        target_file = Path("data/target_funds.txt")
        if target_file.exists():
            return {
                line.strip().lower().replace("https://", "").replace("http://", "").replace("www.", "")
                for line in target_file.read_text().splitlines()
                if line.strip()
            }
        return set()

    def _load_portfolio_companies(self) -> List[Tuple[str, str]]:
        """Load portfolio companies from database or CSV."""
        companies = []

        # Try database first
        try:
            import sqlite3
            db_path = Path("data/leadfactory.db")
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                cursor = conn.execute(
                    "SELECT DISTINCT company_name, fund_name FROM portfolio_companies "
                    "ORDER BY RANDOM() LIMIT ?",
                    (self._max_companies,),
                )
                companies = [(row[0], row[1]) for row in cursor.fetchall()]
                conn.close()
        except Exception:
            pass

        if not companies:
            logger.info("  No portfolio companies found in database")

        return companies

    async def _search_company_investors(
        self, session: aiohttp.ClientSession, company_name: str, source_fund: str
    ) -> List[str]:
        """Search for investors in a specific portfolio company."""
        async with self._sem:
            self._stats["companies_searched"] += 1
            found_funds = []

            queries = [
                f'"{company_name}" raised funding investors',
                f'"{company_name}" Series funding led by',
                f'"{company_name}" venture capital investors',
            ]

            import random
            ua = random.choice(_USER_AGENTS)
            headers = {"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"}

            for query in queries[:2]:  # Limit to 2 queries per company
                self._stats["queries_made"] += 1
                try:
                    # Use DuckDuckGo HTML search (no API key needed)
                    async with session.get(
                        "https://html.duckduckgo.com/html/",
                        params={"q": query},
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()

                        # Extract fund names from search result snippets
                        for match in _FUND_NAME_RE.finditer(html):
                            names = _split_fund_names(match.group(1))
                            found_funds.extend(names)

                        for match in _INVESTOR_LIST_RE.finditer(html):
                            names = _split_fund_names(match.group(1))
                            found_funds.extend(names)

                except Exception as e:
                    self._stats["errors"] += 1
                    logger.debug(f"  Search error for {company_name}: {e}")

                # Rate limit
                await asyncio.sleep(2.0 + (asyncio.get_event_loop().time() % 1))

            return found_funds

    async def discover(self) -> List[InvestorLead]:
        """
        Run reverse portfolio lookup.
        Returns InvestorLead objects for newly discovered funds.
        """
        self._known_domains = self._load_known_domains()
        companies = self._load_portfolio_companies()

        if not companies:
            print("  Reverse portfolio: no portfolio companies to search")
            return []

        print(f"  Reverse portfolio: searching investors for {len(companies)} portfolio companies...")

        async with aiohttp.ClientSession() as session:
            tasks = [
                self._search_company_investors(session, company, fund)
                for company, fund in companies
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect and deduplicate discovered funds
        for (company, source_fund), result in zip(companies, results):
            if isinstance(result, Exception):
                continue
            for fund_name in result:
                fund_key = fund_name.lower().strip()
                if fund_key not in self._discovered_funds:
                    self._discovered_funds[fund_key] = company

        # Generate domains and filter out known ones
        new_leads = []
        seen = set()
        for fund_name, source_company in self._discovered_funds.items():
            domain = _fund_to_domain(fund_name)
            if not domain or domain in self._known_domains or domain in seen:
                continue
            seen.add(domain)
            self._stats["domains_generated"] += 1

            lead = InvestorLead(
                name=fund_name.title(),
                fund=fund_name.title(),
                website=domain,
                source=f"reverse_portfolio:{source_company}",
                scraped_at=datetime.now().isoformat(),
            )
            new_leads.append(lead)

        self._stats["funds_discovered"] = len(self._discovered_funds)

        print(
            f"  Reverse portfolio: {self._stats['funds_discovered']} funds found, "
            f"{self._stats['domains_generated']} new domains "
            f"({self._stats['companies_searched']} companies searched)"
        )

        return new_leads

    @property
    def stats(self) -> dict:
        return dict(self._stats)
