"""
Lead retrieval, filtering, and export endpoints.
"""

import csv
import io
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Campaign, Lead
from ..schemas import LeadResponse, LeadList, OptOutResponse
from ..auth import get_current_user_id

_limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("/campaign/{campaign_id}", response_model=LeadList)
async def list_leads(
    campaign_id: UUID,
    tier: Optional[str] = None,
    min_score: Optional[float] = None,
    has_email: Optional[bool] = None,
    email_verified: Optional[bool] = None,
    email_status: Optional[str] = None,
    fund: Optional[str] = None,
    sector: Optional[str] = None,
    stage: Optional[str] = None,
    check_size: Optional[str] = None,
    hq: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = Query("score", enum=["score", "name", "fund", "scraped_at"]),
    sort_dir: str = Query("desc", enum=["asc", "desc"]),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List leads for a campaign with filtering, sorting, and pagination."""
    # Verify campaign ownership
    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == UUID(user_id))
    )
    if not camp_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    query = select(Lead).where(Lead.campaign_id == campaign_id, Lead.opted_out == False)

    # Apply filters
    if tier:
        query = query.where(Lead.tier == tier.upper())
    if min_score is not None:
        query = query.where(Lead.score >= min_score)
    if has_email is True:
        query = query.where(and_(Lead.email != "N/A", Lead.email != ""))
    elif has_email is False:
        query = query.where(or_(Lead.email == "N/A", Lead.email == ""))
    if email_verified is not None:
        query = query.where(Lead.email_verified == email_verified)
    if email_status:
        status = email_status.lower()
        if status == "verified":
            query = query.where(Lead.email_verified == True, Lead.email_source != "scraped")
        elif status == "scraped":
            query = query.where(Lead.email_source == "scraped")
        elif status == "guessed":
            query = query.where(Lead.email_verified == False, Lead.email_source.in_(["guessed", "pattern"]))
        elif status == "undeliverable":
            query = query.where(Lead.email_verified == False, Lead.email_source == "undeliverable")
        elif status == "catch_all":
            query = query.where(Lead.email_source == "catch_all")
    if fund:
        query = query.where(Lead.fund.ilike(f"%{fund}%"))
    if sector:
        query = query.where(Lead.sectors.ilike(f"%{sector}%"))
    if stage:
        query = query.where(Lead.stage.ilike(f"%{stage}%"))
    if check_size:
        query = query.where(Lead.check_size.ilike(f"%{check_size}%"))
    if hq:
        query = query.where(Lead.hq.ilike(f"%{hq}%"))
    if search:
        query = query.where(
            or_(
                Lead.name.ilike(f"%{search}%"),
                Lead.fund.ilike(f"%{search}%"),
                Lead.email.ilike(f"%{search}%"),
                Lead.role.ilike(f"%{search}%"),
            )
        )

    # Count total matching
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Sort
    sort_col = getattr(Lead, sort_by, Lead.score)
    if sort_dir == "desc":
        query = query.order_by(sort_col.desc())
    else:
        query = query.order_by(sort_col.asc())

    # Paginate
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    leads = result.scalars().all()

    return LeadList(
        leads=[LeadResponse.model_validate(l) for l in leads],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/campaign/{campaign_id}/export")
async def export_leads_csv(
    campaign_id: UUID,
    tier: Optional[str] = None,
    min_score: Optional[float] = None,
    has_email: Optional[bool] = None,
    sector: Optional[str] = None,
    stage: Optional[str] = None,
    check_size: Optional[str] = None,
    hq: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Export campaign leads as a CSV file."""
    # Verify ownership
    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == UUID(user_id))
    )
    campaign = camp_result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    query = select(Lead).where(Lead.campaign_id == campaign_id, Lead.opted_out == False)
    if tier:
        query = query.where(Lead.tier == tier.upper())
    if min_score is not None:
        query = query.where(Lead.score >= min_score)
    if has_email is True:
        query = query.where(and_(Lead.email != "N/A", Lead.email != ""))
    if sector:
        query = query.where(Lead.sectors.ilike(f"%{sector}%"))
    if stage:
        query = query.where(Lead.stage.ilike(f"%{stage}%"))
    if check_size:
        query = query.where(Lead.check_size.ilike(f"%{check_size}%"))
    if hq:
        query = query.where(Lead.hq.ilike(f"%{hq}%"))

    query = query.order_by(Lead.score.desc())
    result = await db.execute(query)
    leads = result.scalars().all()

    # Build CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Name", "Email", "Email Verified", "LinkedIn", "Phone",
        "Fund", "Role", "Website", "Sectors", "Check Size",
        "Stage", "HQ", "Score", "Tier", "Source",
    ])
    for lead in leads:
        writer.writerow([
            lead.name, lead.email, lead.email_verified, lead.linkedin,
            lead.phone, lead.fund, lead.role, lead.website, lead.sectors,
            lead.check_size, lead.stage, lead.hq, lead.score, lead.tier,
            lead.source,
        ])

    output.seek(0)
    filename = f"{campaign.name.replace(' ', '_')}_{campaign.vertical}_leads.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/campaign/{campaign_id}/stats")
async def lead_stats(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated stats for a campaign's leads."""
    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == UUID(user_id))
    )
    if not camp_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    # Total leads
    total = (await db.execute(
        select(func.count()).where(Lead.campaign_id == campaign_id)
    )).scalar()

    # Leads with email
    with_email = (await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id,
            Lead.email != "N/A",
            Lead.email != "",
        )
    )).scalar()

    # Verified emails
    verified = (await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id,
            Lead.email_verified == True,
        )
    )).scalar()

    # Tier breakdown
    hot = (await db.execute(
        select(func.count()).where(Lead.campaign_id == campaign_id, Lead.tier == "HOT")
    )).scalar()
    warm = (await db.execute(
        select(func.count()).where(Lead.campaign_id == campaign_id, Lead.tier == "WARM")
    )).scalar()

    # Average score
    avg_score = (await db.execute(
        select(func.avg(Lead.score)).where(Lead.campaign_id == campaign_id)
    )).scalar() or 0.0

    # Top funds by lead count
    fund_counts = (await db.execute(
        select(Lead.fund, func.count().label("count"))
        .where(Lead.campaign_id == campaign_id)
        .group_by(Lead.fund)
        .order_by(func.count().desc())
        .limit(10)
    )).all()

    return {
        "total_leads": total,
        "with_email": with_email,
        "email_rate": round(with_email / total * 100, 1) if total > 0 else 0,
        "verified_emails": verified,
        "hot_leads": hot,
        "warm_leads": warm,
        "cool_leads": total - hot - warm,
        "avg_score": round(avg_score, 1),
        "top_funds": [{"fund": f, "count": c} for f, c in fund_counts],
    }


# ── Freshness ────────────────────────────────────

@router.get("/campaign/{campaign_id}/freshness")
async def lead_freshness(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get freshness stats: how many leads have been verified/crawled recently."""
    from datetime import datetime, timezone, timedelta

    camp_result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == UUID(user_id))
    )
    if not camp_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Campaign not found")

    total = (await db.execute(
        select(func.count()).where(Lead.campaign_id == campaign_id)
    )).scalar()

    now = datetime.now(timezone.utc)

    # Verified within 7 days
    cutoff_7d = now - timedelta(days=7)
    verified_7d = (await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id,
            Lead.last_verified != None,
            Lead.last_verified >= cutoff_7d,
        )
    )).scalar()

    # Verified within 14 days
    cutoff_14d = now - timedelta(days=14)
    verified_14d = (await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id,
            Lead.last_verified != None,
            Lead.last_verified >= cutoff_14d,
        )
    )).scalar()

    # Never verified
    never_verified = (await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id,
            Lead.last_verified == None,
        )
    )).scalar()

    # Crawled within 7 days
    crawled_7d = (await db.execute(
        select(func.count()).where(
            Lead.campaign_id == campaign_id,
            Lead.last_crawled_at != None,
            Lead.last_crawled_at >= cutoff_7d,
        )
    )).scalar()

    return {
        "total_leads": total,
        "verified_last_7d": verified_7d,
        "verified_last_14d": verified_14d,
        "never_verified": never_verified,
        "crawled_last_7d": crawled_7d,
        "stale_leads": total - crawled_7d,
        "freshness_pct": round(crawled_7d / total * 100, 1) if total > 0 else 0,
    }


# ── Opt-out ────────────────────────────────────

@router.post("/{lead_id}/optout", response_model=OptOutResponse)
async def optout_lead(
    lead_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Opt a lead out (authenticated, by lead ID). Requires the lead to belong to the caller's campaign."""
    result = await db.execute(
        select(Lead)
        .join(Campaign, Lead.campaign_id == Campaign.id)
        .where(Lead.id == lead_id, Campaign.user_id == UUID(user_id))
    )
    lead = result.scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    lead.opted_out = True
    await db.commit()
    return OptOutResponse(email=lead.email, opted_out=True, message="Lead has been opted out")


@router.get("/optout", response_model=OptOutResponse)
@_limiter.limit("10/minute")
async def optout_by_email(
    request: Request,
    email: str = Query(..., description="Email address to opt out"),
    db: AsyncSession = Depends(get_db),
):
    """Public opt-out endpoint — no auth required. Opts out all leads with given email."""
    result = await db.execute(select(Lead).where(Lead.email == email))
    leads = result.scalars().all()

    if not leads:
        # Still return success to avoid leaking whether the email exists
        return OptOutResponse(email=email, opted_out=True, message="Opt-out request processed")

    for lead in leads:
        lead.opted_out = True
    await db.commit()

    return OptOutResponse(
        email=email,
        opted_out=True,
        message=f"Opt-out request processed for {len(leads)} record(s)",
    )
