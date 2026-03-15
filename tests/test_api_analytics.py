"""
Tests for the API analytics router endpoints.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAnalyticsEndpoints:
    """Test analytics API endpoints."""

    def test_pipeline_analytics(self, client):
        response = client.get("/api/analytics/pipeline")
        assert response.status_code == 200
        data = response.json()
        assert "total_runs" in data
        assert "global_counters" in data

    def test_current_run_idle(self, client):
        response = client.get("/api/analytics/pipeline/current")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "idle" or "run_id" in data

    def test_run_history(self, client):
        response = client.get("/api/analytics/pipeline/history?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_email_pattern_stats(self, client):
        response = client.get("/api/analytics/email-patterns")
        assert response.status_code == 200
        data = response.json()
        assert "total_domains" in data

    def test_ml_scorer_stats(self, client):
        response = client.get("/api/analytics/ml-scorer")
        assert response.status_code == 200
        data = response.json()
        assert "model_loaded" in data

    def test_email_validation_stats(self, client):
        response = client.get("/api/analytics/email-validation")
        assert response.status_code == 200
        data = response.json()
        assert "cache_stats" in data

    def test_health_endpoint(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
