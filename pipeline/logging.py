"""
Structured logging for the LeadFactory pipeline.

Provides JSON-formatted log records with context fields (domain, adapter,
phase) so logs can be aggregated, searched, and alerted on in production.

Usage:
    from pipeline.logging import get_logger, configure_logging

    configure_logging()  # call once at startup
    logger = get_logger("crawl.engine")
    logger.info("Stage started", extra={"phase": "discovery", "domain_count": 42})
"""

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Optional


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Merge extra fields (phase, domain, adapter, etc.)
        for key in ("phase", "domain", "adapter", "stage", "duration_s",
                     "lead_count", "error_count", "domain_count", "run_id",
                     "retry_attempt", "email_count"):
            val = getattr(record, key, getattr(record, f"_ctx_{key}", None))
            if val is not None:
                log_entry[key] = val

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


class HumanFormatter(logging.Formatter):
    """Human-readable format with optional context fields."""

    def __init__(self):
        super().__init__(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = []
        for key in ("phase", "domain", "adapter", "stage", "duration_s",
                     "lead_count", "error_count", "run_id"):
            val = getattr(record, key, getattr(record, f"_ctx_{key}", None))
            if val is not None:
                extras.append(f"{key}={val}")
        if extras:
            base += "  [" + " ".join(extras) + "]"
        return base


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    log_file: str = "",
) -> None:
    """
    Configure root logging for the pipeline.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR).
        fmt: 'json' for structured output or 'text' for human-readable.
        log_file: Optional file path. Empty string means stdout only.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers to avoid duplicates on re-configure
    root.handlers.clear()

    formatter = JSONFormatter() if fmt == "json" else HumanFormatter()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    # Optional file handler
    if log_file:
        from pathlib import Path
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (convenience wrapper)."""
    return logging.getLogger(name)


class PipelineContext:
    """
    Context manager that attaches extra fields to all log records
    emitted within its scope.

    Usage:
        with PipelineContext(phase="discovery", run_id="abc123"):
            logger.info("Starting discovery")
            # → {"phase": "discovery", "run_id": "abc123", ...}
    """

    def __init__(self, **fields):
        self.fields = fields
        self._old_factory = None

    def __enter__(self):
        old_factory = logging.getLogRecordFactory()
        self._old_factory = old_factory
        fields = self.fields

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for k, v in fields.items():
                ctx_k = f"_ctx_{k}"
                if not hasattr(record, ctx_k):
                    setattr(record, ctx_k, v)
            return record

        logging.setLogRecordFactory(record_factory)
        return self

    def __exit__(self, *exc):
        if self._old_factory is not None:
            logging.setLogRecordFactory(self._old_factory)
        return False
