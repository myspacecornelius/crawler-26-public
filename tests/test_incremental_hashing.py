"""Tests for incremental crawling with content hashing and HTTP header support."""

import pytest
from enrichment.incremental import CrawlStateManager


class TestContentHashing:
    def test_compute_content_hash_stable(self):
        html = "<html><body><p>Hello world</p></body></html>"
        h1 = CrawlStateManager.compute_content_hash(html)
        h2 = CrawlStateManager.compute_content_hash(html)
        assert h1 == h2

    def test_compute_content_hash_ignores_scripts(self):
        html1 = "<html><body><p>Content</p></body></html>"
        html2 = '<html><body><p>Content</p><script>var x = 1;</script></body></html>'
        h1 = CrawlStateManager.compute_content_hash(html1)
        h2 = CrawlStateManager.compute_content_hash(html2)
        assert h1 == h2

    def test_compute_content_hash_ignores_styles(self):
        html1 = "<html><body><p>Content</p></body></html>"
        html2 = '<html><body><style>.x{color:red}</style><p>Content</p></body></html>'
        assert CrawlStateManager.compute_content_hash(html1) == CrawlStateManager.compute_content_hash(html2)

    def test_compute_content_hash_detects_changes(self):
        html1 = "<html><body><p>John Smith, Partner</p></body></html>"
        html2 = "<html><body><p>Jane Doe, Associate</p></body></html>"
        assert CrawlStateManager.compute_content_hash(html1) != CrawlStateManager.compute_content_hash(html2)

    def test_has_content_changed_first_visit(self):
        mgr = CrawlStateManager()
        assert mgr.has_content_changed("https://example.com", "<p>hello</p>") is True

    def test_has_content_changed_same_content(self):
        mgr = CrawlStateManager()
        html = "<p>hello world</p>"
        mgr.update_content_hash("https://example.com", html)
        assert mgr.has_content_changed("https://example.com", html) is False

    def test_has_content_changed_different_content(self):
        mgr = CrawlStateManager()
        mgr.update_content_hash("https://example.com", "<p>old content</p>")
        assert mgr.has_content_changed("https://example.com", "<p>new content</p>") is True

    def test_ignores_whitespace_differences(self):
        mgr = CrawlStateManager()
        html1 = "<p>hello   world</p>"
        html2 = "<p>hello world</p>"
        mgr.update_content_hash("https://example.com", html1)
        assert mgr.has_content_changed("https://example.com", html2) is False


class TestConditionalHeaders:
    def test_no_headers_initially(self):
        mgr = CrawlStateManager()
        headers = mgr.get_conditional_headers("https://example.com")
        assert headers == {}

    def test_stores_last_modified(self):
        mgr = CrawlStateManager()
        mgr.update_http_headers(
            "https://example.com",
            last_modified="Wed, 15 Mar 2026 10:00:00 GMT",
        )
        headers = mgr.get_conditional_headers("https://example.com")
        assert headers["If-Modified-Since"] == "Wed, 15 Mar 2026 10:00:00 GMT"

    def test_stores_etag(self):
        mgr = CrawlStateManager()
        mgr.update_http_headers("https://example.com", etag='"abc123"')
        headers = mgr.get_conditional_headers("https://example.com")
        assert headers["If-None-Match"] == '"abc123"'

    def test_both_headers(self):
        mgr = CrawlStateManager()
        mgr.update_http_headers(
            "https://example.com",
            last_modified="Wed, 15 Mar 2026 10:00:00 GMT",
            etag='"abc123"',
        )
        headers = mgr.get_conditional_headers("https://example.com")
        assert "If-Modified-Since" in headers
        assert "If-None-Match" in headers

    def test_www_normalization(self):
        mgr = CrawlStateManager()
        mgr.update_http_headers("https://www.example.com", etag='"tag1"')
        headers = mgr.get_conditional_headers("https://example.com")
        assert headers.get("If-None-Match") == '"tag1"'
