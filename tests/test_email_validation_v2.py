"""
Comprehensive tests for EmailValidator with cascading validation,
MX integration, and disposable/role-based detection.
"""

import pytest
from unittest.mock import patch, MagicMock

from enrichment.email_validator import (
    EmailValidator,
    DISPOSABLE_DOMAINS,
    ROLE_PREFIXES,
)


class TestEmailValidatorFormat:
    """Test format validation."""

    def test_valid_email(self, email_validator):
        result = email_validator.validate("test@example.com")
        assert result["valid_format"] is True

    def test_invalid_email_no_at(self, email_validator):
        result = email_validator.validate("testexample.com")
        assert result["valid_format"] is False
        assert result["quality"] == "invalid"

    def test_invalid_email_no_domain(self, email_validator):
        result = email_validator.validate("test@")
        assert result["valid_format"] is False

    def test_invalid_email_no_tld(self, email_validator):
        result = email_validator.validate("test@example")
        assert result["valid_format"] is False

    def test_empty_email(self, email_validator):
        result = email_validator.validate("")
        assert result["quality"] == "invalid"

    def test_na_email(self, email_validator):
        result = email_validator.validate("N/A")
        assert result["quality"] == "invalid"

    def test_none_email(self, email_validator):
        result = email_validator.validate(None)
        assert result["quality"] == "invalid"

    def test_email_with_plus(self, email_validator):
        result = email_validator.validate("user+tag@example.com")
        assert result["valid_format"] is True

    def test_email_with_dots(self, email_validator):
        result = email_validator.validate("first.last@example.com")
        assert result["valid_format"] is True

    def test_email_case_normalized(self, email_validator):
        result = email_validator.validate("Test@Example.COM")
        assert result["email"] == "test@example.com"

    @pytest.mark.parametrize("email", [
        "a@b.co",
        "user@sub.domain.com",
        "first-last@company.io",
        "user_name@firm.org",
    ])
    def test_valid_formats(self, email_validator, email):
        result = email_validator.validate(email)
        assert result["valid_format"] is True

    @pytest.mark.parametrize("email", [
        "@example.com",
        "user@",
        "user@.com",
        "user @example.com",
        "",
    ])
    def test_invalid_formats(self, email_validator, email):
        result = email_validator.validate(email)
        assert result["valid_format"] is False


class TestDisposableDomains:
    """Test disposable domain detection."""

    def test_disposable_domain(self, email_validator):
        result = email_validator.validate("user@mailinator.com")
        assert result["is_disposable"] is True
        assert result["quality"] == "low"

    def test_non_disposable_domain(self, email_validator):
        result = email_validator.validate("user@google.com")
        assert result["is_disposable"] is False

    @pytest.mark.parametrize("domain", [
        "tempmail.com", "guerrillamail.com", "yopmail.com",
        "trashmail.com", "10minutemail.com",
    ])
    def test_known_disposable_domains(self, email_validator, domain):
        result = email_validator.validate(f"test@{domain}")
        assert result["is_disposable"] is True
        assert result["quality"] == "low"

    def test_disposable_domains_loaded_from_config(self):
        assert len(DISPOSABLE_DOMAINS) > 5


class TestRoleBasedEmails:
    """Test role-based email detection."""

    def test_role_based_prefix(self, email_validator):
        result = email_validator.validate("info@company.com")
        assert result["is_role_based"] is True
        assert result["quality"] == "medium"

    def test_personal_email(self, email_validator):
        result = email_validator.validate("john.doe@company.com")
        assert result["is_role_based"] is False

    @pytest.mark.parametrize("prefix", [
        "info", "contact", "admin", "support", "team", "hello",
        "sales", "marketing", "noreply", "office",
    ])
    def test_known_role_prefixes(self, email_validator, prefix):
        result = email_validator.validate(f"{prefix}@example.com")
        assert result["is_role_based"] is True
        assert result["quality"] == "medium"


class TestMXValidation:
    """Test MX record checking."""

    def test_mx_check_cached(self, email_validator):
        # Pre-populate cache
        email_validator._mx_cache["cached.com"] = True
        result = email_validator._check_mx_sync("cached.com")
        assert result["has_mx"] is True
        assert result["dns_error"] is False

    def test_mx_check_cached_false(self, email_validator):
        email_validator._mx_cache["nocached.com"] = False
        result = email_validator._check_mx_sync("nocached.com")
        assert result["has_mx"] is False

    @patch("dns.resolver.resolve")
    def test_mx_check_success(self, mock_resolve, email_validator):
        mock_resolve.return_value = [MagicMock()]
        result = email_validator._check_mx_sync("valid-domain.com")
        assert result["has_mx"] is True

    @patch("dns.resolver.resolve")
    def test_mx_check_nxdomain(self, mock_resolve, email_validator):
        import dns.resolver
        mock_resolve.side_effect = dns.resolver.NXDOMAIN()
        result = email_validator._check_mx_sync("nonexistent.com")
        assert result["has_mx"] is False

    def test_validate_integrates_mx(self, email_validator):
        # Pre-populate MX cache to avoid real DNS calls
        email_validator._mx_cache["example.com"] = True
        result = email_validator.validate("user@example.com")
        assert result["has_mx"] is True
        assert result["quality"] == "high"

    def test_validate_no_mx_is_low_quality(self, email_validator):
        email_validator._mx_cache["badomain.com"] = False
        result = email_validator.validate("user@badomain.com")
        assert result["has_mx"] is False
        assert result["quality"] == "low"


class TestCascadingValidation:
    """Test the cascading validation strategy."""

    def test_cascade_stops_at_format(self, email_validator):
        result = email_validator.validate("not-an-email")
        assert result["quality"] == "invalid"
        assert result["is_disposable"] is False

    def test_cascade_stops_at_disposable(self, email_validator):
        result = email_validator.validate("user@mailinator.com")
        assert result["quality"] == "low"
        assert result["has_mx"] is None  # Should not reach MX check

    def test_cascade_stops_at_role(self, email_validator):
        result = email_validator.validate("info@gmail.com")
        assert result["quality"] == "medium"

    def test_cascade_full_pass(self, email_validator):
        email_validator._mx_cache["company.com"] = True
        result = email_validator.validate("john@company.com")
        assert result["quality"] == "high"

    def test_dns_error_flags_retry(self, email_validator):
        # Simulate DNS error by not caching and patching
        with patch("dns.resolver.resolve", side_effect=Exception("timeout")):
            result = email_validator.validate("user@unknowndomain.xyz")
        assert result["dns_error"] is True
        assert result["quality"] == "medium"
        assert "unknowndomain.xyz" in email_validator.dns_error_domains


class TestValidatorCacheStats:
    """Test cache statistics."""

    def test_cache_stats_empty(self):
        validator = EmailValidator()
        validator._mx_cache.clear()
        stats = validator.cache_stats
        assert stats["domains_cached"] == 0
        assert stats["smtp_checks_cached"] == 0

    def test_cache_stats_after_validation(self, email_validator):
        email_validator._mx_cache.clear()
        email_validator._mx_cache["test.com"] = True
        stats = email_validator.cache_stats
        assert stats["domains_cached"] == 1
        assert stats["domains_with_mx"] == 1


class TestValidateBatch:
    """Test batch validation."""

    @pytest.mark.asyncio
    async def test_batch_validation(self, email_validator):
        emails = ["valid@example.com", "bad-email", "info@company.com"]
        # Pre-populate MX cache
        email_validator._mx_cache["example.com"] = True
        email_validator._mx_cache["company.com"] = True
        results = await email_validator.validate_batch(emails)
        assert len(results) == 3
        assert results[0]["valid_format"] is True
        assert results[1]["valid_format"] is False
        assert results[2]["is_role_based"] is True
