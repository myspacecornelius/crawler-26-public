"""
Tests for SMTP-verified email pattern discovery.
Covers: generate_candidates, _is_person_name fix, _discover_domain_pattern,
Phase 1.5 integration, and pattern cache propagation.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from enrichment.email_guesser import (
    EmailGuesser,
    _is_person_name,
    generate_candidates,
    detect_pattern,
)


# ── Test 1: generate_candidates produces correct patterns ──

def test_generate_candidates_standard_name():
    candidates = generate_candidates("John Smith", "acme.com")
    assert candidates == [
        "john.smith@acme.com",
        "john@acme.com",
        "jsmith@acme.com",
        "johnsmith@acme.com",
        "j.smith@acme.com",
        "smith@acme.com",
        "john_smith@acme.com",
        "smith.john@acme.com",
    ]


def test_generate_candidates_single_name_returns_empty():
    assert generate_candidates("Madonna", "acme.com") == []


def test_generate_candidates_three_part_name():
    candidates = generate_candidates("Mary Jane Watson", "oscorp.com")
    # Should use first=mary, last=watson (first and last words)
    assert candidates[0] == "mary.watson@oscorp.com"
    assert candidates[1] == "mary@oscorp.com"
    assert candidates[2] == "mwatson@oscorp.com"


# ── Test 2: _is_person_name with "partner" fix ──

def test_is_person_name_john_partner():
    """'partner' was removed from _COMPANY_WORDS — names containing it should pass."""
    assert _is_person_name("John Partner") is True


def test_is_person_name_jane_doe():
    assert _is_person_name("Jane Doe") is True


def test_is_person_name_rejects_company():
    assert _is_person_name("Acme Capital") is False


def test_is_person_name_rejects_empty():
    assert _is_person_name("") is False
    assert _is_person_name("N/A") is False


def test_is_person_name_rejects_single_word():
    assert _is_person_name("John") is False


# ── Test 3: _discover_domain_pattern returns None when SMTP unavailable ──

@pytest.mark.anyio
async def test_discover_pattern_smtp_unavailable():
    guesser = EmailGuesser(concurrency=2)
    # Mock smtp_self_test to return False (SMTP blocked)
    guesser.validator.smtp_self_test = AsyncMock(return_value=False)

    result = await guesser._discover_domain_pattern("John Smith", "acme.com")
    assert result is None
    assert guesser._stats["patterns_discovered"] == 0


@pytest.mark.anyio
async def test_discover_pattern_finds_first_at_domain():
    """When SMTP says first@domain is deliverable, lock that pattern."""
    guesser = EmailGuesser(concurrency=2)
    guesser.validator.smtp_self_test = AsyncMock(return_value=True)

    async def mock_verify_smtp(email):
        # first.last@acme.com → not deliverable
        # first@acme.com → deliverable
        if email == "john@acme.com":
            return {"deliverable": True, "smtp_code": 250, "catch_all": False}
        return {"deliverable": False, "smtp_code": 550, "catch_all": False}

    guesser.validator.verify_smtp = mock_verify_smtp

    result = await guesser._discover_domain_pattern("John Smith", "acme.com")
    assert result == "john@acme.com"
    assert guesser._stats["patterns_discovered"] == 1
    assert guesser._pattern_store.get("acme.com") == "{first}@{domain}"


@pytest.mark.anyio
async def test_discover_pattern_all_fail_returns_none():
    """When all 3 probes fail, return None and don't cache a pattern."""
    guesser = EmailGuesser(concurrency=2)
    guesser.validator.smtp_self_test = AsyncMock(return_value=True)
    guesser.validator.verify_smtp = AsyncMock(
        return_value={"deliverable": None, "smtp_code": 0, "catch_all": False}
    )

    result = await guesser._discover_domain_pattern("John Smith", "acme.com")
    assert result is None
    assert guesser._stats["patterns_discovered"] == 0
    assert guesser._pattern_store.get("acme.com") is None


# ── Test 4: Phase 1.5 integration into guess_batch ──

def _make_lead(name, website, email=None):
    return SimpleNamespace(name=name, website=website, email=email, linkedin="N/A", role="N/A")


@pytest.mark.anyio
async def test_guess_batch_phase_1_5_discovers_pattern():
    """Phase 1.5 should probe unknown domains and lock in the discovered pattern."""
    guesser = EmailGuesser(concurrency=2)
    guesser.validator.smtp_self_test = AsyncMock(return_value=True)

    # Mock verify_smtp: first@example.com is deliverable
    async def mock_verify_smtp(email):
        if email.startswith("alice@"):
            return {"deliverable": True, "smtp_code": 250, "catch_all": False}
        return {"deliverable": False, "smtp_code": 550, "catch_all": False}

    guesser.validator.verify_smtp = mock_verify_smtp

    # Mock verify_mx to return True for all domains
    guesser.validator.verify_mx = AsyncMock(return_value=True)

    leads = [
        _make_lead("Alice Johnson", "https://example.com"),
        _make_lead("Bob Williams", "https://example.com"),
    ]

    await guesser.guess_batch(leads)

    # Phase 1.5 should have discovered {first}@{domain} via Alice
    assert guesser._pattern_store.get("example.com") == "{first}@{domain}"
    assert guesser._stats["patterns_discovered"] == 1


# ── Test 5: Pattern cache propagation ──

@pytest.mark.anyio
async def test_pattern_propagation_across_contacts():
    """After discovering first@domain for one contact, all contacts at that domain should use it."""
    guesser = EmailGuesser(concurrency=2)
    guesser.validator.smtp_self_test = AsyncMock(return_value=True)

    async def mock_verify_smtp(email):
        if email == "alice@example.com":
            return {"deliverable": True, "smtp_code": 250, "catch_all": False}
        return {"deliverable": False, "smtp_code": 550, "catch_all": False}

    guesser.validator.verify_smtp = mock_verify_smtp
    guesser.validator.verify_mx = AsyncMock(return_value=True)

    leads = [
        _make_lead("Alice Johnson", "https://example.com"),
        _make_lead("Bob Williams", "https://example.com"),
        _make_lead("Carol Davis", "https://example.com"),
    ]

    await guesser.guess_batch(leads)

    # All contacts should have first@domain pattern applied
    # Alice triggers discovery, Bob and Carol get pattern via Phase 2
    assert leads[0].email in ("alice@example.com",)
    assert leads[1].email == "bob@example.com"
    assert leads[2].email == "carol@example.com"


# ── Test: detect_pattern utility ──

def test_detect_pattern_first_last():
    assert detect_pattern("john.smith@acme.com", "John Smith") == "{first}.{last}@{domain}"


def test_detect_pattern_first_only():
    assert detect_pattern("john@acme.com", "John Smith") == "{first}@{domain}"


def test_detect_pattern_flast():
    assert detect_pattern("jsmith@acme.com", "John Smith") == "{f}{last}@{domain}"


def test_detect_pattern_unknown():
    assert detect_pattern("custom123@acme.com", "John Smith") is None
