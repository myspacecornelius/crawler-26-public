"""
Pydantic schemas for API request/response validation.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ── Auth ─────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    company: str = Field(default="", max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: UUID
    email: str
    name: str
    company: str
    plan: str
    credits_remaining: int
    credits_monthly: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ── Campaigns ────────────────────────────────────

class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    vertical: str = Field(
        min_length=1, max_length=50,
        pattern=r"^[a-z][a-z0-9_]*$",
        description="Vertical slug: vc, pe, family_office, corp_dev",
    )
    config: Dict[str, Any] = Field(default_factory=dict, description="Optional config overrides")


class CampaignResponse(BaseModel):
    id: UUID
    name: str
    vertical: str
    status: str
    config: Dict[str, Any]
    total_leads: int
    total_emails: int
    credits_used: int
    error_message: Optional[str]
    task_id: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CampaignList(BaseModel):
    campaigns: List[CampaignResponse]
    total: int


# ── Leads ────────────────────────────────────────

class LeadResponse(BaseModel):
    id: UUID
    name: str
    email: str
    email_verified: bool
    email_source: str
    email_status: str = "unknown"
    linkedin: str
    phone: str
    fund: str
    role: str
    website: str
    sectors: str
    check_size: str
    stage: str
    hq: str
    score: float
    tier: str
    source: str
    opted_out: bool = False
    scraped_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def model_validate(cls, obj, **kwargs):
        """Override to compute email_status when the column value is 'unknown'.

        If email_status is already set to a meaningful value on the ORM object,
        use it directly. Otherwise, derive from email_verified + email_source
        for backward compatibility with pre-migration data.
        """
        instance = super().model_validate(obj, **kwargs)
        # Only compute if the column has the default 'unknown' value
        if instance.email_status == "unknown":
            if instance.email in ("N/A", "", None):
                instance.email_status = "unknown"
            elif instance.email_verified and instance.email_source == "scraped":
                instance.email_status = "scraped"
            elif instance.email_verified:
                instance.email_status = "verified"
            elif instance.email_source == "scraped":
                instance.email_status = "scraped"
            elif instance.email_source == "guessed":
                instance.email_status = "guessed"
            elif instance.email_source == "pattern":
                instance.email_status = "guessed"
        return instance


class LeadList(BaseModel):
    leads: List[LeadResponse]
    total: int
    page: int
    per_page: int


class LeadFilters(BaseModel):
    tier: Optional[str] = None
    min_score: Optional[float] = None
    has_email: Optional[bool] = None
    email_verified: Optional[bool] = None
    fund: Optional[str] = None
    sector: Optional[str] = None
    stage: Optional[str] = None
    check_size: Optional[str] = None
    hq: Optional[str] = None
    search: Optional[str] = None


# ── Credits ──────────────────────────────────────

class CreditBalance(BaseModel):
    credits_remaining: int
    credits_monthly: int
    plan: str


class CreditTransaction(BaseModel):
    id: UUID
    amount: int
    reason: str
    balance_after: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── API Keys ────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str = Field(default="Default", min_length=1, max_length=100)


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    key: str  # Only returned on creation
    created_at: datetime


class ApiKeyListItem(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    last_used: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ── Verticals ───────────────────────────────────

class VerticalInfo(BaseModel):
    slug: str
    name: str
    description: str
    seed_count: int
    search_queries: List[str]


# ── Stats ───────────────────────────────────────

# ── Billing ─────────────────────────────────────

class CheckoutRequest(BaseModel):
    plan: Optional[str] = Field(None, description="Plan slug: pro, scale")
    credit_pack: Optional[str] = Field(None, description="Credit pack slug: 1k, 5k, 10k")


class CheckoutResponse(BaseModel):
    checkout_url: str


class BillingHistoryItem(BaseModel):
    id: UUID
    amount: int
    reason: str
    balance_after: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BillingHistory(BaseModel):
    transactions: List[BillingHistoryItem]
    total: int


class PortalResponse(BaseModel):
    portal_url: str


# ── Opt-out ─────────────────────────────────────

class OptOutResponse(BaseModel):
    email: str
    opted_out: bool
    message: str


# ── Portfolio ───────────────────────────────────

class PortfolioCompanyResponse(BaseModel):
    id: UUID
    fund_name: str
    company_name: str
    sector: str
    stage: str
    url: str
    year: Optional[int]
    scraped_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PortfolioCompanyList(BaseModel):
    companies: List[PortfolioCompanyResponse]
    total: int
    fund_name: str


class DashboardStats(BaseModel):
    total_campaigns: int
    total_leads: int
    total_emails: int
    email_rate: float
    credits_remaining: int
    hot_leads: int
    warm_leads: int
    recent_campaigns: List[CampaignResponse]


# ── CRM Integration ───────────────────────────────

class CRMPushRequest(BaseModel):
    provider: str = Field(description="CRM provider: hubspot | salesforce")
    campaign_id: str = Field(description="LeadFactory campaign ID")
    test_mode: bool = False
    min_score: float = 0
    tiers: Optional[List[str]] = None
    field_mapping: Optional[Dict[str, str]] = None
    custom_fields: Optional[Dict[str, str]] = None

class CRMPushResultItem(BaseModel):
    email: str
    success: bool
    crm_id: Optional[str] = None
    error: Optional[str] = None
    created: bool = True

class CRMPushResponse(BaseModel):
    provider: str
    total: int
    created: int
    updated: int
    failed: int
    status: str
    results: List[CRMPushResultItem]
    errors: List[str]

class CRMFieldResponse(BaseModel):
    name: str
    label: str
    field_type: str
    required: bool
    options: List[str]

class CRMFieldMappingResponse(BaseModel):
    lead_field: str
    crm_field: str
