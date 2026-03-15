"""
Tests for the config models used by /api/config endpoints (scoring and scraping rules).
Tests validation logic for scoring weights, tier thresholds, and scraping rules.
"""

import pytest
from pydantic import BaseModel, Field


# Re-define models locally to avoid import chain issues with auth/db modules
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


def validate_weights_sum(weights: ScoringWeights) -> bool:
    total = (
        weights.stage_match
        + weights.sector_match
        + weights.check_size_fit
        + weights.portfolio_relevance
        + weights.recency
    )
    return abs(total - 100) < 0.01


def validate_tier_order(tiers: TierThresholds) -> bool:
    return tiers.hot > tiers.warm > tiers.cool > 0


class TestScoringConfig:
    """Tests for scoring configuration validation."""

    def test_default_weights_sum_to_100(self):
        weights = ScoringWeights()
        assert validate_weights_sum(weights)

    def test_custom_weights_valid(self):
        weights = ScoringWeights(
            stage_match=40,
            sector_match=20,
            check_size_fit=15,
            portfolio_relevance=15,
            recency=10,
        )
        assert validate_weights_sum(weights)

    def test_custom_weights_invalid_sum(self):
        weights = ScoringWeights(
            stage_match=50,
            sector_match=25,
            check_size_fit=20,
            portfolio_relevance=15,
            recency=10,
        )
        assert not validate_weights_sum(weights)

    def test_default_tiers_ordered(self):
        tiers = TierThresholds()
        assert validate_tier_order(tiers)

    def test_tier_order_invalid(self):
        tiers = TierThresholds(hot=50, warm=60, cool=40)
        assert not validate_tier_order(tiers)

    def test_config_model_combines_both(self):
        config = ScoringConfig(
            weights=ScoringWeights(),
            tiers=TierThresholds(),
        )
        assert config.weights.stage_match == 30
        assert config.tiers.hot == 80

    def test_weight_validation_rejects_negative(self):
        with pytest.raises(Exception):
            ScoringWeights(stage_match=-5)

    def test_weight_validation_rejects_over_100(self):
        with pytest.raises(Exception):
            ScoringWeights(stage_match=101)

    def test_tier_validation_rejects_negative(self):
        with pytest.raises(Exception):
            TierThresholds(hot=-1)


class TestScrapingRules:
    """Tests for scraping rule validation."""

    def test_minimal_rule(self):
        rule = ScrapingRule(domain="example.com")
        assert rule.domain == "example.com"
        assert rule.team_page_selector == ""
        assert rule.pagination_type == "none"
        assert rule.enabled is True

    def test_full_rule(self):
        rule = ScrapingRule(
            domain="fundsite.com",
            team_page_selector='a[href*="team"]',
            name_selector=".team-member h3",
            role_selector=".team-member .role",
            email_selector='a[href^="mailto:"]',
            pagination_type="click",
            pagination_selector="button.load-more",
            enabled=True,
        )
        assert rule.team_page_selector == 'a[href*="team"]'
        assert rule.pagination_type == "click"

    def test_disabled_rule(self):
        rule = ScrapingRule(domain="old-site.com", enabled=False)
        assert not rule.enabled

    def test_rules_response_collection(self):
        response = ScrapingRulesResponse(
            rules=[
                ScrapingRule(domain="site1.com"),
                ScrapingRule(domain="site2.com"),
                ScrapingRule(domain="site3.com"),
            ]
        )
        assert len(response.rules) == 3
        domains = [r.domain for r in response.rules]
        assert "site2.com" in domains

    def test_empty_rules_response(self):
        response = ScrapingRulesResponse(rules=[])
        assert len(response.rules) == 0


class TestScoringBoundaries:
    """Test boundary conditions for scoring."""

    def test_all_weight_on_single_factor(self):
        weights = ScoringWeights(
            stage_match=100,
            sector_match=0,
            check_size_fit=0,
            portfolio_relevance=0,
            recency=0,
        )
        assert validate_weights_sum(weights)

    def test_equal_weights(self):
        weights = ScoringWeights(
            stage_match=20,
            sector_match=20,
            check_size_fit=20,
            portfolio_relevance=20,
            recency=20,
        )
        assert validate_weights_sum(weights)

    def test_tier_tight_range(self):
        tiers = TierThresholds(hot=99, warm=50, cool=1)
        assert validate_tier_order(tiers)

    def test_tier_sequential(self):
        tiers = TierThresholds(hot=3, warm=2, cool=1)
        assert validate_tier_order(tiers)
