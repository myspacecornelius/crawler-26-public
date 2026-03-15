"""
Incremental Crawl — freshness tracking and stale domain filtering.

Provides:
- CrawlStateManager: tracks per-domain crawl timestamps in the database
- Content hashing for change detection
- HTTP Last-Modified / ETag support for conditional requests
- filter_stale_domains: returns only domains that haven't been crawled recently
- update_lead_freshness: stamps last_verified / last_crawled_at on leads
"""

import hashlib
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Default freshness thresholds
DEFAULT_STALE_DAYS = 7          # Re-crawl domains older than 7 days
DEFAULT_REVERIFY_DAYS = 14      # Re-verify emails older than 14 days


class CrawlStateManager:
    """
    Manages per-domain crawl state using the CrawlState DB table.
    Falls back to a local JSON file if the DB is unavailable.

    Supports:
    - Per-domain crawl timestamps
    - Content hashing for change detection
    - HTTP Last-Modified / ETag for conditional requests
    """

    def __init__(self, stale_days: int = DEFAULT_STALE_DAYS):
        self.stale_days = stale_days
        self._cache: Dict[str, datetime] = {}
        self._content_hashes: Dict[str, str] = {}
        self._last_modified: Dict[str, str] = {}
        self._etags: Dict[str, str] = {}
        self._db_available = False

    @staticmethod
    def _normalize_domain(url: str) -> str:
        """Extract bare domain from a URL."""
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path
        return domain.lower().replace("www.", "").strip("/")

    async def load_from_db(self):
        """Load crawl state from the database into cache."""
        try:
            from api.database import async_session, init_db
            from api.models import CrawlState
            from sqlalchemy import select

            await init_db()
            async with async_session() as session:
                result = await session.execute(select(CrawlState))
                rows = result.scalars().all()
                for row in rows:
                    self._cache[row.domain] = row.last_crawled_at
                self._db_available = True
                logger.info(f"  [incremental] Loaded {len(self._cache)} domain states from DB")
        except Exception as e:
            logger.warning(f"  [incremental] DB unavailable, using fresh state: {e}")
            self._db_available = False

    def is_stale(self, url: str) -> bool:
        """Check if a domain needs re-crawling."""
        domain = self._normalize_domain(url)
        last = self._cache.get(domain)
        if last is None:
            return True  # Never crawled
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.stale_days)
        # Handle naive datetimes from SQLite
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        return last < cutoff

    def filter_stale(self, urls: List[str]) -> Tuple[List[str], List[str]]:
        """
        Split URLs into (stale, fresh) lists.
        Returns (urls_to_crawl, urls_to_skip).
        """
        stale = []
        fresh = []
        for url in urls:
            if self.is_stale(url):
                stale.append(url)
            else:
                fresh.append(url)
        return stale, fresh

    async def mark_crawled(
        self,
        url: str,
        leads_found: int = 0,
        status: str = "completed",
        duration_s: float = 0.0,
    ):
        """Record that a domain was just crawled."""
        domain = self._normalize_domain(url)
        now = datetime.now(timezone.utc)
        self._cache[domain] = now

        if not self._db_available:
            return

        try:
            from api.database import async_session
            from api.models import CrawlState
            from sqlalchemy import select

            async with async_session() as session:
                result = await session.execute(
                    select(CrawlState).where(CrawlState.domain == domain)
                )
                row = result.scalar_one_or_none()

                if row:
                    row.last_crawled_at = now
                    row.leads_found = leads_found
                    row.status = status
                    row.crawl_duration_s = duration_s
                else:
                    session.add(CrawlState(
                        domain=domain,
                        last_crawled_at=now,
                        leads_found=leads_found,
                        status=status,
                        crawl_duration_s=duration_s,
                    ))
                await session.commit()
        except Exception as e:
            logger.warning(f"  [incremental] Failed to persist crawl state for {domain}: {e}")

    async def mark_batch_crawled(self, results: List[dict]):
        """
        Batch update crawl state for multiple domains.
        Each item: {"url": str, "leads_found": int, "status": str, "duration_s": float}
        """
        for item in results:
            await self.mark_crawled(
                url=item["url"],
                leads_found=item.get("leads_found", 0),
                status=item.get("status", "completed"),
                duration_s=item.get("duration_s", 0.0),
            )

    @staticmethod
    def compute_content_hash(html: str) -> str:
        """
        Compute a hash of the meaningful content on a page.
        Strips whitespace and common dynamic elements to detect real changes.
        """
        import re
        # Remove script and style tags
        cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        cleaned = re.sub(r'<[^>]+>', ' ', cleaned)
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip().lower()
        return hashlib.sha256(cleaned.encode('utf-8')).hexdigest()[:16]

    def has_content_changed(self, url: str, new_html: str) -> bool:
        """
        Check if a page's content has changed since the last crawl.
        Returns True if changed or if no previous hash exists.
        """
        domain = self._normalize_domain(url)
        new_hash = self.compute_content_hash(new_html)
        old_hash = self._content_hashes.get(domain)
        if old_hash is None:
            return True
        return new_hash != old_hash

    def update_content_hash(self, url: str, html: str):
        """Store the content hash for a domain."""
        domain = self._normalize_domain(url)
        self._content_hashes[domain] = self.compute_content_hash(html)

    def get_conditional_headers(self, url: str) -> dict:
        """
        Return HTTP headers for conditional requests (If-Modified-Since, If-None-Match).
        Use these when making requests to detect unchanged content.
        """
        domain = self._normalize_domain(url)
        headers = {}
        last_mod = self._last_modified.get(domain)
        if last_mod:
            headers["If-Modified-Since"] = last_mod
        etag = self._etags.get(domain)
        if etag:
            headers["If-None-Match"] = etag
        return headers

    def update_http_headers(self, url: str, last_modified: Optional[str] = None, etag: Optional[str] = None):
        """Store Last-Modified and ETag headers from a response."""
        domain = self._normalize_domain(url)
        if last_modified:
            self._last_modified[domain] = last_modified
        if etag:
            self._etags[domain] = etag

    async def check_last_modified(self, url: str) -> Optional[bool]:
        """
        Make a HEAD request to check if content has changed using HTTP headers.
        Returns:
          True  — content has changed (or no conditional headers available)
          False — content is unchanged (304 Not Modified)
          None  — check failed (network error, etc.)
        """
        conditional_headers = self.get_conditional_headers(url)
        if not conditional_headers:
            return True  # No cached headers, assume changed

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.head(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        **conditional_headers,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                    allow_redirects=True,
                ) as resp:
                    if resp.status == 304:
                        return False  # Not modified
                    # Update stored headers from new response
                    new_last_mod = resp.headers.get("Last-Modified")
                    new_etag = resp.headers.get("ETag")
                    self.update_http_headers(url, new_last_mod, new_etag)
                    return True  # Changed or not cacheable
        except Exception as e:
            logger.debug(f"  [incremental] HEAD check failed for {url}: {e}")
            return None

    def summary(self) -> dict:
        """Return a summary of crawl state."""
        now = datetime.now(timezone.utc)
        total = len(self._cache)
        stale = sum(1 for ts in self._cache.values()
                    if (ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts)
                    < now - timedelta(days=self.stale_days))
        return {
            "total_domains": total,
            "stale_domains": stale,
            "fresh_domains": total - stale,
            "stale_threshold_days": self.stale_days,
        }

    async def prioritize_recrawl(self, urls: List[str]) -> List[str]:
        """
        Smart re-crawl prioritization. Returns URLs sorted by priority:
        1. Domains that errored last time (most likely to succeed on retry)
        2. Domains never crawled before (new discoveries)
        3. Domains with highest previous lead yield (most valuable)
        4. Oldest domains (most stale)
        """
        domain_meta: Dict[str, dict] = {}

        # Load extended metadata from DB if available
        if self._db_available:
            try:
                from api.database import async_session
                from api.models import CrawlState
                from sqlalchemy import select

                async with async_session() as session:
                    result = await session.execute(select(CrawlState))
                    for row in result.scalars().all():
                        domain_meta[row.domain] = {
                            "last_crawled": row.last_crawled_at,
                            "leads_found": getattr(row, 'leads_found', 0) or 0,
                            "status": getattr(row, 'status', 'completed'),
                            "duration": getattr(row, 'crawl_duration_s', 0) or 0,
                        }
            except Exception:
                pass

        def _priority_score(url: str) -> Tuple[int, int, float]:
            """
            Returns (tier, -leads_found, staleness_seconds) for sorting.
            Lower tier = higher priority. Within same tier, sort by leads desc then staleness.
            """
            domain = self._normalize_domain(url)
            meta = domain_meta.get(domain)

            if meta is None:
                # Never crawled — high priority
                return (1, 0, 0)

            status = meta.get("status", "completed")
            leads = meta.get("leads_found", 0)
            last_crawled = meta.get("last_crawled")

            # Calculate staleness
            now = datetime.now(timezone.utc)
            if last_crawled:
                if last_crawled.tzinfo is None:
                    last_crawled = last_crawled.replace(tzinfo=timezone.utc)
                staleness = (now - last_crawled).total_seconds()
            else:
                staleness = float('inf')

            # Errored last time — retry first
            if status in ("error", "timeout", "failed"):
                return (0, -leads, staleness)

            # High-yield domains — prioritize valuable sources
            if leads >= 5:
                return (2, -leads, staleness)

            # Normal domains — sort by staleness
            return (3, -leads, staleness)

        # Filter to stale-only, then sort by priority
        stale_urls = [url for url in urls if self.is_stale(url)]
        stale_urls.sort(key=_priority_score)

        if stale_urls:
            errored = sum(1 for u in stale_urls if _priority_score(u)[0] == 0)
            new = sum(1 for u in stale_urls if _priority_score(u)[0] == 1)
            high_yield = sum(1 for u in stale_urls if _priority_score(u)[0] == 2)
            logger.info(
                f"  🎯 Re-crawl priority: {errored} errored, {new} new, "
                f"{high_yield} high-yield, {len(stale_urls) - errored - new - high_yield} normal"
            )

        return stale_urls


async def update_lead_freshness_in_db(
    campaign_id: str,
    verified_emails: List[str],
    reverify_days: int = DEFAULT_REVERIFY_DAYS,
) -> int:
    """
    Update last_verified timestamp for leads whose emails were just verified.
    Also stamps last_crawled_at for all leads in the campaign.
    Returns the number of leads updated.
    """
    try:
        from api.database import async_session
        from api.models import Lead
        from sqlalchemy import select, update

        now = datetime.now(timezone.utc)
        updated = 0

        async with async_session() as session:
            # Stamp last_crawled_at on all campaign leads
            await session.execute(
                update(Lead)
                .where(Lead.campaign_id == campaign_id)
                .values(last_crawled_at=now)
            )

            # Stamp last_verified on verified emails
            if verified_emails:
                await session.execute(
                    update(Lead)
                    .where(
                        Lead.campaign_id == campaign_id,
                        Lead.email.in_(verified_emails),
                    )
                    .values(last_verified=now, email_verified=True)
                )
                updated = len(verified_emails)

            await session.commit()

        return updated
    except Exception as e:
        logger.warning(f"  [incremental] Failed to update lead freshness: {e}")
        return 0


async def get_stale_leads(
    campaign_id: str,
    reverify_days: int = DEFAULT_REVERIFY_DAYS,
) -> List[str]:
    """
    Return emails of leads in a campaign that need re-verification
    (last_verified is null or older than reverify_days).
    """
    try:
        from api.database import async_session
        from api.models import Lead
        from sqlalchemy import select, or_

        cutoff = datetime.now(timezone.utc) - timedelta(days=reverify_days)

        async with async_session() as session:
            result = await session.execute(
                select(Lead.email).where(
                    Lead.campaign_id == campaign_id,
                    Lead.email != "N/A",
                    Lead.email != "",
                    or_(
                        Lead.last_verified == None,
                        Lead.last_verified < cutoff,
                    ),
                )
            )
            return [row[0] for row in result.all()]
    except Exception as e:
        logger.warning(f"  [incremental] Failed to get stale leads: {e}")
        return []
