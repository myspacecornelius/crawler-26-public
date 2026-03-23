"""
CRAWL — Circuit Breaker Pattern for Scraping

Prevents the crawler from repeatedly hitting domains that are blocking
or timing out. After a configurable number of consecutive failures,
the circuit opens and skips that domain for a cooldown period.
"""

import logging
import time
from enum import Enum
from typing import Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation — requests pass through
    OPEN = "open"            # Failing — requests are blocked
    HALF_OPEN = "half_open"  # Testing — allow one probe request


class CircuitBreaker:
    """
    Per-domain circuit breaker.

    State transitions:
      CLOSED -> OPEN: after `failure_threshold` consecutive failures
      OPEN -> HALF_OPEN: after `cooldown_seconds` have passed
      HALF_OPEN -> CLOSED: if the probe request succeeds
      HALF_OPEN -> OPEN: if the probe request fails (resets cooldown)
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 90.0,
        max_cooldown_seconds: float = 600.0,
    ):
        self.failure_threshold = failure_threshold
        self.base_cooldown = cooldown_seconds
        self.max_cooldown = max_cooldown_seconds
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.last_failure_time: float = 0.0
        self.total_failures = 0
        self.total_successes = 0
        self._trip_count = 0  # number of times circuit has opened

    @property
    def cooldown_seconds(self) -> float:
        """Exponential backoff: 90s → 180s → 360s → 600s (cap)."""
        return min(self.base_cooldown * (2 ** self._trip_count), self.max_cooldown)

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: allow one probe
        return True

    def record_success(self):
        """Record a successful request."""
        self.total_successes += 1
        self.consecutive_failures = 0
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self._trip_count = 0  # reset backoff on recovery
            logger.info("  Circuit breaker: HALF_OPEN -> CLOSED (recovered)")

    def record_failure(self):
        """Record a failed request."""
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_time = time.monotonic()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self._trip_count += 1
            logger.warning(
                f"  Circuit breaker: HALF_OPEN -> OPEN "
                f"(probe failed, next cooldown {self.cooldown_seconds:.0f}s)"
            )
        elif (
            self.state == CircuitState.CLOSED
            and self.consecutive_failures >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            self._trip_count += 1
            logger.warning(
                f"  Circuit breaker: CLOSED -> OPEN "
                f"(after {self.consecutive_failures} consecutive failures, "
                f"cooldown {self.cooldown_seconds:.0f}s)"
            )

    @property
    def stats(self) -> dict:
        return {
            "state": self.state.value,
            "consecutive_failures": self.consecutive_failures,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
        }


class DomainCircuitBreakerManager:
    """
    Manages per-domain circuit breakers.

    Usage:
        manager = DomainCircuitBreakerManager()
        if manager.allow_request("https://example.com/team"):
            try:
                result = await crawl(url)
                manager.record_success(url)
            except Exception:
                manager.record_failure(url)
        else:
            logger.info("Skipping example.com — circuit open")
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 90.0,
        max_cooldown_seconds: float = 600.0,
    ):
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.max_cooldown_seconds = max_cooldown_seconds
        self._breakers: Dict[str, CircuitBreaker] = {}

    def _domain_key(self, url: str) -> str:
        """Extract domain from URL for circuit breaker grouping."""
        if not url.startswith("http"):
            url = "https://" + url
        parsed = urlparse(url)
        return (parsed.netloc or parsed.path).lower().replace("www.", "")

    def _get_breaker(self, url: str) -> CircuitBreaker:
        domain = self._domain_key(url)
        if domain not in self._breakers:
            self._breakers[domain] = CircuitBreaker(
                failure_threshold=self.failure_threshold,
                cooldown_seconds=self.cooldown_seconds,
                max_cooldown_seconds=self.max_cooldown_seconds,
            )
        return self._breakers[domain]

    def allow_request(self, url: str) -> bool:
        return self._get_breaker(url).allow_request()

    def record_success(self, url: str):
        self._get_breaker(url).record_success()

    def record_failure(self, url: str):
        self._get_breaker(url).record_failure()

    def get_open_circuits(self) -> list:
        """Return list of domains with open circuit breakers."""
        return [
            domain
            for domain, breaker in self._breakers.items()
            if breaker.state == CircuitState.OPEN
        ]

    @property
    def stats(self) -> dict:
        total_open = sum(
            1
            for b in self._breakers.values()
            if b.state == CircuitState.OPEN
        )
        return {
            "total_domains_tracked": len(self._breakers),
            "open_circuits": total_open,
            "domains_open": self.get_open_circuits(),
        }
