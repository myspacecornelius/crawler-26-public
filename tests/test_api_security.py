"""
Tests for API security enhancements:
- Password complexity validation
- Settings module
- Auth module (passlib hashing)
"""

import pytest


class TestPasswordComplexity:
    """Test password complexity validation rules."""

    def test_too_short(self):
        from api.auth import validate_password_complexity
        result = validate_password_complexity("Ab1")
        assert result is not None
        assert "at least" in result

    def test_no_uppercase(self):
        from api.auth import validate_password_complexity
        result = validate_password_complexity("longpassword1")
        assert result is not None
        assert "uppercase" in result

    def test_no_digit(self):
        from api.auth import validate_password_complexity
        result = validate_password_complexity("LongPassword")
        assert result is not None
        assert "digit" in result

    def test_valid_password(self):
        from api.auth import validate_password_complexity
        result = validate_password_complexity("StrongPass1")
        assert result is None

    def test_exactly_min_length(self):
        from api.auth import validate_password_complexity
        result = validate_password_complexity("Abcdef1x")
        assert result is None


class TestSettings:
    """Test centralised settings module."""

    def test_settings_import(self):
        from api.settings import settings
        assert settings.app_name == "LeadFactory"

    def test_cors_origin_list(self):
        from api.settings import Settings
        s = Settings(CORS_ORIGINS="http://a.com,http://b.com")
        assert s.cors_origin_list == ["http://a.com", "http://b.com"]

    def test_cors_origin_list_with_spaces(self):
        from api.settings import Settings
        s = Settings(CORS_ORIGINS="http://a.com , http://b.com")
        assert s.cors_origin_list == ["http://a.com", "http://b.com"]

    def test_async_database_url_postgres(self):
        from api.settings import Settings
        s = Settings(DATABASE_URL="postgresql://user:pass@localhost/db")
        assert s.async_database_url == "postgresql+asyncpg://user:pass@localhost/db"

    def test_async_database_url_sqlite(self):
        from api.settings import Settings
        s = Settings(DATABASE_URL="sqlite+aiosqlite:///./data/test.db")
        assert s.async_database_url == "sqlite+aiosqlite:///./data/test.db"

    def test_is_sqlite(self):
        from api.settings import Settings
        s = Settings(DATABASE_URL="sqlite+aiosqlite:///./data/test.db")
        assert s.is_sqlite is True

    def test_is_not_sqlite(self):
        from api.settings import Settings
        s = Settings(DATABASE_URL="postgresql://user:pass@localhost/db")
        assert s.is_sqlite is False


class TestAlembicMigration:
    """Test that initial migration file exists and is valid."""

    def test_initial_migration_exists(self):
        import os
        migration_path = os.path.join("alembic", "versions", "0001_initial_schema.py")
        assert os.path.exists(migration_path), f"Migration file not found: {migration_path}"

    def test_initial_migration_has_tables(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "migration",
            "alembic/versions/0001_initial_schema.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "upgrade")
        assert hasattr(mod, "downgrade")
        assert mod.revision == "0001"


class TestSchemaValidation:
    """Test enhanced Pydantic schema validation."""

    def test_user_create_password_max_length(self):
        from api.schemas import UserCreate
        with pytest.raises(Exception):
            UserCreate(
                email="test@test.com",
                password="a" * 200,
                name="Test",
            )

    def test_campaign_create_vertical_pattern(self):
        from api.schemas import CampaignCreate
        # Valid vertical slug
        c = CampaignCreate(name="Test", vertical="vc")
        assert c.vertical == "vc"

        # Invalid vertical slug (starts with number)
        with pytest.raises(Exception):
            CampaignCreate(name="Test", vertical="1invalid")

    def test_campaign_create_vertical_pattern_underscore(self):
        from api.schemas import CampaignCreate
        c = CampaignCreate(name="Test", vertical="family_office")
        assert c.vertical == "family_office"
