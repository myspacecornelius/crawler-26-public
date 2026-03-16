"""Tests for the adapter registry and plugin discovery system."""

import pytest
from adapters.base import BaseSiteAdapter, InvestorLead
from adapters.registry import AdapterRegistry, register_adapter, get_registry


class FakeAdapter(BaseSiteAdapter):
    """Test adapter for registry tests."""
    ADAPTER_NAME = "fake_test"
    VERTICALS = ["vc", "angel"]
    RATE_LIMIT_RPM = 30
    REQUIRES_AUTH = False

    def parse_card(self, card):
        return None


class AnotherFakeAdapter(BaseSiteAdapter):
    """Another test adapter."""
    ADAPTER_NAME = "another_fake"
    VERTICALS = ["pe"]

    def parse_card(self, card):
        return None


class TestAdapterRegistry:
    def test_register_and_get(self):
        registry = AdapterRegistry()
        registry.register("test_site", FakeAdapter, verticals=["vc"])
        assert registry.get("test_site") is FakeAdapter

    def test_get_nonexistent_returns_none(self):
        registry = AdapterRegistry()
        assert registry.get("nonexistent") is None

    def test_list_adapters(self):
        registry = AdapterRegistry()
        registry.register("site_a", FakeAdapter)
        registry.register("site_b", AnotherFakeAdapter)
        names = registry.list_adapters()
        assert "site_a" in names
        assert "site_b" in names

    def test_get_metadata(self):
        registry = AdapterRegistry()
        registry.register(
            "test_site",
            FakeAdapter,
            verticals=["vc"],
            rate_limit_rpm=30,
            requires_auth=False,
            description="Test adapter",
        )
        meta = registry.get_metadata("test_site")
        assert meta is not None
        assert meta.name == "test_site"
        assert meta.verticals == ["vc"]
        assert meta.rate_limit_rpm == 30
        assert meta.requires_auth is False

    def test_filter_by_vertical(self):
        registry = AdapterRegistry()
        registry.register("vc_site", FakeAdapter, verticals=["vc"])
        registry.register("pe_site", AnotherFakeAdapter, verticals=["pe"])
        vc_adapters = registry.filter_by_vertical("vc")
        assert "vc_site" in vc_adapters
        assert "pe_site" not in vc_adapters

    def test_auto_discover_finds_adapters(self):
        registry = AdapterRegistry()
        registry.auto_discover()
        # Should find at least the OpenVC adapter
        names = registry.list_adapters()
        assert "openvc" in names
        assert "angelmatch" in names

    def test_metadata_to_dict(self):
        registry = AdapterRegistry()
        registry.register("test", FakeAdapter, verticals=["vc"], rate_limit_rpm=10)
        meta = registry.get_metadata("test")
        d = meta.to_dict()
        assert d["name"] == "test"
        assert d["adapter_class"] == "FakeAdapter"
        assert d["verticals"] == ["vc"]

    def test_list_metadata(self):
        registry = AdapterRegistry()
        registry.register("a", FakeAdapter, verticals=["vc"])
        registry.register("b", AnotherFakeAdapter, verticals=["pe"])
        metas = registry.list_metadata()
        assert len(metas) == 2
        names = [m["name"] for m in metas]
        assert "a" in names
        assert "b" in names


class TestGetRegistry:
    def test_global_registry_auto_discovers(self):
        registry = get_registry()
        names = registry.list_adapters()
        # Should find all adapters from the adapters/ package
        assert len(names) >= 7  # openvc, angelmatch, visible_vc, etc.

    def test_global_registry_returns_correct_classes(self):
        registry = get_registry()
        from adapters.openvc import OpenVCAdapter
        assert registry.get("openvc") is OpenVCAdapter


class TestScanModule:
    def test_scan_discovers_adapter_name_attr(self):
        registry = AdapterRegistry()
        import adapters.openvc as mod
        registry._scan_module(mod)
        assert registry.get("openvc") is not None

    def test_explicit_registration_takes_priority(self):
        registry = AdapterRegistry()
        registry.register("openvc", FakeAdapter)
        # Auto-discover should NOT override explicit registration
        registry.auto_discover()
        assert registry.get("openvc") is FakeAdapter
