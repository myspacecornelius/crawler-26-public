"""
LeadFactory API — Analytics & Metrics Router
Exposes pipeline analytics, email pattern statistics, and ML scoring metrics.
"""

from fastapi import APIRouter, Query

from enrichment.analytics import pipeline_analytics
from enrichment.email_guesser import EmailGuesser
from enrichment.ml_scorer import MLLeadScorer

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Shared instances (can be replaced with dependency injection)
_guesser = EmailGuesser()
_ml_scorer = MLLeadScorer()


@router.get("/pipeline")
async def get_pipeline_analytics():
    """Get aggregate pipeline analytics summary."""
    return pipeline_analytics.get_summary()


@router.get("/pipeline/current")
async def get_current_run():
    """Get metrics for the current in-progress pipeline run."""
    run = pipeline_analytics.get_current_run()
    if run is None:
        return {"status": "idle", "message": "No pipeline run in progress"}
    return run


@router.get("/pipeline/history")
async def get_run_history(limit: int = Query(default=20, ge=1, le=100)):
    """Get metrics for recent completed pipeline runs."""
    return pipeline_analytics.get_run_history(limit=limit)


@router.get("/email-patterns")
async def get_email_pattern_stats():
    """
    Get email pattern learning statistics.
    Shows pattern distribution, per-domain confidence, and global rankings.
    """
    return _guesser.pattern_statistics


@router.get("/ml-scorer")
async def get_ml_scorer_stats():
    """Get ML lead scorer statistics and model status."""
    return _ml_scorer.stats


@router.get("/email-validation")
async def get_email_validation_stats():
    """Get email validator cache statistics."""
    from enrichment.email_validator import EmailValidator
    validator = EmailValidator()
    return {
        "cache_stats": validator.cache_stats,
        "dns_error_domains": list(validator.dns_error_domains),
    }
