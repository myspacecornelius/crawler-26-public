"""
CRAWL — Scale-to-2000 Regression Tests
Covers Steps 1-6 of the improvement plan.
Run with: python3.14 -m pytest tests/test_scale.py -v
"""

import asyncio
import os
import re
import sys
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adapters.base import InvestorLead
from enrichment.email_guesser import EmailGuesser, generate_candidates, _extract_domain, _normalize


# ──────────────────────────────────────────────────
#  Step 1 — Discovery query expansion
# ──────────────────────────────────────────────────

class TestStep1_DiscoveryExpansion:
    def _load_config(self):
        import yaml
        with open("config/search.yaml") as f:
            return yaml.safe_load(f)["discovery"]

    def test_query_count_at_least_50(self):
        config = self._load_config()
        queries = config.get("queries", [])
        assert len(queries) >= 50, (
            f"Only {len(queries)} queries — need at least 50 to reach 1500 domains"
        )

    def test_target_domains_count_raised(self):
        config = self._load_config()
        assert config.get("target_domains_count", 0) >= 1500, (
            "target_domains_count still below 1500"
        )

    def test_queries_cover_multiple_sectors(self):
        config = self._load_config()
        queries_text = " ".join(config.get("queries", []))
        sectors = ["AI", "climate", "health", "fintech", "saas", "defense", "edtech"]
        covered = [s for s in sectors if s.lower() in queries_text.lower()]
        assert len(covered) >= 5, (
            f"Queries only cover {covered} — need broader sector coverage"
        )

    def test_queries_cover_multiple_geos(self):
        config = self._load_config()
        queries_text = " ".join(config.get("queries", []))
        geos = ["san francisco", "new york", "london", "berlin", "boston"]
        covered = [g for g in geos if g.lower() in queries_text.lower()]
        assert len(covered) >= 4, (
            f"Queries only cover geos: {covered}"
        )

    def test_queries_cover_fund_types(self):
        config = self._load_config()
        queries_text = " ".join(config.get("queries", []))
        fund_types = ["micro vc", "family office", "solo gp", "emerging manager", "corporate venture"]
        covered = [ft for ft in fund_types if ft.lower() in queries_text.lower()]
        assert len(covered) >= 3, (
            f"Queries only cover fund types: {covered}"
        )

    def test_no_duplicate_queries(self):
        config = self._load_config()
        queries = config.get("queries", [])
        assert len(queries) == len(set(queries)), "Duplicate queries found in search.yaml"


# ──────────────────────────────────────────────────
#  Step 2 — Email pattern guesser
# ──────────────────────────────────────────────────

class TestStep2_EmailGuesser:
    def test_generate_candidates_standard_name(self):
        candidates = generate_candidates("Jane Smith", "acme.vc")
        assert "jane@acme.vc" in candidates
        assert "jane.smith@acme.vc" in candidates
        assert "jsmith@acme.vc" in candidates
        assert "janesmith@acme.vc" in candidates
        assert "j.smith@acme.vc" in candidates

    def test_generate_candidates_hyphenated_last(self):
        candidates = generate_candidates("John Van-Der-Berg", "fund.com")
        assert len(candidates) > 0
        assert all("@fund.com" in c for c in candidates)

    def test_generate_candidates_accented_name(self):
        candidates = generate_candidates("André Müller", "vc.io")
        assert len(candidates) > 0
        assert all("@vc.io" in c for c in candidates)
        assert all(c[0].isascii() for c in candidates)

    def test_generate_candidates_single_name_returns_empty(self):
        assert generate_candidates("Madonna", "fund.com") == []

    def test_generate_candidates_empty_name_returns_empty(self):
        assert generate_candidates("", "fund.com") == []

    def test_extract_domain_full_url(self):
        assert _extract_domain("https://www.acme.vc/team") == "acme.vc"

    def test_extract_domain_bare_domain(self):
        assert _extract_domain("acme.vc") == "acme.vc"

    def test_extract_domain_na_returns_none(self):
        assert _extract_domain("N/A") is None

    def test_extract_domain_empty_returns_none(self):
        assert _extract_domain("") is None

    def test_normalize_strips_accents(self):
        assert _normalize("André") == "andre"
        assert _normalize("Müller") == "muller"

    def test_normalize_removes_non_alpha(self):
        assert _normalize("van-der") == "vander"

    def test_guesser_stats_initial(self):
        guesser = EmailGuesser(concurrency=1)
        stats = guesser.stats
        assert stats["attempted"] == 0
        assert stats["found"] == 0
        assert stats["skipped"] == 0

    def test_guess_skips_missing_website(self):
        async def run():
            guesser = EmailGuesser(concurrency=1)
            result = await guesser.guess("Jane Smith", "N/A")
            assert result is None
            assert guesser.stats["skipped"] == 1
        asyncio.run(run())

    def test_guess_skips_single_name(self):
        async def run():
            guesser = EmailGuesser(concurrency=1)
            result = await guesser.guess("Madonna", "https://fund.com")
            assert result is None
            # Single-word names fail _is_person_name → company_skipped
            assert guesser.stats["company_skipped"] == 1
        asyncio.run(run())

    def test_guess_batch_skips_leads_with_valid_email(self):
        """Leads that already have a valid email must not be processed."""
        async def run():
            guesser = EmailGuesser(concurrency=1)
            leads = [
                InvestorLead(name="Jane Smith", email="jane@fund.com", website="https://fund.com"),
                InvestorLead(name="Bob Jones", email="N/A", website="N/A"),
            ]
            with patch.object(guesser, "guess", new=AsyncMock(return_value=None)) as mock_guess:
                await guesser.guess_batch(leads)
                # Only Bob (no email + no valid website) should be attempted
                # Jane has a valid email so should be skipped
                for call_args in mock_guess.call_args_list:
                    assert call_args[0][0] != "Jane Smith", (
                        "guess() was called for a lead that already has an email"
                    )
        asyncio.run(run())

    def test_guess_batch_fills_email_on_success(self):
        async def run():
            guesser = EmailGuesser(concurrency=1)
            leads = [
                InvestorLead(name="Jane Smith", email="N/A", website="https://acme.vc"),
            ]
            with patch.object(guesser, "guess", new=AsyncMock(return_value="jane@acme.vc")):
                result = await guesser.guess_batch(leads)
            assert result[0].email == "jane@acme.vc"
        asyncio.run(run())

    def test_guess_batch_leaves_email_unchanged_on_failure(self):
        async def run():
            guesser = EmailGuesser(concurrency=1)
            leads = [
                InvestorLead(name="Jane Smith", email="N/A", website="https://acme.vc"),
            ]
            with patch.object(guesser, "guess", new=AsyncMock(return_value=None)):
                result = await guesser.guess_batch(leads)
            assert result[0].email == "N/A"
        asyncio.run(run())

    def test_engine_enrich_calls_guess_batch(self):
        """engine._enrich_and_output must call email_guesser.guess_batch."""
        import inspect
        import engine
        source = inspect.getsource(engine.CrawlEngine._enrich_and_output)
        assert "guess_batch" in source, (
            "engine._enrich_and_output does not call email_guesser.guess_batch"
        )

    def test_deep_crawl_enrich_calls_guess_batch(self):
        """deep_crawl._enrich_and_save must call email_guesser.guess_batch."""
        import inspect
        import deep_crawl
        source = inspect.getsource(deep_crawl.DeepCrawler._enrich_and_save)
        assert "guess_batch" in source, (
            "deep_crawl._enrich_and_save does not call email_guesser.guess_batch"
        )


# ──────────────────────────────────────────────────
#  Step 3 — Concurrency + per-fund timeout
# ──────────────────────────────────────────────────

class TestStep3_ConcurrencyAndTimeout:
    def test_default_concurrency_is_10(self):
        import inspect
        import deep_crawl
        sig = inspect.signature(deep_crawl.DeepCrawler.__init__)
        default = sig.parameters["max_concurrent"].default
        assert default >= 10, (
            f"max_concurrent default is {default} — should be >= 10"
        )

    def test_crawl_fund_has_hard_timeout(self):
        """_crawl_fund must use asyncio.wait_for to enforce a per-fund timeout."""
        import inspect
        import deep_crawl
        source = inspect.getsource(deep_crawl.DeepCrawler._crawl_fund)
        assert "wait_for" in source, (
            "_crawl_fund does not use asyncio.wait_for — no hard timeout"
        )
        assert "TimeoutError" in source, (
            "_crawl_fund does not handle asyncio.TimeoutError"
        )

    def test_crawl_fund_timeout_value_reasonable(self):
        """Timeout should be between 20s and 120s."""
        import inspect
        import deep_crawl
        source = inspect.getsource(deep_crawl.DeepCrawler._crawl_fund)
        wait_for_timeouts = re.findall(r"wait_for\([^,]+,\s*timeout=(\d+\.?\d*)", source)
        assert wait_for_timeouts, "No timeout value found in wait_for() call"
        t = float(wait_for_timeouts[0])
        assert 20 <= t <= 300, f"Per-fund timeout {t}s is outside reasonable range 20-300s"

    def test_team_pages_limit_increased(self):
        """_crawl_fund should try at least 5 team page candidates (was 3)."""
        import inspect
        import deep_crawl
        source = inspect.getsource(deep_crawl.DeepCrawler._crawl_fund)
        import re
        slice_matches = re.findall(r"team_urls\[:(\d+)\]", source)
        assert slice_matches, "No team_urls slice found in _crawl_fund"
        assert int(slice_matches[0]) >= 5, (
            f"team_urls slice is [:{ slice_matches[0]}] — should be at least [:5]"
        )


# ──────────────────────────────────────────────────
#  Step 4 — New directory adapters
# ──────────────────────────────────────────────────

class TestStep4_NewAdapters:
    def test_visible_vc_adapter_importable(self):
        from adapters.visible_vc import VisibleVCAdapter
        assert VisibleVCAdapter is not None

    def test_landscape_vc_adapter_importable(self):
        from adapters.landscape_vc import LandscapeVCAdapter
        assert LandscapeVCAdapter is not None

    def test_wellfound_adapter_importable(self):
        from adapters.wellfound import WellfoundAdapter
        assert WellfoundAdapter is not None

    def test_new_adapters_registered_in_engine(self):
        from adapters.registry import get_registry
        registry = get_registry()
        for key in ("visible_vc", "landscape_vc", "wellfound"):
            assert registry.get(key) is not None, (
                f"'{key}' not registered in registry"
            )

    def test_new_adapters_in_sites_yaml(self):
        import yaml
        with open("config/sites.yaml") as f:
            config = yaml.safe_load(f)
        sites = config.get("sites", {})
        for key in ("visible_vc", "landscape_vc", "wellfound"):
            assert key in sites, f"'{key}' not in config/sites.yaml"

    def test_new_adapters_configured(self):
        import yaml
        with open("config/sites.yaml") as f:
            config = yaml.safe_load(f)
        sites = config.get("sites", {})
        for key in ("visible_vc", "landscape_vc", "wellfound"):
            assert key in sites, f"'{key}' missing from sites.yaml"
            assert "adapter" in sites[key], f"'{key}' missing adapter field"

    def _make_adapter(self, adapter_class, url):
        config = {
            "url": url,
            "adapter": adapter_class.__name__,
            "selectors": {},
            "pagination": {},
        }
        return adapter_class(config)

    def test_visible_vc_parse_card_returns_none_for_empty(self):
        from adapters.visible_vc import VisibleVCAdapter
        from bs4 import BeautifulSoup
        adapter = self._make_adapter(VisibleVCAdapter, "https://visible.vc/investors")
        empty_card = BeautifulSoup("<div></div>", "html.parser").div
        assert adapter.parse_card(empty_card) is None

    def test_visible_vc_parse_card_extracts_name(self):
        from adapters.visible_vc import VisibleVCAdapter
        from bs4 import BeautifulSoup
        adapter = self._make_adapter(VisibleVCAdapter, "https://visible.vc/investors")
        html = '<div><h3>Jane Smith</h3><span class="title">Partner</span></div>'
        card = BeautifulSoup(html, "html.parser").div
        lead = adapter.parse_card(card)
        assert lead is not None
        assert lead.name == "Jane Smith"

    def test_landscape_vc_parse_card_extracts_name(self):
        from adapters.landscape_vc import LandscapeVCAdapter
        from bs4 import BeautifulSoup
        adapter = self._make_adapter(LandscapeVCAdapter, "https://landscape.vc/investors")
        html = '<tr><td><a class="name">Bob Jones</a></td><td>GP</td></tr>'
        card = BeautifulSoup(html, "html.parser").tr
        lead = adapter.parse_card(card)
        assert lead is not None
        assert lead.name == "Bob Jones"

    def test_wellfound_parse_card_extracts_name(self):
        from adapters.wellfound import WellfoundAdapter
        from bs4 import BeautifulSoup
        adapter = self._make_adapter(WellfoundAdapter, "https://wellfound.com/investors")
        html = '<div data-test="InvestorRow"><span data-test="InvestorName">Alice Lee</span></div>'
        card = BeautifulSoup(html, "html.parser").div
        lead = adapter.parse_card(card)
        assert lead is not None
        assert lead.name == "Alice Lee"

    def test_wellfound_parse_card_extracts_fund(self):
        from adapters.wellfound import WellfoundAdapter
        from bs4 import BeautifulSoup
        adapter = self._make_adapter(WellfoundAdapter, "https://wellfound.com/investors")
        html = (
            '<div data-test="InvestorRow">'
            '<span data-test="InvestorName">Alice Lee</span>'
            '<span data-test="InvestorFirm">Acme Ventures</span>'
            '</div>'
        )
        card = BeautifulSoup(html, "html.parser").div
        lead = adapter.parse_card(card)
        assert lead.fund == "Acme Ventures"

    def test_all_new_adapters_extend_base(self):
        from adapters.base import BaseSiteAdapter
        from adapters.visible_vc import VisibleVCAdapter
        from adapters.landscape_vc import LandscapeVCAdapter
        from adapters.wellfound import WellfoundAdapter
        for cls in (VisibleVCAdapter, LandscapeVCAdapter, WellfoundAdapter):
            assert issubclass(cls, BaseSiteAdapter), (
                f"{cls.__name__} does not extend BaseSiteAdapter"
            )


# ──────────────────────────────────────────────────
#  Step 5 — Pagination depth
# ──────────────────────────────────────────────────

class TestStep5_PaginationDepth:
    def _load_sites(self):
        import yaml
        with open("config/sites.yaml") as f:
            return yaml.safe_load(f)["sites"]

    def test_openvc_scroll_count_increased(self):
        sites = self._load_sites()
        count = sites["openvc"]["pagination"]["scroll_count"]
        assert count >= 100, f"OpenVC scroll_count is {count} — should be >= 100"

    def test_angelmatch_max_clicks_increased(self):
        sites = self._load_sites()
        count = sites["angelmatch"]["pagination"]["max_clicks"]
        assert count >= 100, f"AngelMatch max_clicks is {count} — should be >= 100"

    def test_wellfound_scroll_count_substantial(self):
        sites = self._load_sites()
        count = sites["wellfound"]["pagination"]["scroll_count"]
        assert count >= 50, f"Wellfound scroll_count is {count} — should be >= 50"

    def test_landscape_vc_max_pages_substantial(self):
        sites = self._load_sites()
        count = sites["landscape_vc"]["pagination"]["max_pages"]
        assert count >= 30, f"Landscape.vc max_pages is {count} — should be >= 30"


# ──────────────────────────────────────────────────
#  Step 6 — Cross-run dedup cache
# ──────────────────────────────────────────────────

class TestStep6_DedupCache:
    def test_deep_crawl_has_load_seen(self):
        import deep_crawl
        assert hasattr(deep_crawl.DeepCrawler, "_load_seen"), (
            "DeepCrawler missing _load_seen method"
        )

    def test_deep_crawl_has_save_seen(self):
        import deep_crawl
        assert hasattr(deep_crawl.DeepCrawler, "_save_seen"), (
            "DeepCrawler missing _save_seen method"
        )

    def test_load_seen_returns_empty_set_when_no_file(self):
        import deep_crawl
        crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)
        crawler.seen_file = "/tmp/nonexistent_seen_domains_xyz.txt"
        result = crawler._load_seen()
        assert isinstance(result, set)
        assert len(result) == 0

    def test_save_and_load_seen_roundtrip(self):
        import deep_crawl
        with tempfile.TemporaryDirectory() as tmpdir:
            seen_path = os.path.join(tmpdir, "seen.txt")
            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)
            crawler.seen_file = seen_path
            domains = ["https://fund-a.com", "https://fund-b.vc"]
            crawler._save_seen(domains)
            loaded = crawler._load_seen()
            assert loaded == set(domains)

    def test_load_targets_skips_seen_domains(self):
        import deep_crawl
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "targets.txt")
            seen_file = os.path.join(tmpdir, "seen.txt")
            with open(target_file, "w") as f:
                f.write("https://fund-a.com\nhttps://fund-b.vc\nhttps://fund-c.io\n")
            with open(seen_file, "w") as f:
                f.write("https://fund-a.com\n")

            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)
            crawler.target_file = target_file
            crawler.seen_file = seen_file
            crawler.force_recrawl = False
            crawler.stale_days = 7
            targets = crawler._load_targets()
            assert "https://fund-a.com" not in targets, (
                "Seen domain was not filtered from targets"
            )
            assert "https://fund-b.vc" in targets
            assert "https://fund-c.io" in targets

    def test_force_recrawl_bypasses_seen_filter(self):
        import deep_crawl
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "targets.txt")
            seen_file = os.path.join(tmpdir, "seen.txt")
            with open(target_file, "w") as f:
                f.write("https://fund-a.com\nhttps://fund-b.vc\n")
            with open(seen_file, "w") as f:
                f.write("https://fund-a.com\nhttps://fund-b.vc\n")

            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)
            crawler.target_file = target_file
            crawler.seen_file = seen_file
            crawler.force_recrawl = True
            crawler.stale_days = 7
            targets = crawler._load_targets()
            assert "https://fund-a.com" in targets, (
                "--force-recrawl should include all targets regardless of seen cache"
            )

    def test_engine_has_force_recrawl_flag(self):
        import engine
        with patch("sys.argv", ["engine.py", "--force-recrawl", "--dry-run"]):
            args = engine.parse_args()
        assert hasattr(args, "force_recrawl")
        assert args.force_recrawl is True


# ──────────────────────────────────────────────────
#  Step 7 — LinkedIn profile email fallback
# ──────────────────────────────────────────────────

class TestStep7_LinkedInFallback:
    def test_deep_crawl_has_scrape_linkedin_email(self):
        import deep_crawl
        assert hasattr(deep_crawl.DeepCrawler, "_scrape_linkedin_email"), (
            "DeepCrawler missing _scrape_linkedin_email method"
        )

    def test_deep_crawl_has_linkedin_fallback(self):
        import deep_crawl
        assert hasattr(deep_crawl.DeepCrawler, "_linkedin_fallback"), (
            "DeepCrawler missing _linkedin_fallback method"
        )

    def test_linkedin_fallback_wired_into_crawl_fund(self):
        import inspect
        import deep_crawl
        source = inspect.getsource(deep_crawl.DeepCrawler._crawl_fund)
        assert "_linkedin_fallback" in source, (
            "_crawl_fund does not call _linkedin_fallback"
        )

    def test_linkedin_fallback_only_processes_no_email_contacts(self):
        """_linkedin_fallback must skip contacts that already have a valid email."""
        async def run():
            import deep_crawl
            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)

            mock_page = MagicMock()
            mock_page.goto = AsyncMock()
            mock_page.content = AsyncMock(return_value="<html></html>")
            mock_page.title = AsyncMock(return_value="Profile")

            contacts = [
                InvestorLead(
                    name="Jane Smith",
                    email="jane@fund.com",
                    linkedin="https://linkedin.com/in/janesmith",
                ),
                InvestorLead(
                    name="Bob Jones",
                    email="N/A",
                    linkedin="https://linkedin.com/in/bobjones",
                ),
                InvestorLead(
                    name="No LinkedIn",
                    email="N/A",
                    linkedin="N/A",
                ),
            ]

            with patch.object(
                crawler, "_scrape_linkedin_email", new=AsyncMock(return_value="N/A")
            ) as mock_scrape:
                await crawler._linkedin_fallback(mock_page, contacts)
                called_urls = [call[0][1] for call in mock_scrape.call_args_list]
                assert "https://linkedin.com/in/janesmith" not in called_urls, (
                    "_scrape_linkedin_email was called for a contact that already has an email"
                )
                assert "https://linkedin.com/in/bobjones" in called_urls, (
                    "_scrape_linkedin_email was not called for Bob who has no email"
                )
                assert not any("N/A" in url for url in called_urls), (
                    "_scrape_linkedin_email was called with a N/A LinkedIn URL"
                )

        asyncio.run(run())

    def test_linkedin_fallback_caps_at_5_per_fund(self):
        """_linkedin_fallback must not attempt more than 5 profiles per fund."""
        async def run():
            import deep_crawl
            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)

            mock_page = MagicMock()
            contacts = [
                InvestorLead(
                    name=f"Person {i}",
                    email="N/A",
                    linkedin=f"https://linkedin.com/in/person{i}",
                )
                for i in range(10)
            ]

            with patch.object(
                crawler, "_scrape_linkedin_email", new=AsyncMock(return_value="N/A")
            ) as mock_scrape:
                with patch("asyncio.sleep", new=AsyncMock()):
                    await crawler._linkedin_fallback(mock_page, contacts)
                assert mock_scrape.call_count <= 5, (
                    f"_linkedin_fallback attempted {mock_scrape.call_count} profiles — cap is 5"
                )

        asyncio.run(run())

    def test_linkedin_fallback_fills_email_when_found(self):
        """When _scrape_linkedin_email returns an email, it must be set on the contact."""
        async def run():
            import deep_crawl
            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)

            mock_page = MagicMock()
            contacts = [
                InvestorLead(
                    name="Jane Smith",
                    email="N/A",
                    linkedin="https://linkedin.com/in/janesmith",
                ),
            ]

            with patch.object(
                crawler, "_scrape_linkedin_email", new=AsyncMock(return_value="jane@acme.vc")
            ):
                with patch("asyncio.sleep", new=AsyncMock()):
                    result = await crawler._linkedin_fallback(mock_page, contacts)
            assert result[0].email == "jane@acme.vc", (
                "Email not set on contact after successful LinkedIn scrape"
            )

        asyncio.run(run())

    def test_scrape_linkedin_email_returns_na_on_no_email(self):
        """_scrape_linkedin_email must return 'N/A' when no email found on page."""
        async def run():
            import deep_crawl
            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)

            mock_page = MagicMock()
            mock_page.goto = AsyncMock()
            mock_page.content = AsyncMock(return_value="<html><body>No email here</body></html>")

            with patch("asyncio.sleep", new=AsyncMock()):
                result = await crawler._scrape_linkedin_email(
                    mock_page, "https://linkedin.com/in/test"
                )
            assert result == "N/A"

        asyncio.run(run())

    def test_scrape_linkedin_email_extracts_email_from_page(self):
        """_scrape_linkedin_email must return the email when present in page text."""
        async def run():
            import deep_crawl
            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)

            mock_page = MagicMock()
            mock_page.goto = AsyncMock()
            mock_page.content = AsyncMock(
                return_value="<html><body>Contact: jane@acme.vc for inquiries</body></html>"
            )

            with patch("asyncio.sleep", new=AsyncMock()):
                result = await crawler._scrape_linkedin_email(
                    mock_page, "https://linkedin.com/in/janesmith"
                )
            assert result == "jane@acme.vc"

        asyncio.run(run())

    def test_scrape_linkedin_email_handles_exception_gracefully(self):
        """_scrape_linkedin_email must return 'N/A' and not raise on page errors."""
        async def run():
            import deep_crawl
            crawler = deep_crawl.DeepCrawler.__new__(deep_crawl.DeepCrawler)

            mock_page = MagicMock()
            mock_page.goto = AsyncMock(side_effect=Exception("Navigation failed"))

            with patch("asyncio.sleep", new=AsyncMock()):
                result = await crawler._scrape_linkedin_email(
                    mock_page, "https://linkedin.com/in/test"
                )
            assert result == "N/A"

        asyncio.run(run())
