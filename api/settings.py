"""
Centralised configuration via pydantic.BaseSettings.

All hard-coded values (database URL, JWT secrets, SMTP settings, CORS origins,
Stripe keys, etc.) are loaded from environment variables with sensible defaults.

Usage::

    from api.settings import settings
    print(settings.database_url)
"""

import secrets
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── General ────────────────────────────────────
    app_name: str = "LeadFactory"
    debug: bool = False

    # ── Database ───────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/leadfactory.db",
        alias="DATABASE_URL",
    )
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    db_pool_recycle: int = Field(default=3600, alias="DB_POOL_RECYCLE")

    # ── JWT / Auth ─────────────────────────────────
    secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(64),
        alias="LEADFACTORY_SECRET_KEY",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_hours: int = 24

    # ── Password policy ────────────────────────────
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = False

    # ── Rate limiting ──────────────────────────────
    rate_limit_login: str = Field(
        default="5/minute",
        alias="RATE_LIMIT_LOGIN",
        description="Login endpoint rate limit (e.g. '5/minute')",
    )
    rate_limit_register: str = Field(
        default="3/minute",
        alias="RATE_LIMIT_REGISTER",
    )
    rate_limit_default: str = Field(
        default="60/minute",
        alias="RATE_LIMIT_DEFAULT",
    )

    # ── CORS ───────────────────────────────────────
    cors_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
        description="Comma-separated list of allowed CORS origins",
    )

    @property
    def cors_origin_list(self) -> List[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # ── Stripe ─────────────────────────────────────
    stripe_secret_key: str = Field(default="", alias="STRIPE_SECRET_KEY")
    stripe_publishable_key: str = Field(default="", alias="STRIPE_PUBLISHABLE_KEY")
    stripe_webhook_secret: str = Field(default="", alias="STRIPE_WEBHOOK_SECRET")
    stripe_price_starter: str = Field(default="", alias="STRIPE_PRICE_STARTER")
    stripe_price_pro: str = Field(default="", alias="STRIPE_PRICE_PRO")
    stripe_price_scale: str = Field(default="", alias="STRIPE_PRICE_SCALE")
    stripe_price_credits_1k: str = Field(default="", alias="STRIPE_PRICE_CREDITS_1K")
    stripe_price_credits_5k: str = Field(default="", alias="STRIPE_PRICE_CREDITS_5K")
    stripe_price_credits_10k: str = Field(default="", alias="STRIPE_PRICE_CREDITS_10K")

    # ── Frontend ───────────────────────────────────
    frontend_url: str = Field(default="http://localhost:3000", alias="FRONTEND_URL")

    # ── Redis / Task queue ─────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")

    # ── Outreach providers ─────────────────────────
    instantly_api_key: str = Field(default="", alias="INSTANTLY_API_KEY")
    smartlead_api_key: str = Field(default="", alias="SMARTLEAD_API_KEY")

    # ── SMTP (for email sending) ───────────────────
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="", alias="SMTP_FROM_EMAIL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }

    @property
    def async_database_url(self) -> str:
        """Return the database URL with the async driver."""
        url = self.database_url
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def is_sqlite(self) -> bool:
        return "sqlite" in self.database_url


settings = Settings()
