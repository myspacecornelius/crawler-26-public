"""
LeadFactory API — FastAPI application entry point.

Run with: uvicorn api.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routers import users, campaigns, leads, verticals, outreach, billing, crm, portfolio, analytics

logger = logging.getLogger("leadfactory.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB on startup."""
    logger.info("🚀 Starting LeadFactory API...")
    await init_db()
    logger.info("✅ Database initialized")
    yield
    logger.info("👋 Shutting down LeadFactory API")


app = FastAPI(
    title="LeadFactory",
    description="Multi-vertical lead generation platform — VC, PE, Family Offices, Corp Dev",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — allow dashboard origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
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
app.include_router(analytics.router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "leadfactory"}
