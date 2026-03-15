"""
CRAWL — Proxy Rotation Manager
Handles proxy rotation for requests to avoid IP-based blocking.
Includes health checks, automatic replacement, and load balancing.
"""

import asyncio
import logging
import random
import time
import yaml
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ProxyHealth:
    """Tracks health status for a single proxy."""

    def __init__(self, proxy_config: dict):
        self.proxy_config = proxy_config
        self.consecutive_failures = 0
        self.total_requests = 0
        self.total_failures = 0
        self.last_check_time: float = 0.0
        self.last_success_time: float = 0.0
        self.avg_latency_ms: float = 0.0
        self._latencies: List[float] = []
        self.is_healthy = True

    def record_success(self, latency_ms: float = 0.0):
        self.total_requests += 1
        self.consecutive_failures = 0
        self.last_success_time = time.monotonic()
        self.is_healthy = True
        if latency_ms > 0:
            self._latencies.append(latency_ms)
            # Keep a rolling window of 20 latencies
            if len(self._latencies) > 20:
                self._latencies = self._latencies[-20:]
            self.avg_latency_ms = sum(self._latencies) / len(self._latencies)

    def record_failure(self):
        self.total_requests += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        if self.consecutive_failures >= 3:
            self.is_healthy = False

    @property
    def failure_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests

    def to_dict(self) -> dict:
        return {
            "is_healthy": self.is_healthy,
            "consecutive_failures": self.consecutive_failures,
            "total_requests": self.total_requests,
            "failure_rate": round(self.failure_rate, 3),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
        }


class ProxyManager:
    """
    Manages proxy rotation for browser contexts.

    Supports:
    - Provider-based proxies (BrightData, SmartProxy)
    - Custom proxy lists with load balancing
    - Rotation modes: per_request, per_site, sticky_session
    - Health checks and automatic unhealthy proxy replacement
    - Multiple proxy pool support
    """

    def __init__(self, config_path: str = "config/proxies.yaml"):
        self.config = self._load_config(config_path)
        self.enabled = self.config.get("enabled", False)
        self._current_proxy = None
        self._current_proxy_key: Optional[str] = None
        self._request_count = 0
        self._proxy_health: Dict[str, ProxyHealth] = {}
        self._proxy_pools: Dict[str, List[dict]] = {}
        self._health_check_interval = self.config.get("health_check_interval_s", 300)
        self._init_proxy_pools()

    def _load_config(self, path: str) -> dict:
        config_file = Path(path)
        if config_file.exists():
            with open(config_file) as f:
                return yaml.safe_load(f) or {}
        return {"enabled": False}

    def _init_proxy_pools(self):
        """Initialize proxy pools from config."""
        # Primary pool from provider credentials
        creds = self.config.get("credentials", {})
        if creds.get("host"):
            self._proxy_pools["primary"] = [creds]

        # Additional pools
        pools = self.config.get("proxy_pools", {})
        for pool_name, pool_config in pools.items():
            if isinstance(pool_config, list):
                self._proxy_pools[pool_name] = pool_config
            elif isinstance(pool_config, dict) and pool_config.get("host"):
                self._proxy_pools[pool_name] = [pool_config]

        # Fallback pool
        fallback = self.config.get("fallback_proxies", [])
        if fallback:
            self._proxy_pools["fallback"] = [
                {"server": url} for url in fallback
            ]

    def _proxy_key(self, proxy: dict) -> str:
        """Generate a unique key for a proxy config."""
        return proxy.get("server", "") or f"{proxy.get('host', '')}:{proxy.get('port', '')}"

    def _get_health(self, proxy: dict) -> ProxyHealth:
        key = self._proxy_key(proxy)
        if key not in self._proxy_health:
            self._proxy_health[key] = ProxyHealth(proxy)
        return self._proxy_health[key]

    def get_proxy(self, site_name: str = "") -> Optional[dict]:
        """
        Get the next proxy to use based on rotation mode and health.

        Returns:
            Dict with 'server', 'username', 'password' for Playwright,
            or None if proxies are disabled.
        """
        if not self.enabled:
            return None

        rotation_mode = self.config.get("rotation", {}).get("mode", "per_request")

        if rotation_mode == "sticky_session" and self._current_proxy:
            health = self._get_health(self._current_proxy)
            if health.is_healthy:
                return self._current_proxy

        if rotation_mode == "per_site" and self._current_proxy and site_name:
            health = self._get_health(self._current_proxy)
            if health.is_healthy:
                return self._current_proxy

        # Select proxy with health-aware load balancing
        proxy = self._select_healthy_proxy()
        if proxy:
            self._current_proxy = proxy
            self._current_proxy_key = self._proxy_key(proxy)
            self._request_count += 1
            return proxy

        return None

    def _select_healthy_proxy(self) -> Optional[dict]:
        """Select the best proxy using weighted load balancing based on health."""
        # Build proxy from primary provider
        creds = self.config.get("credentials", {})
        if creds.get("host"):
            country = random.choice(
                self.config.get("rotation", {}).get("country_targets", ["US"])
            )
            session_id = random.randint(100000, 999999)
            proxy = {
                "server": f"http://{creds['host']}:{creds.get('port', 22225)}",
                "username": f"{creds.get('username', '')}-country-{country.lower()}-session-{session_id}",
                "password": creds.get("password", ""),
            }
            health = self._get_health(proxy)
            if health.is_healthy:
                return proxy

        # Try proxy pools with weighted selection (prefer healthier proxies)
        all_proxies = []
        for pool_name, pool_proxies in self._proxy_pools.items():
            for p in pool_proxies:
                if p.get("server"):
                    all_proxies.append(p)

        if not all_proxies:
            return None

        # Filter to healthy proxies; if none are healthy, use all
        healthy = [p for p in all_proxies if self._get_health(p).is_healthy]
        candidates = healthy if healthy else all_proxies

        # Weight by inverse failure rate (healthier proxies get more weight)
        weights = []
        for p in candidates:
            h = self._get_health(p)
            weight = max(0.1, 1.0 - h.failure_rate)
            weights.append(weight)

        chosen = random.choices(candidates, weights=weights, k=1)[0]
        return {"server": chosen.get("server", "")}

    def record_success(self, latency_ms: float = 0.0):
        """Record a successful request through the current proxy."""
        if self._current_proxy:
            self._get_health(self._current_proxy).record_success(latency_ms)

    def record_failure(self):
        """Record a failed request through the current proxy."""
        if self._current_proxy:
            health = self._get_health(self._current_proxy)
            health.record_failure()
            if not health.is_healthy:
                logger.warning(
                    f"  Proxy {self._proxy_key(self._current_proxy)} marked unhealthy "
                    f"({health.consecutive_failures} consecutive failures)"
                )
                self.rotate()

    def rotate(self):
        """Force rotation to a new proxy on next get_proxy() call."""
        self._current_proxy = None
        self._current_proxy_key = None

    async def health_check(self, test_url: str = "https://httpbin.org/ip"):
        """
        Run health checks on all known proxies.
        Marks unhealthy proxies and logs status.
        """
        try:
            import aiohttp
        except ImportError:
            return

        checked = 0
        healthy_count = 0

        for pool_name, pool_proxies in self._proxy_pools.items():
            for proxy_config in pool_proxies:
                server = proxy_config.get("server", "")
                if not server:
                    continue

                health = self._get_health(proxy_config)
                start = time.monotonic()

                try:
                    proxy_url = server
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            test_url,
                            proxy=proxy_url,
                            timeout=aiohttp.ClientTimeout(total=10),
                        ) as resp:
                            latency_ms = (time.monotonic() - start) * 1000
                            if resp.status == 200:
                                health.record_success(latency_ms)
                                healthy_count += 1
                            else:
                                health.record_failure()
                except Exception:
                    health.record_failure()

                checked += 1
                health.last_check_time = time.monotonic()

        if checked > 0:
            logger.info(
                f"  Proxy health check: {healthy_count}/{checked} healthy"
            )

    def get_healthy_count(self) -> int:
        """Return the number of currently healthy proxies."""
        return sum(1 for h in self._proxy_health.values() if h.is_healthy)

    @property
    def stats(self) -> dict:
        healthy = sum(1 for h in self._proxy_health.values() if h.is_healthy)
        total = len(self._proxy_health)
        return {
            "enabled": self.enabled,
            "provider": self.config.get("provider", "none"),
            "total_requests_proxied": self._request_count,
            "proxy_pools": len(self._proxy_pools),
            "proxies_tracked": total,
            "proxies_healthy": healthy,
            "proxies_unhealthy": total - healthy,
        }
