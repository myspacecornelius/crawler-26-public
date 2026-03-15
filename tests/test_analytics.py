"""
Tests for PipelineAnalytics.
"""

import pytest
from enrichment.analytics import PipelineAnalytics, StageMetrics, RunMetrics


class TestStageMetrics:
    """Test StageMetrics data class."""

    def test_success_rate_zero(self):
        stage = StageMetrics(name="test")
        assert stage.success_rate == 0.0

    def test_success_rate_calculation(self):
        stage = StageMetrics(name="test", items_processed=10, items_succeeded=8, items_failed=2)
        assert stage.success_rate == 0.8

    def test_to_dict(self):
        stage = StageMetrics(name="discovery", items_processed=5, items_succeeded=5)
        d = stage.to_dict()
        assert d["name"] == "discovery"
        assert d["success_rate"] == 1.0


class TestPipelineAnalytics:
    """Test PipelineAnalytics."""

    def test_start_and_end_run(self):
        analytics = PipelineAnalytics()
        analytics.start_run("run-001")
        assert analytics.get_current_run() is not None
        analytics.end_run()
        assert analytics.get_current_run() is None
        history = analytics.get_run_history()
        assert len(history) == 1
        assert history[0]["run_id"] == "run-001"

    def test_stage_tracking(self):
        analytics = PipelineAnalytics()
        analytics.start_run("run-002")
        analytics.start_stage("discovery")
        analytics.record_success("discovery", count=10)
        analytics.record_failure("discovery", error="timeout", count=2)
        analytics.end_stage("discovery")
        analytics.end_run()

        history = analytics.get_run_history()
        assert len(history) == 1
        stages = history[0]["stages"]
        assert "discovery" in stages
        assert stages["discovery"]["items_succeeded"] == 10
        assert stages["discovery"]["items_failed"] == 2

    def test_lead_and_email_counters(self):
        analytics = PipelineAnalytics()
        analytics.start_run("run-003")
        analytics.record_leads_discovered(100)
        analytics.record_emails_generated(75)
        analytics.record_emails_verified(60)
        analytics.record_bounce_rate(0.05)
        analytics.end_run()

        summary = analytics.get_summary()
        assert summary["total_leads_discovered"] == 100
        assert summary["total_emails_generated"] == 75
        assert summary["total_emails_verified"] == 60
        assert summary["avg_bounce_rate"] == 0.05

    def test_summary_with_no_runs(self):
        analytics = PipelineAnalytics()
        summary = analytics.get_summary()
        assert summary["total_runs"] == 0

    def test_run_history_limit(self):
        analytics = PipelineAnalytics()
        for i in range(5):
            analytics.start_run(f"run-{i}")
            analytics.end_run()
        history = analytics.get_run_history(limit=3)
        assert len(history) == 3

    def test_multiple_runs_aggregate(self):
        analytics = PipelineAnalytics()
        for i in range(3):
            analytics.start_run(f"run-{i}")
            analytics.record_leads_discovered(10)
            analytics.end_run()

        summary = analytics.get_summary()
        assert summary["total_runs"] == 3
        assert summary["total_leads_discovered"] == 30

    def test_stage_averages(self):
        analytics = PipelineAnalytics()
        for i in range(2):
            analytics.start_run(f"run-{i}")
            analytics.start_stage("enrichment")
            analytics.record_success("enrichment", count=50)
            analytics.end_stage("enrichment")
            analytics.end_run()

        summary = analytics.get_summary()
        assert "enrichment" in summary["stage_averages"]
        assert summary["stage_averages"]["enrichment"]["total_succeeded"] == 100

    def test_no_crash_on_end_without_start(self):
        analytics = PipelineAnalytics()
        analytics.end_run()  # Should not crash
        analytics.end_stage("nonexistent")
        analytics.record_success("nonexistent")

    def test_global_counters(self):
        analytics = PipelineAnalytics()
        analytics.start_run("run-x")
        analytics.start_stage("scoring")
        analytics.record_success("scoring", count=5)
        analytics.end_stage("scoring")
        analytics.end_run()

        summary = analytics.get_summary()
        assert summary["global_counters"]["scoring_success"] == 5
