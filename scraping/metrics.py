"""
CRAWL — Scraping Metrics Instrumentation

Records request counts, block rates, extraction times, and other
performance metrics. Exposes data via logs and a summary API.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class ScrapeMetrics:
    """
    Collects and reports scraping performance metrics.

    Tracks per-domain and global:
    - Request counts (total, success, failed, blocked)
    - Extraction times
    - Leads extracted per domain
    - Block/ban rates
    - Circuit breaker trips
    """

    def __init__(self):
        self._start_time = time.monotonic()
        self._domain_stats: Dict[str, dict] = defaultdict(
            lambda: {
                "requests": 0,
                "successes": 0,
                "failures": 0,
                "blocks": 0,
                "leads_found": 0,
                "total_extraction_time_s": 0.0,
                "circuit_trips": 0,
            }
        )
        self._global = {
            "total_requests": 0,
            "total_successes": 0,
            "total_failures": 0,
            "total_blocks": 0,
            "total_leads": 0,
            "total_circuit_trips": 0,
        }

    def _domain_key(self, url: str) -> str:
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        return (parsed.netloc or parsed.path).lower().replace("www.", "")

    def record_request(self, url: str):
        """Record that a request was made."""
        domain = self._domain_key(url)
        self._domain_stats[domain]["requests"] += 1
        self._global["total_requests"] += 1

    def record_success(self, url: str, leads_found: int = 0, extraction_time_s: float = 0.0):
        """Record a successful scrape."""
        domain = self._domain_key(url)
        self._domain_stats[domain]["successes"] += 1
        self._domain_stats[domain]["leads_found"] += leads_found
        self._domain_stats[domain]["total_extraction_time_s"] += extraction_time_s
        self._global["total_successes"] += 1
        self._global["total_leads"] += leads_found

    def record_failure(self, url: str, blocked: bool = False):
        """Record a failed request. Set blocked=True for 403/429 responses."""
        domain = self._domain_key(url)
        self._domain_stats[domain]["failures"] += 1
        self._global["total_failures"] += 1
        if blocked:
            self._domain_stats[domain]["blocks"] += 1
            self._global["total_blocks"] += 1

    def record_circuit_trip(self, url: str):
        """Record that a circuit breaker was tripped for a domain."""
        domain = self._domain_key(url)
        self._domain_stats[domain]["circuit_trips"] += 1
        self._global["total_circuit_trips"] += 1

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._start_time

    @property
    def block_rate(self) -> float:
        total = self._global["total_requests"]
        if total == 0:
            return 0.0
        return self._global["total_blocks"] / total

    @property
    def success_rate(self) -> float:
        total = self._global["total_requests"]
        if total == 0:
            return 0.0
        return self._global["total_successes"] / total

    def avg_extraction_time(self, url: Optional[str] = None) -> float:
        """Average extraction time per request, optionally per domain."""
        if url:
            domain = self._domain_key(url)
            stats = self._domain_stats.get(domain)
            if not stats or stats["successes"] == 0:
                return 0.0
            return stats["total_extraction_time_s"] / stats["successes"]
        total_time = sum(s["total_extraction_time_s"] for s in self._domain_stats.values())
        total_success = self._global["total_successes"]
        if total_success == 0:
            return 0.0
        return total_time / total_success

    def top_domains_by_leads(self, n: int = 10) -> List[dict]:
        """Return top N domains ranked by leads found."""
        ranked = sorted(
            self._domain_stats.items(),
            key=lambda x: x[1]["leads_found"],
            reverse=True,
        )
        return [
            {"domain": domain, **stats}
            for domain, stats in ranked[:n]
        ]

    def blocked_domains(self) -> List[str]:
        """Return domains that have been blocked (403/429)."""
        return [
            domain
            for domain, stats in self._domain_stats.items()
            if stats["blocks"] > 0
        ]

    def summary(self) -> dict:
        """Return a full metrics summary."""
        return {
            "uptime_seconds": round(self.uptime_seconds, 1),
            "global": {
                **self._global,
                "success_rate": round(self.success_rate, 3),
                "block_rate": round(self.block_rate, 3),
                "avg_extraction_time_s": round(self.avg_extraction_time(), 3),
            },
            "domains_crawled": len(self._domain_stats),
            "blocked_domains": self.blocked_domains(),
        }

    def log_summary(self):
        """Log a human-readable metrics summary."""
        s = self.summary()
        g = s["global"]
        logger.info(
            f"  [METRICS] requests={g['total_requests']} "
            f"success={g['total_successes']} "
            f"failed={g['total_failures']} "
            f"blocked={g['total_blocks']} "
            f"leads={g['total_leads']} "
            f"block_rate={g['block_rate']:.1%} "
            f"avg_extraction={g['avg_extraction_time_s']:.2f}s "
            f"domains={s['domains_crawled']} "
            f"uptime={s['uptime_seconds']:.0f}s"
        )


# Global metrics singleton
_global_metrics: Optional[ScrapeMetrics] = None


def get_metrics() -> ScrapeMetrics:
    """Get or create the global metrics instance."""
    global _global_metrics
    if _global_metrics is None:
        _global_metrics = ScrapeMetrics()
    return _global_metrics
