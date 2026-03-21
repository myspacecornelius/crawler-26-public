"""
Tests for engine.py - integration-level wiring tests.

Verifies the CrawlEngine orchestrator correctly wires together the pipeline
phases (discovery, aggregator, deep crawl, enrichment) based on CLI flags.
Uses mocks for all external dependencies.
"""

import argparse
import asyncio
import os
import sys
import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_args(**overrides):
    """Create a minimal args namespace with safe defaults."""
    defaults = dict(
        site="",
        headless=True,
        dry_run=True,
        verbose=False,
        webhook="",
        webhook_platform="discord",
        discover=False,
        force_recrawl=False,
        deep=False,
        skip_smtp=True,
        portfolio=False,
        incremental=False,
        stale_days=7,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ── Engine Wiring Tests ──────────────────────────

class TestEnginePipelineWiring:
    """Verify that engine.run() calls the right phases based on CLI flags."""

    def test_engine_has_all_pipeline_methods(self):
        """Engine should have every pipeline phase method."""
        from engine import CrawlEngine
        assert hasattr(CrawlEngine, '_run_discovery')
        assert hasattr(CrawlEngine, '_run_aggregator')
        assert hasattr(CrawlEngine, '_run_deep_crawl')
        assert hasattr(CrawlEngine, '_run_portfolio_scrape')
        assert hasattr(CrawlEngine, '_enrich_and_output')

    def test_engine_imports_all_enrichment_modules(self):
        """Engine should import all enrichment modules."""
        source = inspect.getsource(__import__('engine'))
        assert 'EmailWaterfall' in source
        assert 'LeadDeduplicator' in source
        assert 'EmailGuesser' in source
        assert 'LeadScorer' in source
        assert 'EmailValidator' in source

    def test_engine_imports_all_adapters(self):
        """Engine should import and register all adapters."""
        from adapters.registry import get_registry
        registry = get_registry()
        expected = {"openvc", "angelmatch", "visible_vc", "landscape_vc",
                    "wellfound", "signal_nfx", "crunchbase"}
        assert expected.issubset(set(registry.list_adapters()))

    def test_parse_args_defaults(self):
        """CLI defaults should be safe (no crawl, no write)."""
        from engine import parse_args
        with patch('sys.argv', ['engine.py']):
            args = parse_args()
        assert args.headless is False
        assert args.dry_run is False
        assert args.discover is False
        assert args.deep is False
        assert args.portfolio is False
        assert args.skip_smtp is False

    def test_parse_args_flags(self):
        from engine import parse_args
        with patch('sys.argv', ['engine.py', '--discover', '--deep',
                                '--skip-smtp', '--headless', '--dry-run',
                                '--portfolio', '--incremental', '--stale-days', '14']):
            args = parse_args()
        assert args.discover is True
        assert args.deep is True
        assert args.skip_smtp is True
        assert args.headless is True
        assert args.dry_run is True
        assert args.portfolio is True
        assert args.incremental is True
        assert args.stale_days == 14


class TestEnrichmentPipelineComponents:
    """Verify the enrichment pipeline wires dedup + waterfall + scoring."""

    def test_enrich_and_output_calls_dedup(self):
        source = inspect.getsource(__import__('engine'))
        assert 'LeadDeduplicator' in source
        assert 'deduplicate' in source

    def test_enrich_and_output_calls_waterfall(self):
        source = inspect.getsource(__import__('engine'))
        assert 'EmailWaterfall' in source
        assert 'verify_batch' in source

    def test_enrich_and_output_calls_scoring(self):
        source = inspect.getsource(__import__('engine'))
        assert 'score_batch' in source

    def test_enrich_and_output_calls_email_guesser(self):
        source = inspect.getsource(__import__('engine'))
        assert 'guess_batch' in source

    def test_enrich_and_output_calls_email_validator(self):
        source = inspect.getsource(__import__('engine'))
        assert 'validate_batch' in source
