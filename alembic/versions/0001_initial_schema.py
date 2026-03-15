"""Initial schema — creates all LeadFactory tables.

Revision ID: 0001
Revises: (none)
Create Date: 2026-03-15

This migration creates the full initial schema for LeadFactory:
- users, api_keys, campaigns, leads, credit_transactions,
  portfolio_companies, crawl_state
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Users ──────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), server_default=""),
        sa.Column("plan", sa.String(50), server_default="starter"),
        sa.Column("credits_remaining", sa.Integer, server_default="500"),
        sa.Column("credits_monthly", sa.Integer, server_default="500"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
        sa.Column("is_admin", sa.Boolean, server_default=sa.text("0")),
        sa.Column("stripe_customer_id", sa.String(255), unique=True, nullable=True),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )

    # ── API Keys ───────────────────────────────
    op.create_table(
        "api_keys",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("user_id", sa.CHAR(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("key_hash", sa.String(255), unique=True, nullable=False),
        sa.Column("name", sa.String(100), server_default="Default"),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used", sa.DateTime(timezone=True), nullable=True),
    )

    # ── Campaigns ──────────────────────────────
    op.create_table(
        "campaigns",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("user_id", sa.CHAR(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("vertical", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), server_default="pending"),
        sa.Column("config", sa.JSON, nullable=True),
        sa.Column("total_leads", sa.Integer, server_default="0"),
        sa.Column("total_emails", sa.Integer, server_default="0"),
        sa.Column("credits_used", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("task_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_campaigns_user_status", "campaigns", ["user_id", "status"])

    # ── Leads ──────────────────────────────────
    op.create_table(
        "leads",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("campaign_id", sa.CHAR(32), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), server_default="N/A"),
        sa.Column("email_verified", sa.Boolean, server_default=sa.text("0")),
        sa.Column("email_source", sa.String(50), server_default="guessed"),
        sa.Column("linkedin", sa.String(500), server_default="N/A"),
        sa.Column("phone", sa.String(50), server_default="N/A"),
        sa.Column("fund", sa.String(255), server_default="N/A"),
        sa.Column("role", sa.String(255), server_default="N/A"),
        sa.Column("website", sa.String(500), server_default="N/A"),
        sa.Column("sectors", sa.String(500), server_default="N/A"),
        sa.Column("check_size", sa.String(100), server_default="N/A"),
        sa.Column("stage", sa.String(100), server_default="N/A"),
        sa.Column("hq", sa.String(100), server_default="N/A"),
        sa.Column("score", sa.Float, server_default="0.0"),
        sa.Column("tier", sa.String(20), server_default="COOL"),
        sa.Column("source", sa.String(500), server_default="N/A"),
        sa.Column("opted_out", sa.Boolean, server_default=sa.text("0")),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_verified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_leads_campaign_score", "leads", ["campaign_id", "score"])
    op.create_index("ix_leads_email", "leads", ["email"])
    op.create_index("ix_leads_fund", "leads", ["fund"])

    # ── Credit Transactions ────────────────────
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("user_id", sa.CHAR(32), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("campaign_id", sa.CHAR(32), sa.ForeignKey("campaigns.id"), nullable=True),
        sa.Column("amount", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(255), nullable=False),
        sa.Column("balance_after", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_credit_tx_user", "credit_transactions", ["user_id", "created_at"])

    # ── Portfolio Companies ────────────────────
    op.create_table(
        "portfolio_companies",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("fund_name", sa.String(255), nullable=False, index=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("sector", sa.String(255), server_default=""),
        sa.Column("stage", sa.String(100), server_default=""),
        sa.Column("url", sa.String(500), server_default=""),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_portfolio_fund_company",
        "portfolio_companies",
        ["fund_name", "company_name"],
        unique=True,
    )

    # ── Crawl State ────────────────────────────
    op.create_table(
        "crawl_state",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("domain", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("last_crawled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leads_found", sa.Integer, server_default="0"),
        sa.Column("status", sa.String(50), server_default="completed"),
        sa.Column("crawl_duration_s", sa.Float, nullable=True),
    )
    op.create_index("ix_crawl_state_last_crawled", "crawl_state", ["last_crawled_at"])


def downgrade() -> None:
    op.drop_table("crawl_state")
    op.drop_table("portfolio_companies")
    op.drop_table("credit_transactions")
    op.drop_table("leads")
    op.drop_table("campaigns")
    op.drop_table("api_keys")
    op.drop_table("users")
