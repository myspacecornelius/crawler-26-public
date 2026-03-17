"""
CRAWL — Multi-Engine Discovery
Extends the HTTP-based discovery to query multiple search engines concurrently:
  1. DuckDuckGo Lite (existing, no API key needed)
  2. Google (via SerpAPI — free tier: 100 searches/month)
  3. Bing Web Search (free tier: 1,000 calls/month)
  4. Brave Search API (free tier: 2,000 calls/month)

Each engine is a plug-in with a common interface. The orchestrator runs all
active engines and merges results with domain-level deduplication.

Usage:
    from discovery.multi_searcher import multi_discover
    domains = await multi_discover(queries, target_count=2000)

Config keys in config/search.yaml:
    discovery:
      engines:
        duckduckgo: {enabled: true}
        google:     {enabled: true, api_key: "SERPAPI_KEY"}
        bing:       {enabled: true, api_key: "BING_KEY"}
        brave:      {enabled: true, api_key: "BRAVE_KEY"}
"""

import asyncio
import logging
import os
import random
import re
import urllib.parse
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

# ── Domain Validation ────────────────────────────

DEFAULT_IGNORE = {
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "crunchbase.com", "angellist.com", "angel.co", "pitchbook.com",
    "dealroom.co", "techcrunch.com", "medium.com", "substack.com",
    "youtube.com", "reddit.com", "wikipedia.org", "google.com",
    "bing.com", "duckduckgo.com", "yahoo.com", "amazon.com",
    "github.com", "stackoverflow.com", "quora.com",
    "tracxn.com", "wellfound.com", "cbinsights.com",
    "sec.gov", "bloomberg.com", "wsj.com", "forbes.com",
    "nytimes.com", "reuters.com", "ft.com",
    "brave.com", "search.brave.com", "serpapi.com",
}


def _is_valid_vc_domain(url: str, ignore_domains: Set[str]) -> bool:
    """Check if a URL likely belongs to an actual VC fund website."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        if not domain or len(domain) < 4:
            return False
        for ignored in ignore_domains:
            if ignored in domain:
                return False
        if domain.endswith((".cn", ".jp", ".ru", ".ir")):
            return False
        if any(x in domain for x in ("gov.", ".gov", ".edu", "news.", "blog.")):
            return False
        return True
    except Exception:
        return False


def _get_base_url(url: str) -> str:
    """Extract protocol + domain from a URL."""
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return url


# ── Base Engine ──────────────────────────────────

class SearchEngine(ABC):
    """Abstract base for a search engine backend."""

    name: str = "base"
    requires_key: bool = False

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key

    @abstractmethod
    async def search(
        self,
        session: aiohttp.ClientSession,
        query: str,
    ) -> List[str]:
        """Return a list of raw result URLs for a single query."""
        ...


# ── DuckDuckGo Engine ────────────────────────────

class DuckDuckGoEngine(SearchEngine):
    """DuckDuckGo Lite HTML — no API key, lightweight HTTP."""

    name = "duckduckgo"
    requires_key = False

    async def search(self, session: aiohttp.ClientSession, query: str) -> List[str]:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        headers = {
            "User-Agent": random.choice([
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/119.0.0.0",
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/121.0.0.0",
            ]),
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                html = await resp.text()
                if "robot" in html.lower() or "captcha" in html.lower():
                    logger.warning(f"  [{self.name}] Rate-limited, backing off")
                    await asyncio.sleep(30)
                    return []
                return self._extract_urls(html)
        except Exception as e:
            logger.debug(f"  [{self.name}] Query failed: {e}")
            return []

    @staticmethod
    def _extract_urls(html: str) -> List[str]:
        urls = []
        for match in re.finditer(r'uddg=([^&"\']+)', html):
            try:
                decoded = urllib.parse.unquote(match.group(1))
                if decoded.startswith("http"):
                    urls.append(decoded)
            except Exception:
                pass
        for match in re.finditer(r'href="(https?://[^"]+)"', html):
            u = match.group(1)
            if "duckduckgo.com" not in u:
                urls.append(u)
        return urls


# ── Google Engine (SerpAPI) ──────────────────────

class GoogleSerpAPIEngine(SearchEngine):
    """Google search via SerpAPI (free tier: 100 searches/month)."""

    name = "google"
    requires_key = True

    async def search(self, session: aiohttp.ClientSession, query: str) -> List[str]:
        if not self.api_key:
            return []
        params = {
            "q": query,
            "api_key": self.api_key,
            "engine": "google",
            "num": 30,
            "gl": "us",
            "hl": "en",
        }
        try:
            async with session.get(
                "https://serpapi.com/search.json",
                params=params,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"  [{self.name}] HTTP {resp.status}")
                    return []
                data = await resp.json()
                results = data.get("organic_results", [])
                return [r["link"] for r in results if "link" in r]
        except Exception as e:
            logger.debug(f"  [{self.name}] Query failed: {e}")
            return []


# ── Bing Engine ──────────────────────────────────

class BingSearchEngine(SearchEngine):
    """Bing Web Search — two modes:
    1. API mode (requires BING_API_KEY): Bing Web Search API v7, 1,000 free/month.
    2. HTML scrape mode (no key): queries bing.com/search, parses result anchors.
       Rate-limited to 1 request per 2-3 seconds to avoid blocks.
    """

    name = "bing"
    requires_key = False  # HTML scrape works without a key

    _USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:123.0) Gecko/20100101 Firefox/123.0",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    ]

    async def search(self, session: aiohttp.ClientSession, query: str) -> List[str]:
        # Prefer API if key is available
        if self.api_key:
            return await self._search_api(session, query)
        return await self._search_html(session, query)

    async def _search_api(self, session: aiohttp.ClientSession, query: str) -> List[str]:
        """Bing Web Search API v7."""
        headers = {"Ocp-Apim-Subscription-Key": self.api_key}
        params = {"q": query, "count": 30, "mkt": "en-US"}
        try:
            async with session.get(
                "https://api.bing.microsoft.com/v7.0/search",
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"  [{self.name}] API HTTP {resp.status}")
                    return []
                data = await resp.json()
                pages = data.get("webPages", {}).get("value", [])
                return [p["url"] for p in pages if "url" in p]
        except Exception as e:
            logger.debug(f"  [{self.name}] API query failed: {e}")
            return []

    async def _search_html(self, session: aiohttp.ClientSession, query: str) -> List[str]:
        """Bing HTML scrape — no API key required."""
        encoded = urllib.parse.quote_plus(query)
        url = f"https://www.bing.com/search?q={encoded}&count=20&setlang=en-US"
        headers = {
            "User-Agent": random.choice(self._USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.bing.com/",
            "DNT": "1",
        }
        try:
            # Polite rate limiting: 2-3 second random delay before each request
            await asyncio.sleep(random.uniform(2.0, 3.5))
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    logger.debug(f"  [{self.name}] HTML HTTP {resp.status}")
                    return []
                html = await resp.text()
                if "captcha" in html.lower() or "blocked" in html.lower():
                    logger.warning(f"  [{self.name}] Possible block/captcha, backing off 60s")
                    await asyncio.sleep(60)
                    return []
                return self._extract_urls_html(html)
        except Exception as e:
            logger.debug(f"  [{self.name}] HTML query failed: {e}")
            return []

    @staticmethod
    def _extract_urls_html(html: str) -> List[str]:
        """Extract result URLs from Bing HTML response."""
        urls = []
        # Primary: Bing wraps organic results in <a> tags with class "tilk" or href starting http
        # Pattern 1: data-href or href inside .b_algo result blocks
        for match in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*tilk[^"]*"', html):
            urls.append(match.group(1))
        # Pattern 2: cite tags contain the displayed URL
        for match in re.finditer(r'<cite[^>]*>(https?://[^<]+)</cite>', html):
            u = match.group(1).strip()
            if u.startswith("http"):
                urls.append(u)
        # Pattern 3: generic href extraction for result links (skip bing internal links)
        for match in re.finditer(r'href="(https?://(?!www\.bing\.com)[^"]+)"', html):
            u = match.group(1)
            # Skip tracking redirects and Bing internals
            if "/ck/a?" not in u and "bing.com" not in u and "microsoft.com" not in u:
                urls.append(u)
        return urls


# ── Brave Engine ─────────────────────────────────

class BraveSearchEngine(SearchEngine):
    """Brave Search API (free tier: 2,000 calls/month)."""

    name = "brave"
    requires_key = True

    async def search(self, session: aiohttp.ClientSession, query: str) -> List[str]:
        if not self.api_key:
            return []
        headers = {
            "X-Subscription-Token": self.api_key,
            "Accept": "application/json",
        }
        params = {"q": query, "count": 20}
        try:
            async with session.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.debug(f"  [{self.name}] HTTP {resp.status}")
                    return []
                data = await resp.json()
                results = data.get("web", {}).get("results", [])
                return [r["url"] for r in results if "url" in r]
        except Exception as e:
            logger.debug(f"  [{self.name}] Query failed: {e}")
            return []


# ── Engine Registry ──────────────────────────────

ENGINE_CLASSES: Dict[str, type] = {
    "duckduckgo": DuckDuckGoEngine,
    "google": GoogleSerpAPIEngine,
    "bing": BingSearchEngine,
    "brave": BraveSearchEngine,
}


def _build_engines(engine_config: dict) -> List[SearchEngine]:
    """Instantiate enabled engines from config."""
    engines = []
    for name, cls in ENGINE_CLASSES.items():
        cfg = engine_config.get(name, {})
        enabled = cfg.get("enabled", name == "duckduckgo")  # DDG on by default
        if not enabled:
            continue

        # API key: config value → env var → None
        api_key = cfg.get("api_key") or os.environ.get(f"{name.upper()}_API_KEY")

        if cls.requires_key and not api_key:
            logger.info(f"  ⚠️  {name} engine enabled but no API key — skipping")
            continue

        engines.append(cls(api_key=api_key))
        logger.info(f"  ✅  {name} engine active")

    if not engines:
        logger.warning("  No search engines configured, falling back to DuckDuckGo")
        engines.append(DuckDuckGoEngine())

    return engines


# ── Orchestrator ─────────────────────────────────

async def multi_discover(
    queries: List[str],
    target_count: int = 2000,
    ignore_domains: Set[str] = None,
    engine_config: dict = None,
    max_concurrent: int = 5,
) -> Set[str]:
    """
    Run search queries across all enabled engines and return unique VC domains.

    Strategy:
    - Distribute queries across engines in round-robin to maximize coverage
    - Deduplicate at the domain level across all engines
    - Respect per-engine rate limits with polite delays
    """
    if ignore_domains is None:
        ignore_domains = DEFAULT_IGNORE
    if engine_config is None:
        engine_config = {}

    engines = _build_engines(engine_config)
    discovered: Set[str] = set()
    sem = asyncio.Semaphore(max_concurrent)
    engine_stats: Dict[str, int] = {e.name: 0 for e in engines}

    print(f"\n{'='*60}")
    print(f"  🔍  MULTI-ENGINE DISCOVERY")
    print(f"  Engines: {', '.join(e.name for e in engines)}")
    print(f"  Queries: {len(queries)} | Target: {target_count} domains")
    print(f"{'='*60}\n")

    async def _run_query(engine: SearchEngine, query: str):
        async with sem:
            try:
                async with aiohttp.ClientSession() as session:
                    urls = await engine.search(session, query)
                new = 0
                for url in urls:
                    if _is_valid_vc_domain(url, ignore_domains):
                        base = _get_base_url(url)
                        if base not in discovered:
                            discovered.add(base)
                            new += 1
                            engine_stats[engine.name] += 1
                return new
            except Exception as e:
                logger.debug(f"  [{engine.name}] Error: {e}")
                return 0

    query_idx = 0
    batch_size = len(engines) * 3  # process 3 queries per engine per batch

    while query_idx < len(queries) and len(discovered) < target_count:
        tasks = []
        batch_end = min(query_idx + batch_size, len(queries))

        for i in range(query_idx, batch_end):
            # Round-robin across engines
            engine = engines[i % len(engines)]
            tasks.append(_run_query(engine, queries[i]))

        results = await asyncio.gather(*tasks)
        total_new = sum(results)

        logger.info(
            f"  🔎  Batch [{query_idx+1}–{batch_end}/{len(queries)}] "
            f"+{total_new} domains (total: {len(discovered)}/{target_count})"
        )

        query_idx = batch_end

        # Polite delay between batches
        await asyncio.sleep(random.uniform(1.5, 3.5))

    # Print summary
    print(f"\n  {'─'*50}")
    print(f"  📊  Discovery Summary")
    for name, count in engine_stats.items():
        print(f"      {name}: {count} unique domains")
    print(f"      TOTAL: {len(discovered)} unique domains")
    print(f"  {'─'*50}\n")

    return discovered
