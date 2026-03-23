"""
SQLAlchemy models for the LeadFactory platform.

Tables: users, campaigns, leads, credits, api_keys
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Index, Enum as SAEnum, JSON, TypeDecorator, CHAR,
)
from sqlalchemy.dialects.postgresql import UUID as pgUUID
from sqlalchemy.orm import relationship, declarative_base


class GUID(TypeDecorator):
    """Platform-independent UUID type.
    Uses PostgreSQL's UUID type when available, otherwise CHAR(32).
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(pgUUID(as_uuid=True))
        else:
            return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        elif dialect.name == "postgresql":
            return value if isinstance(value, uuid.UUID) else uuid.UUID(value)
        else:
            return value.hex if isinstance(value, uuid.UUID) else uuid.UUID(value).hex

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    company = Column(String(255), default="")
    plan = Column(String(50), default="starter")  # starter, pro, scale, enterprise
    credits_remaining = Column(Integer, default=500)
    credits_monthly = Column(Integer, default=500)
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    stripe_customer_id = Column(String(255), nullable=True, unique=True)
    stripe_subscription_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True), nullable=True)

    campaigns = relationship("Campaign", back_populates="user", cascade="all, delete-orphan")
    api_keys = relationship("ApiKey", back_populates="user", cascade="all, delete-orphan")
    credit_transactions = relationship("CreditTransaction", back_populates="user", cascade="all, delete-orphan")


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    key_hash = Column(String(255), nullable=False, unique=True)
    name = Column(String(100), default="Default")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_used = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="api_keys")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    name = Column(String(255), nullable=False)
    vertical = Column(String(50), nullable=False)  # vc, pe, family_office, corp_dev
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    config = Column(JSON, default=dict)  # extra config overrides
    total_leads = Column(Integer, default=0)
    total_emails = Column(Integer, default=0)
    credits_used = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Celery task ID for status tracking
    task_id = Column(String(255), nullable=True)

    user = relationship("User", back_populates="campaigns")
    leads = relationship("Lead", back_populates="campaign", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_campaigns_user_status", "user_id", "status"),
    )


class Lead(Base):
    __tablename__ = "leads"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(GUID(), ForeignKey("campaigns.id"), nullable=False)

    # Contact info
    name = Column(String(255), nullable=False)
    email = Column(String(255), default="N/A")
    email_verified = Column(Boolean, default=False)
    email_source = Column(String(50), default="guessed")  # scraped, pattern, guessed, verified
    email_status = Column(String(50), default="unknown")  # unknown, guessed, scraped, verified, undeliverable, catch_all
    linkedin = Column(String(500), default="N/A")
    phone = Column(String(50), default="N/A")

    # Organization
    fund = Column(String(255), default="N/A")
    role = Column(String(255), default="N/A")
    website = Column(String(500), default="N/A")

    # Investment profile
    sectors = Column(String(500), default="N/A")
    check_size = Column(String(100), default="N/A")
    stage = Column(String(100), default="N/A")
    hq = Column(String(100), default="N/A")

    # Scoring
    score = Column(Float, default=0.0)
    tier = Column(String(20), default="COOL")  # HOT, WARM, COOL

    # Metadata
    source = Column(String(500), default="N/A")  # URL where lead was found
    opted_out = Column(Boolean, default=False)
    scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_verified = Column(DateTime(timezone=True), nullable=True)  # Last SMTP/email re-verification
    last_crawled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    campaign = relationship("Campaign", back_populates="leads")

    __table_args__ = (
        Index("ix_leads_campaign_score", "campaign_id", "score"),
        Index("ix_leads_email", "email"),
        Index("ix_leads_fund", "fund"),
        Index("ix_leads_name_fund", "name", "fund"),
        Index("ix_leads_email_fund", "email", "fund", unique=True),
    )


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    campaign_id = Column(GUID(), ForeignKey("campaigns.id"), nullable=True)
    amount = Column(Integer, nullable=False)  # positive = add, negative = consume
    reason = Column(String(255), nullable=False)  # "campaign_run", "monthly_refill", "purchase"
    balance_after = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="credit_transactions")

    __table_args__ = (
        Index("ix_credit_tx_user", "user_id", "created_at"),
    )


class PortfolioCompany(Base):
    __tablename__ = "portfolio_companies"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    fund_name = Column(String(255), nullable=False, index=True)
    company_name = Column(String(255), nullable=False)
    sector = Column(String(255), default="")
    stage = Column(String(100), default="")
    url = Column(String(500), default="")
    year = Column(Integer, nullable=True)
    scraped_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_portfolio_fund_company", "fund_name", "company_name", unique=True),
    )


class CrawlState(Base):
    """Tracks per-domain crawl freshness for incremental crawl support."""
    __tablename__ = "crawl_state"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    last_crawled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    leads_found = Column(Integer, default=0)
    status = Column(String(50), default="completed")  # completed, failed, timeout
    crawl_duration_s = Column(Float, nullable=True)

    __table_args__ = (
        Index("ix_crawl_state_last_crawled", "last_crawled_at"),
    )


class PipelineLead(Base):
    """
    Streaming lead storage for the pipeline.

    Leads are written incrementally as they are discovered (rather than
    held in memory) and deduplicated via a unique constraint on
    (name_normalized, fund_normalized).
    """
    __tablename__ = "pipeline_leads"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(String(50), nullable=False, index=True)

    # Raw + normalized identity (for dedup)
    name = Column(String(255), nullable=False)
    name_normalized = Column(String(255), nullable=False)
    fund = Column(String(255), default="N/A")
    fund_normalized = Column(String(255), default="")

    # Contact info
    email = Column(String(255), default="N/A")
    email_status = Column(String(50), default="unknown")
    role = Column(String(255), default="N/A")
    linkedin = Column(String(500), default="N/A")
    website = Column(String(500), default="")

    # Investment profile
    location = Column(String(255), default="")
    stage = Column(String(100), default="")
    check_size = Column(String(100), default="")
    focus_areas = Column(Text, default="")

    # Scoring
    lead_score = Column(Integer, default=0)
    tier = Column(String(20), default="")

    # Metadata
    source = Column(String(500), default="")
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_pipeline_leads_name_fund", "name_normalized", "fund_normalized", unique=True),
        Index("ix_pipeline_leads_email", "email"),
        Index("ix_pipeline_leads_run", "run_id"),
        Index("ix_pipeline_leads_email_fund", "email", "fund_normalized"),
    )


class PipelineRun(Base):
    """
    Tracks each pipeline execution for observability.
    Records start/end times, stage results, and error counts.
    """
    __tablename__ = "pipeline_runs"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)
    run_id = Column(String(50), unique=True, nullable=False)
    status = Column(String(50), default="running")  # running, completed, failed
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True), nullable=True)
    total_leads = Column(Integer, default=0)
    total_emails = Column(Integer, default=0)
    total_errors = Column(Integer, default=0)
    stages_completed = Column(Text, default="")  # comma-separated stage names
    error_message = Column(Text, nullable=True)
    config_snapshot = Column(JSON, default=dict)  # args used for this run
