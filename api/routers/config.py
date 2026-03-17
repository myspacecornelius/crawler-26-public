"""
Configuration management endpoints — scoring weights, scraping rules.
"""

import os
import tempfile
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..auth import get_current_user_id

router = APIRouter(prefix="/config", tags=["config"])

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"


# ── Schemas ────────────────────────────────────

class ScoringWeights(BaseModel):
    stage_match: float = Field(ge=0, le=100, default=30)
    sector_match: float = Field(ge=0, le=100, default=25)
    check_size_fit: float = Field(ge=0, le=100, default=20)
    portfolio_relevance: float = Field(ge=0, le=100, default=15)
    recency: float = Field(ge=0, le=100, default=10)


class TierThresholds(BaseModel):
    hot: int = Field(ge=0, le=100, default=80)
    warm: int = Field(ge=0, le=100, default=60)
    cool: int = Field(ge=0, le=100, default=40)


class ScoringConfig(BaseModel):
    weights: ScoringWeights
    tiers: TierThresholds


class ScrapingRule(BaseModel):
    domain: str
    team_page_selector: str = ""
    name_selector: str = ""
    role_selector: str = ""
    email_selector: str = ""
    pagination_type: str = "none"
    pagination_selector: str = ""
    enabled: bool = True


class ScrapingRulesResponse(BaseModel):
    rules: list[ScrapingRule]


# ── Helpers ────────────────────────────

def _atomic_yaml_write(path: Path, data: dict) -> None:
    """Write YAML to a temp file then rename so readers never see a partial write."""
    dir_ = path.parent
    with tempfile.NamedTemporaryFile("w", dir=dir_, delete=False, suffix=".tmp") as tmp:
        yaml.dump(data, tmp, default_flow_style=False, sort_keys=False)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


# ── Scoring endpoints ──────────────────────────

@router.get("/scoring", response_model=ScoringConfig)
async def get_scoring_config(
    _user_id: str = Depends(get_current_user_id),
):
    """Get current scoring configuration."""
    scoring_path = CONFIG_DIR / "scoring.yaml"
    if not scoring_path.exists():
        return ScoringConfig(
            weights=ScoringWeights(),
            tiers=TierThresholds(),
        )

    with open(scoring_path) as f:
        data = yaml.safe_load(f) or {}

    weights_data = data.get("weights", {})
    tiers_data = data.get("tiers", {})

    return ScoringConfig(
        weights=ScoringWeights(
            stage_match=weights_data.get("stage_match", 30),
            sector_match=weights_data.get("sector_match", 25),
            check_size_fit=weights_data.get("check_size_fit", 20),
            portfolio_relevance=weights_data.get("portfolio_relevance", 15),
            recency=weights_data.get("recency", 10),
        ),
        tiers=TierThresholds(
            hot=tiers_data.get("HOT", tiers_data.get("hot", 80)),
            warm=tiers_data.get("WARM", tiers_data.get("warm", 60)),
            cool=tiers_data.get("COOL", tiers_data.get("cool", 40)),
        ),
    )


@router.put("/scoring", response_model=ScoringConfig)
async def update_scoring_config(
    body: ScoringConfig,
    _user_id: str = Depends(get_current_user_id),
):
    """Update scoring configuration."""
    # Validate weights sum to 100
    total = (
        body.weights.stage_match
        + body.weights.sector_match
        + body.weights.check_size_fit
        + body.weights.portfolio_relevance
        + body.weights.recency
    )
    if abs(total - 100) > 0.01:
        raise HTTPException(
            status_code=400,
            detail=f"Scoring weights must sum to 100 (currently {total})",
        )

    # Validate tier thresholds are ordered
    if not (body.tiers.hot > body.tiers.warm > body.tiers.cool > 0):
        raise HTTPException(
            status_code=400,
            detail="Tier thresholds must be ordered: HOT > WARM > COOL > 0",
        )

    scoring_path = CONFIG_DIR / "scoring.yaml"
    existing = {}
    if scoring_path.exists():
        with open(scoring_path) as f:
            existing = yaml.safe_load(f) or {}

    existing["weights"] = {
        "stage_match": body.weights.stage_match,
        "sector_match": body.weights.sector_match,
        "check_size_fit": body.weights.check_size_fit,
        "portfolio_relevance": body.weights.portfolio_relevance,
        "recency": body.weights.recency,
    }
    existing["tiers"] = {
        "HOT": body.tiers.hot,
        "WARM": body.tiers.warm,
        "COOL": body.tiers.cool,
        "COLD": 0,
    }

    _atomic_yaml_write(scoring_path, existing)

    return body


# ── Scraping rules endpoints ──────────────────

@router.get("/scraping-rules", response_model=ScrapingRulesResponse)
async def get_scraping_rules(
    _user_id: str = Depends(get_current_user_id),
):
    """Get current scraping rules from sites.yaml."""
    sites_path = CONFIG_DIR / "sites.yaml"
    if not sites_path.exists():
        return ScrapingRulesResponse(rules=[])

    with open(sites_path) as f:
        data = yaml.safe_load(f) or {}

    rules: list[ScrapingRule] = []
    sites = data.get("sites", data)
    if isinstance(sites, dict):
        for domain, config in sites.items():
            if isinstance(config, dict):
                rules.append(
                    ScrapingRule(
                        domain=domain,
                        team_page_selector=config.get("team_page_selector", ""),
                        name_selector=config.get("name_selector", ""),
                        role_selector=config.get("role_selector", ""),
                        email_selector=config.get("email_selector", ""),
                        pagination_type=config.get("pagination", {}).get("type", "none")
                            if isinstance(config.get("pagination"), dict)
                            else "none",
                        pagination_selector=config.get("pagination", {}).get("selector", "")
                            if isinstance(config.get("pagination"), dict)
                            else "",
                        enabled=config.get("enabled", True),
                    )
                )

    return ScrapingRulesResponse(rules=rules)


@router.post("/scraping-rules", response_model=ScrapingRule, status_code=201)
async def add_scraping_rule(
    body: ScrapingRule,
    _user_id: str = Depends(get_current_user_id),
):
    """Add a new scraping rule."""
    sites_path = CONFIG_DIR / "sites.yaml"
    existing = {}
    if sites_path.exists():
        with open(sites_path) as f:
            existing = yaml.safe_load(f) or {}

    if "sites" not in existing:
        existing = {"sites": existing}

    rule_config: dict = {
        "enabled": body.enabled,
    }
    if body.team_page_selector:
        rule_config["team_page_selector"] = body.team_page_selector
    if body.name_selector:
        rule_config["name_selector"] = body.name_selector
    if body.role_selector:
        rule_config["role_selector"] = body.role_selector
    if body.email_selector:
        rule_config["email_selector"] = body.email_selector
    if body.pagination_type != "none":
        rule_config["pagination"] = {
            "type": body.pagination_type,
            "selector": body.pagination_selector,
        }

    existing["sites"][body.domain] = rule_config

    _atomic_yaml_write(sites_path, existing)

    return body
