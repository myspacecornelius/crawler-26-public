"""
Campaign management — create, run, list, and monitor crawl campaigns.
"""

from uuid import UUID
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Campaign, Lead, User, CreditTransaction
from ..schemas import CampaignCreate, CampaignResponse, CampaignList
from ..auth import get_current_user_id
from verticals import load_vertical, list_verticals

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(
    body: CampaignCreate,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a new crawl campaign."""
    # Validate vertical exists
    available = list_verticals()
    if body.vertical not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown vertical '{body.vertical}'. Available: {available}",
        )

    # Check credits
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.credits_remaining <= 0:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    campaign = Campaign(
        user_id=UUID(user_id),
        name=body.name,
        vertical=body.vertical,
        config=body.config,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)

    return CampaignResponse.model_validate(campaign)


@router.post("/{campaign_id}/run", response_model=CampaignResponse)
async def run_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Start executing a campaign. Dispatches to Celery task queue.
    If Celery is not available, runs synchronously in a background thread.
    """
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == UUID(user_id))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status == "running":
        raise HTTPException(status_code=409, detail="Campaign is already running")

    # Check user credits — use SELECT FOR UPDATE to prevent double-spend races
    user_result = await db.execute(
        select(User).where(User.id == UUID(user_id)).with_for_update()
    )
    user = user_result.scalar_one_or_none()
    if user.credits_remaining <= 0:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    # Update status
    campaign.status = "running"
    campaign.started_at = datetime.now(timezone.utc)
    campaign.error_message = None
    await db.commit()

    # Dispatch to task queue
    try:
        from ..tasks import run_crawl_campaign, CELERY_AVAILABLE
        if CELERY_AVAILABLE:
            task = run_crawl_campaign.delay(str(campaign_id), str(user_id))
            campaign.task_id = getattr(task, "id", "celery")
        else:
            import threading
            campaign.task_id = "local"
            threading.Thread(
                target=run_crawl_campaign,
                args=(str(campaign_id), str(user_id)),
                daemon=True,
            ).start()
        await db.commit()
    except Exception:
        # Celery not available — mark for manual run
        campaign.task_id = "manual"
        await db.commit()

    await db.refresh(campaign)
    return CampaignResponse.model_validate(campaign)


@router.get("", response_model=CampaignList)
async def list_campaigns(
    status_filter: Optional[str] = Query(None, alias="status"),
    vertical: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """List all campaigns for the current user."""
    query = select(Campaign).where(Campaign.user_id == UUID(user_id))

    if status_filter:
        query = query.where(Campaign.status == status_filter)
    if vertical:
        query = query.where(Campaign.vertical == vertical)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    # Paginate
    query = query.order_by(Campaign.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    campaigns = result.scalars().all()

    return CampaignList(
        campaigns=[CampaignResponse.model_validate(c) for c in campaigns],
        total=total,
    )


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Get campaign details."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == UUID(user_id))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return CampaignResponse.model_validate(campaign)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(
    campaign_id: UUID,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Delete a campaign and all its leads."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id, Campaign.user_id == UUID(user_id))
    )
    campaign = result.scalar_one_or_none()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status == "running":
        raise HTTPException(status_code=409, detail="Cannot delete a running campaign")

    await db.delete(campaign)
    await db.commit()
