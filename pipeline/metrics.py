"""
Pipeline metrics collection and export.

Captures per-run and per-stage metrics (durations, counts, error rates)
and exposes them as:
  1. CSV append log  — lightweight, always-on
  2. Prometheus exposition — optional, for dashboards

Usage:
    from pipeline.metrics import PipelineMetrics

    metrics = PipelineMetrics()
    metrics.stage_start("discovery")
    ...
    metrics.stage_end("discovery", lead_count=420, error_count=2)
    metrics.flush()  # write CSV row + update Prometheus gauges
"""

import csv
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class PipelineMetrics:
    """Collects and exports pipeline performance metrics."""

    def __init__(
        self,
        csv_path: str = "data/metrics/pipeline_metrics.csv",
        run_id: Optional[str] = None,
    ):
        self.csv_path = Path(csv_path)
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._stage_starts: Dict[str, float] = {}
        self._stage_metrics: Dict[str, dict] = {}
        self._run_start: float = time.monotonic()
        self._counters: Dict[str, int] = defaultdict(int)

    # ── Stage lifecycle ──────────────────────────────────────────

    def stage_start(self, stage: str) -> None:
        """Mark the beginning of a pipeline stage."""
        self._stage_starts[stage] = time.monotonic()
        logger.info(
            f"Stage started: {stage}",
            extra={"phase": stage, "run_id": self.run_id},
        )

    def stage_end(
        self,
        stage: str,
        lead_count: int = 0,
        error_count: int = 0,
        extra: Optional[dict] = None,
    ) -> None:
        """Mark the end of a pipeline stage and record metrics."""
        start = self._stage_starts.pop(stage, None)
        duration = time.monotonic() - start if start else 0.0

        entry = {
            "stage": stage,
            "duration_s": round(duration, 2),
            "lead_count": lead_count,
            "error_count": error_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            entry.update(extra)

        self._stage_metrics[stage] = entry

        logger.info(
            f"Stage completed: {stage} in {duration:.1f}s "
            f"(leads={lead_count}, errors={error_count})",
            extra={
                "phase": stage,
                "run_id": self.run_id,
                "duration_s": round(duration, 2),
                "lead_count": lead_count,
                "error_count": error_count,
            },
        )

    # ── Counters ─────────────────────────────────────────────────

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment a named counter (e.g. 'emails_verified')."""
        self._counters[name] += amount

    def get_counter(self, name: str) -> int:
        return self._counters.get(name, 0)

    # ── Run summary ──────────────────────────────────────────────

    def run_summary(self) -> dict:
        """Return a summary of the entire pipeline run."""
        total_duration = time.monotonic() - self._run_start
        total_errors = sum(m.get("error_count", 0) for m in self._stage_metrics.values())
        total_leads = max(
            (m.get("lead_count", 0) for m in self._stage_metrics.values()),
            default=0,
        )
        return {
            "run_id": self.run_id,
            "total_duration_s": round(total_duration, 2),
            "total_stages": len(self._stage_metrics),
            "total_errors": total_errors,
            "total_leads": total_leads,
            "stages": dict(self._stage_metrics),
            "counters": dict(self._counters),
        }

    # ── CSV export ───────────────────────────────────────────────

    def flush(self) -> None:
        """Append per-stage rows to the CSV metrics log."""
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.csv_path.exists()

        fieldnames = [
            "run_id", "timestamp", "stage", "duration_s",
            "lead_count", "error_count",
        ]

        try:
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                if not file_exists:
                    writer.writeheader()
                for stage, entry in self._stage_metrics.items():
                    row = {"run_id": self.run_id, **entry}
                    writer.writerow(row)

            # Also write a summary row
            summary = self.run_summary()
            with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writerow({
                    "run_id": self.run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "stage": "_run_total",
                    "duration_s": summary["total_duration_s"],
                    "lead_count": summary["total_leads"],
                    "error_count": summary["total_errors"],
                })

            logger.info(f"Metrics flushed to {self.csv_path}")
        except Exception as e:
            logger.warning(f"Failed to flush metrics CSV: {e}")

    # ── Prometheus export (optional) ─────────────────────────────

    def start_prometheus_server(self, port: int = 9090) -> None:
        """
        Start a Prometheus metrics HTTP server on the given port.
        Requires `prometheus_client` package (optional dependency).
        """
        try:
            from prometheus_client import Gauge, Counter, start_http_server

            self._prom_stage_duration = Gauge(
                "pipeline_stage_duration_seconds",
                "Duration of each pipeline stage",
                ["stage"],
            )
            self._prom_stage_leads = Gauge(
                "pipeline_stage_lead_count",
                "Leads produced by each stage",
                ["stage"],
            )
            self._prom_stage_errors = Counter(
                "pipeline_stage_errors_total",
                "Errors encountered per stage",
                ["stage"],
            )
            self._prom_total_leads = Gauge(
                "pipeline_total_leads",
                "Total leads in current run",
            )

            start_http_server(port)
            logger.info(f"Prometheus metrics server started on :{port}")
            self._prom_enabled = True
        except ImportError:
            logger.info("prometheus_client not installed — Prometheus export disabled")
            self._prom_enabled = False

    def update_prometheus(self) -> None:
        """Push current metrics to Prometheus gauges."""
        if not getattr(self, "_prom_enabled", False):
            return
        for stage, entry in self._stage_metrics.items():
            self._prom_stage_duration.labels(stage=stage).set(entry.get("duration_s", 0))
            self._prom_stage_leads.labels(stage=stage).set(entry.get("lead_count", 0))
            if entry.get("error_count", 0) > 0:
                self._prom_stage_errors.labels(stage=stage).inc(entry["error_count"])
        summary = self.run_summary()
        self._prom_total_leads.set(summary["total_leads"])
