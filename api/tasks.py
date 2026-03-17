"""
Celery tasks for async crawl job execution.

When Celery + Redis are available, campaigns run as background tasks.
Falls back to in-process execution for local development.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger("leadfactory.tasks")

# ── Celery setup (optional — degrades gracefully) ──

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

try:
    from celery import Celery
    celery_app = Celery("leadfactory", broker=REDIS_URL, backend=REDIS_URL)
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        task_track_started=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
    )
    CELERY_AVAILABLE = True
except ImportError:
    celery_app = None
    CELERY_AVAILABLE = False
    logger.info("Celery not installed — tasks will run in-process")


def _run_campaign_sync(campaign_id: str, user_id: str):
    """
    Execute a crawl campaign synchronously.
    This is the core logic shared by both Celery and in-process execution.
    """
    # Import here to avoid circular imports
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from .models import Campaign, Lead, User, CreditTransaction
    from .settings import settings as _settings
    DATABASE_URL = _settings.database_url
    from verticals import load_vertical

    # Use sync engine for task execution
    sync_url = DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")
    engine = create_engine(sync_url)

    with Session(engine) as db:
        campaign = db.query(Campaign).filter(Campaign.id == UUID(campaign_id)).first()
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found")
            return

        user = db.query(User).filter(User.id == UUID(user_id)).first()
        if not user:
            logger.error(f"User {user_id} not found")
            return

        try:
            # Load vertical config
            vertical = load_vertical(campaign.vertical)
            logger.info(f"Running campaign '{campaign.name}' with vertical '{vertical.name}'")

            # Run the crawl engine
            from engine import CrawlEngine

            engine_instance = CrawlEngine(
                headless=True,
                deep=True,
                dry_run=False,
                vertical=campaign.vertical,
            )

            # Run the engine and collect leads
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                all_leads = loop.run_until_complete(engine_instance.run())
            finally:
                loop.close()

            # Build lead objects in memory first so credit deduction
            # only happens after all objects are ready (no partial commits).
            lead_objects = []
            emails_found = 0
            for lead_data in all_leads:
                email = getattr(lead_data, "email", "N/A")
                lead_objects.append(Lead(
                    campaign_id=campaign.id,
                    name=getattr(lead_data, "name", "Unknown"),
                    email=email,
                    email_verified=False,
                    email_source="scraped" if email != "N/A" else "none",
                    linkedin=getattr(lead_data, "linkedin", "N/A"),
                    fund=getattr(lead_data, "fund", "N/A"),
                    role=getattr(lead_data, "role", "N/A"),
                    website=getattr(lead_data, "website", "N/A"),
                    sectors="; ".join(getattr(lead_data, "focus_areas", [])) or "N/A",
                    check_size=getattr(lead_data, "check_size", "N/A"),
                    stage=getattr(lead_data, "stage", "N/A"),
                    hq=getattr(lead_data, "location", "N/A"),
                    score=float(getattr(lead_data, "lead_score", 0)),
                    tier=getattr(lead_data, "tier", "COOL"),
                    source=getattr(lead_data, "source", "N/A"),
                ))
                if email and email != "N/A":
                    emails_found += 1

            leads_stored = len(lead_objects)
            db.add_all(lead_objects)

            # Deduct credits only after all lead objects are built — if anything
            # above raised an exception the session will roll back untouched.
            credits_used = min(emails_found, user.credits_remaining)
            user.credits_remaining -= credits_used

            # Record transaction
            tx = CreditTransaction(
                user_id=user.id,
                campaign_id=campaign.id,
                amount=-credits_used,
                reason="campaign_run",
                balance_after=user.credits_remaining,
            )
            db.add(tx)

            # Update campaign
            campaign.status = "completed"
            campaign.total_leads = leads_stored
            campaign.total_emails = emails_found
            campaign.credits_used = credits_used
            campaign.completed_at = datetime.now(timezone.utc)

            db.commit()
            logger.info(
                f"Campaign '{campaign.name}' completed: "
                f"{leads_stored} leads, {emails_found} emails, {credits_used} credits used"
            )

        except Exception as e:
            campaign.status = "failed"
            campaign.error_message = str(e)[:500]
            campaign.completed_at = datetime.now(timezone.utc)
            db.commit()
            logger.error(f"Campaign '{campaign.name}' failed: {e}")
            raise


# ── Celery task (if available) ──────────────────

if CELERY_AVAILABLE:
    @celery_app.task(bind=True, max_retries=1)
    def run_crawl_campaign(self, campaign_id: str, user_id: str):
        """Celery task wrapper for campaign execution."""
        try:
            _run_campaign_sync(campaign_id, user_id)
        except Exception as exc:
            logger.error(f"Task failed: {exc}")
            raise self.retry(exc=exc, countdown=60)
else:
    def run_crawl_campaign(campaign_id: str, user_id: str):
        """Fallback: run synchronously when Celery is not available."""
        _run_campaign_sync(campaign_id, user_id)

    # Add a .delay() method for compatibility
    run_crawl_campaign.delay = lambda campaign_id, user_id: run_crawl_campaign(campaign_id, user_id)
