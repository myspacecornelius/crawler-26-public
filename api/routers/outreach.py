"""
API routes for outreach campaign management.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from typing import List, Optional

from ..auth import get_current_user_id

router = APIRouter(prefix="/outreach", tags=["outreach"])

SUPPORTED_PROVIDERS = {"instantly", "smartlead"}


class OutreachCampaignCreate(BaseModel):
    name: str
    provider: str = "instantly"  # instantly | smartlead
    vertical: str = "vc"
    campaign_id: str  # LeadFactory campaign ID to pull leads from
    from_email: str = ""
    from_name: str = ""
    min_score: int = 0
    tiers: Optional[List[str]] = None  # ["HOT", "WARM"]
    api_key: Optional[str] = None  # Provider API key (or use env var)
    custom_vars: Optional[dict] = None  # Extra template variables

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider '{v}'. Must be one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}")
        return v


class OutreachCampaignAction(BaseModel):
    provider: str = "instantly"
    provider_campaign_id: str
    api_key: Optional[str] = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider '{v}'. Must be one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}")
        return v


@router.post("/launch")
async def launch_outreach(
    data: OutreachCampaignCreate,
    user_id: str = Depends(get_current_user_id),
):
    """Launch an outreach campaign from a LeadFactory campaign's leads."""
    from ..database import async_session
    from ..models import Campaign, Lead
    from sqlalchemy import select, and_

    from outreach.manager import OutreachManager
    from outreach.base import OutreachLead

    # Verify campaign belongs to user
    async with async_session() as session:
        result = await session.execute(
            select(Campaign).where(Campaign.id == data.campaign_id, Campaign.user_id == user_id)
        )
        campaign = result.scalar_one_or_none()
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")
        if campaign.status != "completed":
            raise HTTPException(status_code=400, detail="Campaign must be completed before launching outreach")

        # Fetch only usable leads: not opted out, with valid email, meeting score/tier criteria
        lead_query = select(Lead).where(
            Lead.campaign_id == data.campaign_id,
            Lead.opted_out == False,
            Lead.email != "N/A",
            Lead.email != "",
            Lead.email.contains("@"),
        )
        if data.min_score > 0:
            lead_query = lead_query.where(Lead.score >= data.min_score)
        if data.tiers:
            lead_query = lead_query.where(Lead.tier.in_(data.tiers))

        result = await session.execute(lead_query)
        db_leads = result.scalars().all()

    # Convert to OutreachLead objects
    outreach_leads = []
    for lead in db_leads:
        parts = (lead.name or "").split(None, 1)
        outreach_leads.append(OutreachLead(
            email=lead.email,
            first_name=parts[0] if parts else "",
            last_name=parts[1] if len(parts) > 1 else "",
            company=lead.fund or "",
            role=lead.role or "",
            linkedin=lead.linkedin or "",
            custom_vars=data.custom_vars or {},
        ))

    if not outreach_leads:
        raise HTTPException(status_code=400, detail="No leads with valid emails match the criteria")

    # Launch
    try:
        manager = OutreachManager(provider_name=data.provider, api_key=data.api_key)
        result = await manager.launch_campaign(
            name=data.name,
            vertical=data.vertical,
            leads=outreach_leads,
            from_email=data.from_email,
            from_name=data.from_name,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Outreach provider error: {str(e)}")


@router.post("/start")
async def start_outreach(
    data: OutreachCampaignAction,
    user_id: str = Depends(get_current_user_id),
):
    """Start/activate an outreach campaign."""
    from outreach.manager import OutreachManager
    try:
        manager = OutreachManager(provider_name=data.provider, api_key=data.api_key)
        await manager.start(data.provider_campaign_id)
        return {"status": "started", "campaign_id": data.provider_campaign_id}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/pause")
async def pause_outreach(
    data: OutreachCampaignAction,
    user_id: str = Depends(get_current_user_id),
):
    """Pause an outreach campaign."""
    from outreach.manager import OutreachManager
    try:
        manager = OutreachManager(provider_name=data.provider, api_key=data.api_key)
        await manager.pause(data.provider_campaign_id)
        return {"status": "paused", "campaign_id": data.provider_campaign_id}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/stats/{provider}/{provider_campaign_id}")
async def get_outreach_stats(
    provider: str,
    provider_campaign_id: str,
    api_key: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Get outreach campaign analytics."""
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{provider}'. Must be one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}",
        )
    from outreach.manager import OutreachManager
    try:
        manager = OutreachManager(provider_name=provider, api_key=api_key)
        stats = await manager.stats(provider_campaign_id)
        return {
            "campaign_id": provider_campaign_id,
            "provider": provider,
            "total_leads": stats.total_leads,
            "emails_sent": stats.emails_sent,
            "opens": stats.opens,
            "open_rate": stats.open_rate,
            "replies": stats.replies,
            "reply_rate": stats.reply_rate,
            "bounces": stats.bounces,
            "clicks": stats.clicks,
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/templates")
async def list_templates(user_id: str = Depends(get_current_user_id)):
    """List available outreach sequence templates."""
    from outreach.templates import TEMPLATES, get_template
    result = []
    for slug in TEMPLATES:
        seq = get_template(slug)
        result.append({
            "vertical": slug,
            "name": seq.name,
            "steps": len(seq.steps),
            "subjects": [s.subject for s in seq.steps],
        })
    return result
