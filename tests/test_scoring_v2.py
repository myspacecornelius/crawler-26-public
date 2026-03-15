"""
Tests for LeadScorer and MLLeadScorer.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from enrichment.scoring import LeadScorer
from enrichment.ml_scorer import MLLeadScorer, extract_features, STAGE_ENCODING, ROLE_ENCODING


class TestLeadScorerInit:
    """Test LeadScorer initialization and configuration."""

    def test_default_config(self):
        scorer = LeadScorer(config_path="nonexistent.yaml")
        assert scorer.weights["stage_match"] == 30
        assert scorer.weights["sector_match"] == 25

    def test_loaded_config(self):
        scorer = LeadScorer(config_path="config/scoring.yaml")
        assert "stage_match" in scorer.weights
        assert "hot" in scorer.tiers


class TestLeadScorerScoring:
    """Test scoring logic."""

    def test_score_returns_tuple(self, sample_lead):
        scorer = LeadScorer()
        score, tier = scorer.score(sample_lead)
        assert isinstance(score, int)
        assert isinstance(tier, str)
        assert 0 <= score <= 100

    def test_score_clamped_to_0_100(self, sample_lead):
        scorer = LeadScorer()
        sample_lead.stage = "N/A"
        sample_lead.email = "N/A"
        sample_lead.linkedin = "N/A"
        sample_lead.focus_areas = []
        score, tier = scorer.score(sample_lead)
        assert 0 <= score <= 100

    def test_high_quality_lead_scores_high(self, sample_lead):
        scorer = LeadScorer()
        sample_lead.stage = "seed"
        sample_lead.focus_areas = ["AI", "SaaS"]
        sample_lead.email = "john@test.com"
        sample_lead.linkedin = "https://linkedin.com/in/john"
        sample_lead.role = "Managing Partner"
        sample_lead.email_status = "verified"
        score, tier = scorer.score(sample_lead)
        assert score >= 50  # Should score well

    def test_low_quality_lead_scores_low(self, sample_lead):
        scorer = LeadScorer()
        sample_lead.stage = "growth"  # Wrong stage for pre-seed startup
        sample_lead.focus_areas = ["Real Estate"]  # No overlap
        sample_lead.email = "N/A"
        sample_lead.linkedin = "N/A"
        sample_lead.role = "Intern"
        score, tier = scorer.score(sample_lead)
        assert score < 50

    def test_batch_scoring(self, sample_leads):
        scorer = LeadScorer()
        scored = scorer.score_batch(sample_leads)
        assert len(scored) == len(sample_leads)
        # Should be sorted by score descending
        scores = [lead.lead_score for lead in scored]
        assert scores == sorted(scores, reverse=True)


class TestLeadScorerTiers:
    """Test tier assignment."""

    def test_hot_tier(self, sample_lead):
        scorer = LeadScorer()
        tier = scorer._get_tier(85)
        assert "HOT" in tier

    def test_warm_tier(self, sample_lead):
        scorer = LeadScorer()
        tier = scorer._get_tier(65)
        assert "WARM" in tier

    def test_cool_tier(self, sample_lead):
        scorer = LeadScorer()
        tier = scorer._get_tier(45)
        assert "COOL" in tier

    def test_cold_tier(self, sample_lead):
        scorer = LeadScorer()
        tier = scorer._get_tier(20)
        assert "COLD" in tier


class TestLeadScorerRoles:
    """Test role-based scoring."""

    def test_partner_gets_bonus(self, sample_lead):
        scorer = LeadScorer()
        sample_lead.role = "Managing Partner"
        score1 = scorer._score_role("Managing Partner")
        score2 = scorer._score_role("Intern")
        assert score1 > score2

    def test_unknown_role_zero(self, sample_lead):
        scorer = LeadScorer()
        score = scorer._score_role("Chief Cheerleader")
        assert score == 0


class TestLeadScorerStages:
    """Test stage matching."""

    def test_exact_match(self):
        scorer = LeadScorer()
        score = scorer._score_stage("seed")
        # Should get partial or full credit depending on startup_profile
        assert score >= 0

    def test_na_stage(self):
        scorer = LeadScorer()
        score = scorer._score_stage("N/A")
        assert score > 0  # Unknown gets partial credit


class TestLeadScorerStats:
    """Test scorer statistics."""

    def test_stats_empty(self):
        scorer = LeadScorer()
        stats = scorer.stats
        assert stats["total_scored"] == 0

    def test_stats_after_scoring(self, sample_leads):
        scorer = LeadScorer()
        scorer.score_batch(sample_leads)
        stats = scorer.stats
        assert stats["total_scored"] == len(sample_leads)
        assert "avg_score" in stats


class TestMLFeatureExtraction:
    """Test ML feature extraction."""

    def test_extract_features(self, sample_lead):
        features = extract_features(sample_lead)
        assert "stage_encoded" in features
        assert "has_email" in features
        assert "has_linkedin" in features
        assert "sector_count" in features
        assert "role_encoded" in features

    def test_stage_encoding(self, sample_lead):
        sample_lead.stage = "seed"
        features = extract_features(sample_lead)
        assert features["stage_encoded"] == 1

    def test_email_features(self, sample_lead):
        sample_lead.email = "test@example.com"
        sample_lead.email_status = "verified"
        features = extract_features(sample_lead)
        assert features["has_email"] == 1.0
        assert features["email_verified"] == 1.0

    def test_no_email_features(self, sample_lead):
        sample_lead.email = "N/A"
        features = extract_features(sample_lead)
        assert features["has_email"] == 0.0

    def test_sector_features(self, sample_lead):
        sample_lead.focus_areas = ["AI", "SaaS"]
        features = extract_features(sample_lead)
        assert features["sector_ai"] == 1.0
        assert features["sector_saas"] == 1.0
        assert features["sector_count"] == 2

    def test_role_encoding(self, sample_lead):
        sample_lead.role = "Managing Partner"
        features = extract_features(sample_lead)
        assert features["role_encoded"] == 4.0  # Partner = 4


class TestMLLeadScorer:
    """Test MLLeadScorer."""

    def test_no_model_returns_fallback(self, sample_lead):
        scorer = MLLeadScorer()
        score, confidence = scorer.predict(sample_lead)
        assert score == -1
        assert confidence == 0.0

    def test_model_not_available_without_load(self):
        scorer = MLLeadScorer()
        assert scorer.model_available is False

    def test_load_nonexistent_model(self):
        scorer = MLLeadScorer(model_path="/nonexistent/model.joblib")
        assert scorer.load_model() is False

    def test_stats(self):
        scorer = MLLeadScorer()
        stats = scorer.stats
        assert stats["model_loaded"] is False
        assert stats["predictions_made"] == 0
        assert stats["fallbacks_to_rules"] == 0

    def test_predict_batch(self, sample_leads):
        scorer = MLLeadScorer()
        results = scorer.predict_batch(sample_leads)
        assert len(results) == len(sample_leads)
        for score, confidence in results:
            assert score == -1  # No model loaded
