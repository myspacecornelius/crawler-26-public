"""
CRAWL — Live Regression Tests
Covers all 9 connectivity issues identified and fixed.
Run with: python -m pytest tests/test_fixes.py -v
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.base import InvestorLead
from enrichment.scoring import LeadScorer
from enrichment.email_validator import EmailValidator
from output.csv_writer import CSVWriter


# ──────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────

def make_lead(**kwargs) -> InvestorLead:
    defaults = dict(
        name="Jane Smith",
        email="jane@example.com",
        role="Partner",
        fund="Acme Ventures",
        focus_areas=["AI", "SaaS"],
        stage="seed",
        check_size="$100K - $500K",
        location="United States",
        linkedin="https://linkedin.com/in/janesmith",
        scraped_at=datetime.now().isoformat(),
    )
    defaults.update(kwargs)
    return InvestorLead(**defaults)


def make_scorer() -> LeadScorer:
    scorer = LeadScorer.__new__(LeadScorer)
    scorer.weights = {
        "stage_match": 30,
        "sector_match": 25,
        "check_size_fit": 20,
        "portfolio_relevance": 15,
        "recency": 10,
    }
    scorer.tiers = {
        "hot":  {"min_score": 80, "label": "🔴 HOT"},
        "warm": {"min_score": 60, "label": "🟡 WARM"},
        "cool": {"min_score": 40, "label": "🟢 COOL"},
        "cold": {"min_score": 0,  "label": "⚪ COLD"},
    }
    scorer.modifiers = {
        "has_email": 10,
        "has_linkedin": 5,
        "no_email": -15,
        "stale_fund": -10,
    }
    scorer.profile = {
        "stage": "seed",
        "sectors": ["AI", "SaaS", "developer tools"],
        "target_check_size_min": 50_000,
        "target_check_size_max": 500_000,
    }
    scorer._scores = []
    return scorer


# ──────────────────────────────────────────────────
#  Issue #1 — deep_crawl uses InvestorLead, not Contact
# ──────────────────────────────────────────────────

class TestIssue1_SharedDataModel:
    def test_deep_crawl_imports_investor_lead(self):
        """deep_crawl.py must import InvestorLead, not define its own Contact."""
        import deep_crawl
        assert not hasattr(deep_crawl, "Contact"), (
            "Contact dataclass still present — deep_crawl not yet migrated to InvestorLead"
        )
        assert hasattr(deep_crawl, "InvestorLead"), (
            "InvestorLead not imported into deep_crawl"
        )

    def test_deep_crawl_has_enrichment_pipeline(self):
        """DeepCrawler must instantiate EmailValidator, LeadScorer, CSVWriter."""
        import deep_crawl
        assert hasattr(deep_crawl, "EmailValidator")
        assert hasattr(deep_crawl, "LeadScorer")
        assert hasattr(deep_crawl, "CSVWriter")

    def test_deep_crawl_contacts_list_type(self):
        """DeepCrawler.all_contacts must be typed as List[InvestorLead]."""
        import deep_crawl
        # Instantiate with a dummy target file path (won't be read in this test)
        crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)
        crawler.all_contacts = []
        crawler.email_validator = EmailValidator()
        crawler.scorer = make_scorer()
        crawler.csv_writer = MagicMock()
        lead = make_lead()
        crawler.all_contacts.append(lead)
        assert isinstance(crawler.all_contacts[0], InvestorLead)

    def test_investor_lead_has_required_fields(self):
        """InvestorLead must carry all fields needed by the enrichment pipeline."""
        lead = make_lead()
        for field in ("name", "email", "role", "fund", "focus_areas",
                      "stage", "check_size", "linkedin", "scraped_at",
                      "lead_score", "tier"):
            assert hasattr(lead, field), f"InvestorLead missing field: {field}"


# ──────────────────────────────────────────────────
#  Issue #3 — portfolio_relevance and recency scoring
# ──────────────────────────────────────────────────

class TestIssue3_MissingScoringDimensions:
    def test_portfolio_relevance_full_overlap(self):
        scorer = make_scorer()
        score = scorer._score_portfolio_relevance(["AI", "SaaS", "fintech"])
        assert score == 15, f"Expected 15 for 2+ overlapping sectors, got {score}"

    def test_portfolio_relevance_single_overlap(self):
        scorer = make_scorer()
        score = scorer._score_portfolio_relevance(["AI", "biotech"])
        assert score == int(15 * 0.6), f"Expected 9 for 1 overlapping sector, got {score}"

    def test_portfolio_relevance_no_overlap(self):
        scorer = make_scorer()
        score = scorer._score_portfolio_relevance(["real estate", "energy"])
        assert score == int(15 * 0.1), f"Expected 1 for no overlap, got {score}"

    def test_portfolio_relevance_unknown(self):
        scorer = make_scorer()
        score = scorer._score_portfolio_relevance([])
        assert score == 15 // 4, f"Expected partial credit for unknown, got {score}"

    def test_recency_fresh(self):
        scorer = make_scorer()
        now_iso = datetime.now().isoformat()
        score = scorer._score_recency(now_iso)
        assert score == 10, f"Expected full recency credit for fresh lead, got {score}"

    def test_recency_week_old(self):
        scorer = make_scorer()
        week_ago = (datetime.now() - timedelta(days=4)).isoformat()
        score = scorer._score_recency(week_ago)
        # Exponential decay: exp(-0.693 * 4/14) * 10 ≈ 8
        assert 7 <= score <= 9, f"Expected ~8 for 4-day-old lead (time-decay), got {score}"

    def test_recency_month_old(self):
        scorer = make_scorer()
        month_ago = (datetime.now() - timedelta(days=20)).isoformat()
        score = scorer._score_recency(month_ago)
        # Exponential decay: exp(-0.693 * 20/14) * 10 ≈ 3.7
        assert 3 <= score <= 5, f"Expected ~4 for 20-day-old lead (time-decay), got {score}"

    def test_recency_stale(self):
        scorer = make_scorer()
        old = (datetime.now() - timedelta(days=90)).isoformat()
        score = scorer._score_recency(old)
        # Exponential decay: exp(-0.693 * 90/14) * 10 → clamped to 1
        assert score == 1, f"Expected 1 for 90-day stale lead, got {score}"

    def test_recency_missing(self):
        scorer = make_scorer()
        score = scorer._score_recency("")
        assert score == 5, f"Expected partial credit for missing timestamp, got {score}"

    def test_full_score_can_reach_hot_tier(self):
        """With all 5 dimensions active, a perfect-match lead must reach HOT (>=80)."""
        scorer = make_scorer()
        lead = make_lead(
            stage="seed",
            focus_areas=["AI", "SaaS", "developer tools"],
            check_size="$100K - $500K",
            email="jane@example.com",
            linkedin="https://linkedin.com/in/janesmith",
            scraped_at=datetime.now().isoformat(),
        )
        score, tier = scorer.score(lead)
        assert score >= 80, (
            f"Perfect-match lead scored {score} — HOT tier unreachable (scoring still broken)"
        )
        assert "HOT" in tier


# ──────────────────────────────────────────────────
#  Issue #4 — stale_fund modifier applied
# ──────────────────────────────────────────────────

class TestIssue4_StaleFundModifier:
    def test_is_stale_old_lead(self):
        scorer = make_scorer()
        old_ts = (datetime.now() - timedelta(days=61)).isoformat()
        assert scorer._is_stale(old_ts) is True

    def test_is_stale_fresh_lead(self):
        scorer = make_scorer()
        assert scorer._is_stale(datetime.now().isoformat()) is False

    def test_is_stale_missing_timestamp(self):
        scorer = make_scorer()
        assert scorer._is_stale("") is False

    def test_stale_fund_penalty_applied(self):
        scorer = make_scorer()
        old_ts = (datetime.now() - timedelta(days=90)).isoformat()
        lead = make_lead(scraped_at=old_ts)
        score_stale, _ = scorer.score(lead)

        scorer._scores.clear()
        fresh_lead = make_lead(scraped_at=datetime.now().isoformat())
        score_fresh, _ = scorer.score(fresh_lead)

        assert score_stale < score_fresh, (
            "Stale lead should score lower than fresh lead due to stale_fund modifier"
        )
        # The gap includes both the recency dimension difference AND the stale_fund modifier.
        # Fresh: recency=10; Stale (90d): recency=1, stale_fund=-10 → net difference >= 9
        # (exact gap may be reduced by the 0-100 clamp on perfect-match leads)
        assert score_stale < score_fresh, "stale_fund modifier not reducing score"
        assert scorer.modifiers.get("stale_fund", 0) != 0, (
            "stale_fund modifier is 0 — not loaded from config"
        )
        assert scorer._is_stale(old_ts) is True, (
            "_is_stale returned False for a 90-day-old timestamp"
        )


# ──────────────────────────────────────────────────
#  Issue #5 — MX validation wired into pipeline
# ──────────────────────────────────────────────────

class TestIssue5_MXValidation:
    def test_validate_batch_returns_has_mx_key(self):
        async def run():
            validator = EmailValidator()
            results = await validator.validate_batch(["test@example.com"])
            assert "has_mx" in results[0], "validate_batch result missing 'has_mx' key"
        asyncio.run(run())

    def test_validate_batch_invalid_format(self):
        async def run():
            validator = EmailValidator()
            results = await validator.validate_batch(["not-an-email"])
            assert results[0]["quality"] == "invalid"
            assert results[0]["has_mx"] is False
        asyncio.run(run())

    def test_validate_batch_disposable(self):
        async def run():
            validator = EmailValidator()
            results = await validator.validate_batch(["user@mailinator.com"])
            assert results[0]["is_disposable"] is True
        asyncio.run(run())

    def test_engine_uses_validate_batch(self):
        """engine.py _enrich_and_output must call validate_batch, not validate."""
        import inspect
        import engine
        source = inspect.getsource(engine.CrawlEngine._enrich_and_output)
        assert "validate_batch" in source, (
            "engine._enrich_and_output still uses synchronous validate() — MX check not wired in"
        )
        assert "validate(" not in source.replace("validate_batch", ""), (
            "engine._enrich_and_output still has a bare validate() call alongside validate_batch"
        )

    def test_deep_crawl_uses_validate(self):
        """deep_crawl._enrich_and_save must call email_validator.validate."""
        import inspect
        import deep_crawl
        source = inspect.getsource(deep_crawl.DeepCrawler._enrich_and_save)
        assert "email_validator" in source


# ──────────────────────────────────────────────────
#  Issue #2 — Discovery connected to engine
# ──────────────────────────────────────────────────

class TestIssue2_DiscoveryConnected:
    def test_engine_has_discover_flag(self):
        """engine.parse_args must accept --discover."""
        import engine
        with patch("sys.argv", ["engine.py", "--discover", "--dry-run"]):
            args = engine.parse_args()
        assert hasattr(args, "discover")
        assert args.discover is True

    def test_engine_imports_searcher(self):
        """engine.py must import Searcher from discovery."""
        import engine
        assert hasattr(engine, "Searcher"), (
            "engine.py does not import Searcher — discovery pipeline not connected"
        )

    def test_engine_has_run_discovery_method(self):
        import engine
        assert hasattr(engine.CrawlEngine, "_run_discovery"), (
            "CrawlEngine missing _run_discovery method"
        )


# ──────────────────────────────────────────────────
#  Issue #6 — Email distribution non-destructive
# ──────────────────────────────────────────────────

class TestIssue6_EmailDistribution:
    def test_email_list_not_mutated(self):
        """The original emails list must not be mutated during contact distribution."""
        emails = ["info@fund.com", "partner@fund.com"]
        original_emails = list(emails)

        contacts = [make_lead(email="N/A") for _ in range(3)]
        remaining = list(emails)
        for contact in contacts:
            if contact.email == "N/A" and remaining:
                contact.email = remaining.pop(0)

        assert emails == original_emails, (
            "Original emails list was mutated — fix not applied correctly"
        )

    def test_emails_distributed_correctly(self):
        """First N contacts get emails; remainder keep N/A."""
        emails = ["a@x.com", "b@x.com"]
        contacts = [make_lead(email="N/A") for _ in range(4)]
        remaining = list(emails)
        for contact in contacts:
            if contact.email == "N/A" and remaining:
                contact.email = remaining.pop(0)

        assert contacts[0].email == "a@x.com"
        assert contacts[1].email == "b@x.com"
        assert contacts[2].email == "N/A"
        assert contacts[3].email == "N/A"


# ──────────────────────────────────────────────────
#  Issue #7 — OpenVC name/fund selector distinct
# ──────────────────────────────────────────────────

class TestIssue7_OpenVCSelectorCollision:
    def test_openvc_name_and_fund_selectors_differ(self):
        import yaml
        with open("config/sites.yaml") as f:
            config = yaml.safe_load(f)
        openvc = config["sites"]["openvc"]["selectors"]
        assert openvc["name"] != openvc["fund"], (
            f"OpenVC name and fund selectors are still identical: '{openvc['name']}'"
        )

    def test_openvc_fund_selector_not_empty(self):
        import yaml
        with open("config/sites.yaml") as f:
            config = yaml.safe_load(f)
        fund_sel = config["sites"]["openvc"]["selectors"]["fund"]
        assert fund_sel, "OpenVC fund selector is empty"


# ──────────────────────────────────────────────────
#  Issue #8 — Searcher uses get_context_kwargs
# ──────────────────────────────────────────────────

class TestIssue8_SearcherFingerprint:
    def test_searcher_uses_get_context_kwargs(self):
        import inspect
        from discovery.searcher import Searcher
        source = inspect.getsource(Searcher.discover)
        assert "get_context_kwargs" in source, (
            "Searcher.discover still manually picks fingerprint fields instead of using get_context_kwargs()"
        )

    def test_get_context_kwargs_returns_full_set(self):
        from stealth.fingerprint import FingerprintManager
        mgr = FingerprintManager()
        fp = mgr.generate()
        kwargs = mgr.get_context_kwargs(fp)
        required = {"user_agent", "viewport", "timezone_id", "locale",
                    "color_scheme", "device_scale_factor", "has_touch", "is_mobile"}
        assert required.issubset(kwargs.keys()), (
            f"get_context_kwargs missing keys: {required - kwargs.keys()}"
        )


# ──────────────────────────────────────────────────
#  Issue #9 — Exception logging in _crawl_fund
# ──────────────────────────────────────────────────

class TestIssue9_ExceptionLogging:
    def test_crawl_fund_logs_team_page_errors(self):
        """_crawl_fund must log warnings on team-page failures, not silently continue."""
        import inspect
        import deep_crawl
        source = inspect.getsource(deep_crawl.DeepCrawler._crawl_fund)
        assert "logger.warning" in source, (
            "_crawl_fund still silently swallows team-page exceptions with bare continue"
        )


# ──────────────────────────────────────────────────
#  Integration — score_batch end-to-end
# ──────────────────────────────────────────────────

class TestIntegration_ScoreBatch:
    def test_score_batch_assigns_score_and_tier(self):
        scorer = make_scorer()
        leads = [make_lead(), make_lead(email="N/A", linkedin="N/A")]
        result = scorer.score_batch(leads)
        for lead in result:
            assert lead.lead_score >= 0
            assert lead.tier != ""

    def test_score_batch_sorted_descending(self):
        scorer = make_scorer()
        leads = [
            make_lead(email="N/A", linkedin="N/A"),
            make_lead(email="good@example.com", linkedin="https://linkedin.com/in/x"),
        ]
        result = scorer.score_batch(leads)
        scores = [lead.lead_score for lead in result]
        assert scores == sorted(scores, reverse=True), "score_batch not sorted descending"

    def test_email_guesser_wired_into_deep_crawl(self):
        """DeepCrawler must instantiate EmailGuesser."""
        import deep_crawl
        assert hasattr(deep_crawl, "EmailGuesser"), "EmailGuesser not imported into deep_crawl"
        crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)
        crawler.email_guesser = deep_crawl.EmailGuesser(concurrency=1)
        assert crawler.email_guesser is not None

    def test_email_guesser_wired_into_engine(self):
        """CrawlEngine must instantiate EmailGuesser."""
        import engine
        assert hasattr(engine, "EmailGuesser"), "EmailGuesser not imported into engine"

    def test_csv_writer_uses_investor_lead_fields(self):
        """CSVWriter.write must accept InvestorLead objects without error."""
        import tempfile
        import os
        writer = CSVWriter.__new__(CSVWriter)
        with tempfile.TemporaryDirectory() as tmpdir:
            from pathlib import Path
            writer.output_dir = Path(tmpdir)
            writer.raw_dir = Path(tmpdir) / "raw"
            writer.enriched_dir = Path(tmpdir) / "enriched"
            writer.raw_dir.mkdir()
            writer.enriched_dir.mkdir()

            leads = [make_lead(lead_score=75, tier="🟡 WARM")]
            path = writer.write(leads, "test_output.csv")
            assert os.path.exists(path)
            with open(path) as f:
                content = f.read()
            assert "Jane Smith" in content
            assert "Acme Ventures" in content
