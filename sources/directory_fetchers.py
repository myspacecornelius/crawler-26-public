"""
CRAWL — VC Directory Fetchers
Fetches VC firm data from publicly accessible web directories via HTTP.
Parses JSON APIs, HTML pages, and structured data without requiring a browser.
"""

import re
import json
import asyncio
import logging
from typing import List, Optional
from datetime import datetime

import aiohttp
from bs4 import BeautifulSoup

from adapters.base import InvestorLead

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=20)


# ──────────────────────────────────────────────────
#  Helper utilities
# ──────────────────────────────────────────────────

def _make_lead(
    name: str,
    source: str,
    fund: str = "",
    website: str = "",
    location: str = "",
    focus_areas: Optional[list] = None,
    stage: str = "",
    email: str = "N/A",
    linkedin: str = "N/A",
) -> InvestorLead:
    """Build an InvestorLead with sensible defaults."""
    return InvestorLead(
        name=name.strip(),
        fund=fund.strip() or name.strip(),
        website=website.strip() or "N/A",
        location=location.strip() or "N/A",
        focus_areas=focus_areas or [],
        stage=stage.strip() or "N/A",
        email=email,
        linkedin=linkedin,
        source=source,
        scraped_at=datetime.now().isoformat(),
    )


def _deduplicate(leads: List[InvestorLead]) -> List[InvestorLead]:
    """Deduplicate leads by lowercased name + fund."""
    seen = set()
    unique = []
    for lead in leads:
        key = (lead.name.lower().strip(), lead.fund.lower().strip())
        if key not in seen:
            seen.add(key)
            unique.append(lead)
    return unique


# ──────────────────────────────────────────────────
#  Source 1: OpenVC API
# ──────────────────────────────────────────────────

async def _fetch_openvc(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch investor data from OpenVC's public API."""
    leads = []
    source = "directory:openvc"

    # OpenVC exposes a public investor search API
    api_url = "https://api.openvc.app/api/v1/investors"
    # Also try their search endpoint
    search_urls = [
        "https://openvc.app/api/investors?page=1&per_page=100",
        "https://openvc.app/api/investors?page=2&per_page=100",
        "https://openvc.app/api/investors?page=3&per_page=100",
    ]

    for url in [api_url] + search_urls:
        try:
            async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)

                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    items = data.get("data", data.get("investors", data.get("results", [])))

                for item in items:
                    if isinstance(item, dict):
                        name = item.get("name", item.get("firm_name", ""))
                        if not name:
                            continue
                        leads.append(_make_lead(
                            name=name,
                            source=source,
                            fund=item.get("firm_name", item.get("fund_name", name)),
                            website=item.get("website", item.get("url", "")),
                            location=item.get("location", item.get("hq", "")),
                            focus_areas=item.get("sectors", item.get("focus_areas", [])),
                            stage=item.get("stage", item.get("investment_stage", "")),
                        ))
        except Exception as e:
            logger.debug(f"  OpenVC {url}: {e}")

    logger.debug(f"  OpenVC: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 2: NVCA Member Directory
# ──────────────────────────────────────────────────

async def _fetch_nvca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch NVCA (National Venture Capital Association) member data."""
    leads = []
    source = "directory:nvca"

    urls = [
        "https://nvca.org/wp-json/wp/v2/members?per_page=100&page=1",
        "https://nvca.org/wp-json/wp/v2/members?per_page=100&page=2",
        "https://nvca.org/wp-json/wp/v2/members?per_page=100&page=3",
        "https://nvca.org/member-directory/",
    ]

    # Try WP REST API first
    for url in urls[:3]:
        try:
            async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)
                if isinstance(data, list):
                    for item in data:
                        name = ""
                        if isinstance(item, dict):
                            name = item.get("title", {})
                            if isinstance(name, dict):
                                name = name.get("rendered", "")
                            website = item.get("acf", {}).get("website", "") if isinstance(item.get("acf"), dict) else ""
                            if name:
                                leads.append(_make_lead(
                                    name=BeautifulSoup(str(name), "html.parser").get_text(),
                                    source=source,
                                    website=website,
                                ))
        except Exception as e:
            logger.debug(f"  NVCA API: {e}")

    # Fallback: scrape the HTML directory page
    if not leads:
        try:
            async with session.get(urls[-1], timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    # Look for member list items
                    for el in soup.select("a[href*='member'], .member-name, .directory-item, li.member"):
                        name = el.get_text(strip=True)
                        href = el.get("href", "")
                        if name and len(name) > 2 and len(name) < 100:
                            leads.append(_make_lead(name=name, source=source, website=href if href.startswith("http") else ""))
        except Exception as e:
            logger.debug(f"  NVCA HTML: {e}")

    logger.debug(f"  NVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 3: YC Top Companies (public JSON data)
# ──────────────────────────────────────────────────

async def _fetch_yc_companies(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch Y Combinator's publicly listed top companies and investors."""
    leads = []
    source = "directory:ycombinator"

    urls = [
        "https://yc-oss.github.io/api/batches/latest.json",
        "https://yc-oss.github.io/api/companies/all.json",
        "https://raw.githubusercontent.com/yc-oss/api/main/out/companies/all.json",
    ]

    for url in urls:
        try:
            async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)
                items = data if isinstance(data, list) else data.get("companies", data.get("data", []))
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name", item.get("company_name", ""))
                    if not name:
                        continue
                    leads.append(_make_lead(
                        name=name,
                        source=source,
                        fund="Y Combinator",
                        website=item.get("url", item.get("website", "")),
                        location=item.get("location", item.get("city", "")),
                        focus_areas=[item.get("vertical", "")] if item.get("vertical") else [],
                        stage=item.get("stage", item.get("batch", "")),
                    ))
                if leads:
                    break
        except Exception as e:
            logger.debug(f"  YC {url}: {e}")

    logger.debug(f"  YC Companies: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 4: European VC Directories (InvestEurope)
# ──────────────────────────────────────────────────

async def _fetch_invest_europe(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch European VC/PE directory data from InvestEurope."""
    leads = []
    source = "directory:invest_europe"

    try:
        url = "https://www.investeurope.eu/members/member-directory/"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status == 200:
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                for card in soup.select(".member-card, .member-item, .directory-listing a, tr.member-row"):
                    name_el = card.select_one("h3, h4, .name, .member-name, td:first-child")
                    loc_el = card.select_one(".location, .member-location, td:nth-child(2)")
                    link = card.get("href", "")
                    if not link and card.select_one("a"):
                        link = card.select_one("a").get("href", "")

                    name = name_el.get_text(strip=True) if name_el else card.get_text(strip=True)
                    location = loc_el.get_text(strip=True) if loc_el else ""

                    if name and len(name) > 2 and len(name) < 120:
                        leads.append(_make_lead(
                            name=name, source=source, location=location,
                            website=link if link.startswith("http") else "",
                        ))
    except Exception as e:
        logger.debug(f"  InvestEurope: {e}")

    logger.debug(f"  InvestEurope: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 5: TopVCFirms.com / VC-list aggregators
# ──────────────────────────────────────────────────

async def _fetch_vc_list_sites(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Scrape known VC list/aggregator pages that serve plain HTML."""
    leads = []
    source = "directory:vc_lists"

    list_pages = [
        {
            "url": "https://vcguide.co/firms",
            "name": "VCGuide",
        },
        {
            "url": "https://www.thevcproject.com/venture-capital-firms",
            "name": "TheVCProject",
        },
        {
            "url": "https://fundingstack.com/venture-capital-firms",
            "name": "FundingStack",
        },
    ]

    for page_info in list_pages:
        try:
            async with session.get(page_info["url"], timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                # Generic extraction: look for structured firm listings
                for sel in ["a[href*='firm'], a[href*='investor'], .firm-card, .firm-name, .company-name",
                            "table tr td:first-child a", "li a[href*='venture'], li a[href*='capital']",
                            ".card h3, .card h4, .list-item h3"]:
                    for el in soup.select(sel):
                        name = el.get_text(strip=True)
                        href = el.get("href", "")
                        if name and 2 < len(name) < 100 and not name.lower().startswith(("home", "about", "contact", "menu")):
                            leads.append(_make_lead(
                                name=name,
                                source=f"directory:{page_info['name'].lower()}",
                                website=href if href.startswith("http") else "",
                            ))
        except Exception as e:
            logger.debug(f"  {page_info['name']}: {e}")

    logger.debug(f"  VC List Sites: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 6: Signal/NFX Venture Firms List
# ──────────────────────────────────────────────────

async def _fetch_signal_nfx(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch VC data from NFX Signal's public API."""
    leads = []
    source = "directory:signal_nfx"

    # Signal lists top investors with an API
    urls = [
        "https://signal.nfx.com/api/investors?limit=200",
        "https://signal.nfx.com/api/firms?limit=200",
    ]

    for url in urls:
        try:
            async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)
                items = data if isinstance(data, list) else data.get("data", data.get("investors", data.get("firms", [])))
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name", item.get("firm_name", ""))
                    if not name:
                        continue
                    leads.append(_make_lead(
                        name=name,
                        source=source,
                        fund=item.get("firm", item.get("fund_name", name)),
                        website=item.get("website", item.get("url", "")),
                        location=item.get("location", ""),
                        focus_areas=item.get("sectors", item.get("focus", [])),
                        stage=item.get("stage", ""),
                    ))
        except Exception as e:
            logger.debug(f"  Signal NFX {url}: {e}")

    logger.debug(f"  Signal NFX: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 7: Crunchbase Open Data / Odette
# ──────────────────────────────────────────────────

async def _fetch_crunchbase_odette(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch VC data from Crunchbase's open data files and Odette mirrors."""
    leads = []
    source = "directory:crunchbase_open"

    # Crunchbase publishes some open datasets; community mirrors exist
    urls = [
        "https://raw.githubusercontent.com/notpeter/crunchbase-data/main/investors.json",
        "https://raw.githubusercontent.com/harshitsinghai77/crunchbase-vc-data/main/data.json",
    ]

    for url in urls:
        try:
            async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)
                items = data if isinstance(data, list) else data.get("data", data.get("investors", []))
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name", item.get("investor_name", item.get("organization_name", "")))
                    if not name:
                        continue
                    leads.append(_make_lead(
                        name=name,
                        source=source,
                        fund=item.get("fund_name", name),
                        website=item.get("homepage_url", item.get("website", "")),
                        location=item.get("city", item.get("location", "")),
                        focus_areas=item.get("category_list", "").split(",") if isinstance(item.get("category_list"), str) else [],
                        stage=item.get("investment_type", ""),
                    ))
        except Exception as e:
            logger.debug(f"  Crunchbase open {url}: {e}")

    logger.debug(f"  Crunchbase Open: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 8: VC4Africa (African VC directory)
# ──────────────────────────────────────────────────

async def _fetch_vc4africa(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch African VC directory from VC4Africa."""
    leads = []
    source = "directory:vc4africa"

    try:
        url = "https://vc4a.com/investors/"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for card in soup.select(".investor-card, .member-card, .listing-item, article.investor"):
                name_el = card.select_one("h2, h3, h4, .name, .title")
                loc_el = card.select_one(".location, .region, .country")
                link_el = card.select_one("a[href]")

                name = name_el.get_text(strip=True) if name_el else ""
                location = loc_el.get_text(strip=True) if loc_el else ""
                website = link_el.get("href", "") if link_el else ""

                if name and len(name) > 2:
                    leads.append(_make_lead(
                        name=name, source=source, location=location,
                        website=website if website.startswith("http") else "",
                        focus_areas=["Africa"],
                    ))
    except Exception as e:
        logger.debug(f"  VC4Africa: {e}")

    logger.debug(f"  VC4Africa: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 9: BVCA (British VC Association)
# ──────────────────────────────────────────────────

async def _fetch_bvca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch UK VC data from BVCA member directory."""
    leads = []
    source = "directory:bvca"

    try:
        url = "https://www.bvca.co.uk/Our-Members/Member-Directory"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .directory-item, .member-card, tr.member, li.member"):
                name_el = el.select_one("h3, h4, .name, a, td:first-child")
                link_el = el.select_one("a[href]")

                name = name_el.get_text(strip=True) if name_el else el.get_text(strip=True)
                href = link_el.get("href", "") if link_el else ""

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="United Kingdom",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  BVCA: {e}")

    logger.debug(f"  BVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 10: Public VC JSON datasets on GitHub
# ──────────────────────────────────────────────────

async def _fetch_github_json_datasets(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch structured VC datasets published as JSON on GitHub."""
    leads = []
    source = "directory:github_json"

    datasets = [
        {
            "url": "https://raw.githubusercontent.com/jbkunst/vc-firms/main/data/vc_firms.json",
            "name_key": "name",
            "website_key": "website",
            "location_key": "location",
        },
        {
            "url": "https://raw.githubusercontent.com/docsallover/venture-capital-firms/main/data.json",
            "name_key": "name",
            "website_key": "website",
            "location_key": "location",
        },
        {
            "url": "https://raw.githubusercontent.com/mrmrs/vc/main/data/firms.json",
            "name_key": "name",
            "website_key": "url",
            "location_key": "hq",
        },
    ]

    for ds in datasets:
        try:
            async with session.get(ds["url"], timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)
                items = data if isinstance(data, list) else data.get("firms", data.get("data", data.get("investors", [])))
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = item.get(ds["name_key"], "")
                    if not name:
                        continue
                    leads.append(_make_lead(
                        name=name,
                        source=source,
                        website=item.get(ds["website_key"], ""),
                        location=item.get(ds["location_key"], ""),
                        focus_areas=item.get("focus", item.get("sectors", item.get("categories", []))),
                        stage=item.get("stage", ""),
                    ))
        except Exception as e:
            logger.debug(f"  GitHub JSON dataset {ds['url']}: {e}")

    logger.debug(f"  GitHub JSON datasets: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 11: AVCA (African Private Equity & VC)
# ──────────────────────────────────────────────────

async def _fetch_avca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch African PE/VC data from AVCA member directory."""
    leads = []
    source = "directory:avca"

    try:
        url = "https://www.avca-africa.org/members/our-members/"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, .directory-listing li, .member-list a"):
                name_el = el.select_one("h3, h4, .name, .title")
                name = name_el.get_text(strip=True) if name_el else el.get_text(strip=True)
                href = el.get("href", "")
                if not href and el.select_one("a"):
                    href = el.select_one("a").get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="Africa",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  AVCA: {e}")

    logger.debug(f"  AVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 12: Indian VC directory (IVCA)
# ──────────────────────────────────────────────────

async def _fetch_ivca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch Indian VC data from IVCA member directory."""
    leads = []
    source = "directory:ivca"

    try:
        url = "https://www.ivca.in/member-directory"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, .directory-item, .member-listing li, article"):
                name_el = el.select_one("h2, h3, h4, .name, .title, a")
                name = name_el.get_text(strip=True) if name_el else el.get_text(strip=True)
                href = ""
                link_el = el.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="India",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  IVCA: {e}")

    logger.debug(f"  IVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 13: LAVCA (Latin America VC Association)
# ──────────────────────────────────────────────────

async def _fetch_lavca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch Latin American VC data from LAVCA member directory."""
    leads = []
    source = "directory:lavca"

    try:
        url = "https://lavca.org/members/"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, .directory-item, article, .listing-item"):
                name_el = el.select_one("h2, h3, h4, .name, .title, a")
                name = name_el.get_text(strip=True) if name_el else el.get_text(strip=True)
                href = ""
                link_el = el.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="Latin America",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  LAVCA: {e}")

    logger.debug(f"  LAVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 14: SVCA (Singapore Venture Capital Assoc.)
# ──────────────────────────────────────────────────

async def _fetch_svca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch Singapore VC data from SVCA member directory."""
    leads = []
    source = "directory:svca"

    try:
        url = "https://www.svca.org.sg/members/"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, .directory-item, li.member, article"):
                name_el = el.select_one("h2, h3, h4, .name, a")
                name = name_el.get_text(strip=True) if name_el else el.get_text(strip=True)
                href = ""
                link_el = el.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="Singapore",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  SVCA: {e}")

    logger.debug(f"  SVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 15: HKVCA (Hong Kong VC Association)
# ──────────────────────────────────────────────────

async def _fetch_hkvca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch Hong Kong VC data from HKVCA member directory."""
    leads = []
    source = "directory:hkvca"

    try:
        url = "https://www.hkvca.com.hk/en/members.html"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, .directory-item, li, article, tr"):
                name_el = el.select_one("h2, h3, h4, .name, a, td:first-child")
                name = name_el.get_text(strip=True) if name_el else ""
                href = ""
                link_el = el.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="Hong Kong",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  HKVCA: {e}")

    logger.debug(f"  HKVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 16: AVCAL (Australia Private Equity & VC)
# ──────────────────────────────────────────────────

async def _fetch_avcal(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch Australian PE/VC data from AVCAL member directory."""
    leads = []
    source = "directory:avcal"

    try:
        url = "https://www.avcal.com.au/member-directory"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, .directory-item, li.member, article"):
                name_el = el.select_one("h2, h3, h4, .name, a")
                name = name_el.get_text(strip=True) if name_el else el.get_text(strip=True)
                href = ""
                link_el = el.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="Australia",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  AVCAL: {e}")

    logger.debug(f"  AVCAL: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 17: KVCA (Korea Venture Capital Association)
# ──────────────────────────────────────────────────

async def _fetch_kvca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch Korean VC data from KVCA."""
    leads = []
    source = "directory:kvca"

    try:
        url = "https://www.kvca.or.kr/en/member/member.html"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, li, tr, article"):
                name_el = el.select_one("h2, h3, h4, .name, a, td:first-child")
                name = name_el.get_text(strip=True) if name_el else ""
                href = ""
                link_el = el.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="South Korea",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  KVCA: {e}")

    logger.debug(f"  KVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 18: ILPA (Institutional LP Association)
# ──────────────────────────────────────────────────

async def _fetch_ilpa(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch LP/GP data from ILPA member directory."""
    leads = []
    source = "directory:ilpa"

    try:
        url = "https://ilpa.org/membership/member-directory/"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, .directory-item, li, article"):
                name_el = el.select_one("h2, h3, h4, .name, a")
                name = name_el.get_text(strip=True) if name_el else el.get_text(strip=True)
                href = ""
                link_el = el.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  ILPA: {e}")

    logger.debug(f"  ILPA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 19: JVCA (Japan Venture Capital Association)
# ──────────────────────────────────────────────────

async def _fetch_jvca(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch Japanese VC data from JVCA member list."""
    leads = []
    source = "directory:jvca"

    try:
        url = "https://www.jvca.jp/en/members"
        async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
            if resp.status != 200:
                return leads
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")

            for el in soup.select(".member-item, .member-card, li, tr, article, .company"):
                name_el = el.select_one("h2, h3, h4, .name, a, td:first-child")
                name = name_el.get_text(strip=True) if name_el else ""
                href = ""
                link_el = el.select_one("a[href]")
                if link_el:
                    href = link_el.get("href", "")

                if name and 2 < len(name) < 120:
                    leads.append(_make_lead(
                        name=name, source=source,
                        location="Japan",
                        website=href if href.startswith("http") else "",
                    ))
    except Exception as e:
        logger.debug(f"  JVCA: {e}")

    logger.debug(f"  JVCA: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 20: Dealroom public data
# ──────────────────────────────────────────────────

async def _fetch_dealroom_public(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch publicly available investor data from Dealroom API."""
    leads = []
    source = "directory:dealroom"

    # Dealroom's public API may expose some investor data
    urls = [
        "https://api.dealroom.co/api/v1/investors?limit=100&offset=0",
        "https://api.dealroom.co/api/v1/investors?limit=100&offset=100",
        "https://api.dealroom.co/api/v1/investors?limit=100&offset=200",
    ]

    for url in urls:
        try:
            async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                data = await resp.json(content_type=None)
                items = data if isinstance(data, list) else data.get("items", data.get("investors", data.get("data", [])))
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name", item.get("entity_name", ""))
                    if not name:
                        continue
                    leads.append(_make_lead(
                        name=name,
                        source=source,
                        fund=item.get("name", name),
                        website=item.get("url", item.get("website", "")),
                        location=item.get("hq_city", item.get("location", "")),
                        focus_areas=item.get("tags", []),
                        stage=item.get("investor_type", ""),
                    ))
        except Exception as e:
            logger.debug(f"  Dealroom {url}: {e}")

    logger.debug(f"  Dealroom Public: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Source 21: AngelList / Wellfound Public API
# ──────────────────────────────────────────────────

async def _fetch_angellist_investors(session: aiohttp.ClientSession) -> List[InvestorLead]:
    """Fetch publicly listed investors from AngelList/Wellfound."""
    leads = []
    source = "directory:angellist"

    urls = [
        "https://api.wellfound.com/graphql",
    ]

    # Try the public startup listings which include investor data
    pages = [
        "https://wellfound.com/investors",
        "https://angel.co/investors",
    ]

    for url in pages:
        try:
            async with session.get(url, timeout=DEFAULT_TIMEOUT) as resp:
                if resp.status != 200:
                    continue
                html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")

                for el in soup.select("a[href*='/v/'], a[href*='/i/'], .investor-card, .styles_name"):
                    name = el.get_text(strip=True)
                    href = el.get("href", "")
                    if name and 2 < len(name) < 100:
                        leads.append(_make_lead(
                            name=name,
                            source=source,
                            website=href if href.startswith("http") else "",
                        ))
        except Exception as e:
            logger.debug(f"  AngelList {url}: {e}")

    logger.debug(f"  AngelList/Wellfound: {len(leads)} leads")
    return leads


# ──────────────────────────────────────────────────
#  Main aggregation function
# ──────────────────────────────────────────────────

# Registry of all fetcher functions
_FETCHERS = [
    ("OpenVC", _fetch_openvc),
    ("NVCA", _fetch_nvca),
    # ("YC Companies", _fetch_yc_companies),  # Disabled: pulls portfolio companies (startups), not VC funds
    ("InvestEurope", _fetch_invest_europe),
    ("VC List Sites", _fetch_vc_list_sites),
    ("Signal NFX", _fetch_signal_nfx),
    ("Crunchbase Open", _fetch_crunchbase_odette),
    ("VC4Africa", _fetch_vc4africa),
    ("BVCA", _fetch_bvca),
    ("GitHub JSON", _fetch_github_json_datasets),
    ("AVCA", _fetch_avca),
    ("IVCA", _fetch_ivca),
    ("LAVCA", _fetch_lavca),
    ("SVCA", _fetch_svca),
    ("HKVCA", _fetch_hkvca),
    ("AVCAL", _fetch_avcal),
    ("KVCA", _fetch_kvca),
    ("ILPA", _fetch_ilpa),
    ("JVCA", _fetch_jvca),
    ("Dealroom", _fetch_dealroom_public),
    ("AngelList", _fetch_angellist_investors),
]


async def fetch_all_directories() -> List[InvestorLead]:
    """
    Run all directory fetchers concurrently and return deduplicated results.
    Each fetcher is isolated — a failure in one does not affect others.
    """
    all_leads: List[InvestorLead] = []

    async with aiohttp.ClientSession(
        headers={"User-Agent": USER_AGENT}
    ) as session:
        tasks = []
        for name, fetcher in _FETCHERS:
            tasks.append(fetcher(session))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (name, _), result in zip(_FETCHERS, results):
            if isinstance(result, Exception):
                logger.warning(f"  Directory fetcher '{name}' failed: {result}")
            elif isinstance(result, list):
                logger.info(f"  {name}: {len(result)} leads")
                all_leads.extend(result)
            else:
                logger.debug(f"  {name}: unexpected result type {type(result)}")

    deduped = _deduplicate(all_leads)
    logger.info(f"  Directory Fetchers: {len(deduped)} unique leads from {len(_FETCHERS)} sources (before dedup: {len(all_leads)})")
    return deduped
