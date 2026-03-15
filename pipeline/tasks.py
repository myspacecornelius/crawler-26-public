"""
Celery task definitions for decoupled pipeline stages.

Each pipeline stage (discovery, aggregation, deep crawl, enrichment,
portfolio scraping) is defined as an independent Celery task that can
be scheduled, retried, and monitored independently.

Usage:
    # Start Celery worker:
    #   celery -A pipeline.tasks worker --loglevel=info

    # Trigger a full pipeline run:
    from pipeline.tasks import run_full_pipeline
    result = run_full_pipeline.delay()

    # Or run individual stages:
    from pipeline.tasks import run_discovery
    result = run_discovery.delay()

    # Chain stages:
    from celery import chain
    workflow = chain(
        run_aggregation.si(),
        run_discovery.si(),
        run_deep_crawl.si(),
        run_enrichment.si(),
    )
    workflow.apply_async()
"""

import asyncio
import logging
import os
from datetime import datetime, timezone

from celery import Celery
from celery.utils.log import get_task_logger

from config.settings import settings

logger = get_task_logger(__name__)

# ── Celery app ───────────────────────────────────────────────────

app = Celery(
    "leadfactory",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=3600,   # 1 hour soft limit
    task_time_limit=7200,        # 2 hour hard limit
    task_default_retry_delay=60,
    task_max_retries=3,
)


def _run_async(coro):
    """Helper to run async code from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Pipeline tasks ───────────────────────────────────────────────

@app.task(bind=True, name="pipeline.run_aggregation", max_retries=3)
def run_aggregation(self):
    """
    Stage 1: Aggregate leads from deterministic sources (seed DB, GitHub, HTTP).
    """
    logger.info("Starting aggregation stage")
    try:
        from sources.aggregator import SourceAggregator, generate_target_funds

        async def _aggregate():
            aggregator = SourceAggregator()
            leads = await aggregator.aggregate()
            await generate_target_funds(leads)
            return len(leads)

        count = _run_async(_aggregate())
        logger.info(f"Aggregation complete: {count} leads")
        return {"stage": "aggregation", "lead_count": count, "status": "completed"}

    except Exception as exc:
        logger.error(f"Aggregation failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, name="pipeline.run_discovery", max_retries=3)
def run_discovery(self):
    """
    Stage 2: Multi-engine domain discovery for VC websites.
    """
    logger.info("Starting discovery stage")
    try:
        import yaml
        from pathlib import Path
        from discovery.multi_searcher import multi_discover
        from sources.http_discovery import http_discover

        async def _discover():
            with open(settings.search_config) as f:
                search_config = yaml.safe_load(f).get("discovery", {})

            queries = search_config.get("queries", [])
            target_count = search_config.get("target_domains_count", 2000)
            ignore = set(search_config.get("ignore_domains", []))
            engine_config = search_config.get("engines", {})

            if engine_config:
                domains = await multi_discover(
                    queries, target_count=target_count,
                    ignore_domains=ignore, engine_config=engine_config,
                )
            else:
                domains = await http_discover(
                    queries, target_count=target_count, ignore_domains=ignore,
                )

            target_file = Path("data/target_funds.txt")
            target_file.parent.mkdir(parents=True, exist_ok=True)
            with open(target_file, "w") as f:
                for domain in sorted(domains):
                    f.write(domain + "\n")

            return len(domains)

        count = _run_async(_discover())
        logger.info(f"Discovery complete: {count} domains")
        return {"stage": "discovery", "domain_count": count, "status": "completed"}

    except Exception as exc:
        logger.error(f"Discovery failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, name="pipeline.run_deep_crawl", max_retries=2)
def run_deep_crawl(self, concurrency: int = 10, headless: bool = True):
    """
    Stage 3: Deep crawl fund websites to extract team member contacts.
    """
    logger.info("Starting deep crawl stage")
    try:
        from deep_crawl import DeepCrawler

        async def _deep_crawl():
            crawler = DeepCrawler(
                target_file="data/target_funds.txt",
                output_file="data/vc_contacts.csv",
                max_concurrent=concurrency,
                headless=headless,
                skip_enrichment=True,
            )
            await crawler.run()
            return len(crawler.all_contacts)

        count = _run_async(_deep_crawl())
        logger.info(f"Deep crawl complete: {count} contacts")
        return {"stage": "deep_crawl", "lead_count": count, "status": "completed"}

    except Exception as exc:
        logger.error(f"Deep crawl failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, name="pipeline.run_enrichment", max_retries=2)
def run_enrichment(self, checkpoint_path: str = ""):
    """
    Stage 4: Enrichment pipeline (dedup, email validation, scoring).
    Loads leads from checkpoint or DB, enriches, and writes output.
    """
    logger.info("Starting enrichment stage")
    try:
        import argparse

        async def _enrich():
            from engine import CrawlEngine, _load_checkpoint

            args = argparse.Namespace(
                site="", headless=True, dry_run=False, verbose=False,
                webhook="", webhook_platform="discord", discover=False,
                force_recrawl=False, deep=False, skip_smtp=False,
                skip_greyhat=False, portfolio=False, incremental=False,
                stale_days=settings.stale_days, concurrency=settings.concurrency,
                smtp_concurrency=settings.smtp_concurrency, resume="", scale=False,
            )
            engine = CrawlEngine(args)

            if checkpoint_path:
                engine.all_leads = _load_checkpoint(checkpoint_path)
            else:
                # Load from lead store
                from pipeline.lead_store import LeadStore
                store = LeadStore()
                await store.init()
                engine.all_leads = await store.load_all()

            if engine.all_leads:
                await engine._enrich_and_output()

            return len(engine.all_leads)

        count = _run_async(_enrich())
        logger.info(f"Enrichment complete: {count} leads")
        return {"stage": "enrichment", "lead_count": count, "status": "completed"}

    except Exception as exc:
        logger.error(f"Enrichment failed: {exc}")
        raise self.retry(exc=exc)


@app.task(bind=True, name="pipeline.run_portfolio_scrape", max_retries=2)
def run_portfolio_scrape(self, headless: bool = True):
    """
    Stage 5: Scrape portfolio companies from fund websites.
    """
    logger.info("Starting portfolio scrape stage")
    try:
        from enrichment.portfolio_scraper import PortfolioScraper
        from pathlib import Path

        async def _scrape():
            target_file = Path("data/target_funds.txt")
            if not target_file.exists():
                return 0

            fund_urls = [
                line.strip() for line in target_file.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

            scraper = PortfolioScraper(max_concurrent=10, headless=headless)
            companies = await scraper.scrape_funds(fund_urls)
            return len(companies)

        count = _run_async(_scrape())
        logger.info(f"Portfolio scrape complete: {count} companies")
        return {"stage": "portfolio_scrape", "company_count": count, "status": "completed"}

    except Exception as exc:
        logger.error(f"Portfolio scrape failed: {exc}")
        raise self.retry(exc=exc)


@app.task(name="pipeline.run_full_pipeline")
def run_full_pipeline(
    discover: bool = True,
    deep_crawl: bool = True,
    portfolio: bool = False,
    headless: bool = True,
):
    """
    Orchestrate the full pipeline as a chain of independent tasks.
    Each stage runs as its own Celery task with individual retry logic.
    """
    from celery import chain

    stages = [run_aggregation.si()]

    if discover:
        stages.append(run_discovery.si())

    if deep_crawl:
        stages.append(run_deep_crawl.si(
            concurrency=settings.concurrency,
            headless=headless,
        ))

    if portfolio:
        stages.append(run_portfolio_scrape.si(headless=headless))

    stages.append(run_enrichment.si())

    workflow = chain(*stages)
    result = workflow.apply_async()

    logger.info(f"Full pipeline chain started: {result.id}")
    return {"pipeline_task_id": result.id, "stages": len(stages)}
