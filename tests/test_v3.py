"""
CRAWL — V3 Optimization Tests
Covers: lead score enrichment, email pattern detection, expanded seed DB, SMTP verification.
Run with: venv/bin/python3 -m pytest tests/test_v3.py -v
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.base import InvestorLead
from enrichment.email_guesser import (
    detect_pattern, generate_candidates, _extract_domain,
    PatternStore, EmailGuesser, _normalize,
)
from enrichment.email_validator import EmailValidator


# ──────────────────────────────────────────────────
#  Email Pattern Detection
# ──────────────────────────────────────────────────

class TestPatternDetection:
    def test_detect_first_at_domain(self):
        pattern = detect_pattern("john@accel.com", "John Smith")
        assert pattern == "{first}@{domain}"

    def test_detect_first_dot_last(self):
        pattern = detect_pattern("john.smith@accel.com", "John Smith")
        assert pattern == "{first}.{last}@{domain}"

    def test_detect_flast(self):
        pattern = detect_pattern("jsmith@accel.com", "John Smith")
        assert pattern == "{f}{last}@{domain}"

    def test_detect_firstlast(self):
        pattern = detect_pattern("johnsmith@accel.com", "John Smith")
        assert pattern == "{first}{last}@{domain}"

    def test_detect_f_dot_last(self):
        pattern = detect_pattern("j.smith@accel.com", "John Smith")
        assert pattern == "{f}.{last}@{domain}"

    def test_detect_last_only(self):
        pattern = detect_pattern("smith@accel.com", "John Smith")
        assert pattern == "{last}@{domain}"

    def test_detect_first_underscore_last(self):
        pattern = detect_pattern("john_smith@accel.com", "John Smith")
        assert pattern == "{first}_{last}@{domain}"

    def test_detect_returns_none_for_unknown(self):
        pattern = detect_pattern("random123@accel.com", "John Smith")
        assert pattern is None

    def test_detect_returns_none_for_single_name(self):
        pattern = detect_pattern("john@accel.com", "John")
        assert pattern is None

    def test_detect_handles_accented_names(self):
        pattern = detect_pattern("rene@fund.com", "René Dupont")
        assert pattern == "{first}@{domain}"


class TestPatternStore:
    def test_learn_and_get(self):
        cache = PatternStore()
        cache.learn("accel.com", "john@accel.com", "John Smith")
        assert cache.get("accel.com") == "{first}@{domain}"

    def test_apply_known_pattern(self):
        cache = PatternStore()
        cache.learn("accel.com", "john@accel.com", "John Smith")
        email = cache.apply("Jane Doe", "accel.com")
        assert email == "jane@accel.com"

    def test_apply_unknown_domain_returns_none(self):
        cache = PatternStore()
        assert cache.apply("Jane Doe", "unknown.com") is None

    def test_learn_does_not_overwrite(self):
        cache = PatternStore()
        cache.learn("accel.com", "john@accel.com", "John Smith")
        cache.learn("accel.com", "john.smith@accel.com", "John Smith")
        # First pattern should stick
        assert cache.get("accel.com") == "{first}@{domain}"

    def test_domains_known_count(self):
        cache = PatternStore()
        assert cache.domains_known == 0
        cache.learn("a.com", "john@a.com", "John Smith")
        cache.learn("b.com", "john.smith@b.com", "John Smith")
        assert cache.domains_known == 2

    def test_apply_with_first_dot_last_pattern(self):
        cache = PatternStore()
        cache.learn("fund.com", "john.smith@fund.com", "John Smith")
        email = cache.apply("Alice Johnson", "fund.com")
        assert email == "alice.johnson@fund.com"

    def test_apply_returns_none_for_single_name(self):
        cache = PatternStore()
        cache.learn("fund.com", "john@fund.com", "John Smith")
        assert cache.apply("Madonna", "fund.com") is None


class TestGuesserPatternIntegration:
    def test_guesser_has_pattern_store(self):
        guesser = EmailGuesser()
        assert hasattr(guesser, '_pattern_store')
        assert isinstance(guesser._pattern_store, PatternStore)

    def test_guesser_stats_has_pattern_hits(self):
        guesser = EmailGuesser()
        assert "pattern_hits" in guesser.stats

    def test_guess_batch_learns_from_existing_emails(self):
        async def run():
            guesser = EmailGuesser()
            leads = [
                InvestorLead(name="John Smith", email="john@fund.com", website="https://fund.com"),
                InvestorLead(name="Jane Doe", email="N/A", website="https://fund.com"),
            ]
            # Mock validator to avoid real DNS
            with patch.object(guesser, 'guess', new=AsyncMock(return_value=None)):
                await guesser.guess_batch(leads)
            # Pattern should have been learned
            assert guesser._pattern_store.get("fund.com") == "{first}@{domain}"
            # Jane should get pattern-based email
            assert leads[1].email == "jane@fund.com"
        asyncio.run(run())

    def test_guess_batch_pattern_hits_counted(self):
        async def run():
            guesser = EmailGuesser()
            leads = [
                InvestorLead(name="John Smith", email="john@fund.com", website="https://fund.com"),
                InvestorLead(name="Jane Doe", email="N/A", website="https://fund.com"),
                InvestorLead(name="Bob Jones", email="N/A", website="https://fund.com"),
            ]
            with patch.object(guesser, 'guess', new=AsyncMock(return_value=None)):
                await guesser.guess_batch(leads)
            assert guesser.stats["pattern_hits"] == 2  # Jane + Bob
        asyncio.run(run())


# ──────────────────────────────────────────────────
#  SMTP Verification
# ──────────────────────────────────────────────────

class TestSMTPVerification:
    def test_validator_has_smtp_cache(self):
        v = EmailValidator()
        assert hasattr(v, '_smtp_cache')

    def test_verify_smtp_exists(self):
        assert hasattr(EmailValidator, 'verify_smtp')

    def test_validate_batch_deep_exists(self):
        assert hasattr(EmailValidator, 'validate_batch_deep')

    def test_verify_smtp_rejects_empty(self):
        async def run():
            v = EmailValidator()
            result = await v.verify_smtp("")
            assert result["deliverable"] is False
        asyncio.run(run())

    def test_verify_smtp_rejects_no_at(self):
        async def run():
            v = EmailValidator()
            result = await v.verify_smtp("noemail")
            assert result["deliverable"] is False
        asyncio.run(run())

    def test_cache_stats_includes_smtp(self):
        v = EmailValidator()
        stats = v.cache_stats
        assert "smtp_checks_cached" in stats

    def test_validate_batch_deep_runs(self):
        async def run():
            v = EmailValidator()
            results = await v.validate_batch_deep(["test@example.com"], smtp_check=False)
            assert len(results) == 1
            assert "valid_format" in results[0]
        asyncio.run(run())


# ──────────────────────────────────────────────────
#  Lead Score Enrichment (metadata inheritance)
# ──────────────────────────────────────────────────

class TestLeadScoreEnrichment:
    def test_engine_run_deep_crawl_has_fund_meta_logic(self):
        import inspect
        import engine
        source = inspect.getsource(engine.CrawlEngine._run_deep_crawl)
        assert "fund_meta" in source
        assert "focus_areas" in source
        assert "enriched_count" in source

    def test_engine_has_skip_smtp_flag(self):
        import engine
        import inspect
        source = inspect.getsource(engine.parse_args)
        assert "skip-smtp" in source or "skip_smtp" in source


# ──────────────────────────────────────────────────
#  Expanded Seed DB
# ──────────────────────────────────────────────────

class TestExpandedSeedDB:
    def test_seed_db_has_500_plus(self):
        from sources.seed_db import load_seed_leads
        leads = load_seed_leads()
        assert len(leads) >= 500, f"Seed DB only has {len(leads)} leads after dedup — need 500+"

    def test_seed_db_has_international_vcs(self):
        from sources.seed_db import load_seed_leads
        leads = load_seed_leads()
        locations = {l.location for l in leads}
        international = [loc for loc in locations if any(
            country in loc for country in ("UK", "Germany", "India", "Singapore", "France", "Japan", "Brazil")
        )]
        assert len(international) >= 5, f"Only {len(international)} international locations found"

    def test_seed_db_has_sector_specialists(self):
        from sources.seed_db import load_seed_leads
        leads = load_seed_leads()
        all_areas = set()
        for lead in leads:
            for area in lead.focus_areas:
                all_areas.add(area.lower())
        for sector in ("healthtech", "fintech", "climate", "gaming", "biotech", "edtech"):
            assert any(sector in a for a in all_areas), f"Missing sector: {sector}"

    def test_seed_db_has_growth_stage_firms(self):
        from sources.seed_db import load_seed_leads
        leads = load_seed_leads()
        growth = [l for l in leads if "Growth" in l.stage]
        assert len(growth) >= 20, f"Only {len(growth)} growth-stage firms"

    def test_seed_db_websites_are_resolvable(self):
        from sources.seed_db import load_seed_leads
        leads = load_seed_leads()
        with_website = [l for l in leads if l.website and l.website != "N/A" and l.website.startswith("http")]
        ratio = len(with_website) / len(leads)
        assert ratio > 0.95, f"Only {ratio:.0%} have valid http(s) websites"
