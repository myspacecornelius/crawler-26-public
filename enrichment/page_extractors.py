"""
Fund Page Extractors — structured extraction from VC fund website pages.

Each extractor handles a specific page type (homepage, team, portfolio,
thesis/blog, news) and returns normalized data with evidence.

Extraction strategy per page (in priority order):
1. JSON-LD / structured metadata
2. Semantic HTML sections
3. Repeated card/list structures
4. Generic anchor + heading extraction
5. Raw text fallback
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

# ── Shared Utilities ──────────────────────────────────────


def _safe_text(tag: Optional[Tag], max_len: int = 500) -> str:
    """Safely extract text from a BS4 tag."""
    if not tag:
        return ""
    return tag.get_text(separator=" ", strip=True)[:max_len]


def _extract_jsonld(soup: BeautifulSoup) -> List[dict]:
    """Extract all JSON-LD objects from a page."""
    results = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def _extract_meta(soup: BeautifulSoup) -> dict:
    """Extract OpenGraph and standard meta tags."""
    meta = {}
    for tag in soup.find_all("meta"):
        prop = tag.get("property", "") or tag.get("name", "")
        content = tag.get("content", "")
        if prop and content:
            meta[prop.lower()] = content
    return meta


def _find_year(text: str) -> Optional[int]:
    """Extract most recent plausible year from text."""
    years = re.findall(r'\b(20[0-2]\d)\b', text)
    if years:
        return max(int(y) for y in years)
    return None


def _find_all_years(text: str) -> List[int]:
    """Extract all plausible years from text."""
    return sorted(set(int(y) for y in re.findall(r'\b(20[0-2]\d)\b', text)), reverse=True)


def _extract_dates(text: str) -> List[str]:
    """Extract date-like strings from text."""
    patterns = [
        r'\b\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b',
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{4}[/\-]\d{2}[/\-]\d{2}\b',
    ]
    dates = []
    for p in patterns:
        dates.extend(re.findall(p, text, re.I))
    return dates


def _match_keywords(text: str, keyword_dict: Dict[str, List[str]]) -> Dict[str, int]:
    """Match text against keyword buckets. Returns {bucket: match_count}."""
    lower = text.lower()
    results = {}
    for bucket, keywords in keyword_dict.items():
        count = sum(1 for kw in keywords if kw.lower() in lower)
        if count > 0:
            results[bucket] = count
    return results


# ── Data Models ───────────────────────────────────────────


@dataclass
class HomepageData:
    """Extracted data from a fund homepage/about page."""
    location: str = ""
    location_evidence: str = ""
    stage_keywords: List[str] = field(default_factory=list)
    sector_keywords: Dict[str, int] = field(default_factory=dict)
    geography_keywords: Dict[str, int] = field(default_factory=dict)
    check_size: str = ""
    check_size_evidence: str = ""
    strategy_snippets: List[str] = field(default_factory=list)
    description: str = ""
    source_url: str = ""


@dataclass
class TeamMember:
    """A team member extracted from a team page."""
    name: str
    role: str = ""
    bio: str = ""
    linkedin: str = ""
    email: str = ""
    decision_maker_score: int = 0
    source_url: str = ""


@dataclass
class TeamPageData:
    """Extracted data from a team page."""
    members: List[TeamMember] = field(default_factory=list)
    source_url: str = ""


@dataclass
class PortfolioCompany:
    """A portfolio company extracted from a portfolio page."""
    name: str
    url: str = ""
    sector: str = ""
    stage: str = ""
    year: Optional[int] = None
    description: str = ""
    status: str = ""  # active, exited, acquired


@dataclass
class PortfolioPageData:
    """Extracted data from portfolio pages."""
    companies: List[PortfolioCompany] = field(default_factory=list)
    has_active_exited_labels: bool = False
    source_urls: List[str] = field(default_factory=list)


@dataclass
class ThesisPost:
    """A blog/thesis post with investment theme relevance."""
    title: str
    url: str
    date: str = ""
    sector_keywords: Dict[str, int] = field(default_factory=dict)
    stage_keywords: List[str] = field(default_factory=list)
    snippet: str = ""


@dataclass
class ThesisPageData:
    """Extracted data from thesis/blog/insights pages."""
    posts: List[ThesisPost] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)


@dataclass
class NewsItem:
    """An investment announcement or news item."""
    headline: str
    url: str = ""
    date: str = ""
    company_names: List[str] = field(default_factory=list)
    verbs: List[str] = field(default_factory=list)
    snippet: str = ""


@dataclass
class NewsPageData:
    """Extracted data from news/press pages."""
    items: List[NewsItem] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)


# ── Extractors ────────────────────────────────────────────


# Default title scores for decision-maker ranking
DEFAULT_TITLE_SCORES = {
    "founding partner": 100, "founder & partner": 100,
    "co-founder": 95, "general partner": 95,
    "managing partner": 90, "senior partner": 85,
    "managing director": 80, "partner": 75,
    "venture partner": 70, "operating partner": 65,
    "director": 60, "principal": 55,
    "vice president": 50, "vp": 50,
    "senior associate": 40, "associate": 30,
    "analyst": 20, "platform": 15,
    "operations": 15, "talent": 10, "marketing": 10,
}

# Stage keywords to detect
STAGE_KEYWORDS_SET = {
    "pre-seed", "preseed", "seed", "series a", "series b", "series c",
    "series d", "series e", "growth", "late stage", "late-stage",
    "early stage", "early-stage", "expansion", "venture",
}

# Location patterns
LOCATION_PATTERNS = [
    # "Based in X" / "Headquartered in X"
    re.compile(r'(?:based|headquartered|located|offices?)\s+in\s+([A-Z][a-zA-Z\s,]+?)(?:\.|,\s*(?:with|and)|$)', re.I),
    # "X, Y" address patterns (City, State)
    re.compile(r'\b([A-Z][a-z]+(?:\s[A-Z][a-z]+)?,\s*(?:CA|NY|MA|TX|IL|WA|CO|GA|FL|PA|CT|DC|VA))\b'),
    # Major city names
    re.compile(r'\b(San Francisco|New York|Boston|Los Angeles|Chicago|Seattle|Austin|Miami|Denver|Palo Alto|Menlo Park|Mountain View)\b', re.I),
]

# Check size patterns
CHECK_SIZE_PATTERNS = [
    re.compile(r'(?:checks?(?:\s*sizes?)?|invest(?:ment)?s?)\s*(?:of|from|between|ranging)?\s*\$?([\d.]+[MmKk]?)\s*(?:to|[-–])\s*\$?([\d.]+[MmKk]?)', re.I),
    re.compile(r'\$([\d.]+[MmKk]?)\s*(?:to|[-–])\s*\$([\d.]+[MmKk]?)\s*(?:check|investment|initial)', re.I),
    re.compile(r'(?:up to|typically|average)\s+\$?([\d.]+[MmKk]?)\s*(?:per|check|investment)', re.I),
]


class HomepageExtractor:
    """Extracts fund metadata from homepage and about pages."""

    def __init__(
        self,
        sector_keywords: Optional[Dict[str, List[str]]] = None,
        geography_keywords: Optional[Dict[str, List[str]]] = None,
    ):
        self.sector_keywords = sector_keywords or {}
        self.geography_keywords = geography_keywords or {}

    def extract(self, html: str, url: str) -> HomepageData:
        """Extract homepage data from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        meta = _extract_meta(soup)
        jsonld = _extract_jsonld(soup)

        data = HomepageData(source_url=url)

        # Description from meta or JSON-LD
        data.description = (
            meta.get("og:description", "") or
            meta.get("description", "") or
            ""
        )[:500]
        for ld in jsonld:
            if ld.get("@type") == "Organization" and ld.get("description"):
                data.description = ld["description"][:500]
                break

        # Location
        data.location, data.location_evidence = self._extract_location(text, jsonld)

        # Stage keywords
        data.stage_keywords = self._extract_stages(text)

        # Sector keywords
        if self.sector_keywords:
            data.sector_keywords = _match_keywords(text, self.sector_keywords)

        # Geography keywords
        if self.geography_keywords:
            data.geography_keywords = _match_keywords(text, self.geography_keywords)

        # Check size
        data.check_size, data.check_size_evidence = self._extract_check_size(text)

        # Strategy snippets
        data.strategy_snippets = self._extract_strategy(soup)

        return data

    def _extract_location(self, text: str, jsonld: List[dict]) -> Tuple[str, str]:
        """Extract HQ location."""
        # Try JSON-LD first
        for ld in jsonld:
            addr = ld.get("address")
            if isinstance(addr, dict):
                city = addr.get("addressLocality", "")
                region = addr.get("addressRegion", "")
                if city:
                    loc = f"{city}, {region}" if region else city
                    return loc, "json-ld"
            if isinstance(addr, str) and len(addr) < 100:
                return addr, "json-ld"

        # Try regex patterns
        for pattern in LOCATION_PATTERNS:
            m = pattern.search(text)
            if m:
                return m.group(1).strip().rstrip(","), f"pattern: {m.group(0)[:80]}"

        return "", ""

    def _extract_stages(self, text: str) -> List[str]:
        """Extract mentioned funding stages."""
        lower = text.lower()
        found = []
        for stage in STAGE_KEYWORDS_SET:
            if stage in lower:
                found.append(stage.replace("-", " ").title())
        return sorted(set(found))

    def _extract_check_size(self, text: str) -> Tuple[str, str]:
        """Extract check size range."""
        for pattern in CHECK_SIZE_PATTERNS:
            m = pattern.search(text)
            if m:
                groups = m.groups()
                if len(groups) >= 2:
                    return f"${groups[0]}–${groups[1]}", m.group(0)[:100]
                elif len(groups) == 1:
                    return f"up to ${groups[0]}", m.group(0)[:100]
        return "", ""

    def _extract_strategy(self, soup: BeautifulSoup) -> List[str]:
        """Extract strategy/thesis snippets from page sections."""
        snippets = []
        strategy_keywords = {"invest", "thesis", "focus", "believe", "partner", "back", "support"}

        for tag in soup.find_all(["p", "h2", "h3", "blockquote"]):
            text = tag.get_text(strip=True)
            if not text or len(text) < 30 or len(text) > 300:
                continue
            lower = text.lower()
            if any(kw in lower for kw in strategy_keywords):
                snippets.append(text)
                if len(snippets) >= 5:
                    break

        return snippets


class TeamExtractor:
    """Extracts team members from team pages."""

    def __init__(self, title_scores: Optional[Dict[str, int]] = None):
        self.title_scores = title_scores or DEFAULT_TITLE_SCORES

    def extract(self, html: str, url: str) -> TeamPageData:
        """Extract team data from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        data = TeamPageData(source_url=url)

        # Strategy 1: JSON-LD Person entries
        jsonld = _extract_jsonld(soup)
        for ld in jsonld:
            if ld.get("@type") == "Person":
                member = TeamMember(
                    name=ld.get("name", ""),
                    role=ld.get("jobTitle", ""),
                    email=ld.get("email", ""),
                    source_url=url,
                )
                if ld.get("sameAs"):
                    urls = ld["sameAs"] if isinstance(ld["sameAs"], list) else [ld["sameAs"]]
                    for u in urls:
                        if "linkedin.com" in u:
                            member.linkedin = u
                            break
                member.decision_maker_score = self._score_title(member.role)
                if member.name:
                    data.members.append(member)

        # Strategy 2: Profile cards (div/li/article with heading + role)
        if len(data.members) < 3:
            card_members = self._extract_cards(soup, url)
            # Merge with existing (avoid duplicates by name)
            existing = {m.name.lower() for m in data.members}
            for m in card_members:
                if m.name.lower() not in existing:
                    data.members.append(m)
                    existing.add(m.name.lower())

        # Strategy 3: Simple name-role pattern in text
        if len(data.members) < 3:
            text_members = self._extract_from_text(soup, url)
            existing = {m.name.lower() for m in data.members}
            for m in text_members:
                if m.name.lower() not in existing:
                    data.members.append(m)
                    existing.add(m.name.lower())

        return data

    def _extract_cards(self, soup: BeautifulSoup, url: str) -> List[TeamMember]:
        """Extract team members from card-like structures."""
        members = []
        seen = set()

        for container in soup.find_all(["div", "li", "article", "section"]):
            card_text = container.get_text(separator=" ", strip=True)
            if len(card_text) < 5 or len(card_text) > 800:
                continue

            # Need a heading element for the name
            name_el = container.find(["h2", "h3", "h4", "h5", "strong", "b"])
            if not name_el:
                continue

            name = name_el.get_text(strip=True)
            if not self._valid_name(name):
                continue

            name_lower = name.lower()
            if name_lower in seen:
                continue
            seen.add(name_lower)

            # Find role (usually in a smaller element near the name)
            role = ""
            for role_tag in container.find_all(["p", "span", "em", "small", "div"]):
                if role_tag == name_el:
                    continue
                candidate = role_tag.get_text(strip=True)
                if candidate and len(candidate) < 80 and self._looks_like_title(candidate):
                    role = candidate
                    break

            # LinkedIn link
            linkedin = ""
            for a in container.find_all("a", href=True):
                if "linkedin.com" in a["href"]:
                    linkedin = a["href"]
                    break

            # Email from mailto
            email = ""
            for a in container.find_all("a", href=True):
                if a["href"].startswith("mailto:"):
                    email = a["href"].replace("mailto:", "").split("?")[0].strip()
                    break

            # Bio text
            bio = ""
            for p in container.find_all("p"):
                p_text = p.get_text(strip=True)
                if len(p_text) > 50:
                    bio = p_text[:300]
                    break

            member = TeamMember(
                name=name,
                role=role,
                bio=bio,
                linkedin=linkedin,
                email=email,
                decision_maker_score=self._score_title(role),
                source_url=url,
            )
            members.append(member)

        return members

    def _extract_from_text(self, soup: BeautifulSoup, url: str) -> List[TeamMember]:
        """Fallback: extract name-role pairs from headings."""
        members = []
        seen = set()

        for heading in soup.find_all(["h2", "h3", "h4"]):
            name = heading.get_text(strip=True)
            if not self._valid_name(name):
                continue
            if name.lower() in seen:
                continue
            seen.add(name.lower())

            # Try to get role from the next sibling
            role = ""
            nxt = heading.find_next_sibling()
            if nxt:
                candidate = nxt.get_text(strip=True)
                if candidate and len(candidate) < 80 and self._looks_like_title(candidate):
                    role = candidate

            members.append(TeamMember(
                name=name,
                role=role,
                decision_maker_score=self._score_title(role),
                source_url=url,
            ))

        return members

    def _score_title(self, title: str) -> int:
        """Score a job title for decision-maker relevance."""
        if not title:
            return 0
        lower = title.lower().strip()
        best = 0
        for keyword, score in self.title_scores.items():
            if keyword in lower:
                best = max(best, score)
        return best

    def _valid_name(self, text: str) -> bool:
        """Check if text looks like a person name."""
        if not text or len(text) < 3 or len(text) > 50:
            return False
        words = text.split()
        if len(words) < 2 or len(words) > 5:
            return False
        if any(c.isdigit() for c in text):
            return False
        # Must have at least one uppercase start
        if not any(w[0].isupper() for w in words if w):
            return False
        # Reject common non-name strings
        lower = text.lower()
        reject = {"team", "portfolio", "about", "contact", "news", "blog",
                  "home", "careers", "privacy", "terms", "menu", "close",
                  "read more", "learn more", "view all", "load more",
                  "our team", "our people", "investment team", "leadership team"}
        if lower in reject:
            return False
        return True

    def _looks_like_title(self, text: str) -> bool:
        """Check if text looks like a job title."""
        lower = text.lower()
        title_words = {"partner", "director", "associate", "analyst", "principal",
                       "founder", "president", "vp", "vice", "managing", "general",
                       "senior", "head", "chief", "officer", "lead", "venture",
                       "operating", "investment", "platform", "cfo", "cto", "coo",
                       "ceo", "chairman", "board"}
        return any(w in lower for w in title_words)


class PortfolioExtractor:
    """Extracts portfolio companies from portfolio pages."""

    STAGE_MAP = {
        "pre-seed": "Pre-Seed", "preseed": "Pre-Seed", "seed": "Seed",
        "series a": "Series A", "series b": "Series B", "series c": "Series C",
        "series d": "Series D", "growth": "Growth", "late stage": "Late Stage",
        "early stage": "Early Stage", "exited": "Exited", "acquired": "Acquired",
    }

    STATUS_KEYWORDS = {
        "active": ["active", "current", "portfolio"],
        "exited": ["exited", "exit", "acquired", "ipo", "public", "former"],
    }

    def extract(self, html: str, url: str, fund_name: str = "") -> PortfolioPageData:
        """Extract portfolio data from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        data = PortfolioPageData(source_urls=[url])

        # Check for active/exited sections
        text_lower = soup.get_text(separator=" ").lower()
        data.has_active_exited_labels = any(
            w in text_lower for w in ["exited", "former", "previous investments", "realized"]
        )

        # Strategy 1: Structured cards
        data.companies = self._extract_cards(soup, url)

        # Strategy 2: Logo grid fallback
        if len(data.companies) < 5:
            logos = self._extract_logos(soup, url)
            existing = {c.name.lower() for c in data.companies}
            for c in logos:
                if c.name.lower() not in existing:
                    data.companies.append(c)

        # Strategy 3: Link list fallback
        if len(data.companies) < 5:
            links = self._extract_links(soup, url)
            existing = {c.name.lower() for c in data.companies}
            for c in links:
                if c.name.lower() not in existing:
                    data.companies.append(c)

        return data

    def _extract_cards(self, soup: BeautifulSoup, url: str) -> List[PortfolioCompany]:
        """Extract from structured card elements."""
        companies = []
        seen = set()

        for container in soup.find_all(["div", "li", "article", "a"]):
            card_text = container.get_text(separator=" ", strip=True)
            if len(card_text) > 500 or len(card_text) < 3:
                continue

            headings = container.find_all(["h2", "h3", "h4", "h5", "strong"])
            if len(headings) != 1:
                continue
            name_el = headings[0]
            name = name_el.get_text(strip=True)
            if not self._valid_company(name) or name.lower() in seen:
                continue
            seen.add(name.lower())

            # Extract metadata
            sector = self._find_sector(container)
            stage = self._find_stage(card_text)
            year = _find_year(card_text)
            comp_url = self._find_url(container, url)
            status = self._find_status(container)
            desc = ""
            for p in container.find_all("p"):
                t = p.get_text(strip=True)
                if len(t) > 20 and len(t) < 300:
                    desc = t
                    break

            companies.append(PortfolioCompany(
                name=name, url=comp_url, sector=sector, stage=stage,
                year=year, description=desc, status=status,
            ))

        return companies

    def _extract_logos(self, soup: BeautifulSoup, url: str) -> List[PortfolioCompany]:
        """Extract from logo/image grids."""
        companies = []
        seen = set()

        for img in soup.find_all("img"):
            name = (img.get("alt", "") or img.get("title", "")).strip()
            if not name:
                continue
            # Clean "X logo" patterns
            name = re.sub(r'\s*logo\s*$', '', name, flags=re.I).strip()
            if not self._valid_company(name) or name.lower() in seen:
                continue
            seen.add(name.lower())

            comp_url = ""
            parent = img.parent
            if parent and parent.name == "a" and parent.get("href"):
                comp_url = urljoin(url, parent["href"])

            companies.append(PortfolioCompany(name=name, url=comp_url))

        return companies

    def _extract_links(self, soup: BeautifulSoup, url: str) -> List[PortfolioCompany]:
        """Extract from link lists (external links = portfolio companies)."""
        companies = []
        seen = set()
        base_domain = urlparse(url).netloc.lower()

        for a in soup.find_all("a", href=True):
            href = a["href"]
            full = urljoin(url, href)
            parsed = urlparse(full)
            if parsed.netloc.lower() == base_domain:
                continue
            text = a.get_text(strip=True)
            if text and self._valid_company(text) and text.lower() not in seen:
                seen.add(text.lower())
                companies.append(PortfolioCompany(name=text, url=full))

        return companies

    def _valid_company(self, text: str) -> bool:
        """Check if text looks like a company name."""
        if not text or len(text) < 2 or len(text) > 80:
            return False
        lower = text.lower()
        reject = {
            "portfolio", "companies", "investments", "our portfolio",
            "back to top", "learn more", "read more", "view all",
            "see all", "load more", "contact us", "about us",
            "privacy policy", "terms of service", "cookie policy",
            "home", "blog", "news", "team", "careers",
            "menu", "close", "search", "login", "sign up",
            "background", "hero", "banner", "icon", "placeholder",
            "logo", "image", "photo", "avatar", "thumbnail",
        }
        if lower in reject:
            return False
        if len(text.split()) > 10:
            return False
        return True

    def _find_sector(self, container: Tag) -> str:
        """Find sector label in a card."""
        for cls in ["sector", "category", "tag", "industry", "vertical"]:
            for el in container.find_all(True, class_=re.compile(cls, re.I)):
                text = el.get_text(strip=True)
                if text and len(text) < 60:
                    return text
        return ""

    def _find_stage(self, text: str) -> str:
        """Detect funding stage from text."""
        lower = text.lower()
        for kw, label in self.STAGE_MAP.items():
            if kw in lower:
                return label
        return ""

    def _find_url(self, container: Tag, page_url: str) -> str:
        """Find company URL from card links."""
        base_domain = urlparse(page_url).netloc.lower()
        for a in container.find_all("a", href=True):
            href = a["href"]
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            full = urljoin(page_url, href)
            if urlparse(full).netloc.lower() != base_domain:
                return full
        for a in container.find_all("a", href=True):
            href = a["href"]
            if href.startswith("#") or href.startswith("javascript:"):
                continue
            return urljoin(page_url, href)
        return ""

    def _find_status(self, container: Tag) -> str:
        """Detect if company is marked as active or exited."""
        text = container.get_text(separator=" ").lower()
        for status, keywords in self.STATUS_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return status
        # Check parent/ancestor section headings
        parent = container.parent
        for _ in range(3):
            if parent is None:
                break
            heading = parent.find(["h1", "h2", "h3"])
            if heading:
                h_text = heading.get_text().lower()
                for status, keywords in self.STATUS_KEYWORDS.items():
                    if any(kw in h_text for kw in keywords):
                        return status
            parent = parent.parent
        return ""


class ThesisExtractor:
    """Extracts blog/thesis posts and investment theme signals."""

    def __init__(self, sector_keywords: Optional[Dict[str, List[str]]] = None):
        self.sector_keywords = sector_keywords or {}

    def extract(self, html: str, url: str) -> ThesisPageData:
        """Extract thesis/blog data from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        data = ThesisPageData(source_urls=[url])

        # Strategy 1: Article/post cards
        for container in soup.find_all(["article", "div", "li"]):
            card_text = container.get_text(separator=" ", strip=True)
            if len(card_text) > 2000 or len(card_text) < 20:
                continue

            title_el = container.find(["h2", "h3", "h4", "a"])
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            if not title or len(title) > 200 or len(title) < 10:
                continue

            # Get link
            post_url = ""
            if title_el.name == "a" and title_el.get("href"):
                post_url = urljoin(url, title_el["href"])
            else:
                a = container.find("a", href=True)
                if a:
                    post_url = urljoin(url, a["href"])

            # Date
            date = ""
            time_el = container.find("time")
            if time_el:
                date = time_el.get("datetime", "") or time_el.get_text(strip=True)
            if not date:
                dates = _extract_dates(card_text[:200])
                if dates:
                    date = dates[0]

            # Keywords
            sector_kw = _match_keywords(card_text, self.sector_keywords) if self.sector_keywords else {}
            lower = card_text.lower()
            stages = [s.title() for s in STAGE_KEYWORDS_SET if s in lower]

            # Snippet
            snippet = ""
            for p in container.find_all("p"):
                t = p.get_text(strip=True)
                if len(t) > 30:
                    snippet = t[:200]
                    break

            post = ThesisPost(
                title=title,
                url=post_url,
                date=date,
                sector_keywords=sector_kw,
                stage_keywords=stages,
                snippet=snippet,
            )
            data.posts.append(post)

            if len(data.posts) >= 20:
                break

        return data


class NewsExtractor:
    """Extracts investment announcements from news/press pages."""

    INVESTMENT_VERBS = [
        "invested", "led", "co-led", "participated", "backed",
        "announced", "closed", "raised", "funded", "seed round",
        "series", "joined", "co-invested", "invested in",
        "portfolio company",
    ]

    def extract(self, html: str, url: str) -> NewsPageData:
        """Extract news items from HTML."""
        soup = BeautifulSoup(html, "html.parser")
        data = NewsPageData(source_urls=[url])

        for container in soup.find_all(["article", "div", "li"]):
            card_text = container.get_text(separator=" ", strip=True)
            if len(card_text) > 2000 or len(card_text) < 15:
                continue

            title_el = container.find(["h2", "h3", "h4", "a"])
            if not title_el:
                continue
            headline = title_el.get_text(strip=True)
            if not headline or len(headline) > 200 or len(headline) < 10:
                continue

            # Check for investment-related content
            combined = (headline + " " + card_text).lower()
            matched_verbs = [v for v in self.INVESTMENT_VERBS if v in combined]
            if not matched_verbs:
                continue

            # URL
            item_url = ""
            if title_el.name == "a" and title_el.get("href"):
                item_url = urljoin(url, title_el["href"])
            else:
                a = container.find("a", href=True)
                if a:
                    item_url = urljoin(url, a["href"])

            # Date
            date = ""
            time_el = container.find("time")
            if time_el:
                date = time_el.get("datetime", "") or time_el.get_text(strip=True)
            if not date:
                dates = _extract_dates(card_text[:200])
                if dates:
                    date = dates[0]

            # Company names (capitalized multi-word strings near investment verbs)
            company_names = self._extract_company_names(card_text)

            data.items.append(NewsItem(
                headline=headline,
                url=item_url,
                date=date,
                company_names=company_names,
                verbs=matched_verbs[:3],
                snippet=card_text[:200],
            ))

            if len(data.items) >= 20:
                break

        return data

    def _extract_company_names(self, text: str) -> List[str]:
        """Extract likely company names from investment text."""
        # Pattern: capitalized words/phrases near investment verbs
        names = []
        # Look for patterns like "invested in CompanyName" or "backed CompanyName"
        patterns = [
            re.compile(r'(?:invested in|backed|led .* in|announced .* in)\s+([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){0,3})', re.I),
            re.compile(r'([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+){0,2})\s+(?:raises?|closes?|secures?|announces?)', re.I),
        ]
        for p in patterns:
            for m in p.finditer(text):
                name = m.group(1).strip()
                if len(name) > 2 and name.lower() not in {"the", "our", "this", "that", "new"}:
                    names.append(name)
        return names[:5]
