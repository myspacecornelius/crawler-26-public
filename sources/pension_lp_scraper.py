"""
CRAWL — Pension Fund LP Disclosure Scraper

Public pension funds are legally required to disclose their alternative investment
allocations. These disclosures list every VC/PE fund they've committed to, including
fund names, GP entities, vintage years, and commitment amounts.

This is the single most authoritative source of "who has money to deploy" because
it's the money trail itself — not marketing, not self-reported, but regulatory fact.

Sources scraped:
- CalPERS (California Public Employees' Retirement System)
- CalSTRS (California State Teachers' Retirement System)
- Texas Teachers (Teacher Retirement System of Texas)
- Washington State Investment Board
- Oregon Public Employees Retirement Fund
- NYC Comptroller's Office
- State of Wisconsin Investment Board
- Pennsylvania PSERS
- Florida SBA
- Additional public pension systems with online disclosure
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, List, Set, Tuple
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from adapters.base import InvestorLead

logger = logging.getLogger(__name__)

# VC/PE fund name patterns in pension disclosures
_FUND_PATTERN = re.compile(
    r'([A-Z][A-Za-z\s&\-\.]+(?:Capital|Ventures|Partners|Fund|Equity|Growth|'
    r'Investment[s]?|Management|Advisors|Holdings|Group|Associates)(?:\s+(?:I{1,3}V?|V|VI{0,3}|'
    r'[0-9]+|LP|LLC|L\.P\.?))*)',
    re.IGNORECASE,
)

# Common LP disclosure page patterns
_DISCLOSURE_SOURCES = [
    {
        "name": "CalPERS",
        "url": "https://www.calpers.ca.gov/page/investments/asset-classes/private-equity/program-holdings",
        "type": "html_table",
    },
    {
        "name": "CalSTRS",
        "url": "https://www.calstrs.com/private-equity-program",
        "type": "html_links",
    },
    {
        "name": "WSIB",
        "url": "https://www.sib.wa.gov/financial/pdfs/investments/private_equity.pdf",
        "type": "text_page",
    },
    {
        "name": "OregonPERS",
        "url": "https://www.oregon.gov/treasury/invested-for-oregon/pages/alternative-investments.aspx",
        "type": "html_links",
    },
    {
        "name": "SWIB",
        "url": "https://www.swib.state.wi.us/private-equity-investments",
        "type": "html_table",
    },
    {
        "name": "Florida_SBA",
        "url": "https://www.sbafla.com/fsb/FundsManagement/PrivateEquity.aspx",
        "type": "html_table",
    },
    {
        "name": "Texas_TRS",
        "url": "https://www.trs.texas.gov/Pages/investments_alternative.aspx",
        "type": "html_links",
    },
    {
        "name": "NYC_Comptroller",
        "url": "https://comptroller.nyc.gov/reports/annual-investment-report/",
        "type": "html_links",
    },
]

# User agent for requests
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0"

# Known words that indicate VC/PE funds (to distinguish from pension plan names)
_GP_INDICATORS = {
    "capital", "ventures", "partners", "equity", "fund", "growth",
    "management", "advisors", "holdings", "associates", "investment",
}


def _is_gp_name(name: str) -> bool:
    """Check if a name looks like a GP/fund name rather than a pension plan."""
    words = name.lower().split()
    return any(w in _GP_INDICATORS for w in words)


def _clean_fund_name(raw: str) -> str:
    """Clean and normalize a fund name from disclosure text."""
    # Strip fund number suffixes for the GP name
    name = re.sub(r'\s+(I{1,3}V?|V|VI{0,3}|[0-9]+)\s*$', '', raw.strip())
    name = re.sub(r'\s+(LP|LLC|L\.P\.?|Ltd\.?)\s*$', '', name, flags=re.IGNORECASE)
    name = name.strip(' .,')
    return name


def _fund_to_domain(fund_name: str) -> str:
    """Derive probable website domain from a fund name."""
    name = re.sub(
        r'\b(llc|lp|l\.p\.|ltd|inc|corp|fund)\b', '', fund_name, flags=re.IGNORECASE
    ).strip()
    name = re.sub(r'[,.\'"!?()&@\-]', '', name).strip()
    slug = re.sub(r'\s+', '', name).lower().strip('-')
    if len(slug) < 4:
        return ''
    return slug + '.com'


class PensionLPScraper:
    """
    Scrapes public pension fund LP disclosures to find GP/fund names,
    then generates leads with probable website domains.
    """

    def __init__(self, concurrency: int = 5):
        self._sem = asyncio.Semaphore(concurrency)
        self._discovered_gps: Dict[str, Set[str]] = {}  # gp_name → {source_pension, ...}
        self._stats = {
            "sources_scraped": 0,
            "sources_failed": 0,
            "raw_fund_names": 0,
            "unique_gps": 0,
            "leads_generated": 0,
        }

    async def _fetch_html(
        self, session: aiohttp.ClientSession, url: str
    ) -> str:
        """Fetch a page with timeout and error handling."""
        try:
            async with session.get(
                url,
                headers={"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"  LP scraper: {url} returned {resp.status}")
                    return ""
                return await resp.text()
        except Exception as e:
            logger.debug(f"  LP scraper: error fetching {url}: {e}")
            return ""

    async def _scrape_source(
        self, session: aiohttp.ClientSession, source: dict
    ) -> List[str]:
        """Scrape a single pension fund disclosure source."""
        async with self._sem:
            name = source["name"]
            url = source["url"]
            source_type = source["type"]

            html = await self._fetch_html(session, url)
            if not html:
                self._stats["sources_failed"] += 1
                return []

            self._stats["sources_scraped"] += 1
            fund_names = []

            soup = BeautifulSoup(html, "html.parser")

            if source_type == "html_table":
                # Extract from table cells
                for table in soup.find_all("table"):
                    for row in table.find_all("tr"):
                        cells = row.find_all(["td", "th"])
                        for cell in cells:
                            text = cell.get_text(strip=True)
                            if _is_gp_name(text) and len(text) > 5:
                                fund_names.append(text)

                # Also scan for fund names in any text
                for match in _FUND_PATTERN.finditer(soup.get_text()):
                    candidate = match.group(1).strip()
                    if _is_gp_name(candidate):
                        fund_names.append(candidate)

            elif source_type == "html_links":
                # Extract from links and surrounding text
                for link in soup.find_all("a"):
                    text = link.get_text(strip=True)
                    if _is_gp_name(text) and len(text) > 5:
                        fund_names.append(text)

                # Scan page text for fund name patterns
                for match in _FUND_PATTERN.finditer(soup.get_text()):
                    candidate = match.group(1).strip()
                    if _is_gp_name(candidate):
                        fund_names.append(candidate)

            elif source_type == "text_page":
                # Pure text extraction via regex
                text = soup.get_text()
                for match in _FUND_PATTERN.finditer(text):
                    candidate = match.group(1).strip()
                    if _is_gp_name(candidate):
                        fund_names.append(candidate)

            # Record source attribution
            for fn in fund_names:
                gp = _clean_fund_name(fn)
                if gp and len(gp) > 3:
                    self._discovered_gps.setdefault(gp.lower(), set()).add(name)

            self._stats["raw_fund_names"] += len(fund_names)
            logger.info(f"  LP scraper: {name} yielded {len(fund_names)} fund names")

            # Polite delay between sources
            await asyncio.sleep(2.0)
            return fund_names

    async def discover(self) -> List[InvestorLead]:
        """
        Scrape all configured pension fund disclosures.
        Returns InvestorLead objects for discovered GPs.
        """
        print(f"  LP disclosure: scraping {len(_DISCLOSURE_SOURCES)} pension fund sources...")

        async with aiohttp.ClientSession() as session:
            tasks = [
                self._scrape_source(session, source)
                for source in _DISCLOSURE_SOURCES
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

        # Generate leads from discovered GPs
        # Load known domains to filter
        known_domains: Set[str] = set()
        from pathlib import Path
        target_file = Path("data/target_funds.txt")
        if target_file.exists():
            known_domains = {
                line.strip().lower().replace("https://", "").replace("http://", "").replace("www.", "")
                for line in target_file.read_text().splitlines()
                if line.strip()
            }

        leads = []
        seen_domains = set()

        for gp_name, sources in self._discovered_gps.items():
            domain = _fund_to_domain(gp_name)
            if not domain or domain in known_domains or domain in seen_domains:
                continue
            seen_domains.add(domain)

            lead = InvestorLead(
                name=gp_name.title(),
                fund=gp_name.title(),
                website=domain,
                source=f"pension_lp:{','.join(sorted(sources))}",
                scraped_at=datetime.now().isoformat(),
            )
            leads.append(lead)

        self._stats["unique_gps"] = len(self._discovered_gps)
        self._stats["leads_generated"] = len(leads)

        print(
            f"  LP disclosure: {self._stats['unique_gps']} unique GPs found, "
            f"{self._stats['leads_generated']} new leads "
            f"({self._stats['sources_scraped']}/{len(_DISCLOSURE_SOURCES)} sources scraped)"
        )

        return leads

    @property
    def stats(self) -> dict:
        return dict(self._stats)
