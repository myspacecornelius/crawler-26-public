"""Add processed_stripe_events table for webhook idempotency.

Revision ID: 0003
Revises: 33fcb7868b87
Create Date: 2026-04-02

Prevents double-processing of Stripe webhook events by storing
each event ID after successful handling.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "33fcb7868b87"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processed_stripe_events",
        sa.Column("id", sa.CHAR(32), primary_key=True),
        sa.Column("stripe_event_id", sa.String(255), unique=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_processed_stripe_events_event_id",
        "processed_stripe_events",
        ["stripe_event_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_processed_stripe_events_event_id", table_name="processed_stripe_events")
    op.drop_table("processed_stripe_events")
