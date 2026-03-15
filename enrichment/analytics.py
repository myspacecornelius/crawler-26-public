"""
CRAWL — Pipeline Analytics
Collects and exposes pipeline metrics: leads per run, success/failure rates,
email bounce rates, time per stage, and proxy health.

Provides data for the /api/analytics endpoint and can be extended
with Prometheus exporters.
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class StageMetrics:
    """Metrics for a single pipeline stage."""

    name: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    items_processed: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.items_processed == 0:
            return 0.0
        return self.items_succeeded / self.items_processed

    def to_dict(self) -> dict:
        d = asdict(self)
        d["success_rate"] = round(self.success_rate, 4)
        return d


@dataclass
class RunMetrics:
    """Metrics for a complete pipeline run."""

    run_id: str
    started_at: str = ""
    completed_at: str = ""
    total_duration_seconds: float = 0.0
    total_leads_discovered: int = 0
    total_leads_enriched: int = 0
    total_emails_generated: int = 0
    total_emails_verified: int = 0
    email_bounce_rate: float = 0.0
    stages: Dict[str, StageMetrics] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stages"] = {k: v.to_dict() if isinstance(v, StageMetrics) else v for k, v in self.stages.items()}
        return d


class PipelineAnalytics:
    """
    Central analytics collector for the LeadFactory pipeline.

    Usage:
        analytics = PipelineAnalytics()
        analytics.start_run("run-001")
        analytics.start_stage("discovery")
        analytics.record_success("discovery")
        analytics.end_stage("discovery")
        analytics.end_run()
        print(analytics.get_summary())
    """

    def __init__(self):
        self._runs: List[RunMetrics] = []
        self._current_run: Optional[RunMetrics] = None
        self._stage_timers: Dict[str, float] = {}
        self._global_counters: Dict[str, int] = defaultdict(int)

    def start_run(self, run_id: str):
        """Begin tracking a new pipeline run."""
        self._current_run = RunMetrics(
            run_id=run_id,
            started_at=datetime.now().isoformat(),
        )
        self._stage_timers.clear()
        logger.info("Analytics: started run %s", run_id)

    def end_run(self):
        """Finalize the current run and store metrics."""
        if self._current_run is None:
            return
        self._current_run.completed_at = datetime.now().isoformat()
        try:
            start = datetime.fromisoformat(self._current_run.started_at)
            end = datetime.fromisoformat(self._current_run.completed_at)
            self._current_run.total_duration_seconds = (end - start).total_seconds()
        except (ValueError, TypeError):
            pass
        self._runs.append(self._current_run)
        logger.info(
            "Analytics: run %s completed in %.1fs — %d leads, %d emails",
            self._current_run.run_id,
            self._current_run.total_duration_seconds,
            self._current_run.total_leads_discovered,
            self._current_run.total_emails_generated,
        )
        self._current_run = None

    def start_stage(self, stage_name: str):
        """Begin timing a pipeline stage."""
        if self._current_run is None:
            return
        self._stage_timers[stage_name] = time.monotonic()
        metrics = StageMetrics(name=stage_name, started_at=datetime.now().isoformat())
        self._current_run.stages[stage_name] = metrics

    def end_stage(self, stage_name: str):
        """Finalize timing for a pipeline stage."""
        if self._current_run is None or stage_name not in self._current_run.stages:
            return
        stage = self._current_run.stages[stage_name]
        stage.completed_at = datetime.now().isoformat()
        if stage_name in self._stage_timers:
            stage.duration_seconds = time.monotonic() - self._stage_timers[stage_name]

    def record_success(self, stage_name: str, count: int = 1):
        """Record successful items in a stage."""
        if self._current_run and stage_name in self._current_run.stages:
            stage = self._current_run.stages[stage_name]
            stage.items_processed += count
            stage.items_succeeded += count
        self._global_counters[f"{stage_name}_success"] += count

    def record_failure(self, stage_name: str, error: str = "", count: int = 1):
        """Record failed items in a stage."""
        if self._current_run and stage_name in self._current_run.stages:
            stage = self._current_run.stages[stage_name]
            stage.items_processed += count
            stage.items_failed += count
            if error:
                stage.errors.append(error)
        self._global_counters[f"{stage_name}_failure"] += count

    def record_leads_discovered(self, count: int):
        if self._current_run:
            self._current_run.total_leads_discovered += count
        self._global_counters["total_leads_discovered"] += count

    def record_emails_generated(self, count: int):
        if self._current_run:
            self._current_run.total_emails_generated += count
        self._global_counters["total_emails_generated"] += count

    def record_emails_verified(self, count: int):
        if self._current_run:
            self._current_run.total_emails_verified += count
        self._global_counters["total_emails_verified"] += count

    def record_bounce_rate(self, rate: float):
        if self._current_run:
            self._current_run.email_bounce_rate = rate

    def get_current_run(self) -> Optional[dict]:
        """Get metrics for the current (in-progress) run."""
        if self._current_run is None:
            return None
        return self._current_run.to_dict()

    def get_run_history(self, limit: int = 20) -> List[dict]:
        """Get metrics for the most recent completed runs."""
        return [r.to_dict() for r in self._runs[-limit:]]

    def get_summary(self) -> dict:
        """
        Get aggregate analytics summary.
        Returns metrics suitable for the API/dashboard.
        """
        total_runs = len(self._runs)
        if total_runs == 0:
            return {
                "total_runs": 0,
                "global_counters": dict(self._global_counters),
                "current_run": self.get_current_run(),
            }

        total_leads = sum(r.total_leads_discovered for r in self._runs)
        total_emails = sum(r.total_emails_generated for r in self._runs)
        total_verified = sum(r.total_emails_verified for r in self._runs)
        avg_duration = sum(r.total_duration_seconds for r in self._runs) / total_runs
        avg_bounce = sum(r.email_bounce_rate for r in self._runs) / total_runs

        # Stage-level aggregates
        stage_totals: Dict[str, Dict[str, float]] = defaultdict(lambda: {"duration": 0, "success": 0, "failure": 0, "count": 0})
        for run in self._runs:
            for name, stage in run.stages.items():
                s = stage if isinstance(stage, StageMetrics) else StageMetrics(**stage)
                stage_totals[name]["duration"] += s.duration_seconds
                stage_totals[name]["success"] += s.items_succeeded
                stage_totals[name]["failure"] += s.items_failed
                stage_totals[name]["count"] += 1

        stage_averages = {}
        for name, totals in stage_totals.items():
            count = totals["count"] or 1
            stage_averages[name] = {
                "avg_duration_seconds": round(totals["duration"] / count, 2),
                "total_succeeded": int(totals["success"]),
                "total_failed": int(totals["failure"]),
                "avg_success_rate": round(totals["success"] / (totals["success"] + totals["failure"]), 4) if (totals["success"] + totals["failure"]) > 0 else 0,
            }

        return {
            "total_runs": total_runs,
            "total_leads_discovered": total_leads,
            "total_emails_generated": total_emails,
            "total_emails_verified": total_verified,
            "avg_run_duration_seconds": round(avg_duration, 2),
            "avg_bounce_rate": round(avg_bounce, 4),
            "stage_averages": stage_averages,
            "global_counters": dict(self._global_counters),
            "current_run": self.get_current_run(),
            "recent_runs": self.get_run_history(5),
        }


# Global analytics instance
pipeline_analytics = PipelineAnalytics()
