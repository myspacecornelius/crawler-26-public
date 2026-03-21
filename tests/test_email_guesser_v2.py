"""
Tests for EmailGuesser v3 — pattern learning, statistics, person detection.
"""

import json
import pytest
import tempfile
from pathlib import Path

from enrichment.email_guesser import (
    EmailGuesser,
    PatternStore,
    _is_person_name,
    _clean_person_name,
    _normalize,
    _extract_domain,
    detect_pattern,
    generate_candidates,
)


class TestPersonNameDetection:
    """Test _is_person_name heuristic."""

    @pytest.mark.parametrize("name,expected", [
        ("John Smith", True),
        ("Alice Johnson", True),
        ("Dr. Jane Doe", True),
        ("Prof. Robert Wilson", True),
        ("Capital Ventures", False),
        ("Growth Partners Fund", False),
        ("N/A", False),
        ("unknown", False),
        ("", False),
        ("John", False),  # Single word
        ("A B C D E F", False),  # Too many words
        ("JOHN SMITH DOE", False),  # All caps multi-word
        ("Abc123 Def", False),  # Contains numbers
        ("Meet Sarah Jones", True),  # "Meet" prefix stripped
        ("About Mark Brown", True),  # "About" prefix stripped
        ("Twitter LinkedIn", False),  # Social media words
        ("Join Our Team", False),  # Company words
    ])
    def test_person_detection(self, name, expected):
        assert _is_person_name(name) == expected


class TestNameCleaning:
    """Test _clean_person_name."""

    def test_strip_meet_prefix(self):
        assert _clean_person_name("Meet John Smith") == "John Smith"

    def test_strip_dr_prefix(self):
        assert _clean_person_name("Dr. Jane Doe") == "Jane Doe"

    def test_strip_trailing_period(self):
        assert _clean_person_name("John Smith.") == "John Smith"

    def test_no_prefix(self):
        assert _clean_person_name("John Smith") == "John Smith"


class TestNormalize:
    """Test _normalize for accent stripping and character filtering."""

    def test_basic(self):
        assert _normalize("John") == "john"

    def test_accents(self):
        assert _normalize("José") == "jose"

    def test_umlaut(self):
        assert _normalize("Müller") == "muller"

    def test_cedilla(self):
        assert _normalize("François") == "francois"

    def test_non_alpha_stripped(self):
        assert _normalize("O'Brien") == "obrien"

    def test_hyphen_stripped(self):
        assert _normalize("Jean-Pierre") == "jeanpierre"


class TestExtractDomain:
    """Test _extract_domain."""

    def test_basic_url(self):
        assert _extract_domain("https://example.com") == "example.com"

    def test_www_stripped(self):
        assert _extract_domain("https://www.example.com") == "example.com"

    def test_no_scheme(self):
        assert _extract_domain("example.com") == "example.com"

    def test_with_path(self):
        assert _extract_domain("https://example.com/about") == "example.com"

    def test_na(self):
        assert _extract_domain("N/A") is None

    def test_empty(self):
        assert _extract_domain("") is None

    def test_none(self):
        assert _extract_domain(None) is None


class TestGenerateCandidates:
    """Test generate_candidates."""

    def test_generates_all_patterns(self):
        candidates = generate_candidates("John Smith", "example.com")
        assert len(candidates) == 8
        assert "john.smith@example.com" in candidates
        assert "john@example.com" in candidates
        assert "jsmith@example.com" in candidates
        assert "johnsmith@example.com" in candidates
        assert "j.smith@example.com" in candidates
        assert "smith@example.com" in candidates
        assert "john_smith@example.com" in candidates
        assert "smith.john@example.com" in candidates

    def test_single_name_returns_empty(self):
        assert generate_candidates("John", "example.com") == []

    def test_accented_name(self):
        candidates = generate_candidates("José García", "example.com")
        assert "jose.garcia@example.com" in candidates

    def test_multi_part_name_uses_first_last(self):
        candidates = generate_candidates("Mary Jane Watson", "example.com")
        assert "mary.watson@example.com" in candidates


class TestDetectPattern:
    """Test detect_pattern."""

    def test_first_dot_last(self):
        assert detect_pattern("john.smith@example.com", "John Smith") == "{first}.{last}@{domain}"

    def test_first_only(self):
        assert detect_pattern("john@example.com", "John Smith") == "{first}@{domain}"

    def test_first_initial_last(self):
        assert detect_pattern("jsmith@example.com", "John Smith") == "{f}{last}@{domain}"

    def test_first_last_concatenated(self):
        assert detect_pattern("johnsmith@example.com", "John Smith") == "{first}{last}@{domain}"

    def test_last_dot_first(self):
        assert detect_pattern("smith.john@example.com", "John Smith") == "{last}.{first}@{domain}"

    def test_unrecognized_pattern(self):
        assert detect_pattern("js123@example.com", "John Smith") is None

    def test_single_name(self):
        assert detect_pattern("john@example.com", "John") is None


class TestPatternStore:
    """Test PatternStore with frequency-based learning."""

    def test_learn_and_get(self):
        store = PatternStore(store_path=Path("/tmp/test_patterns_unused.json"))
        store._patterns.clear()
        store._best_pattern.clear()

        store.learn("example.com", "john.smith@example.com", "John Smith")
        assert store.get("example.com") == "{first}.{last}@{domain}"

    def test_frequency_counting(self):
        store = PatternStore(store_path=Path("/tmp/test_patterns_unused.json"))
        store._patterns.clear()
        store._best_pattern.clear()

        # Learn first.last twice
        store.learn("example.com", "john.smith@example.com", "John Smith")
        store.learn("example.com", "jane.doe@example.com", "Jane Doe")
        # Learn first once
        store.learn("example.com", "bob@example.com", "Bob Jones")

        # first.last should win by frequency
        assert store.get("example.com") == "{first}.{last}@{domain}"
        assert store._patterns["example.com"]["{first}.{last}@{domain}"] == 2
        assert store._patterns["example.com"]["{first}@{domain}"] == 1

    def test_apply_learned_pattern(self):
        store = PatternStore(store_path=Path("/tmp/test_patterns_unused.json"))
        store._patterns.clear()
        store._best_pattern.clear()

        store.learn("example.com", "john.smith@example.com", "John Smith")
        email = store.apply("Jane Doe", "example.com")
        assert email == "jane.doe@example.com"

    def test_apply_no_pattern(self):
        store = PatternStore(store_path=Path("/tmp/test_patterns_unused.json"))
        store._patterns.clear()
        store._best_pattern.clear()

        email = store.apply("Jane Doe", "unknown.com")
        assert email is None

    def test_statistics(self):
        store = PatternStore(store_path=Path("/tmp/test_patterns_unused.json"))
        store._patterns.clear()
        store._best_pattern.clear()

        store.learn("a.com", "john.smith@a.com", "John Smith")
        store.learn("a.com", "jane.doe@a.com", "Jane Doe")
        store.learn("b.com", "bob@b.com", "Bob Jones")

        stats = store.get_statistics()
        assert stats["total_domains"] == 2
        assert stats["total_observations"] == 3
        assert len(stats["global_pattern_ranking"]) >= 1
        assert len(stats["top_domains"]) == 2

    def test_persistence(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            tmp_path = Path(f.name)

        try:
            store1 = PatternStore(store_path=tmp_path)
            store1._patterns.clear()
            store1._best_pattern.clear()
            store1.learn("test.com", "alice.bob@test.com", "Alice Bob")
            store1.save()

            # Load in a new instance
            store2 = PatternStore(store_path=tmp_path)
            assert store2.get("test.com") == "{first}.{last}@{domain}"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_domains_known(self):
        store = PatternStore(store_path=Path("/tmp/test_patterns_unused.json"))
        store._patterns.clear()
        store._best_pattern.clear()

        assert store.domains_known == 0
        store.learn("a.com", "john.smith@a.com", "John Smith")
        assert store.domains_known == 1


class TestEmailGuesserInit:
    """Test EmailGuesser initialization."""

    def test_default_init(self):
        guesser = EmailGuesser()
        assert guesser.concurrency == 10
        assert guesser.stats["attempted"] == 0

    def test_custom_concurrency(self):
        guesser = EmailGuesser(concurrency=5)
        assert guesser.concurrency == 5


class TestEmailGuesserCandidates:
    """Test candidate generation through the guesser."""

    def test_generate_all_candidates(self):
        guesser = EmailGuesser()
        candidates = guesser.generate_all_candidates("John Smith", "https://example.com")
        assert len(candidates) == 8
        assert "john.smith@example.com" in candidates

    def test_company_name_no_candidates(self):
        guesser = EmailGuesser()
        candidates = guesser.generate_all_candidates("Capital Ventures", "https://example.com")
        assert candidates == []

    def test_na_website_no_candidates(self):
        guesser = EmailGuesser()
        candidates = guesser.generate_all_candidates("John Smith", "N/A")
        assert candidates == []


class TestEmailGuesserPatternStats:
    """Test pattern statistics endpoint."""

    def test_pattern_statistics_empty(self):
        guesser = EmailGuesser()
        guesser._pattern_store._patterns.clear()
        guesser._pattern_store._best_pattern.clear()
        stats = guesser.pattern_statistics
        assert stats["total_domains"] == 0
        assert stats["total_observations"] == 0

    def test_stats_property(self):
        guesser = EmailGuesser()
        stats = guesser.stats
        assert "attempted" in stats
        assert "found" in stats
        assert "pattern_hits" in stats
        assert "company_skipped" in stats
