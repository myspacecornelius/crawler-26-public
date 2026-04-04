"""
Centralized configuration via pydantic BaseSettings.

All pipeline settings are environment-driven with sensible defaults.
Override via environment variables or a .env file.

Usage:
    from config.settings import settings
    print(settings.concurrency)
    print(settings.smtp_timeout)
"""

from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class CrawlSettings(BaseSettings):
    """Pipeline-wide configuration. Every field maps to an env var."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # ── Concurrency ──────────────────────────────────────────────
    concurrency: int = Field(10, description="Max concurrent browser instances for deep crawl")
    smtp_concurrency: int = Field(20, description="Max concurrent SMTP connections")
    greyhat_concurrency: int = Field(10, description="Concurrency for greyhat enrichment modules")
    dorker_concurrency: int = Field(3, description="Google Dorker concurrent workers")
    gravatar_concurrency: int = Field(50, description="Gravatar oracle concurrent workers")

    # ── Timeouts (seconds) ───────────────────────────────────────
    page_timeout_ms: int = Field(60000, description="Playwright page navigation timeout (ms)")
    browser_timeout_ms: int = Field(15000, description="JS scraper browser timeout (ms)")
    smtp_timeout: int = Field(10, description="SMTP connection timeout (seconds)")
    http_timeout: int = Field(30, description="General HTTP request timeout (seconds)")

    # ── Retries ──────────────────────────────────────────────────
    max_retries: int = Field(3, description="Max retries for transient errors")
    retry_base_delay: float = Field(1.0, description="Base delay for exponential backoff (seconds)")
    retry_max_delay: float = Field(30.0, description="Maximum retry delay (seconds)")

    # ── Freshness & Incremental ──────────────────────────────────
    stale_days: int = Field(7, description="Days before a domain is considered stale")
    reverify_days: int = Field(14, description="Days before re-verifying an email")

    # ── Data Directories ─────────────────────────────────────────
    data_dir: Path = Field(Path("data"), description="Root data directory")
    enriched_dir: Path = Field(Path("data/enriched"), description="Enriched output directory")
    screenshot_dir: Path = Field(Path("data/screenshots"), description="Screenshot directory")
    checkpoint_dir: Path = Field(Path("data/enriched"), description="Checkpoint directory")

    # ── Database ─────────────────────────────────────────────────
    database_url: str = Field(
        "sqlite+aiosqlite:///./data/leadfactory.db",
        description="Database URL (PostgreSQL or SQLite)",
    )

    # ── API Keys ─────────────────────────────────────────────────
    serpapi_key: str = Field("", description="SerpAPI key for Google search")
    github_token: str = Field("", description="GitHub API token")
    hunter_api_key: str = Field("", description="Hunter.io API key")
    zerobounce_api_key: str = Field("", description="ZeroBounce API key")
    millionverifier_api_key: str = Field("", description="MillionVerifier API key")

    # ── SMTP ─────────────────────────────────────────────────────
    smtp_helo_domain: str = Field("leadfactory.io", description="HELO domain for SMTP verification")
    smtp_proxy_host: str = Field("", description="SMTP proxy host")
    smtp_proxy_port: int = Field(0, description="SMTP proxy port")

    # ── Celery / Task Queue ──────────────────────────────────────
    celery_broker_url: str = Field(
        "redis://localhost:6379/0",
        description="Celery broker URL (Redis)",
    )
    celery_result_backend: str = Field(
        "redis://localhost:6379/1",
        description="Celery result backend URL",
    )

    # ── Logging ──────────────────────────────────────────────────
    log_level: str = Field("INFO", description="Logging level")
    log_format: str = Field(
        "json",
        description="Log format: 'json' for structured or 'text' for human-readable",
    )
    log_file: str = Field("", description="Log file path (empty = stdout only)")

    # ── Metrics ──────────────────────────────────────────────────
    metrics_enabled: bool = Field(True, description="Enable pipeline metrics collection")
    metrics_port: int = Field(9090, description="Prometheus metrics exporter port")
    metrics_file: str = Field(
        "data/metrics/pipeline_metrics.csv",
        description="CSV metrics output file",
    )

    # ── Pipeline ─────────────────────────────────────────────────
    target_lead_count: int = Field(150000, description="Target total lead count")
    lead_batch_size: int = Field(100, description="Batch size for DB persistence of leads")

    # ── Deep Crawl Caps ─────────────────────────────────────────
    max_bio_pages_per_fund: int = Field(25, description="Max bio pages to follow per fund")
    max_team_pages_per_fund: int = Field(12, description="Max team pages to try per fund")

    # ── Waterfall ─────────────────────────────────────────────
    waterfall_max_concurrent: int = Field(5, description="Max concurrent waterfall verification requests")
    waterfall_cache_by_domain: bool = Field(True, description="Cache waterfall results by domain to reduce API calls")

    # ── WHOIS Enrichment ──────────────────────────────────────
    whois_enabled: bool = Field(False, description="Enable WHOIS enricher in greyhat phase (set WHOIS_ENABLED=true)")
    whois_rate_limit: float = Field(1.0, description="Seconds between WHOIS queries to avoid rate limiting")
    whois_max_domains: int = Field(500, description="Max domains to query via WHOIS per run")

    # ── Config file paths ────────────────────────────────────────
    sites_config: Path = Field(Path("config/sites.yaml"), description="Sites config YAML")
    scoring_config: Path = Field(Path("config/scoring.yaml"), description="Scoring config YAML")
    proxies_config: Path = Field(Path("config/proxies.yaml"), description="Proxies config YAML")
    search_config: Path = Field(Path("config/search.yaml"), description="Search config YAML")


# Singleton — importable from anywhere
settings = CrawlSettings()
