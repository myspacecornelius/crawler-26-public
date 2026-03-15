"""
Tests for adapter base class and site-specific adapters.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from bs4 import BeautifulSoup

from adapters.base import InvestorLead, BaseSiteAdapter


class TestInvestorLead:
    """Test InvestorLead data model."""

    def test_defaults(self):
        lead = InvestorLead(name="Test User")
        assert lead.name == "Test User"
        assert lead.email == "N/A"
        assert lead.role == "N/A"
        assert lead.fund == "N/A"
        assert lead.focus_areas == []
        assert lead.lead_score == 0
        assert lead.email_status == "unknown"

    def test_to_dict(self):
        lead = InvestorLead(
            name="Jane Doe",
            email="jane@test.com",
            focus_areas=["AI", "SaaS"],
        )
        d = lead.to_dict()
        assert d["name"] == "Jane Doe"
        assert d["email"] == "jane@test.com"
        assert d["focus_areas"] == "AI; SaaS"

    def test_to_dict_empty_focus(self):
        lead = InvestorLead(name="Test")
        d = lead.to_dict()
        assert d["focus_areas"] == "N/A"

    def test_all_fields(self):
        lead = InvestorLead(
            name="John Smith",
            email="john@fund.com",
            role="Partner",
            fund="Seed Fund",
            focus_areas=["Fintech"],
            stage="seed",
            check_size="$1M-$5M",
            location="New York",
            linkedin="https://linkedin.com/in/john",
            website="https://seedfund.com",
            source="openvc",
            scraped_at="2024-01-01T00:00:00",
            lead_score=85,
            tier="HOT",
            email_status="verified",
        )
        d = lead.to_dict()
        assert d["lead_score"] == 85
        assert d["tier"] == "HOT"


class TestBaseSiteAdapter:
    """Test BaseSiteAdapter base functionality."""

    def _make_adapter(self, selectors=None, pagination=None):
        """Create a concrete adapter subclass for testing."""
        class TestAdapter(BaseSiteAdapter):
            def parse_card(self, card):
                name = self._safe_text(card, "h3", "Unknown")
                email = self._extract_email(card)
                return InvestorLead(name=name, email=email)

        config = {
            "url": "https://test.example.com",
            "adapter": "test",
            "selectors": selectors or {"card": "div.card"},
            "pagination": pagination or {"type": "none"},
        }
        return TestAdapter(config)

    def test_adapter_name(self):
        adapter = self._make_adapter()
        assert adapter.name == "test"

    def test_safe_text(self):
        adapter = self._make_adapter()
        html = '<div><h3>John Doe</h3></div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._safe_text(card, "h3") == "John Doe"

    def test_safe_text_missing(self):
        adapter = self._make_adapter()
        html = '<div></div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._safe_text(card, "h3") == "N/A"

    def test_safe_text_default(self):
        adapter = self._make_adapter()
        html = '<div></div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._safe_text(card, "h3", "default") == "default"

    def test_safe_attr(self):
        adapter = self._make_adapter()
        html = '<div><a href="https://example.com">Link</a></div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._safe_attr(card, "a", "href") == "https://example.com"

    def test_safe_attr_missing(self):
        adapter = self._make_adapter()
        html = '<div></div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._safe_attr(card, "a", "href") == "N/A"

    def test_safe_list(self):
        adapter = self._make_adapter()
        html = '<div><span>AI</span><span>SaaS</span></div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._safe_list(card, "span") == ["AI", "SaaS"]

    def test_extract_email_mailto(self):
        adapter = self._make_adapter(selectors={"card": "div", "email": "a"})
        html = '<div><a href="mailto:test@example.com">Email</a></div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._extract_email(card) == "test@example.com"

    def test_extract_email_in_text(self):
        adapter = self._make_adapter()
        html = '<div>Contact: alice@fund.com for more info</div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._extract_email(card) == "alice@fund.com"

    def test_extract_email_none(self):
        adapter = self._make_adapter()
        html = '<div>No email here</div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        assert adapter._extract_email(card) == "N/A"

    def test_parse_card(self):
        adapter = self._make_adapter()
        html = '<div class="card"><h3>Jane Smith</h3></div>'
        card = BeautifulSoup(html, "html.parser").select_one("div")
        lead = adapter.parse_card(card)
        assert lead.name == "Jane Smith"
        assert lead.email == "N/A"

    def test_pagination_type_detection(self):
        adapter = self._make_adapter(pagination={"type": "infinite_scroll"})
        assert adapter.pagination["type"] == "infinite_scroll"

        adapter2 = self._make_adapter(pagination={"type": "load_more_button"})
        assert adapter2.pagination["type"] == "load_more_button"

        adapter3 = self._make_adapter(pagination={"type": "numbered_pages"})
        assert adapter3.pagination["type"] == "numbered_pages"


class TestAdapterDedup:
    """Test within-adapter deduplication."""

    def _make_adapter(self):
        class TestAdapter(BaseSiteAdapter):
            def parse_card(self, card):
                name = self._safe_text(card, "h3", "Unknown")
                return InvestorLead(name=name)
        config = {
            "url": "https://test.com",
            "adapter": "test",
            "selectors": {"card": "div.card"},
            "pagination": {"type": "none"},
        }
        return TestAdapter(config)

    @pytest.mark.asyncio
    async def test_dedup_within_adapter(self):
        adapter = self._make_adapter()
        html = """
        <html><body>
            <div class="card"><h3>John Doe</h3></div>
            <div class="card"><h3>John Doe</h3></div>
            <div class="card"><h3>Jane Smith</h3></div>
        </body></html>
        """
        page = AsyncMock()
        page.content.return_value = html
        await adapter._extract_from_page(page)
        assert len(adapter.leads) == 2  # John Doe deduped
