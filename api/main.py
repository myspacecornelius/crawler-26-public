"""
LeadFactory API — FastAPI application entry point.

Run with: uvicorn api.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .database import init_db
from .settings import settings
from .routers import users, campaigns, leads, verticals, outreach, billing, crm, portfolio
from .routers import metrics, notifications

logger = logging.getLogger("leadfactory.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    logger.info("Starting LeadFactory API...")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down LeadFactory API")


app = FastAPI(
    title="LeadFactory",
    description="Multi-vertical lead generation platform — VC, PE, Family Offices, Corp Dev",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# ── Rate limiting ──────────────────────────────
app.state.limiter = users.limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS — configurable via CORS_ORIGINS env var ─
# To add origins for staging or production, set the CORS_ORIGINS
# environment variable to a comma-separated list of allowed origins.
# Example: CORS_ORIGINS=https://app.leadfactory.io,https://staging.leadfactory.io
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routers
app.include_router(users.router, prefix="/api")
app.include_router(campaigns.router, prefix="/api")
app.include_router(leads.router, prefix="/api")
app.include_router(verticals.router, prefix="/api")
app.include_router(outreach.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(crm.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "leadfactory"}
