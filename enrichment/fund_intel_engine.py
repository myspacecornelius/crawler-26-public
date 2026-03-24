"""
Fund Intelligence Engine — orchestrates site discovery, page extraction,
and rule-based inference for VC fund enrichment.

This is the main entry point for the fund intelligence enrichment pipeline.
It coordinates:
1. Site discovery (find relevant pages)
2. Page fetching (HTTP with optional Playwright fallback)
3. Structured extraction (homepage, team, portfolio, thesis, news)
4. Rule-based inference (active_status, lead_follow, sector_fit, etc.)
5. Merging results into InvestorLead objects

Usage:
    from enrichment.fund_intel_engine import FundIntelEngine
    engine = FundIntelEngine()
    leads = await engine.enrich_batch(leads)
"""

import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

import aiohttp
import yaml

from enrichment.site_discoverer import SiteDiscoverer, SiteDiscoveryResult
from enrichment.page_extractors import (
    HomepageExtractor, TeamExtractor, PortfolioExtractor,
    ThesisExtractor, NewsExtractor,
    HomepageData, TeamPageData, PortfolioPageData,
    ThesisPageData, NewsPageData, TeamMember,
)

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "fund_intel.yaml"


def _load_config() -> dict:
    """Load fund intelligence config from YAML."""
    try:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"Failed to load fund_intel.yaml: {e}")
    return {}


# ── Fund-Level Intelligence Result ────────────────────────

@dataclass
class FundIntelResult:
    """Complete intelligence result for a single fund domain."""
    domain: str
    firm_domain: str = ""

    # Portfolio
    portfolio_companies: List[str] = field(default_factory=list)
    portfolio_source_url: str = ""
    portfolio_count: int = 0
    recent_investments: List[str] = field(default_factory=list)
    recent_investments_source_urls: List[str] = field(default_factory=list)
    last_investment_date: str = ""

    # Geography
    hq_geography: str = ""
    hq_geography_evidence: str = ""
    geography_investment_signals: Dict[str, int] = field(default_factory=dict)

    # Strategy
    stage: List[str] = field(default_factory=list)
    sector_fit_keywords: Dict[str, int] = field(default_factory=dict)
    sector_fit_keyword_counts: int = 0
    business_model_keywords: Dict[str, int] = field(default_factory=dict)
    thesis_evidence_url: str = ""
    thesis_evidence_title: str = ""
    check_size_estimate: str = ""
    check_size_evidence: str = ""

    # Team
    decision_maker_names: List[str] = field(default_factory=list)
    decision_maker_roles: List[str] = field(default_factory=list)
    decision_maker_source_url: str = ""
    team_size: int = 0

    # Inferred status
    active_status: str = "unknown"  # active, possibly_active, stale, unknown
    active_status_confidence: float = 0.0
    active_status_evidence: List[str] = field(default_factory=list)

    # Lead/follow
    lead_follow_preference: str = "unknown"  # lead, lead_or_follow, mostly_follow, unknown
    lead_follow_confidence: float = 0.0
    lead_follow_evidence: List[str] = field(default_factory=list)

    # Board signals
    board_seat_signals: List[str] = field(default_factory=list)

    # Strategy snippets
    strategy_snippets: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to dict with JSON for complex fields."""
        d = {}
        for k, v in asdict(self).items():
            if isinstance(v, (dict, list)):
                d[k] = json.dumps(v) if v else ""
            else:
                d[k] = v
        return d


# ── Rule-Based Inference Engine ───────────────────────────

class InferenceEngine:
    """Deterministic scoring and inference from extracted data."""

    def __init__(self, config: dict):
        self.config = config
        recency = config.get("recency", {})
        self.recent_months = recency.get("recent", 12)
        self.active_months = recency.get("active", 24)
        self.stale_months = recency.get("stale", 36)
        self.lead_evidence = config.get("lead_evidence", {})

    def infer_active_status(
        self,
        portfolio: PortfolioPageData,
        thesis: ThesisPageData,
        news: NewsPageData,
    ) -> tuple:
        """
        Infer fund active status from evidence.
        Returns (status, confidence, evidence_list).
        """
        evidence = []
        score = 0.0
        now = datetime.now()

        # Check portfolio investment years
        if portfolio and portfolio.companies:
            years = [c.year for c in portfolio.companies if c.year]
            if years:
                max_year = max(years)
                age_months = (now.year - max_year) * 12
                if age_months <= self.recent_months:
                    score += 0.4
                    evidence.append(f"portfolio investment in {max_year}")
                elif age_months <= self.active_months:
                    score += 0.2
                    evidence.append(f"portfolio investment in {max_year} (not recent)")

        # Check thesis/blog post dates
        if thesis and thesis.posts:
            for post in thesis.posts[:5]:
                if post.date:
                    years = re.findall(r'(20[0-2]\d)', post.date)
                    if years:
                        post_year = int(max(years))
                        age_months = (now.year - post_year) * 12
                        if age_months <= self.recent_months:
                            score += 0.2
                            evidence.append(f"blog post '{post.title[:50]}' dated {post.date}")
                            break

        # Check news dates
        if news and news.items:
            for item in news.items[:5]:
                if item.date:
                    years = re.findall(r'(20[0-2]\d)', item.date)
                    if years:
                        news_year = int(max(years))
                        age_months = (now.year - news_year) * 12
                        if age_months <= self.recent_months:
                            score += 0.3
                            evidence.append(f"news: '{item.headline[:50]}' dated {item.date}")
                            break

        # Portfolio count signal
        if portfolio and len(portfolio.companies) >= 5:
            score += 0.1
            evidence.append(f"{len(portfolio.companies)} portfolio companies listed")

        # Determine status
        if score >= 0.5:
            status = "active"
        elif score >= 0.2:
            status = "possibly_active"
        elif evidence:
            status = "stale"
        else:
            status = "unknown"

        confidence = min(score, 1.0)
        return status, confidence, evidence

    def infer_lead_follow(
        self,
        homepage: HomepageData,
        news: NewsPageData,
    ) -> tuple:
        """
        Infer lead/follow preference from text evidence.
        Returns (preference, confidence, evidence_list).
        """
        evidence = []
        lead_score = 0.0
        follow_score = 0.0

        lead_phrases = self.lead_evidence.get("lead", [
            "we lead", "lead investor", "led seed", "led the round",
            "lead rounds", "we typically lead", "led series",
            "lead or co-lead", "board seat", "we take board",
        ])
        follow_phrases = self.lead_evidence.get("follow", [
            "we participate", "participated in", "co-invested",
            "follow-on", "syndicate", "we join", "alongside",
        ])

        # Check homepage strategy snippets
        if homepage:
            full_text = " ".join(homepage.strategy_snippets).lower()
            full_text += " " + homepage.description.lower()
            for phrase in lead_phrases:
                if phrase.lower() in full_text:
                    lead_score += 0.3
                    evidence.append(f"homepage: '{phrase}'")
            for phrase in follow_phrases:
                if phrase.lower() in full_text:
                    follow_score += 0.3
                    evidence.append(f"homepage: '{phrase}'")

        # Check news items
        if news:
            for item in news.items[:10]:
                text = item.headline.lower() + " " + item.snippet.lower()
                if any(v in text for v in ["led", "led the", "lead"]):
                    lead_score += 0.1
                    evidence.append(f"news led: '{item.headline[:50]}'")
                if any(v in text for v in ["participated", "joined", "co-invested"]):
                    follow_score += 0.1
                    evidence.append(f"news follow: '{item.headline[:50]}'")

        # Determine preference
        if lead_score >= 0.3 and lead_score > follow_score:
            pref = "lead"
        elif lead_score > 0 and follow_score > 0:
            pref = "lead_or_follow"
        elif follow_score >= 0.3:
            pref = "mostly_follow"
        else:
            pref = "unknown"

        confidence = min(max(lead_score, follow_score), 1.0)
        return pref, confidence, evidence

    def extract_board_signals(
        self,
        homepage: HomepageData,
        news: NewsPageData,
        team: TeamPageData,
    ) -> List[str]:
        """Extract board seat signals."""
        signals = []
        board_phrases = ["board seat", "board member", "board director",
                         "board of directors", "sits on the board",
                         "joins the board", "board observer"]

        # Check homepage
        if homepage:
            text = " ".join(homepage.strategy_snippets).lower()
            for phrase in board_phrases:
                if phrase in text:
                    signals.append(f"homepage mentions '{phrase}'")

        # Check team bios
        if team:
            for member in team.members:
                bio_lower = member.bio.lower()
                for phrase in board_phrases:
                    if phrase in bio_lower:
                        signals.append(f"{member.name} bio mentions '{phrase}'")
                        break

        # Check news
        if news:
            for item in news.items[:10]:
                text = (item.headline + " " + item.snippet).lower()
                for phrase in board_phrases:
                    if phrase in text:
                        signals.append(f"news: '{item.headline[:50]}' mentions '{phrase}'")
                        break

        return signals[:5]


# ── Main Engine ───────────────────────────────────────────

class FundIntelEngine:
    """
    Orchestrates fund intelligence enrichment for a batch of leads.

    For each unique fund domain:
    1. Discover site structure
    2. Fetch and parse relevant pages
    3. Run inference rules
    4. Merge results into lead objects
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or _load_config()
        crawl_cfg = self.config.get("crawl", {})

        self.request_timeout = crawl_cfg.get("request_timeout", 12)
        self.crawl_delay = crawl_cfg.get("crawl_delay", 0.5)
        self.concurrency = crawl_cfg.get("concurrency", 5)
        self.user_agent = crawl_cfg.get("user_agent",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36")
        self.max_internal_pages = crawl_cfg.get("max_internal_pages", 30)

        sector_kw = self.config.get("sector_keywords", {})
        geo_kw = self.config.get("geography_keywords", {})
        biz_kw = self.config.get("business_model_keywords", {})
        title_scores = self.config.get("title_scores", {})

        self.discoverer = SiteDiscoverer(
            page_keywords=self.config.get("page_keywords"),
            request_timeout=self.request_timeout,
            crawl_delay=self.crawl_delay,
            max_internal_pages=self.max_internal_pages,
            user_agent=self.user_agent,
        )
        self.homepage_extractor = HomepageExtractor(
            sector_keywords=sector_kw,
            geography_keywords=geo_kw,
        )
        self.team_extractor = TeamExtractor(title_scores=title_scores)
        self.portfolio_extractor = PortfolioExtractor()
        self.thesis_extractor = ThesisExtractor(sector_keywords=sector_kw)
        self.news_extractor = NewsExtractor()
        self.inference = InferenceEngine(self.config)
        self.business_model_keywords = biz_kw

        self.stats = {
            "domains_processed": 0,
            "pages_fetched": 0,
            "portfolio_companies_found": 0,
            "decision_makers_found": 0,
            "active_inferred": 0,
            "lead_follow_inferred": 0,
            "errors": 0,
        }

        # Persistent cache for fund intel results
        self._cache_path = Path("data/fund_intel_cache.json")
        self._cache: Dict[str, dict] = self._load_cache()

    def _load_cache(self) -> dict:
        try:
            if self._cache_path.exists():
                with open(self._cache_path) as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_cache(self):
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._cache_path, "w") as f:
                json.dump(self._cache, f)
        except Exception as e:
            logger.debug(f"Failed to save fund intel cache: {e}")

    async def enrich_batch(self, leads: list) -> list:
        """
        Enrich a batch of InvestorLead objects with fund intelligence.
        Groups leads by fund domain and enriches each domain once.
        """
        # Group leads by domain
        domain_leads: Dict[str, list] = defaultdict(list)
        for lead in leads:
            url = lead.website
            if not url or url in ("N/A", ""):
                continue
            if not url.startswith("http"):
                url = "https://" + url
            domain = urlparse(url).netloc.lower().replace("www.", "")
            if domain:
                domain_leads[domain].append((lead, url))

        if not domain_leads:
            return leads

        print(f"  Fund intelligence: {len(domain_leads)} unique domains to enrich")

        sem = asyncio.Semaphore(self.concurrency)
        results: Dict[str, FundIntelResult] = {}

        async def _process_domain(domain: str, lead_url_pairs: list):
            async with sem:
                # Check cache (skip if already enriched recently)
                cached = self._cache.get(domain)
                if cached:
                    cached_at = cached.get("_cached_at", "")
                    if cached_at:
                        try:
                            age = datetime.now() - datetime.fromisoformat(cached_at)
                            if age < timedelta(days=7):
                                results[domain] = self._result_from_cache(domain, cached)
                                return
                        except Exception:
                            pass

                fund_url = lead_url_pairs[0][1]
                try:
                    result = await self._enrich_domain(domain, fund_url)
                    results[domain] = result
                    self.stats["domains_processed"] += 1

                    # Cache result
                    cache_entry = result.to_dict()
                    cache_entry["_cached_at"] = datetime.now().isoformat()
                    self._cache[domain] = cache_entry
                except Exception as e:
                    logger.warning(f"  Fund intel failed for {domain}: {e}")
                    self.stats["errors"] += 1

        tasks = [_process_domain(d, pairs) for d, pairs in domain_leads.items()]
        await asyncio.gather(*tasks)

        # Save cache
        self._save_cache()

        # Merge results into leads
        enriched_count = 0
        for lead in leads:
            url = lead.website
            if not url or url in ("N/A", ""):
                continue
            if not url.startswith("http"):
                url = "https://" + url
            domain = urlparse(url).netloc.lower().replace("www.", "")
            result = results.get(domain)
            if not result:
                continue

            self._merge_into_lead(lead, result)
            enriched_count += 1

        print(
            f"  Fund intelligence complete: {self.stats['domains_processed']} domains, "
            f"{self.stats['portfolio_companies_found']} portfolio cos, "
            f"{self.stats['decision_makers_found']} decision makers, "
            f"{self.stats['active_inferred']} active inferred"
        )

        return leads

    async def _enrich_domain(self, domain: str, fund_url: str) -> FundIntelResult:
        """Run full enrichment for a single fund domain."""
        result = FundIntelResult(domain=domain, firm_domain=domain)

        timeout = aiohttp.ClientTimeout(total=self.request_timeout)
        async with aiohttp.ClientSession(
            timeout=timeout,
            headers={"User-Agent": self.user_agent},
        ) as session:
            # Step 1: Discover site structure
            discovery = await self.discoverer.discover(fund_url)

            # Step 2: Fetch and extract pages
            homepage_data = None
            team_data = None
            portfolio_data = None
            thesis_data = None
            news_data = None

            # Homepage/About
            about_url = discovery.best_url("about") or fund_url
            html = await self._fetch_page(session, about_url)
            if html:
                homepage_data = self.homepage_extractor.extract(html, about_url)
                # Also try homepage if about was different
                if about_url != fund_url:
                    hp_html = await self._fetch_page(session, fund_url)
                    if hp_html:
                        hp_data = self.homepage_extractor.extract(hp_html, fund_url)
                        # Merge: prefer whichever found more
                        if not homepage_data.location and hp_data.location:
                            homepage_data.location = hp_data.location
                            homepage_data.location_evidence = hp_data.location_evidence
                        if not homepage_data.check_size and hp_data.check_size:
                            homepage_data.check_size = hp_data.check_size
                            homepage_data.check_size_evidence = hp_data.check_size_evidence
                        homepage_data.strategy_snippets.extend(hp_data.strategy_snippets)
                        for k, v in hp_data.sector_keywords.items():
                            homepage_data.sector_keywords[k] = homepage_data.sector_keywords.get(k, 0) + v
                        for k, v in hp_data.geography_keywords.items():
                            homepage_data.geography_keywords[k] = homepage_data.geography_keywords.get(k, 0) + v

            # Team page
            team_url = discovery.best_url("team")
            if team_url:
                html = await self._fetch_page(session, team_url)
                if html:
                    team_data = self.team_extractor.extract(html, team_url)

            # Portfolio page
            portfolio_url = discovery.best_url("portfolio")
            if portfolio_url:
                html = await self._fetch_page(session, portfolio_url)
                if html:
                    portfolio_data = self.portfolio_extractor.extract(html, portfolio_url, domain)

            # Thesis/blog
            thesis_url = discovery.best_url("thesis")
            if thesis_url:
                html = await self._fetch_page(session, thesis_url)
                if html:
                    thesis_data = self.thesis_extractor.extract(html, thesis_url)

            # News
            news_url = discovery.best_url("news")
            if news_url:
                html = await self._fetch_page(session, news_url)
                if html:
                    news_data = self.news_extractor.extract(html, news_url)

        # Step 3: Populate result from extracted data
        self._populate_result(result, homepage_data, team_data, portfolio_data, thesis_data, news_data)

        # Step 4: Run inference
        status, conf, evidence = self.inference.infer_active_status(
            portfolio_data, thesis_data, news_data
        )
        result.active_status = status
        result.active_status_confidence = conf
        result.active_status_evidence = evidence
        if status in ("active", "possibly_active"):
            self.stats["active_inferred"] += 1

        pref, conf, evidence = self.inference.infer_lead_follow(
            homepage_data, news_data
        )
        result.lead_follow_preference = pref
        result.lead_follow_confidence = conf
        result.lead_follow_evidence = evidence
        if pref != "unknown":
            self.stats["lead_follow_inferred"] += 1

        result.board_seat_signals = self.inference.extract_board_signals(
            homepage_data, news_data, team_data
        )

        # Business model keywords from all text
        if homepage_data and self.business_model_keywords:
            all_text = homepage_data.description + " " + " ".join(homepage_data.strategy_snippets)
            from enrichment.page_extractors import _match_keywords
            result.business_model_keywords = _match_keywords(all_text, self.business_model_keywords)

        return result

    def _populate_result(
        self,
        result: FundIntelResult,
        homepage: Optional[HomepageData],
        team: Optional[TeamPageData],
        portfolio: Optional[PortfolioPageData],
        thesis: Optional[ThesisPageData],
        news: Optional[NewsPageData],
    ):
        """Populate FundIntelResult from extracted data."""
        # Homepage
        if homepage:
            result.hq_geography = homepage.location
            result.hq_geography_evidence = homepage.location_evidence
            result.stage = homepage.stage_keywords
            result.sector_fit_keywords = homepage.sector_keywords
            result.sector_fit_keyword_counts = sum(homepage.sector_keywords.values())
            result.geography_investment_signals = homepage.geography_keywords
            result.check_size_estimate = homepage.check_size
            result.check_size_evidence = homepage.check_size_evidence
            result.strategy_snippets = homepage.strategy_snippets[:5]

        # Team
        if team and team.members:
            # Sort by decision-maker score
            sorted_members = sorted(team.members, key=lambda m: m.decision_maker_score, reverse=True)
            # Top decision makers (score >= 60)
            dms = [m for m in sorted_members if m.decision_maker_score >= 60]
            if not dms:
                dms = sorted_members[:3]  # fallback: top 3

            result.decision_maker_names = [m.name for m in dms[:10]]
            result.decision_maker_roles = [m.role for m in dms[:10] if m.role]
            result.decision_maker_source_url = team.source_url
            result.team_size = len(team.members)
            self.stats["decision_makers_found"] += len(dms)

        # Portfolio
        if portfolio and portfolio.companies:
            result.portfolio_companies = [c.name for c in portfolio.companies]
            result.portfolio_source_url = portfolio.source_urls[0] if portfolio.source_urls else ""
            result.portfolio_count = len(portfolio.companies)
            self.stats["portfolio_companies_found"] += len(portfolio.companies)

            # Recent investments
            now_year = datetime.now().year
            recent = [c for c in portfolio.companies if c.year and (now_year - c.year) <= 2]
            result.recent_investments = [c.name for c in recent]
            result.recent_investments_source_urls = portfolio.source_urls

            # Last investment date
            years = [c.year for c in portfolio.companies if c.year]
            if years:
                result.last_investment_date = str(max(years))

        # Thesis
        if thesis and thesis.posts:
            # Best thesis URL = most keyword-rich post
            best = max(thesis.posts, key=lambda p: sum(p.sector_keywords.values()) + len(p.stage_keywords))
            result.thesis_evidence_url = best.url
            result.thesis_evidence_title = best.title

            # Merge sector keywords from blog posts
            for post in thesis.posts:
                for k, v in post.sector_keywords.items():
                    result.sector_fit_keywords[k] = result.sector_fit_keywords.get(k, 0) + v

    async def _fetch_page(self, session: aiohttp.ClientSession, url: str) -> Optional[str]:
        """Fetch a page via HTTP. Returns HTML or None."""
        try:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    return None
                self.stats["pages_fetched"] += 1
                text = await resp.text()
                # Skip if too small (likely error page) or too large
                if len(text) < 500 or len(text) > 5_000_000:
                    return None
                return text
        except Exception:
            return None
        finally:
            await asyncio.sleep(self.crawl_delay)

    def _merge_into_lead(self, lead, result: FundIntelResult):
        """Merge fund intel result into an InvestorLead object."""
        # Backfill basic fields if empty
        if lead.location in ("N/A", "", None) and result.hq_geography:
            lead.location = result.hq_geography

        if lead.stage in ("N/A", "", None) and result.stage:
            lead.stage = "; ".join(result.stage[:3])

        if not lead.focus_areas and result.sector_fit_keywords:
            # Top sector keywords as focus areas
            sorted_sectors = sorted(result.sector_fit_keywords.items(), key=lambda x: x[1], reverse=True)
            lead.focus_areas = [s[0] for s in sorted_sectors[:5]]

        if lead.check_size in ("N/A", "", None) and result.check_size_estimate:
            lead.check_size = result.check_size_estimate

        # Store enriched fields in the fund_intel dict
        # These get serialized to CSV as JSON columns
        if not hasattr(lead, 'fund_intel'):
            lead.fund_intel = {}

        lead.fund_intel = result.to_dict()

    def _result_from_cache(self, domain: str, cached: dict) -> FundIntelResult:
        """Reconstruct FundIntelResult from cache dict."""
        result = FundIntelResult(domain=domain)
        for k, v in cached.items():
            if k.startswith("_"):
                continue
            if hasattr(result, k):
                if isinstance(v, str) and v.startswith("["):
                    try:
                        setattr(result, k, json.loads(v))
                    except Exception:
                        setattr(result, k, v)
                elif isinstance(v, str) and v.startswith("{"):
                    try:
                        setattr(result, k, json.loads(v))
                    except Exception:
                        setattr(result, k, v)
                else:
                    setattr(result, k, v)
        return result
