"""
Tests for enrichment/dedup.py

Verifies:
- Name normalization (titles, middle initials, whitespace)
- Fund normalization (common suffixes)
- Dedup key generation
- LeadDeduplicator merge logic (email priority, field filling, focus areas)
- Cross-batch deduplication
- Index persistence and loading
- Stats computation
- Edge cases: empty names, empty lists, corrupt index
"""

import json
import os
import tempfile
import pytest

from enrichment.dedup import (
    _normalize_name,
    _normalize_fund,
    _dedup_key,
    LeadDeduplicator,
    EMAIL_PRIORITY,
)


# ── Fixtures ─────────────────────────────────────

class FakeLead:
    """Minimal lead-like object for dedup testing."""
    def __init__(self, **kwargs):
        self.name = kwargs.get("name", "John Doe")
        self.fund = kwargs.get("fund", "Acme Capital")
        self.email = kwargs.get("email", "N/A")
        self.email_status = kwargs.get("email_status", "unknown")
        self.role = kwargs.get("role", "N/A")
        self.linkedin = kwargs.get("linkedin", "N/A")
        self.website = kwargs.get("website", "")
        self.location = kwargs.get("location", "")
        self.stage = kwargs.get("stage", "")
        self.check_size = kwargs.get("check_size", "")
        self.focus_areas = kwargs.get("focus_areas", [])
        self.lead_score = kwargs.get("lead_score", 0)
        self.tier = kwargs.get("tier", "")
        self.source = kwargs.get("source", "")


def make_dedup(tmp_dir):
    """Create a LeadDeduplicator with index in a temp directory."""
    index_path = os.path.join(tmp_dir, "dedup_index.json")
    return LeadDeduplicator(index_path=index_path)


# ── Name Normalization ───────────────────────────

class TestNormalizeName:
    def test_basic(self):
        assert _normalize_name("John Doe") == "john doe"

    def test_strips_whitespace(self):
        assert _normalize_name("  Jane Smith  ") == "jane smith"

    def test_removes_title_dr(self):
        assert _normalize_name("Dr. Alice Brown") == "alice brown"

    def test_removes_title_mr(self):
        assert _normalize_name("Mr. Bob Jones") == "bob jones"

    def test_removes_title_mrs(self):
        assert _normalize_name("Mrs. Claire Danes") == "claire danes"

    def test_removes_title_ms(self):
        assert _normalize_name("Ms. Dana White") == "dana white"

    def test_removes_middle_initial(self):
        assert _normalize_name("John A. Doe") == "john doe"

    def test_removes_middle_initial_no_period(self):
        assert _normalize_name("John A Doe") == "john doe"

    def test_keeps_two_part_name(self):
        assert _normalize_name("John Doe") == "john doe"

    def test_empty_string(self):
        assert _normalize_name("") == ""

    def test_none_returns_empty(self):
        assert _normalize_name(None) == ""


# ── Fund Normalization ───────────────────────────

class TestNormalizeFund:
    def test_basic(self):
        assert _normalize_fund("Acme Capital") == "acme"

    def test_strips_ventures(self):
        assert _normalize_fund("Sequoia Ventures") == "sequoia"

    def test_strips_partners(self):
        assert _normalize_fund("Insight Partners") == "insight"

    def test_strips_fund(self):
        assert _normalize_fund("Tiger Global Fund") == "tiger global"

    def test_strips_management(self):
        assert _normalize_fund("Ares Management") == "ares"

    def test_strips_llc(self):
        assert _normalize_fund("Benchmark LLC") == "benchmark"

    def test_case_insensitive(self):
        assert _normalize_fund("ACME CAPITAL") == "acme"

    def test_empty(self):
        assert _normalize_fund("") == ""

    def test_none(self):
        assert _normalize_fund(None) == ""


# ── Dedup Key ────────────────────────────────────

class TestDedupKey:
    def test_same_inputs_same_key(self):
        k1 = _dedup_key("John Doe", "Acme Capital")
        k2 = _dedup_key("John Doe", "Acme Capital")
        assert k1 == k2

    def test_case_insensitive(self):
        k1 = _dedup_key("John Doe", "Acme Capital")
        k2 = _dedup_key("JOHN DOE", "ACME CAPITAL")
        assert k1 == k2

    def test_fund_suffix_ignored(self):
        k1 = _dedup_key("John Doe", "Acme")
        k2 = _dedup_key("John Doe", "Acme Capital")
        assert k1 == k2

    def test_title_ignored(self):
        k1 = _dedup_key("John Doe", "Acme")
        k2 = _dedup_key("Dr. John Doe", "Acme")
        assert k1 == k2

    def test_different_people_different_keys(self):
        k1 = _dedup_key("John Doe", "Acme")
        k2 = _dedup_key("Jane Smith", "Acme")
        assert k1 != k2

    def test_same_name_different_fund(self):
        k1 = _dedup_key("John Doe", "Acme")
        k2 = _dedup_key("John Doe", "Benchmark")
        assert k1 != k2


# ── Email Priority ───────────────────────────────

class TestEmailPriority:
    def test_verified_highest(self):
        assert EMAIL_PRIORITY["verified"] > EMAIL_PRIORITY["scraped"]

    def test_scraped_over_guessed(self):
        assert EMAIL_PRIORITY["scraped"] > EMAIL_PRIORITY["guessed"]

    def test_undeliverable_lowest(self):
        assert EMAIL_PRIORITY["undeliverable"] == 0


# ── Deduplicator Core ────────────────────────────

class TestLeadDeduplicator:
    def test_new_leads_added_to_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            leads = [FakeLead(name="Alice", fund="Fund A")]
            result = dedup.deduplicate(leads)
            assert len(result) == 1
            assert len(dedup.index) == 1

    def test_duplicate_in_same_batch_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            leads = [
                FakeLead(name="Alice", fund="Fund A"),
                FakeLead(name="Alice", fund="Fund A"),
                FakeLead(name="Alice", fund="Fund A"),
            ]
            result = dedup.deduplicate(leads)
            assert len(result) == 1
            assert len(dedup.index) == 1

    def test_different_leads_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            leads = [
                FakeLead(name="Alice", fund="Fund A"),
                FakeLead(name="Bob", fund="Fund A"),
                FakeLead(name="Alice", fund="Fund B"),
            ]
            result = dedup.deduplicate(leads)
            assert len(result) == 3

    def test_merge_fills_empty_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            leads1 = [FakeLead(name="Alice", fund="Fund A", role="N/A")]
            dedup.deduplicate(leads1)

            leads2 = [FakeLead(name="Alice", fund="Fund A", role="Partner")]
            result = dedup.deduplicate(leads2)
            key = _dedup_key("Alice", "Fund A")
            assert dedup.index[key]["role"] == "Partner"

    def test_merge_upgrades_email_by_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            leads1 = [FakeLead(name="Alice", fund="Fund A",
                              email="alice@guessed.com", email_status="guessed")]
            dedup.deduplicate(leads1)

            leads2 = [FakeLead(name="Alice", fund="Fund A",
                              email="alice@verified.com", email_status="verified")]
            result = dedup.deduplicate(leads2)

            key = _dedup_key("Alice", "Fund A")
            assert dedup.index[key]["email"] == "alice@verified.com"
            assert dedup.index[key]["email_status"] == "verified"

    def test_merge_does_not_downgrade_email(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            leads1 = [FakeLead(name="Alice", fund="Fund A",
                              email="alice@verified.com", email_status="verified")]
            dedup.deduplicate(leads1)

            leads2 = [FakeLead(name="Alice", fund="Fund A",
                              email="alice@guessed.com", email_status="guessed")]
            dedup.deduplicate(leads2)

            key = _dedup_key("Alice", "Fund A")
            assert dedup.index[key]["email"] == "alice@verified.com"

    def test_merge_unions_focus_areas(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            leads1 = [FakeLead(name="Alice", fund="Fund A",
                              focus_areas=["SaaS", "AI"])]
            dedup.deduplicate(leads1)

            leads2 = [FakeLead(name="Alice", fund="Fund A",
                              focus_areas=["AI", "Fintech"])]
            dedup.deduplicate(leads2)

            key = _dedup_key("Alice", "Fund A")
            areas = set(dedup.index[key]["focus_areas"])
            assert areas == {"SaaS", "AI", "Fintech"}

    def test_times_seen_increments(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            lead = FakeLead(name="Alice", fund="Fund A")
            dedup.deduplicate([lead])
            dedup.deduplicate([FakeLead(name="Alice", fund="Fund A")])
            dedup.deduplicate([FakeLead(name="Alice", fund="Fund A")])

            key = _dedup_key("Alice", "Fund A")
            assert dedup.index[key]["times_seen"] == 3


# ── Index Persistence ────────────────────────────

class TestIndexPersistence:
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            dedup.deduplicate([FakeLead(name="Alice", fund="Fund A")])

            dedup2 = make_dedup(tmp)
            assert len(dedup2.index) == 1
            key = _dedup_key("Alice", "Fund A")
            assert key in dedup2.index

    def test_corrupt_index_resets(self):
        with tempfile.TemporaryDirectory() as tmp:
            index_path = os.path.join(tmp, "dedup_index.json")
            with open(index_path, "w") as f:
                f.write("NOT VALID JSON!!!")
            dedup = LeadDeduplicator(index_path=index_path)
            assert dedup.index == {}

    def test_missing_index_starts_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            assert dedup.index == {}

    def test_empty_list_no_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            result = dedup.deduplicate([])
            assert result == []
            assert len(dedup.index) == 0


# ── Stats ────────────────────────────────────────

class TestDedupStats:
    def test_stats_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            stats = dedup.get_stats()
            assert stats["total_unique_leads"] == 0
            assert stats["with_email"] == 0
            assert stats["seen_multiple_times"] == 0

    def test_stats_with_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            dedup = make_dedup(tmp)
            dedup.deduplicate([
                FakeLead(name="Alice", fund="A", email="alice@a.com"),
                FakeLead(name="Bob", fund="A", email="N/A"),
            ])
            dedup.deduplicate([FakeLead(name="Alice", fund="A")])

            stats = dedup.get_stats()
            assert stats["total_unique_leads"] == 2
            assert stats["with_email"] == 1
            assert stats["seen_multiple_times"] == 1


# ── Generational Suffix & Unicode Normalization ──

class TestNormalizeNameExtended:
    def test_removes_jr_suffix(self):
        assert _normalize_name("John Smith Jr.") == "john smith"

    def test_removes_jr_no_period(self):
        assert _normalize_name("John Smith Jr") == "john smith"

    def test_removes_sr_suffix(self):
        assert _normalize_name("Robert Brown Sr.") == "robert brown"

    def test_removes_iii(self):
        assert _normalize_name("William Ford III") == "william ford"

    def test_removes_iv(self):
        assert _normalize_name("James Walton IV") == "james walton"

    def test_removes_esq(self):
        assert _normalize_name("Alice Green Esq.") == "alice green"

    def test_removes_phd(self):
        assert _normalize_name("Dr. Emily Chen Ph.D.") == "emily chen"

    def test_unicode_accents_normalized(self):
        assert _normalize_name("José García") == "jose garcia"

    def test_unicode_umlaut(self):
        # ð (eth) is a distinct letter, not a diacritic, so NFD normalization preserves it
        assert _normalize_name("Björk Guðmundsdóttir") == "bjork guðmundsdottir"

    def test_unicode_cedilla(self):
        assert _normalize_name("François Müller") == "francois muller"

    def test_jr_and_unicode_combined(self):
        assert _normalize_name("José García Jr.") == "jose garcia"

    def test_dedup_key_matches_across_accents(self):
        """Same person with/without accents should get the same dedup key."""
        k1 = _dedup_key("José García", "Acme Capital")
        k2 = _dedup_key("Jose Garcia", "Acme Capital")
        assert k1 == k2

    def test_dedup_key_matches_across_suffixes(self):
        """Same person with/without Jr. should get the same dedup key."""
        k1 = _dedup_key("John Smith Jr.", "Benchmark")
        k2 = _dedup_key("John Smith", "Benchmark")
        assert k1 == k2
