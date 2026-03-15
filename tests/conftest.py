"""
Shared fixtures for the LeadFactory test suite.
"""

import pytest
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MockInvestorLead:
    """Lightweight mock of adapters.base.InvestorLead for testing."""

    name: str = "John Doe"
    email: str = "N/A"
    role: str = "Partner"
    fund: str = "Test Ventures"
    focus_areas: list = field(default_factory=lambda: ["AI", "SaaS"])
    stage: str = "seed"
    check_size: str = "$100K - $500K"
    location: str = "United States"
    linkedin: str = "https://linkedin.com/in/johndoe"
    website: str = "https://testventures.com"
    source: str = "test"
    scraped_at: str = ""
    lead_score: int = 0
    tier: str = ""
    email_status: str = "unknown"
    times_seen: int = 1


@pytest.fixture
def sample_lead():
    """A standard sample lead for testing."""
    return MockInvestorLead()


@pytest.fixture
def sample_leads():
    """A batch of sample leads with varying attributes."""
    return [
        MockInvestorLead(
            name="Alice Johnson",
            email="alice@venture.com",
            role="Managing Partner",
            fund="Venture Capital Fund",
            focus_areas=["AI", "SaaS"],
            stage="seed",
            website="https://venture.com",
        ),
        MockInvestorLead(
            name="Bob Smith",
            email="N/A",
            role="Associate",
            fund="Growth Partners",
            focus_areas=["Fintech"],
            stage="series-a",
            website="https://growthpartners.com",
        ),
        MockInvestorLead(
            name="Charlie Brown",
            email="charlie@techfund.io",
            role="Principal",
            fund="Tech Fund",
            focus_areas=["SaaS", "developer tools"],
            stage="pre-seed",
            website="https://techfund.io",
            email_status="verified",
        ),
        MockInvestorLead(
            name="Capital Partners Group",
            email="N/A",
            role="N/A",
            fund="Capital Partners",
            focus_areas=[],
            stage="N/A",
            website="https://capitalpartners.com",
        ),
        MockInvestorLead(
            name="Diana Ross",
            email="N/A",
            role="Analyst",
            fund="Seed Investments",
            focus_areas=["Health", "Bio"],
            stage="seed",
            website="https://seedinvest.co",
            linkedin="N/A",
        ),
    ]


@pytest.fixture
def email_validator():
    """A fresh EmailValidator instance for testing."""
    from enrichment.email_validator import EmailValidator
    return EmailValidator()
