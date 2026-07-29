"""Scheduler that runs the domestic electrical data pipeline daily or monthly."""

import asyncio
import logging
import os
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import cast

import schedule
import structlog

from data_pipeline.config import settings
from data_pipeline.loader import run_pipeline

logger = structlog.get_logger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal health endpoint for Railway liveness/readiness probes."""

    def log_message(self, format: str, *args) -> None:  # type: ignore[no-untyped-def]
        # Suppress per-request logs; the scheduler logs are noisy enough.
        pass

    def do_GET(self) -> None:  # type: ignore[override]
        if self.path == "/health":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()


def _start_health_server() -> None:
    """Start a tiny HTTP server in a background thread for health checks."""
    port = int(os.environ.get("PORT", "8000"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("health_server_started", port=port)


def _parse_run_time(run_time: str) -> tuple[int, int]:
    """Parse HH:MM string into hour and minute."""
    try:
        hour, minute = run_time.split(":")
        return int(hour), int(minute)
    except ValueError as exc:
        raise ValueError(f"Invalid daily_run_time format: {run_time!r}") from exc


def _log_result(result: dict[str, int]) -> None:
    """Log the outcome of a pipeline run."""
    logger.info(
        "pipeline_run_complete",
        products_scraped=result.get("products_scraped"),
        products_normalized=result.get("products_normalized"),
        cost_items_upserted=result.get("cost_items_upserted"),
        stale_items_deactivated=result.get("stale_items_deactivated"),
    )


def _run_pipeline_sync() -> None:
    """Synchronous wrapper that executes the async pipeline."""
    logger.info("pipeline_run_started", scheduled_time=settings.daily_run_time)
    try:
        result = asyncio.run(run_pipeline())
        _log_result(result)
    except Exception:
        logger.exception("pipeline_run_failed")


def schedule_daily_job() -> schedule.Job:
    """Schedule the pipeline to run at the configured time each day."""
    hour, minute = _parse_run_time(settings.daily_run_time)
    return cast(
        "schedule.Job",
        schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(_run_pipeline_sync),
    )


def _should_run_monthly() -> bool:
    """Check whether today is the configured monthly run day."""
    return datetime.utcnow().day == settings.monthly_run_day


def _run_if_monthly_due() -> None:
    """Trigger the pipeline only on the configured day of the month."""
    if _should_run_monthly():
        _run_pipeline_sync()


def schedule_monthly_job() -> schedule.Job:
    """Schedule a daily check that runs the pipeline once per month."""
    hour, minute = _parse_run_time(settings.daily_run_time)
    return cast(
        "schedule.Job",
        schedule.every().day.at(f"{hour:02d}:{minute:02d}").do(_run_if_monthly_due),
    )


def run_scheduler(run_on_start: bool = False) -> None:
    """Run the scheduler loop, optionally executing the pipeline immediately."""
    logging.basicConfig(
        stream=sys.stdout,
        level=logging.INFO,
        format="%(message)s",
    )
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    _start_health_server()

    if settings.scrape_frequency == "monthly":
        job = schedule_monthly_job()
        logger.info(
            "scheduler_started",
            scrape_frequency=settings.scrape_frequency,
            monthly_run_day=settings.monthly_run_day,
            daily_run_time=settings.daily_run_time,
            next_run=str(job.next_run),
        )
    else:
        job = schedule_daily_job()
        logger.info(
            "scheduler_started",
            scrape_frequency=settings.scrape_frequency,
            daily_run_time=settings.daily_run_time,
            next_run=str(job.next_run),
        )

    if run_on_start:
        _run_pipeline_sync()

    while True:
        schedule.run_pending()
        time.sleep(60)


def main() -> None:
    """CLI entry point for the scheduler."""
    import argparse

    parser = argparse.ArgumentParser(description="Domestic electrical data pipeline scheduler")
    parser.add_argument(
        "--run-on-start",
        action="store_true",
        help="Run the pipeline once immediately, then schedule daily runs",
    )
    args = parser.parse_args()
    run_scheduler(run_on_start=args.run_on_start)


if __name__ == "__main__":
    main()
