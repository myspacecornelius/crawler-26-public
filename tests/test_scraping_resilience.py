"""Tests for circuit breaker, domain limiter, and metrics."""

import asyncio
import pytest
from scraping.circuit_breaker import CircuitBreaker, CircuitState, DomainCircuitBreakerManager
from scraping.domain_limiter import DomainConcurrencyLimiter
from scraping.metrics import ScrapeMetrics


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.consecutive_failures == 0
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.0)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # Cooldown is 0, so should transition to HALF_OPEN
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_to_closed_on_success(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.0)
        cb.record_failure()
        cb.allow_request()  # transitions to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_to_open_on_failure(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.0)
        cb.record_failure()
        cb.allow_request()  # transitions to HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_stats(self):
        cb = CircuitBreaker()
        cb.record_success()
        cb.record_failure()
        stats = cb.stats
        assert stats["total_successes"] == 1
        assert stats["total_failures"] == 1
        assert stats["state"] == "closed"


class TestDomainCircuitBreakerManager:
    def test_separate_circuits_per_domain(self):
        mgr = DomainCircuitBreakerManager(failure_threshold=2)
        # Fail domain A
        mgr.record_failure("https://a.com/page1")
        mgr.record_failure("https://a.com/page2")
        assert mgr.allow_request("https://a.com/team") is False

        # Domain B should still be open
        assert mgr.allow_request("https://b.com/team") is True

    def test_www_normalization(self):
        mgr = DomainCircuitBreakerManager(failure_threshold=2)
        mgr.record_failure("https://www.example.com/a")
        mgr.record_failure("https://example.com/b")
        assert mgr.allow_request("https://www.example.com/c") is False

    def test_get_open_circuits(self):
        mgr = DomainCircuitBreakerManager(failure_threshold=1)
        mgr.record_failure("https://blocked.com")
        mgr.record_success("https://ok.com")
        open_list = mgr.get_open_circuits()
        assert "blocked.com" in open_list
        assert "ok.com" not in open_list

    def test_stats(self):
        mgr = DomainCircuitBreakerManager(failure_threshold=1)
        mgr.record_failure("https://blocked.com")
        stats = mgr.stats
        assert stats["open_circuits"] == 1
        assert "blocked.com" in stats["domains_open"]


class TestDomainConcurrencyLimiter:
    @pytest.mark.asyncio
    async def test_limits_per_domain(self):
        limiter = DomainConcurrencyLimiter(max_per_domain=1, global_max=10)
        acquired = []

        async def acquire_and_hold(url, delay):
            async with limiter.acquire(url):
                acquired.append(url)
                await asyncio.sleep(delay)

        # Two tasks for the same domain should be serialized
        t1 = asyncio.create_task(acquire_and_hold("https://a.com/1", 0.1))
        await asyncio.sleep(0.01)  # Let t1 start
        t2 = asyncio.create_task(acquire_and_hold("https://a.com/2", 0.1))

        # At this point, only t1 should have acquired
        await asyncio.sleep(0.05)
        assert len(acquired) == 1

        await asyncio.gather(t1, t2)
        assert len(acquired) == 2

    @pytest.mark.asyncio
    async def test_different_domains_concurrent(self):
        limiter = DomainConcurrencyLimiter(max_per_domain=1, global_max=10)
        acquired = []

        async def acquire_and_hold(url, delay):
            async with limiter.acquire(url):
                acquired.append(url)
                await asyncio.sleep(delay)

        # Two different domains should run concurrently
        t1 = asyncio.create_task(acquire_and_hold("https://a.com/1", 0.1))
        t2 = asyncio.create_task(acquire_and_hold("https://b.com/1", 0.1))

        await asyncio.sleep(0.05)
        assert len(acquired) == 2  # Both should have acquired

        await asyncio.gather(t1, t2)

    @pytest.mark.asyncio
    async def test_global_limit(self):
        limiter = DomainConcurrencyLimiter(max_per_domain=5, global_max=2)
        acquired_count = 0

        async def acquire_and_hold(url, delay):
            nonlocal acquired_count
            async with limiter.acquire(url):
                acquired_count += 1
                await asyncio.sleep(delay)

        tasks = [
            asyncio.create_task(acquire_and_hold(f"https://domain{i}.com", 0.15))
            for i in range(5)
        ]

        await asyncio.sleep(0.05)
        # Only global_max (2) should be running
        assert acquired_count <= 2

        await asyncio.gather(*tasks)
        assert acquired_count == 5


class TestScrapeMetrics:
    def test_record_request_and_success(self):
        m = ScrapeMetrics()
        m.record_request("https://a.com")
        m.record_success("https://a.com", leads_found=5, extraction_time_s=1.2)
        s = m.summary()
        assert s["global"]["total_requests"] == 1
        assert s["global"]["total_successes"] == 1
        assert s["global"]["total_leads"] == 5

    def test_record_failure(self):
        m = ScrapeMetrics()
        m.record_request("https://a.com")
        m.record_failure("https://a.com", blocked=True)
        s = m.summary()
        assert s["global"]["total_failures"] == 1
        assert s["global"]["total_blocks"] == 1

    def test_block_rate(self):
        m = ScrapeMetrics()
        for _ in range(8):
            m.record_request("https://a.com")
            m.record_success("https://a.com")
        for _ in range(2):
            m.record_request("https://a.com")
            m.record_failure("https://a.com", blocked=True)
        assert abs(m.block_rate - 0.2) < 0.01

    def test_success_rate(self):
        m = ScrapeMetrics()
        m.record_request("https://a.com")
        m.record_success("https://a.com")
        m.record_request("https://b.com")
        m.record_failure("https://b.com")
        assert abs(m.success_rate - 0.5) < 0.01

    def test_avg_extraction_time(self):
        m = ScrapeMetrics()
        m.record_success("https://a.com", extraction_time_s=2.0)
        m.record_success("https://a.com", extraction_time_s=4.0)
        assert abs(m.avg_extraction_time() - 3.0) < 0.01

    def test_top_domains_by_leads(self):
        m = ScrapeMetrics()
        m.record_success("https://a.com", leads_found=10)
        m.record_success("https://b.com", leads_found=20)
        m.record_success("https://c.com", leads_found=5)
        top = m.top_domains_by_leads(2)
        assert len(top) == 2
        assert top[0]["domain"] == "b.com"
        assert top[1]["domain"] == "a.com"

    def test_blocked_domains(self):
        m = ScrapeMetrics()
        m.record_failure("https://blocked.com", blocked=True)
        m.record_success("https://ok.com")
        blocked = m.blocked_domains()
        assert "blocked.com" in blocked
        assert "ok.com" not in blocked

    def test_circuit_trip_recording(self):
        m = ScrapeMetrics()
        m.record_circuit_trip("https://tripped.com")
        s = m.summary()
        assert s["global"]["total_circuit_trips"] == 1
