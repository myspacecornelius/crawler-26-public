"""
CRAWL — GitHub VC List Fetcher
Fetches curated VC lists from known GitHub repositories via raw HTTP (no browser).
Parses markdown tables, bullet lists, and CSV/JSON data files to extract VC names
and websites.
"""

import csv
import io
import json
import re
import logging
from typing import List
from datetime import datetime

import aiohttp

from adapters.base import InvestorLead

logger = logging.getLogger(__name__)

# Known GitHub raw URLs containing curated VC lists
GITHUB_SOURCES = [
    # ── Original sources ──
    {
        "name": "awesome-vc (mckaywrigley)",
        "url": "https://raw.githubusercontent.com/mckaywrigley/awesome-vc/main/README.md",
    },
    {
        "name": "awesome-venture-capital",
        "url": "https://raw.githubusercontent.com/byjonah/awesome-venture-capital/main/README.md",
    },
    {
        "name": "vc-firms (jbkunst)",
        "url": "https://raw.githubusercontent.com/jbkunst/vc-firms/main/README.md",
    },
    # ── Expanded sources ──
    {
        "name": "awesome-vc-list (govc)",
        "url": "https://raw.githubusercontent.com/govc/awesome-vc/main/README.md",
    },
    {
        "name": "startup-investors (codingforentrepreneurs)",
        "url": "https://raw.githubusercontent.com/codingforentrepreneurs/startup-investors/main/README.md",
    },
    {
        "name": "global-vc-list (dbreunig)",
        "url": "https://raw.githubusercontent.com/dbreunig/venture-capital/master/README.md",
    },
    {
        "name": "european-vc-list",
        "url": "https://raw.githubusercontent.com/nicbou/european-vc/main/README.md",
    },
    {
        "name": "awesome-crypto-vc",
        "url": "https://raw.githubusercontent.com/nicklockwood/awesome-crypto-vc/main/README.md",
    },
    {
        "name": "awesome-climate-vc",
        "url": "https://raw.githubusercontent.com/elainesfolder/awesome-climate-vc/main/README.md",
    },
    {
        "name": "vc-list-usa (founder-resources)",
        "url": "https://raw.githubusercontent.com/founder-resources/vc-database/main/README.md",
    },
    {
        "name": "seed-vc-list",
        "url": "https://raw.githubusercontent.com/seed-vc/awesome-seed-vc/main/README.md",
    },
    {
        "name": "women-led-vc",
        "url": "https://raw.githubusercontent.com/gogirl-vc/women-led-vc/main/README.md",
    },
    # ── Additional sources for scale ──
    {
        "name": "awesome-startups-investors",
        "url": "https://raw.githubusercontent.com/ahmadnassri/awesome-startup-resources/master/README.md",
    },
    {
        "name": "vc-firms-hiring",
        "url": "https://raw.githubusercontent.com/samhodge-sern/vc-firms-hiring/main/README.md",
    },
    {
        "name": "awesome-indie-vc",
        "url": "https://raw.githubusercontent.com/tunapanda/awesome-alternative-funding/master/README.md",
    },
    {
        "name": "awesome-fintech",
        "url": "https://raw.githubusercontent.com/nicholasren/awesome-fintech/main/README.md",
    },
    {
        "name": "latam-vc-list",
        "url": "https://raw.githubusercontent.com/allstartups/latam-vc-list/main/README.md",
    },
    {
        "name": "africa-vc-list",
        "url": "https://raw.githubusercontent.com/africa-vc/awesome-african-vc/main/README.md",
    },
    {
        "name": "india-vc-list",
        "url": "https://raw.githubusercontent.com/indian-vc/awesome-indian-vc/main/README.md",
    },
    {
        "name": "southeast-asia-vc",
        "url": "https://raw.githubusercontent.com/nicklockwood/awesome-sea-vc/main/README.md",
    },
    {
        "name": "climate-tech-vc",
        "url": "https://raw.githubusercontent.com/climateaction-tech/awesome-climate-resources/main/README.md",
    },
    {
        "name": "health-tech-vc",
        "url": "https://raw.githubusercontent.com/kakoni/awesome-healthcare/master/README.md",
    },
    {
        "name": "deep-tech-vc",
        "url": "https://raw.githubusercontent.com/nicklockwood/awesome-deep-tech-vc/main/README.md",
    },
    {
        "name": "web3-investors",
        "url": "https://raw.githubusercontent.com/nicklockwood/awesome-web3-vc/main/README.md",
    },
    # ── CSV / JSON data files (high-yield structured data) ──
    {
        "name": "VentureCapital-CSV (CharlesCreativeContent)",
        "url": "https://raw.githubusercontent.com/CharlesCreativeContent/VentureCapital/main/VentureCapital.csv",
    },
    {
        "name": "vc-database-investors-CSV (notliam)",
        "url": "https://raw.githubusercontent.com/notliam/vc-database/main/investors.csv",
    },
    {
        "name": "investor-list-CSV (macroaxis)",
        "url": "https://raw.githubusercontent.com/macroaxis/investor-list/main/investors.csv",
    },
    {
        "name": "vc-list-JSON (alasdairrae)",
        "url": "https://raw.githubusercontent.com/alasdairrae/wpc/master/files/vc-list.json",
    },
    {
        "name": "startup-funding-investors-CSV (rfordce)",
        "url": "https://raw.githubusercontent.com/rfordce/startup-funding/main/investors.csv",
    },
    {
        "name": "venture-capital-firms-CSV (datasets)",
        "url": "https://raw.githubusercontent.com/datasets/venture-capital/main/data/vc_firms.csv",
    },
    {
        "name": "awesome-vc-firms-JSON (vcguide)",
        "url": "https://raw.githubusercontent.com/vcguide/vc-firms/main/firms.json",
    },
    {
        "name": "techstars-network-CSV",
        "url": "https://raw.githubusercontent.com/washingtonpost/data-investors/main/investors.csv",
    },
    {
        "name": "global-investors-CSV (openvc-data)",
        "url": "https://raw.githubusercontent.com/openvc-data/investors/main/global_investors.csv",
    },
    {
        "name": "vc-firms-airtable-export-CSV",
        "url": "https://raw.githubusercontent.com/founding-0/vc-list/main/vc_firms.csv",
    },
    # ── Additional markdown sources ──
    {
        "name": "awesome-investors (dvassallo)",
        "url": "https://raw.githubusercontent.com/dvassallo/awesome-investors/main/README.md",
    },
    {
        "name": "vc-landscape (nxpkg)",
        "url": "https://raw.githubusercontent.com/nxpkg/vc-landscape/main/README.md",
    },
    {
        "name": "pre-seed-funds (harshjv)",
        "url": "https://raw.githubusercontent.com/harshjv/pre-seed-vc/main/README.md",
    },
    {
        "name": "awesome-angels (torchnyu)",
        "url": "https://raw.githubusercontent.com/torchnyu/awesome-angels/main/README.md",
    },
    {
        "name": "defense-tech-vc",
        "url": "https://raw.githubusercontent.com/dod-jedi/defense-tech-investors/main/README.md",
    },
    {
        "name": "corporate-venture-arms",
        "url": "https://raw.githubusercontent.com/corporate-vc/cvc-list/main/README.md",
    },
    {
        "name": "solo-gp-funds",
        "url": "https://raw.githubusercontent.com/solo-gp/fund-list/main/README.md",
    },
    {
        "name": "micro-vc-list (versatile)",
        "url": "https://raw.githubusercontent.com/versatile-vc/micro-vc/main/README.md",
    },
    {
        "name": "emerging-managers-list",
        "url": "https://raw.githubusercontent.com/emergingmanager/funds/main/README.md",
    },
    {
        "name": "impact-investing-funds",
        "url": "https://raw.githubusercontent.com/impactvc/impact-funds/main/README.md",
    },
    {
        "name": "family-office-list",
        "url": "https://raw.githubusercontent.com/familyoffice-data/fo-list/main/README.md",
    },
    {
        "name": "vc-twitter-list (tpawlowski)",
        "url": "https://raw.githubusercontent.com/tpawlowski/vc-twitter/main/README.md",
    },
    {
        "name": "funded-startups-investors-JSON",
        "url": "https://raw.githubusercontent.com/crunchbase-data/investors/main/investors.json",
    },
    {
        "name": "vc-database-europe-CSV",
        "url": "https://raw.githubusercontent.com/eu-vc-data/european-vcs/main/investors.csv",
    },
]


def _parse_csv_data(text: str) -> List[dict]:
    """Parse CSV files with flexible column name matching for investor data."""
    results = []
    try:
        reader = csv.DictReader(io.StringIO(text))
        if reader.fieldnames is None:
            return results

        # Normalise header names for fuzzy matching
        headers_lower = {h.lower().strip(): h for h in reader.fieldnames if h}

        def _find_col(*candidates):
            for c in candidates:
                for h_lower, h_orig in headers_lower.items():
                    if c in h_lower:
                        return h_orig
            return None

        name_col    = _find_col("firm", "name", "company", "fund", "organization", "org")
        website_col = _find_col("website", "url", "site", "web", "homepage", "domain")
        email_col   = _find_col("email", "mail", "contact")
        linkedin_col = _find_col("linkedin")
        location_col = _find_col("location", "city", "hq", "region", "country")
        stage_col   = _find_col("stage", "phase", "round")
        focus_col   = _find_col("focus", "sector", "vertical", "thesis", "area")

        if not name_col:
            return results

        for row in reader:
            name = (row.get(name_col) or "").strip()
            if not name or len(name) < 2:
                continue
            website = (row.get(website_col) or "").strip() if website_col else ""
            # Normalise website: ensure it starts with http
            if website and not website.startswith("http"):
                website = f"https://{website}"
            results.append({
                "name": name,
                "website": website,
                "email": (row.get(email_col) or "").strip() if email_col else "",
                "linkedin": (row.get(linkedin_col) or "").strip() if linkedin_col else "",
                "location": (row.get(location_col) or "").strip() if location_col else "",
                "stage": (row.get(stage_col) or "").strip() if stage_col else "",
                "focus_areas": (row.get(focus_col) or "").strip() if focus_col else "",
            })
    except Exception as exc:
        logger.debug(f"  CSV parse error: {exc}")
    return results


def _parse_json_data(text: str) -> List[dict]:
    """Parse JSON arrays or objects containing investor data."""
    results = []
    try:
        data = json.loads(text)
        # Handle both top-level list and dict with a list value
        if isinstance(data, dict):
            for key in ("firms", "investors", "funds", "data", "results", "items"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                # Try the first list value
                for v in data.values():
                    if isinstance(v, list):
                        data = v
                        break

        if not isinstance(data, list):
            return results

        def _get(obj, *keys):
            for k in keys:
                for ok in obj:
                    if ok.lower().replace("_", "").replace("-", "") == k.replace("_", "").replace("-", ""):
                        return (obj[ok] or "").strip() if isinstance(obj[ok], str) else ""
            return ""

        for item in data:
            if not isinstance(item, dict):
                continue
            name = _get(item, "name", "firmname", "firm", "company", "fund", "organization")
            if not name:
                continue
            website = _get(item, "website", "url", "site", "homepage", "web")
            if website and not website.startswith("http"):
                website = f"https://{website}"
            results.append({
                "name": name,
                "website": website,
                "email": _get(item, "email", "mail"),
                "linkedin": _get(item, "linkedin", "linkedinurl"),
                "location": _get(item, "location", "city", "hq", "country"),
                "stage": _get(item, "stage", "phase"),
                "focus_areas": _get(item, "focus", "sector", "vertical", "thesis"),
            })
    except Exception as exc:
        logger.debug(f"  JSON parse error: {exc}")
    return results


def _parse_markdown_links(text: str) -> List[dict]:
    """Extract [name](url) patterns from markdown text."""
    # Match markdown links: [Name](https://example.com)
    pattern = r'\[([^\]]+)\]\((https?://[^\)]+)\)'
    matches = re.findall(pattern, text)
    results = []
    for name, url in matches:
        name = name.strip()
        # Skip navigation/badge links
        if len(name) < 3 or name.lower() in ("link", "website", "here", "source"):
            continue
        if "badge" in url or "shields.io" in url or "github.com" in url:
            continue
        results.append({"name": name, "website": url})
    return results


def _parse_markdown_table(text: str) -> List[dict]:
    """Extract rows from markdown tables with Name and URL columns."""
    results = []
    lines = text.split("\n")
    header_idx = -1
    name_col = -1
    url_col = -1

    for i, line in enumerate(lines):
        if "|" in line and ("name" in line.lower() or "firm" in line.lower() or "fund" in line.lower()):
            cols = [c.strip().lower() for c in line.split("|")]
            for j, col in enumerate(cols):
                if any(kw in col for kw in ("name", "firm", "fund", "company")):
                    name_col = j
                if any(kw in col for kw in ("url", "website", "link", "site")):
                    url_col = j
            if name_col >= 0:
                header_idx = i
                break

    if header_idx < 0:
        return results

    for line in lines[header_idx + 2:]:  # skip header + separator
        if "|" not in line:
            break
        cols = [c.strip() for c in line.split("|")]
        if name_col < len(cols):
            name = cols[name_col].strip()
            # Extract URL from markdown link in cell
            link_match = re.search(r'\[([^\]]*)\]\(([^\)]+)\)', name)
            if link_match:
                name = link_match.group(1)
                url = link_match.group(2)
            elif url_col >= 0 and url_col < len(cols):
                url = cols[url_col].strip()
                link_match = re.search(r'\[([^\]]*)\]\(([^\)]+)\)', url)
                if link_match:
                    url = link_match.group(2)
            else:
                url = ""

            if name and len(name) > 2:
                results.append({"name": name, "website": url if url.startswith("http") else ""})

    return results


def _parse_bullet_list(text: str) -> List[dict]:
    """Extract VC entries from bullet-point lists with links."""
    results = []
    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith(("-", "*", "+")):
            continue
        # Try to find a markdown link
        link_match = re.search(r'\[([^\]]+)\]\((https?://[^\)]+)\)', line)
        if link_match:
            name = link_match.group(1).strip()
            url = link_match.group(2).strip()
            if len(name) > 2 and "badge" not in url and "shields.io" not in url:
                results.append({"name": name, "website": url})
    return results


async def _fetch_and_parse(session: aiohttp.ClientSession, source: dict) -> List[InvestorLead]:
    """Fetch a single GitHub source and parse into leads."""
    leads = []
    url_lower = source["url"].lower()
    try:
        async with session.get(source["url"], timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.debug(f"  GitHub {source['name']}: HTTP {resp.status}")
                return leads

            text = await resp.text()

            # Dispatch parser based on file extension
            entries = []
            if url_lower.endswith(".csv"):
                entries = _parse_csv_data(text)
            elif url_lower.endswith(".json"):
                entries = _parse_json_data(text)
            else:
                # Default: markdown (try all three parsers)
                entries.extend(_parse_markdown_table(text))
                entries.extend(_parse_markdown_links(text))
                entries.extend(_parse_bullet_list(text))

            # Dedup within this source
            seen = set()
            for entry in entries:
                key = entry["name"].lower().strip()
                if key in seen:
                    continue
                seen.add(key)

                leads.append(InvestorLead(
                    name=entry["name"],
                    fund=entry["name"],
                    website=entry.get("website", "N/A") or "N/A",
                    email=entry.get("email", "") or "",
                    location=entry.get("location", "") or "",
                    stage=entry.get("stage", "") or "",
                    focus_areas=[s.strip() for s in entry.get("focus_areas", "").split(",") if s.strip()],
                    source=f"github:{source['name']}",
                    scraped_at=datetime.now().isoformat(),
                ))

            logger.debug(f"  GitHub {source['name']}: {len(leads)} entries parsed")

    except Exception as e:
        logger.debug(f"  GitHub {source['name']}: fetch failed: {e}")

    return leads


async def fetch_github_vc_lists() -> List[InvestorLead]:
    """Fetch VC lists from all known GitHub sources."""
    all_leads = []

    async with aiohttp.ClientSession(
        headers={"User-Agent": "Mozilla/5.0 (compatible; CrawlBot/1.0)"}
    ) as session:
        tasks = [_fetch_and_parse(session, src) for src in GITHUB_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                all_leads.extend(result)

    logger.info(f"  🐙  GitHub VC lists: {len(all_leads)} total entries from {len(GITHUB_SOURCES)} sources")
    return all_leads


# Need asyncio for gather
import asyncio
