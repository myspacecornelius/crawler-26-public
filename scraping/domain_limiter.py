"""
CRAWL — Per-Domain Concurrency Limiter

Ensures that no single domain is overwhelmed with too many concurrent
requests. This prevents triggering rate-limiters and IP bans.
"""

import asyncio
import logging
from typing import Dict
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class DomainConcurrencyLimiter:
    """
    Limits concurrent requests per domain.

    Usage:
        limiter = DomainConcurrencyLimiter(max_per_domain=2)
        async with limiter.acquire("https://example.com/team"):
            await crawl(url)
    """

    def __init__(self, max_per_domain: int = 2, global_max: int = 10):
        self.max_per_domain = max_per_domain
        self.global_max = global_max
        self._domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._global_semaphore = asyncio.Semaphore(global_max)
        self._active_counts: Dict[str, int] = {}

    def _domain_key(self, url: str) -> str:
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        return (parsed.netloc or parsed.path).lower().replace("www.", "")

    def _get_semaphore(self, url: str) -> asyncio.Semaphore:
        domain = self._domain_key(url)
        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = asyncio.Semaphore(self.max_per_domain)
        return self._domain_semaphores[domain]

    def acquire(self, url: str) -> "_DomainLock":
        """Return an async context manager that limits concurrency for this domain."""
        return _DomainLock(self, url)

    @property
    def stats(self) -> dict:
        return {
            "domains_tracked": len(self._domain_semaphores),
            "max_per_domain": self.max_per_domain,
            "global_max": self.global_max,
        }


class _DomainLock:
    """Async context manager combining per-domain and global semaphores."""

    def __init__(self, limiter: DomainConcurrencyLimiter, url: str):
        self._limiter = limiter
        self._url = url
        self._domain_sem = limiter._get_semaphore(url)
        self._global_sem = limiter._global_semaphore

    async def __aenter__(self):
        await self._global_sem.acquire()
        await self._domain_sem.acquire()
        domain = self._limiter._domain_key(self._url)
        self._limiter._active_counts[domain] = (
            self._limiter._active_counts.get(domain, 0) + 1
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        domain = self._limiter._domain_key(self._url)
        self._limiter._active_counts[domain] = max(
            0, self._limiter._active_counts.get(domain, 1) - 1
        )
        self._domain_sem.release()
        self._global_sem.release()
        return False
