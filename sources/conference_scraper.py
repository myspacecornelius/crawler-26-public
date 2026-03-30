"""
CRAWL — Conference Speaker Scraper

VCs who speak at major conferences are self-selected active deployers — they wouldn't
be on stage if they weren't raising or investing. Speaker pages list name, title,
firm, headshot, and often a bio with contact info.

Scrapes speaker directories from major tech/finance/VC conferences.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, List, Set
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from adapters.base import InvestorLead

logger = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0"

# Major conferences with public speaker pages
_CONFERENCES = [
    # Tech/startup conferences
    {"name": "TechCrunch_Disrupt", "url": "https://techcrunch.com/events/tc-disrupt-2025/speakers/", "type": "card"},
    {"name": "WebSummit", "url": "https://websummit.com/speakers", "type": "card"},
    {"name": "Collision", "url": "https://collisionconf.com/speakers", "type": "card"},
    {"name": "SXSW", "url": "https://schedule.sxsw.com/speakers", "type": "card"},
    {"name": "CES", "url": "https://www.ces.tech/conference/speaker-directory", "type": "card"},
    # VC/PE specific conferences
    {"name": "SuperReturn", "url": "https://informaconnect.com/superreturn-international/speakers/", "type": "card"},
    {"name": "RAISE_Global", "url": "https://www.raiseglobal.com/speakers", "type": "card"},
    {"name": "All_In_Summit", "url": "https://www.allin.com/summit", "type": "card"},
    {"name": "Upfront_Summit", "url": "https://www.upfrontsummit.com/speakers", "type": "card"},
    # Finance conferences
    {"name": "Money2020", "url": "https://us.money2020.com/speakers", "type": "card"},
    {"name": "Finovate", "url": "https://finovate.com/speakers/", "type": "card"},
    {"name": "LendIt_Fintech", "url": "https://www.lendit.com/usa/speakers", "type": "card"},
    # Climate/impact
    {"name": "Climate_Week", "url": "https://www.climateweeknyc.org/speakers", "type": "card"},
    {"name": "VERGE", "url": "https://www.greenbiz.com/events/verge/speakers", "type": "card"},
    # Health/bio
    {"name": "JPM_Healthcare", "url": "https://www.jpmorganhealthcareconference.com/speakers", "type": "card"},
    {"name": "BIO_International", "url": "https://www.bio.org/events/bio-international-convention/speakers", "type": "card"},
]

# VC/investment role keywords
_INVESTOR_ROLES = {
    "partner", "managing", "general partner", "gp", "principal", "venture",
    "investor", "director", "founder", "ceo", "president", "chairman",
    "managing director", "md", "operating partner", "venture partner",
    "investment", "portfolio", "fund manager",
}

# VC firm name indicators
_VC_INDICATORS = {
    "capital", "ventures", "partners", "vc", "fund", "equity", "growth",
    "investment", "holdings", "advisors", "management", "associates",
}

# Common speaker card CSS patterns
_CARD_SELECTORS = [
    "[class*='speaker']",
    "[class*='Speaker']",
    "[class*='person']",
    "[class*='Person']",
    "[class*='panelist']",
    "[data-speaker]",
    "article[class*='card']",
    ".speaker-card",
    ".speaker-item",
    ".person-card",
]

_NAME_SELECTORS = [
    "h2", "h3", "h4",
    "[class*='name']", "[class*='Name']",
    "[class*='title']", "[class*='Title']",
    "strong", ".speaker-name", ".person-name",
]

_ROLE_SELECTORS = [
    "[class*='role']", "[class*='Role']",
    "[class*='title']", "[class*='Title']",
    "[class*='position']", "[class*='Position']",
    "[class*='company']", "[class*='Company']",
    "[class*='org']", "[class*='Org']",
    "p", "span", ".speaker-title", ".person-role",
]


def _is_investor(role: str, company: str) -> bool:
    """Check if a speaker appears to be an investor based on role and company."""
    combined = f"{role} {company}".lower()
    has_investor_role = any(r in combined for r in _INVESTOR_ROLES)
    has_vc_company = any(v in combined for v in _VC_INDICATORS)
    return has_investor_role or has_vc_company


def _extract_speakers_from_html(html: str, base_url: str) -> List[dict]:
    """Extract speaker info from HTML using common patterns."""
    soup = BeautifulSoup(html, "html.parser")
    speakers = []
    seen_names = set()

    # Try each card selector
    for card_sel in _CARD_SELECTORS:
        cards = soup.select(card_sel)
        if not cards:
            continue

        for card in cards:
            name = ""
            role = ""
            company = ""
            linkedin = ""

            # Extract name
            for sel in _NAME_SELECTORS:
                elem = card.select_one(sel)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 2 and len(text) < 50:
                        name = text
                        break

            if not name:
                continue

            # Extract role/company from subsequent elements
            texts = [
                el.get_text(strip=True)
                for el in card.find_all(["p", "span", "div"])
                if el.get_text(strip=True) and el.get_text(strip=True) != name
            ]
            if texts:
                role = texts[0] if len(texts) >= 1 else ""
                company = texts[1] if len(texts) >= 2 else ""
                # Sometimes role includes company: "Partner at Sequoia Capital"
                if " at " in role and not company:
                    parts = role.split(" at ", 1)
                    role = parts[0].strip()
                    company = parts[1].strip()
                elif ", " in role and not company:
                    parts = role.split(", ", 1)
                    role = parts[0].strip()
                    company = parts[1].strip()

            # Extract LinkedIn
            for link in card.find_all("a", href=True):
                if "linkedin.com/in/" in link["href"]:
                    linkedin = link["href"]
                    break

            name_key = name.lower().strip()
            if name_key not in seen_names and len(name.split()) >= 2:
                seen_names.add(name_key)
                speakers.append({
                    "name": name,
                    "role": role,
                    "company": company,
                    "linkedin": linkedin,
                })

        if speakers:
            break  # Found speakers with this selector, no need to try more

    # Fallback: scan all headings followed by text
    if not speakers:
        for heading in soup.find_all(["h2", "h3", "h4"]):
            text = heading.get_text(strip=True)
            if len(text.split()) >= 2 and len(text) < 50 and text[0].isupper():
                sibling_text = ""
                for sib in heading.find_next_siblings()[:3]:
                    t = sib.get_text(strip=True)
                    if t:
                        sibling_text = t
                        break
                name_key = text.lower()
                if name_key not in seen_names:
                    seen_names.add(name_key)
                    speakers.append({
                        "name": text,
                        "role": sibling_text,
                        "company": "",
                        "linkedin": "",
                    })

    return speakers


def _fund_to_domain(fund_name: str) -> str:
    """Derive probable website domain from a fund/company name."""
    name = re.sub(
        r'\b(llc|lp|l\.p\.|ltd|inc|corp)\b', '', fund_name, flags=re.IGNORECASE
    ).strip()
    name = re.sub(r'[,.\'"!?()&@\-]', '', name).strip()
    slug = re.sub(r'\s+', '', name).lower().strip('-')
    if len(slug) < 4:
        return ''
    return slug + '.com'


class ConferenceSpeakerScraper:
    """
    Scrapes speaker directories from tech/finance conferences to find active investors.
    """

    def __init__(self, concurrency: int = 3):
        self._sem = asyncio.Semaphore(concurrency)
        self._stats = {
            "conferences_scraped": 0,
            "conferences_failed": 0,
            "total_speakers": 0,
            "investor_speakers": 0,
            "leads_generated": 0,
        }

    async def _scrape_conference(
        self, session: aiohttp.ClientSession, conf: dict
    ) -> List[dict]:
        """Scrape a single conference speaker page."""
        async with self._sem:
            try:
                async with session.get(
                    conf["url"],
                    headers={
                        "User-Agent": _UA,
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                    timeout=aiohttp.ClientTimeout(total=20),
                    allow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        self._stats["conferences_failed"] += 1
                        logger.debug(f"  Conference {conf['name']}: HTTP {resp.status}")
                        return []

                    html = await resp.text()
                    speakers = _extract_speakers_from_html(html, conf["url"])
                    self._stats["conferences_scraped"] += 1
                    self._stats["total_speakers"] += len(speakers)

                    # Tag with source
                    for s in speakers:
                        s["source_conference"] = conf["name"]

                    logger.info(f"  Conference {conf['name']}: {len(speakers)} speakers found")
                    return speakers

            except Exception as e:
                self._stats["conferences_failed"] += 1
                logger.debug(f"  Conference {conf['name']} error: {e}")
                return []
            finally:
                await asyncio.sleep(2.0)

    async def discover(self) -> List[InvestorLead]:
        """
        Scrape all configured conference speaker pages.
        Returns InvestorLead objects for speakers identified as investors.
        """
        print(f"  Conference scraper: scanning {len(_CONFERENCES)} conferences...")

        async with aiohttp.ClientSession() as session:
            tasks = [
                self._scrape_conference(session, conf)
                for conf in _CONFERENCES
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter to investors and generate leads
        all_speakers = []
        for result in results:
            if isinstance(result, list):
                all_speakers.extend(result)

        leads = []
        seen_names = set()

        for speaker in all_speakers:
            name = speaker.get("name", "").strip()
            role = speaker.get("role", "")
            company = speaker.get("company", "")
            linkedin = speaker.get("linkedin", "")
            source_conf = speaker.get("source_conference", "")

            if not name or name.lower() in seen_names:
                continue

            # Filter to likely investors
            if not _is_investor(role, company):
                continue

            self._stats["investor_speakers"] += 1
            seen_names.add(name.lower())

            # Determine fund name and domain
            fund = company if company else ""
            domain = _fund_to_domain(fund) if fund else ""

            lead = InvestorLead(
                name=name,
                fund=fund,
                role=role,
                linkedin=linkedin if linkedin else "N/A",
                website=domain if domain else "N/A",
                source=f"conference:{source_conf}",
                scraped_at=datetime.now().isoformat(),
            )
            leads.append(lead)

        self._stats["leads_generated"] = len(leads)

        print(
            f"  Conference scraper: {self._stats['investor_speakers']} investors "
            f"from {self._stats['total_speakers']} speakers "
            f"({self._stats['conferences_scraped']} conferences, "
            f"{self._stats['leads_generated']} new leads)"
        )

        return leads

    @property
    def stats(self) -> dict:
        return dict(self._stats)
