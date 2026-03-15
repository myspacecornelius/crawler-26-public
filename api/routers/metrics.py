"""
Metrics and pattern statistics endpoints.

Provides pipeline run statistics, email pattern stats, and dashboard-level
aggregations for monitoring and analytics.
"""

from uuid import UUID
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Campaign, Lead, User, CreditTransaction, CrawlState
from ..auth import get_current_user_id

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/pipeline")
async def pipeline_stats(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Pipeline run statistics — campaigns by status, success rates, timing."""
    uid = UUID(user_id)

    total = (await db.execute(
        select(func.count()).where(Campaign.user_id == uid)
    )).scalar() or 0

    completed = (await db.execute(
        select(func.count()).where(Campaign.user_id == uid, Campaign.status == "completed")
    )).scalar() or 0

    failed = (await db.execute(
        select(func.count()).where(Campaign.user_id == uid, Campaign.status == "failed")
    )).scalar() or 0

    running = (await db.execute(
        select(func.count()).where(Campaign.user_id == uid, Campaign.status == "running")
    )).scalar() or 0

    pending = (await db.execute(
        select(func.count()).where(Campaign.user_id == uid, Campaign.status == "pending")
    )).scalar() or 0

    total_leads = (await db.execute(
        select(func.sum(Campaign.total_leads)).where(Campaign.user_id == uid)
    )).scalar() or 0

    total_emails = (await db.execute(
        select(func.sum(Campaign.total_emails)).where(Campaign.user_id == uid)
    )).scalar() or 0

    total_credits = (await db.execute(
        select(func.sum(Campaign.credits_used)).where(Campaign.user_id == uid)
    )).scalar() or 0

    # Recent campaigns (last 10)
    recent = (await db.execute(
        select(
            Campaign.id, Campaign.name, Campaign.vertical,
            Campaign.status, Campaign.total_leads, Campaign.credits_used,
            Campaign.started_at, Campaign.completed_at, Campaign.created_at,
        )
        .where(Campaign.user_id == uid)
        .order_by(Campaign.created_at.desc())
        .limit(10)
    )).all()

    return {
        "total_campaigns": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "pending": pending,
        "success_rate": round(completed / total * 100, 1) if total > 0 else 0,
        "total_leads_generated": total_leads,
        "total_emails_found": total_emails,
        "total_credits_used": total_credits,
        "recent_campaigns": [
            {
                "id": str(r.id),
                "name": r.name,
                "vertical": r.vertical,
                "status": r.status,
                "total_leads": r.total_leads,
                "credits_used": r.credits_used,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in recent
        ],
    }


@router.get("/patterns")
async def pattern_stats(
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Email pattern statistics — breakdown of email sources, verification rates."""
    uid = UUID(user_id)

    # Get all campaigns for this user
    campaigns = (await db.execute(
        select(Campaign.id).where(Campaign.user_id == uid)
    )).scalars().all()

    if not campaigns:
        return {
            "total_leads": 0,
            "email_sources": {},
            "verification_rate": 0,
            "tier_distribution": {},
        }

    campaign_ids = list(campaigns)

    total = (await db.execute(
        select(func.count()).where(Lead.campaign_id.in_(campaign_ids))
    )).scalar() or 0

    # Email source breakdown
    source_counts = (await db.execute(
        select(Lead.email_source, func.count().label("count"))
        .where(Lead.campaign_id.in_(campaign_ids))
        .group_by(Lead.email_source)
    )).all()

    # Verification rate
    verified = (await db.execute(
        select(func.count()).where(
            Lead.campaign_id.in_(campaign_ids),
            Lead.email_verified == True,
        )
    )).scalar() or 0

    # Tier distribution
    tier_counts = (await db.execute(
        select(Lead.tier, func.count().label("count"))
        .where(Lead.campaign_id.in_(campaign_ids))
        .group_by(Lead.tier)
    )).all()

    # Leads with email
    with_email = (await db.execute(
        select(func.count()).where(
            Lead.campaign_id.in_(campaign_ids),
            Lead.email != "N/A",
            Lead.email != "",
        )
    )).scalar() or 0

    return {
        "total_leads": total,
        "leads_with_email": with_email,
        "email_rate": round(with_email / total * 100, 1) if total > 0 else 0,
        "email_sources": {src: cnt for src, cnt in source_counts},
        "verified_emails": verified,
        "verification_rate": round(verified / with_email * 100, 1) if with_email > 0 else 0,
        "tier_distribution": {tier: cnt for tier, cnt in tier_counts},
    }


@router.get("/crawl-health")
async def crawl_health(
    days: int = Query(7, ge=1, le=90),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Crawl health metrics from the crawl_state table."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    total_domains = (await db.execute(
        select(func.count()).select_from(CrawlState)
    )).scalar() or 0

    recent = (await db.execute(
        select(func.count()).where(CrawlState.last_crawled_at >= cutoff)
    )).scalar() or 0

    failed = (await db.execute(
        select(func.count()).where(CrawlState.status == "failed")
    )).scalar() or 0

    avg_duration = (await db.execute(
        select(func.avg(CrawlState.crawl_duration_s)).where(
            CrawlState.last_crawled_at >= cutoff,
            CrawlState.crawl_duration_s.isnot(None),
        )
    )).scalar()

    avg_leads = (await db.execute(
        select(func.avg(CrawlState.leads_found)).where(
            CrawlState.last_crawled_at >= cutoff,
        )
    )).scalar()

    return {
        "total_domains": total_domains,
        "crawled_last_n_days": recent,
        "failed_crawls": failed,
        "avg_crawl_duration_s": round(avg_duration, 2) if avg_duration else None,
        "avg_leads_per_crawl": round(avg_leads, 1) if avg_leads else None,
        "period_days": days,
    }
