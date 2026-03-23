"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   CRAWL ENGINE v3 — Investor Lead Machine                    ║
║                                                              ║
║   Config-driven, multi-site crawler with stealth,            ║
║   enrichment, scoring, and automated output.                 ║
║                                                              ║
║   v3: Structured logging, retry resilience, metrics,         ║
║       streaming DB persistence, centralized config.          ║
║                                                              ║
║   Usage:                                                     ║
║     python engine.py                    # Crawl all sites    ║
║     python engine.py --site openvc      # Crawl one site     ║
║     python engine.py --dry-run          # Test without save  ║
║     python engine.py --headless         # No browser window  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

import asyncio
import argparse
import logging
import time
import traceback
import uuid
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime, timezone

import yaml
from playwright.async_api import async_playwright

# ── Pipeline infrastructure ──
from pipeline.logging import configure_logging, get_logger, PipelineContext
from pipeline.metrics import PipelineMetrics
from pipeline.retry import retry_async, RetryExhausted
from pipeline.lead_store import LeadStore
from config.settings import settings

# ── Internal modules ──
from adapters.registry import get_registry
from stealth.fingerprint import FingerprintManager
from stealth.behavior import HumanBehavior
from stealth.proxy import ProxyManager
from enrichment.email_validator import EmailValidator
from enrichment.email_guesser import EmailGuesser
from enrichment.scoring import LeadScorer
from output.csv_writer import CSVWriter
from output.webhook import WebhookNotifier
from discovery.searcher import Searcher
from sources.aggregator import SourceAggregator, generate_target_funds
from sources.http_discovery import http_discover
from discovery.multi_searcher import multi_discover
from deep_crawl import DeepCrawler
from enrichment.portfolio_scraper import PortfolioScraper
from enrichment.incremental import CrawlStateManager, update_lead_freshness_in_db
from dotenv import load_dotenv
load_dotenv()  # .env → os.environ (SERPAPI_KEY, GITHUB_TOKEN, etc.)

from enrichment.google_dorker import GoogleDorker
from enrichment.github_miner import GitHubMiner
from enrichment.sec_edgar import SECEdgarScraper
from enrichment.wayback_enricher import WaybackEnricher
from enrichment.dns_harvester import DNSHarvester
from enrichment.catchall_detector import CatchAllDetector
from enrichment.gravatar_oracle import GravatarOracle
from enrichment.pgp_keyserver import PGPKeyserverScraper
from enrichment.dedup import LeadDeduplicator
from enrichment.email_waterfall import EmailWaterfall
from enrichment.hunter_domain_finder import HunterDomainFinder
from enrichment.edgar_bulk import run_edgar_bulk_discovery

logger = get_logger("crawl.engine")


# ──────────────────────────────────────────────────
#  Engine
# ──────────────────────────────────────────────────

class CrawlEngine:
    """
    Main orchestrator. Wires together:
    - Site configs → Adapters
    - Stealth layer (fingerprints, human behavior, proxies)
    - Enrichment pipeline (email validation, lead scoring)
    - Output (CSV, webhooks)
    - Metrics collection and structured logging
    """

    def __init__(self, args):
        self.args = args
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.config = self._load_config(str(settings.sites_config))
        self.adapter_registry = get_registry()
        self.fingerprint_mgr = FingerprintManager()
        self.behavior = HumanBehavior(speed_factor=1.0)
        self.proxy_mgr = ProxyManager(str(settings.proxies_config))
        self.email_validator = EmailValidator()
        self.email_guesser = EmailGuesser(concurrency=settings.concurrency)
        self.hunter_finder = HunterDomainFinder(
            pattern_store=self.email_guesser.pattern_store,
        )
        self.scorer = LeadScorer(str(settings.scoring_config))
        self.csv_writer = CSVWriter(str(settings.data_dir))
        self.webhook = WebhookNotifier(
            webhook_url=args.webhook or "",
            platform=args.webhook_platform or "discord",
        )
        self.all_leads = []
        self.crawl_state = CrawlStateManager(
            stale_days=getattr(args, 'stale_days', settings.stale_days)
        )

        # Pipeline infrastructure
        self.metrics = PipelineMetrics(
            csv_path=settings.metrics_file,
            run_id=self.run_id,
        )
        self.lead_store = LeadStore(run_id=self.run_id)
        self._error_count = 0
        self._stages_completed = []

    def _load_config(self, path: str) -> dict:
        try:
            with open(path) as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.error(f"Config file not found: {path}")
            return {"sites": {}, "defaults": {}}
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in {path}: {e}")
            return {"sites": {}, "defaults": {}}

    async def _run_discovery(self):
        """Run multi-engine discovery and save results to data/target_funds.txt."""
        self.metrics.stage_start("discovery")
        logger.info("Starting multi-engine domain discovery", extra={"phase": "discovery"})
        print("\n  DISCOVERY MODE — finding VC domains via multi-engine search...")

        try:
            with open(str(settings.search_config)) as f:
                search_config = yaml.safe_load(f).get("discovery", {})

            queries = search_config.get("queries", [])
            target_count = search_config.get("target_domains_count", 2000)
            ignore = set(search_config.get("ignore_domains", []))
            engine_config = search_config.get("engines", {})

            if engine_config:
                domains = await multi_discover(
                    queries,
                    target_count=target_count,
                    ignore_domains=ignore,
                    engine_config=engine_config,
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

            logger.info(
                f"Discovery complete: {len(domains)} domains",
                extra={"phase": "discovery", "domain_count": len(domains)},
            )
            print(f"  Discovery complete: {len(domains)} domains -> {target_file}")
            self.metrics.stage_end("discovery", lead_count=len(domains))
            self._stages_completed.append("discovery")
            return domains

        except Exception as e:
            self._error_count += 1
            logger.error(
                f"Discovery failed: {e}",
                extra={"phase": "discovery"},
                exc_info=self.args.verbose,
            )
            self.metrics.stage_end("discovery", error_count=1)
            print(f"  Discovery failed: {e}")
            return []

    @staticmethod
    def _fund_name_to_domain(fund_name: str) -> str:
        """
        Heuristically derive a probable website domain from a fund name.
        Strips legal suffixes, punctuation, and converts to lowercase bare domain.
        Returns '' if the name is too short or generic.
        """
        import re as _re
        # Strip common legal entity suffixes
        name = _re.sub(
            r'\b(llc|lp|l\.p\.|ltd|limited|inc|corp|fund\s+[ixv]+|fund\s+\d+|gp|llp|plc|co\.?)\b',
            '', fund_name, flags=_re.IGNORECASE
        ).strip()
        # Remove punctuation except hyphens
        name = _re.sub(r'[,.\'"!?()&@]', '', name).strip()
        # Collapse whitespace, convert to lowercase, strip trailing hyphens/spaces
        slug = _re.sub(r'\s+', '', name).lower().strip('-')
        if len(slug) < 4:
            return ''
        return slug + '.com'

    @staticmethod
    def _fund_name_to_domains(fund_name: str) -> list:
        """
        Generate multiple candidate domains from a fund name.
        Tries .com, .vc, .co, and hyphenated variants.
        """
        import re as _re
        name = _re.sub(
            r'\b(llc|lp|l\.p\.|ltd|limited|inc|corp|fund\s+[ixv]+|fund\s+\d+|gp|llp|plc|co\.?)\b',
            '', fund_name, flags=_re.IGNORECASE
        ).strip()
        name = _re.sub(r'[,.\'"!?()&@]', '', name).strip()

        # Two slug variants: concatenated and hyphenated
        words = name.lower().split()
        slug_concat = ''.join(words).strip('-')
        slug_hyphen = '-'.join(words).strip('-')

        if len(slug_concat) < 4:
            return []

        candidates = []
        for slug in [slug_concat, slug_hyphen]:
            for tld in ['.com', '.vc', '.co', '.capital', '.ventures', '.fund', '.io']:
                candidates.append(slug + tld)
        return list(dict.fromkeys(candidates))  # dedup preserving order

    async def _run_edgar_bulk(self):
        """Pull Form D fund officers from SEC EDGAR at bulk scale."""
        self.metrics.stage_start("edgar_bulk")
        edgar_years = getattr(self.args, "edgar_years", None) or [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]
        max_filings = getattr(self.args, "edgar_max", 200000)
        print(f"\n  EDGAR BULK — pulling Form D officers (years={edgar_years}, max={max_filings})...")
        try:
            edgar_leads = await run_edgar_bulk_discovery(
                output_file="data/edgar_form_d.csv",
                years=edgar_years,
                max_filings=max_filings,
            )
            # Assign probable fund domains to leads so email_guesser can run.
            # Form D XML has no website field, so we derive it from the fund name.
            # Try multiple TLD variants (.com, .vc, .co, etc.)
            for lead in edgar_leads:
                if not lead.website or lead.website in ("N/A", ""):
                    candidates = self._fund_name_to_domains(lead.fund or "")
                    if candidates:
                        lead.website = candidates[0]  # Best guess (.com first)

            existing_emails = {lead.email for lead in self.all_leads if lead.email and lead.email != "N/A"}
            new_count = 0
            for lead in edgar_leads:
                if lead.email not in existing_emails:
                    self.all_leads.append(lead)
                    if lead.email and lead.email != "N/A":
                        existing_emails.add(lead.email)
                    new_count += 1
            await self.lead_store.add_leads(edgar_leads, source="edgar_bulk")
            print(f"  EDGAR: {new_count} new leads added (total {len(edgar_leads)} extracted)")

            # Derive and DNS-verify fund domains, then add to target_funds.txt
            # so the deep crawl can find their team pages.
            target_file = Path("data/target_funds.txt")
            existing_domains: set[str] = set()
            if target_file.exists():
                existing_domains = {l.strip() for l in target_file.read_text().splitlines() if l.strip()}

            # Collect unique fund names and generate domain candidates
            from scripts.verify_fund_domains import domain_candidates as _domain_candidates
            import socket as _socket

            fund_candidates: list[str] = []
            cand_seen: set[str] = set()
            for lead in edgar_leads:
                fund = lead.fund or ""
                if not fund or fund == "N/A":
                    continue
                for cand in _domain_candidates(fund):
                    if cand not in existing_domains and cand not in cand_seen:
                        cand_seen.add(cand)
                        fund_candidates.append(cand)

            # DNS-verify candidates asynchronously (batch, 200 concurrent)
            verified_domains: list[str] = []
            if fund_candidates:
                print(f"  EDGAR: DNS-verifying {len(fund_candidates)} fund domain candidates...")
                sem = asyncio.Semaphore(200)
                loop = asyncio.get_event_loop()

                async def _check(d: str) -> tuple:
                    async with sem:
                        try:
                            result = await loop.run_in_executor(
                                None,
                                lambda: _socket.getaddrinfo(d, None, _socket.AF_INET, _socket.SOCK_STREAM),
                            )
                            return d, bool(result)
                        except Exception:
                            return d, False

                checks = await asyncio.gather(*[_check(d) for d in fund_candidates])
                verified_domains = [d for d, ok in checks if ok]
                print(f"  EDGAR: {len(verified_domains)}/{len(fund_candidates)} fund domains verified via DNS")

            if verified_domains:
                with open(target_file, "a") as fh:
                    for d in sorted(verified_domains):
                        fh.write(d + "\n")
                print(f"  EDGAR: {len(verified_domains)} verified fund domains added to target_funds.txt")

            self.metrics.stage_end("edgar_bulk", lead_count=new_count)
            self._stages_completed.append("edgar_bulk")
        except Exception as e:
            self._error_count += 1
            self.metrics.stage_end("edgar_bulk", error_count=1)
            print(f"  EDGAR bulk failed (continuing): {e}")
            logger.error(f"EDGAR bulk failed: {e}", extra={"phase": "edgar_bulk"}, exc_info=self.args.verbose)

    async def _run_aggregator(self):
        """Run the Source Aggregator to collect leads from deterministic sources."""
        self.metrics.stage_start("aggregation")
        logger.info("Starting source aggregation", extra={"phase": "aggregation"})

        try:
            aggregator = SourceAggregator()
            leads = await aggregator.aggregate()

            # Also generate target_funds.txt for deep_crawl
            await generate_target_funds(leads)

            # Merge into engine's lead pool
            existing_names = {lead.name.lower() for lead in self.all_leads}
            new_count = 0
            for lead in leads:
                if lead.name.lower() not in existing_names:
                    self.all_leads.append(lead)
                    existing_names.add(lead.name.lower())
                    new_count += 1

            # Persist to lead store incrementally
            await self.lead_store.add_leads(leads, source="aggregator")

            logger.info(
                f"Aggregator added {new_count} new leads",
                extra={"phase": "aggregation", "lead_count": new_count},
            )
            print(f"  Aggregator added {new_count} new leads to pipeline")
            self.metrics.stage_end("aggregation", lead_count=new_count)
            self._stages_completed.append("aggregation")
            return leads

        except Exception as e:
            self._error_count += 1
            logger.error(
                f"Aggregation failed: {e}",
                extra={"phase": "aggregation"},
                exc_info=self.args.verbose,
            )
            self.metrics.stage_end("aggregation", error_count=1)
            print(f"  Aggregation failed: {e}")
            return []

    async def _run_deep_crawl(self):
        """Run deep crawl on fund websites to extract individual team members."""
        self.metrics.stage_start("deep_crawl")
        logger.info("Starting deep crawl", extra={"phase": "deep_crawl"})
        print(f"\n{'='*60}")
        print("  DEEP CRAWL — extracting team members from fund websites")
        print(f"{'='*60}\n")

        try:
            # ── Incremental: load crawl state and filter stale domains ──
            incremental = getattr(self.args, 'incremental', False)
            if incremental:
                await self.crawl_state.load_from_db()
                summary = self.crawl_state.summary()
                logger.info(
                    f"Incremental mode: {summary['stale_domains']}/{summary['total_domains']} stale",
                    extra={"phase": "deep_crawl"},
                )
                print(f"  Incremental mode: {summary['stale_domains']}/{summary['total_domains']} domains stale "
                      f"(>{self.crawl_state.stale_days}d threshold)")

            concurrency = getattr(self.args, 'concurrency', settings.concurrency)
            crawler = DeepCrawler(
                target_file="data/target_funds.txt",
                output_file="data/vc_contacts.csv",
                max_concurrent=concurrency,
                headless=getattr(self.args, 'headless', True),
                skip_enrichment=True,
                stale_days=getattr(self.args, 'stale_days', settings.stale_days),
            )

            if getattr(self.args, 'force_recrawl', False):
                crawler.force_recrawl = True

            # Filter target_funds.txt to stale-only when incremental
            if incremental and not getattr(self.args, 'force_recrawl', False):
                target_file = Path("data/target_funds.txt")
                if target_file.exists():
                    all_urls = [
                        line.strip() for line in target_file.read_text().splitlines()
                        if line.strip() and not line.strip().startswith("#")
                    ]
                    stale_urls, fresh_urls = self.crawl_state.filter_stale(all_urls)
                    print(f"  Skipping {len(fresh_urls)} fresh domains, crawling {len(stale_urls)} stale")
                    incremental_file = Path("data/target_funds_incremental.txt")
                    incremental_file.write_text("\n".join(stale_urls) + "\n")
                    crawler.target_file = str(incremental_file)

            await crawler.run()

            # Build fund metadata index from aggregator leads (keyed by domain)
            fund_meta = {}
            for lead in self.all_leads:
                if lead.website and lead.website not in ("N/A", "", "/pricing"):
                    try:
                        domain = urlparse(lead.website).netloc.lower().replace("www.", "")
                    except Exception:
                        continue
                    if domain and domain not in fund_meta:
                        fund_meta[domain] = {
                            "focus_areas": lead.focus_areas,
                            "stage": lead.stage,
                            "check_size": lead.check_size,
                            "location": lead.location,
                        }

            # Merge deep_crawl contacts into engine lead pool + inherit fund metadata
            existing_names = {lead.name.lower() for lead in self.all_leads}
            new_count = 0
            enriched_count = 0
            for contact in crawler.all_contacts:
                key = contact.name.lower()
                if key and key not in existing_names and key != "unknown":
                    if contact.website and contact.website not in ("N/A", ""):
                        try:
                            cdomain = urlparse(contact.website).netloc.lower().replace("www.", "")
                        except Exception:
                            cdomain = ""
                        meta = fund_meta.get(cdomain)
                        if meta:
                            if not contact.focus_areas or contact.focus_areas == []:
                                contact.focus_areas = meta["focus_areas"]
                            if contact.stage in ("N/A", ""):
                                contact.stage = meta["stage"]
                            if contact.check_size in ("N/A", ""):
                                contact.check_size = meta["check_size"]
                            if contact.location in ("N/A", ""):
                                contact.location = meta["location"]
                            enriched_count += 1

                    self.all_leads.append(contact)
                    existing_names.add(key)
                    new_count += 1

            # Persist to lead store
            await self.lead_store.add_leads(crawler.all_contacts, source="deep_crawl")

            logger.info(
                f"Deep crawl: {new_count} new contacts, {enriched_count} enriched with fund metadata",
                extra={"phase": "deep_crawl", "lead_count": new_count},
            )
            print(f"\n  Deep crawl added {new_count} team member leads to pipeline")
            print(f"  Enriched {enriched_count}/{new_count} contacts with fund metadata")
            print(f"  Total leads now: {len(self.all_leads)}")

            # ── Record crawl state for incremental tracking ──
            if incremental:
                domain_counts = {}
                for contact in crawler.all_contacts:
                    if contact.website and contact.website not in ("N/A", ""):
                        try:
                            d = urlparse(contact.website).netloc.lower().replace("www.", "")
                            domain_counts[d] = domain_counts.get(d, 0) + 1
                        except Exception:
                            pass
                batch = [
                    {"url": f"https://{d}", "leads_found": c, "status": "completed"}
                    for d, c in domain_counts.items()
                ]
                await self.crawl_state.mark_batch_crawled(batch)
                print(f"  Updated crawl state for {len(batch)} domains")

            self.metrics.stage_end("deep_crawl", lead_count=new_count)
            self._stages_completed.append("deep_crawl")

        except Exception as e:
            self._error_count += 1
            logger.error(
                f"Deep crawl failed: {e}",
                extra={"phase": "deep_crawl"},
                exc_info=self.args.verbose,
            )
            self.metrics.stage_end("deep_crawl", error_count=1)
            print(f"  Deep crawl failed: {e}")
            if self.args.verbose:
                traceback.print_exc()

    async def _run_portfolio_scrape(self):
        """Scrape portfolio pages from fund websites and persist to database."""
        self.metrics.stage_start("portfolio_scrape")
        logger.info("Starting portfolio scrape", extra={"phase": "portfolio_scrape"})
        print(f"\n{'='*60}")
        print("  PORTFOLIO SCRAPE — extracting portfolio companies")
        print(f"{'='*60}\n")

        try:
            target_file = Path("data/target_funds.txt")
            if not target_file.exists():
                print("  No target_funds.txt found — run aggregator or discovery first")
                self.metrics.stage_end("portfolio_scrape")
                return

            fund_urls = [
                line.strip() for line in target_file.read_text().splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]

            if not fund_urls:
                print("  No fund URLs in target_funds.txt")
                self.metrics.stage_end("portfolio_scrape")
                return

            scraper = PortfolioScraper(
                max_concurrent=settings.concurrency,
                headless=getattr(self.args, 'headless', True),
            )

            companies = await scraper.scrape_funds(fund_urls)

            # Persist to database
            if companies:
                try:
                    from api.database import async_session, init_db
                    from api.models import PortfolioCompany as PortfolioCompanyModel

                    await init_db()

                    from sqlalchemy import select
                    async with async_session() as session:
                        inserted = 0
                        for c in companies:
                            existing = await session.execute(
                                select(PortfolioCompanyModel).where(
                                    PortfolioCompanyModel.fund_name == c.fund_name,
                                    PortfolioCompanyModel.company_name == c.company_name,
                                )
                            )
                            if existing.scalar_one_or_none():
                                continue
                            row = PortfolioCompanyModel(
                                fund_name=c.fund_name,
                                company_name=c.company_name,
                                sector=c.sector,
                                stage=c.stage,
                                url=c.url,
                                year=c.year,
                            )
                            session.add(row)
                            inserted += 1

                        await session.commit()
                        logger.info(
                            f"Persisted {inserted} portfolio companies",
                            extra={"phase": "portfolio_scrape", "lead_count": inserted},
                        )
                        print(f"  Persisted {inserted} new portfolio companies to database")
                except Exception as e:
                    self._error_count += 1
                    logger.error(f"Failed to persist portfolio data: {e}", extra={"phase": "portfolio_scrape"})
                    print(f"  Failed to persist portfolio data: {e}")

            print(f"  Total portfolio companies: {len(companies)}")
            self.metrics.stage_end("portfolio_scrape", lead_count=len(companies))
            self._stages_completed.append("portfolio_scrape")

        except Exception as e:
            self._error_count += 1
            logger.error(f"Portfolio scrape failed: {e}", extra={"phase": "portfolio_scrape"}, exc_info=self.args.verbose)
            self.metrics.stage_end("portfolio_scrape", error_count=1)
            print(f"  Portfolio scrape failed: {e}")

    async def run(self):
        """Execute the full crawl pipeline."""
        start_time = time.time()

        # Initialize lead store for streaming persistence
        await self.lead_store.init()

        # --scale mode: automatically enables deep crawl + discovery for max volume
        if getattr(self.args, 'scale', False):
            self.args.deep = True
            self.args.discover = True
            self.args.headless = True
            self.args.edgar = True
            logger.info("SCALE MODE: auto-enabling --deep --discover --headless --edgar")

        self._print_banner()

        with PipelineContext(run_id=self.run_id):
            # ── Stages 1-2.5: Run independent data sourcing concurrently ──
            init_tasks = []
            if not self.args.site:
                init_tasks.append(self._run_aggregator())
            if self.args.discover:
                init_tasks.append(self._run_discovery())
            if getattr(self.args, 'edgar', False):
                init_tasks.append(self._run_edgar_bulk())
            if init_tasks:
                await asyncio.gather(*init_tasks)

            # ── Stage 3: Adapter-based site crawling ──
            sites = self.config.get("sites", {})
            defaults = self.config.get("defaults", {})

            if self.args.site:
                if self.args.site not in sites:
                    print(f"\n  Site '{self.args.site}' not found in config.")
                    print(f"  Available: {', '.join(sites.keys())}")
                    return
                sites = {self.args.site: sites[self.args.site]}

            self.metrics.stage_start("site_crawl")
            async with async_playwright() as p:
                crawl_tasks = []
                for site_name, site_config in sites.items():
                    if not site_config.get("enabled", True):
                        print(f"\n  Skipping {site_name} (disabled)")
                        continue

                    adapter_name = site_config.get("adapter", "")
                    adapter_class = self.adapter_registry.get(adapter_name)

                    if not adapter_class:
                        print(f"\n  No adapter found for '{adapter_name}', skipping {site_name}")
                        continue

                    crawl_tasks.append(
                        self._crawl_site_safe(p, site_name, site_config, adapter_class, defaults)
                    )

                if crawl_tasks:
                    results = await asyncio.gather(*crawl_tasks)
                    for leads in results:
                        self.all_leads.extend(leads)
                        await self.lead_store.add_leads(leads, source="adapter")

            site_lead_count = sum(len(r) for r in results) if crawl_tasks else 0
            self.metrics.stage_end("site_crawl", lead_count=site_lead_count)
            self._stages_completed.append("site_crawl")

            # ── Stage 4: Deep crawl ──
            if getattr(self.args, 'deep', False):
                await self._run_deep_crawl()

            # ── Stage 5: Portfolio scrape ──
            if getattr(self.args, 'portfolio', False):
                await self._run_portfolio_scrape()

            # ── Stage 6: Enrichment + Output ──
            if self.all_leads:
                await self._enrich_and_output()
            else:
                print("\n  No leads collected. Check your site configs and selectors.")

        # ── Final metrics ──
        elapsed = time.time() - start_time
        self.metrics.stage_end("pipeline_total", lead_count=len(self.all_leads), error_count=self._error_count)
        self.metrics.flush()
        self.metrics.update_prometheus()

        # Save enriched leads back to DB
        await self.lead_store.save_all(self.all_leads)

        # Record pipeline run
        await self._record_run(elapsed)

        self._print_summary(elapsed)

    async def _record_run(self, elapsed: float):
        """Record this pipeline run to the database for observability."""
        try:
            from api.database import async_session, init_db
            from api.models import PipelineRun

            await init_db()
            async with async_session() as session:
                total_emails = sum(
                    1 for lead in self.all_leads
                    if lead.email and lead.email != "N/A" and "@" in lead.email
                )
                run = PipelineRun(
                    run_id=self.run_id,
                    status="completed" if self._error_count == 0 else "completed_with_errors",
                    completed_at=datetime.now(timezone.utc),
                    total_leads=len(self.all_leads),
                    total_emails=total_emails,
                    total_errors=self._error_count,
                    stages_completed=",".join(self._stages_completed),
                )
                session.add(run)
                await session.commit()
                logger.info(f"Pipeline run recorded: {self.run_id}", extra={"run_id": self.run_id})
        except Exception as e:
            logger.warning(f"Failed to record pipeline run: {e}")

    async def _crawl_site_safe(self, playwright, site_name, site_config, adapter_class, defaults):
        """Wrapper that catches per-site errors so one failure doesn't kill the batch."""
        try:
            return await self._crawl_site(playwright, site_name, site_config, adapter_class, defaults)
        except Exception as e:
            self._error_count += 1
            logger.error(
                f"Error crawling {site_name}: {e}",
                extra={"phase": "site_crawl", "adapter": site_name},
                exc_info=self.args.verbose,
            )
            if self.args.verbose:
                traceback.print_exc()
            return []

    async def _crawl_site(self, playwright, site_name, site_config, adapter_class, defaults):
        """Crawl a single site with a fresh browser context."""
        logger.info(f"Crawling site: {site_name}", extra={"adapter": site_name, "phase": "site_crawl"})
        print(f"\n  Initializing browser for {site_name}...")

        # Generate a fresh fingerprint for this site
        fingerprint = self.fingerprint_mgr.generate()
        context_kwargs = self.fingerprint_mgr.get_context_kwargs(fingerprint)

        # Check for proxy
        proxy = self.proxy_mgr.get_proxy(site_name)

        # Determine headless mode
        headless = self.args.headless or defaults.get("headless", False)

        # Launch browser
        browser = await playwright.chromium.launch(headless=headless)
        try:
            context = await browser.new_context(
                **context_kwargs,
                **({"proxy": proxy} if proxy else {}),
            )

            # Apply JS fingerprint overrides
            page = await context.new_page()
            await self.fingerprint_mgr.apply_js_overrides(page)

            # Run the adapter
            adapter = adapter_class(site_config, stealth_module=self.behavior)
            leads = await adapter.run(page)

            # Take a screenshot if configured
            if defaults.get("screenshots", False):
                ss_dir = Path(defaults.get("screenshot_dir", str(settings.screenshot_dir)))
                ss_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                await page.screenshot(
                    path=str(ss_dir / f"{site_name}_{timestamp}.png"),
                    full_page=True,
                )
                print("  Screenshot saved")

            logger.info(
                f"Crawled {site_name}: {len(leads)} leads",
                extra={"adapter": site_name, "lead_count": len(leads), "phase": "site_crawl"},
            )
            return leads
        finally:
            await browser.close()

    def _checkpoint(self, phase_name: str):
        """Save leads to a checkpoint file after each enrichment phase."""
        try:
            self.csv_writer.write(
                self.all_leads,
                f"checkpoint_{phase_name}.csv",
                enriched=True,
            )
            self._log_progress(phase_name)
        except Exception as e:
            logger.warning(f"Failed to write checkpoint for {phase_name}: {e}")

    def _log_progress(self, phase: str):
        """Log structured progress counters toward 30k target."""
        total = len(self.all_leads)
        with_email = sum(1 for lead in self.all_leads if lead.email and lead.email != "N/A" and "@" in lead.email)
        verified = sum(1 for lead in self.all_leads if lead.email_status == "verified")
        target = settings.target_lead_count
        logger.info(
            f"[PROGRESS] phase={phase} total_leads={total} with_email={with_email} "
            f"verified={verified} target={target} completion={100*with_email//target if target else 0}%",
            extra={
                "phase": phase,
                "lead_count": total,
                "email_count": with_email,
                "run_id": self.run_id,
            },
        )

    async def _enrich_and_output(self):
        """Run enrichment and output pipeline on collected leads."""
        self.metrics.stage_start("enrichment")
        logger.info("Starting enrichment pipeline", extra={"phase": "enrichment"})
        print(f"\n{'='*60}")
        print("  ENRICHMENT PIPELINE")
        print(f"{'='*60}\n")

        # ── Filter fund-level rows FIRST (name == fund name → not a person) ──
        before_filter = len(self.all_leads)
        self.all_leads = [
            lead for lead in self.all_leads
            if lead.name.lower().strip() != lead.fund.lower().strip()
        ]
        filtered_out = before_filter - len(self.all_leads)
        if filtered_out:
            print(f"  Filtered {filtered_out} fund-level rows (name == fund name)")
        print(f"  {len(self.all_leads)} person-level leads remaining")

        # ── Cross-run deduplication ──
        try:
            dedup = LeadDeduplicator()
            self.all_leads = dedup.deduplicate(self.all_leads)
            self._checkpoint("dedup")
        except Exception as e:
            self._error_count += 1
            logger.error(f"Deduplication failed: {e}", extra={"phase": "dedup"}, exc_info=True)
            print(f"  Deduplication failed (continuing without): {e}")

        # ── Email validation (with MX verification) ──
        try:
            print(f"  Validating {len(self.all_leads)} emails (+ MX check)...")
            emails = [lead.email for lead in self.all_leads]
            results = await self.email_validator.validate_batch(emails)
            for lead, result in zip(self.all_leads, results):
                if result["quality"] == "invalid":
                    lead.email = "N/A"
                elif not result.get("has_mx", True):
                    lead.email = "N/A"
                elif result["is_disposable"]:
                    lead.email = "N/A"

            # Mark scraped emails
            pre_existing = 0
            for lead in self.all_leads:
                if lead.email and lead.email != "N/A" and "@" in lead.email:
                    lead.email_status = "scraped"
                    pre_existing += 1
            print(f"  Pre-existing emails (scraped from pages): {pre_existing}")
            self._checkpoint("validation")
        except Exception as e:
            self._error_count += 1
            logger.error(f"Email validation failed: {e}", extra={"phase": "validation"}, exc_info=True)
            print(f"  Email validation failed (continuing): {e}")

        # ── Hunter domain search (pattern + known contacts, 1 call/domain) ──
        if self.hunter_finder.enabled:
            try:
                self.all_leads = await self.hunter_finder.enrich_leads(self.all_leads)
                self._checkpoint("hunter")
            except Exception as e:
                self._error_count += 1
                logger.error(
                    f"Hunter domain finder failed: {e}",
                    extra={"phase": "hunter"}, exc_info=True,
                )
                print(f"  Hunter domain finder failed (continuing): {e}")
        else:
            logger.debug("Hunter domain finder disabled (no HUNTER_API_KEY)")

        # ── Email guessing (for leads still missing an email) ──
        try:
            print("  Guessing emails for contacts without one...")
            self.all_leads = await self.email_guesser.guess_batch(self.all_leads)
            gs = self.email_guesser.stats
            print(f"  Guesser: {gs['found']} found / {gs['attempted']} domains checked")
            if gs.get("pattern_hits", 0):
                print(f"  Pattern hits: {gs['pattern_hits']} (from learned patterns)")
            if gs.get("default_hits", 0):
                print(f"  Default pattern (first.last@domain): {gs['default_hits']}")
            if gs.get("mx_rejects", 0):
                print(f"  Domains without MX records: {gs['mx_rejects']}")
            if gs.get("company_skipped", 0):
                print(f"  Company/fund names skipped: {gs['company_skipped']}")

            for lead in self.all_leads:
                if lead.email_status == "unknown" and lead.email and lead.email != "N/A" and "@" in lead.email:
                    lead.email_status = "guessed"

            total_emails = sum(
                1 for lead in self.all_leads
                if lead.email and lead.email != "N/A" and "@" in lead.email
            )
            print(f"  TOTAL emails: {total_emails}/{len(self.all_leads)} ({100*total_emails//len(self.all_leads) if self.all_leads else 0}%)")
            self.metrics.increment("emails_total", total_emails)
            self._checkpoint("guesser")
        except Exception as e:
            self._error_count += 1
            logger.error(f"Email guessing failed: {e}", extra={"phase": "guesser"}, exc_info=True)
            print(f"  Email guessing failed (continuing): {e}")

        # ── Email pattern expansion (--expand-emails) ──
        if getattr(self.args, 'expand_emails', False):
            pre = len(self.all_leads)
            self.all_leads = self.email_guesser.expand_leads_with_all_patterns(
                self.all_leads
            )
            print(f"  Expanded {pre} contacts → {len(self.all_leads)} email-pattern rows")

        # ── Greyhat enrichment ──
        if not getattr(self.args, 'skip_greyhat', False):
            try:
                await self._run_greyhat_enrichment()
                self._checkpoint("greyhat")
            except Exception as e:
                self._error_count += 1
                logger.error(f"Greyhat enrichment failed: {e}", extra={"phase": "greyhat"}, exc_info=True)
                print(f"  Greyhat enrichment failed (continuing): {e}")
        else:
            print("  Greyhat enrichment skipped (--skip-greyhat)")

        # ── SMTP batch verification ──
        if not getattr(self.args, 'skip_smtp', False):
            try:
                smtp_candidates = [
                    lead for lead in self.all_leads
                    if lead.email and lead.email != "N/A" and "@" in lead.email
                ]
                if smtp_candidates:
                    print(f"  SMTP verification on {len(smtp_candidates)} emails...")
                    email_list = [lead.email for lead in smtp_candidates]
                    smtp_results = await self.email_validator.verify_smtp_batch(
                        email_list,
                        concurrency=getattr(self.args, 'smtp_concurrency', settings.smtp_concurrency),
                    )

                    verified = undeliverable = catch_all = unknown = 0
                    for lead in smtp_candidates:
                        result = smtp_results.get(lead.email)
                        if not result:
                            unknown += 1
                            continue
                        if result["deliverable"] is True:
                            if result["catch_all"]:
                                lead.email_status = "catch_all"
                                catch_all += 1
                            else:
                                lead.email_status = "verified"
                                verified += 1
                        elif result["deliverable"] is False:
                            lead.email_status = "undeliverable"
                            undeliverable += 1
                        else:
                            unknown += 1

                    self.metrics.increment("emails_verified", verified)
                    self.metrics.increment("emails_undeliverable", undeliverable)
                    print(f"  SMTP summary: {verified} verified, {undeliverable} undeliverable, "
                          f"{catch_all} catch-all, {unknown} unknown")
                self._checkpoint("smtp")
            except Exception as e:
                self._error_count += 1
                logger.error(f"SMTP verification failed: {e}", extra={"phase": "smtp"}, exc_info=True)
                print(f"  SMTP verification failed (continuing): {e}")
        else:
            print("  SMTP verification skipped (--skip-smtp)")

        # ── Email waterfall verification ──
        try:
            waterfall = EmailWaterfall()
            if waterfall.providers:
                self.all_leads = await waterfall.verify_batch(self.all_leads)
                self._checkpoint("waterfall")
            else:
                print("  Email waterfall skipped (no API keys configured)")
        except Exception as e:
            self._error_count += 1
            logger.error(f"Email waterfall failed: {e}", extra={"phase": "waterfall"}, exc_info=True)
            print(f"  Email waterfall failed (continuing): {e}")

        # ── Lead scoring ──
        try:
            print("  Scoring leads...")
            self.all_leads = self.scorer.score_batch(self.all_leads)
        except Exception as e:
            self._error_count += 1
            logger.error(f"Lead scoring failed: {e}", extra={"phase": "scoring"}, exc_info=True)
            print(f"  Lead scoring failed (continuing): {e}")

        # ── Delta detection ──
        try:
            deltas = self.csv_writer.detect_deltas(self.all_leads)
        except Exception as e:
            logger.warning(f"Delta detection failed: {e}")
            deltas = []

        # ── Output ──
        if not self.args.dry_run:
            try:
                print("\n  Writing output...")
                self.csv_writer.write_master(self.all_leads)

                hot_count = sum(1 for lead in self.all_leads if lead.lead_score >= 80)
                await self.webhook.notify_hot_leads(self.all_leads)
                await self.webhook.notify_crawl_complete(
                    total=len(self.all_leads),
                    new=len(deltas),
                    hot=hot_count,
                )
            except Exception as e:
                self._error_count += 1
                logger.error(f"Output failed: {e}", extra={"phase": "output"}, exc_info=True)
                print(f"  Output failed: {e}")
        else:
            print("\n  DRY RUN — no files written")

        self.metrics.stage_end("enrichment", lead_count=len(self.all_leads), error_count=self._error_count)
        self._stages_completed.append("enrichment")

    async def _run_greyhat_enrichment(self):
        """
        Run all greyhat email enrichment modules in sequence.
        Each module has its own try/except so a single module failure
        doesn't abort the entire greyhat phase.
        """
        self.metrics.stage_start("greyhat")
        logger.info("Starting greyhat enrichment", extra={"phase": "greyhat"})
        print(f"\n{'='*60}")
        print("  GREYHAT ENRICHMENT")
        print(f"{'='*60}\n")

        missing_before = sum(
            1 for lead in self.all_leads
            if not lead.email or lead.email in ("N/A", "N/A (invalid)")
        )
        print(f"  {missing_before} leads still need emails — running greyhat modules...")

        greyhat_errors = 0

        # ── Phases 0-6: Run independent enrichers concurrently ──
        # Each enricher has its own rate limiting and targets different
        # external APIs, so running them in parallel is safe and ~5-7x faster.
        import copy

        async def _run_enricher(name, make_enricher, leads_snapshot, log_fn):
            """Run a single enricher on a snapshot; return enriched leads."""
            try:
                enricher = make_enricher()
                enriched = await enricher.enrich_batch(leads_snapshot)
                log_fn(enricher)
                return name, enriched, None
            except Exception as e:
                logger.error(f"{name} failed: {e}", extra={"phase": "greyhat", "stage": name})
                print(f"  {name} failed (continuing): {e}")
                return name, leads_snapshot, e

        # Snapshot leads so each enricher works independently
        leads_snapshot = copy.deepcopy(self.all_leads)

        def _log_dns(e):
            s = e.stats
            print(f"  DNS: {s['leads_enriched']} enriched, {s['emails_found']} emails found, {s['domains_queried']} domains queried")

        def _log_dorker(e):
            s = e.stats
            print(f"  Dorker: {s['leads_enriched']} enriched, {s['emails_found']} emails, {s['queries_made']} queries")

        def _log_gravatar(e):
            s = e.stats
            print(f"  Gravatar: {s['emails_confirmed']} confirmed out of {s['candidates_probed']} probes")

        def _log_pgp(e):
            s = e.stats
            print(f"  PGP: {s['leads_enriched']} enriched, {s['emails_extracted']} emails extracted ({s['keyservers_queried']} queries)")

        def _log_github(e):
            s = e.stats
            print(f"  GitHub: {s['leads_enriched']} enriched, {s['emails_found']} emails, {s['commits_inspected']} commits scanned")

        def _log_edgar(e):
            s = e.stats
            print(f"  EDGAR: {s['leads_enriched']} enriched, {s['emails_found']} emails, {s['domains_searched']} domains searched")

        def _log_wayback(e):
            s = e.stats
            print(f"  Wayback: {s['leads_enriched']} enriched, {s['emails_found']} emails, {s['snapshots_fetched']} snapshots fetched")

        print("  Running phases 0-6 concurrently...")
        enricher_tasks = [
            _run_enricher("dns", DNSHarvester, copy.deepcopy(leads_snapshot), _log_dns),
            _run_enricher("dorker", lambda: GoogleDorker(concurrency=settings.dorker_concurrency), copy.deepcopy(leads_snapshot), _log_dorker),
            _run_enricher("gravatar", lambda: GravatarOracle(concurrency=settings.gravatar_concurrency), copy.deepcopy(leads_snapshot), _log_gravatar),
            _run_enricher("pgp", lambda: PGPKeyserverScraper(concurrency=settings.greyhat_concurrency), copy.deepcopy(leads_snapshot), _log_pgp),
            _run_enricher("github", lambda: GitHubMiner(concurrency=settings.greyhat_concurrency), copy.deepcopy(leads_snapshot), _log_github),
            _run_enricher("edgar", SECEdgarScraper, copy.deepcopy(leads_snapshot), _log_edgar),
            _run_enricher("wayback", WaybackEnricher, copy.deepcopy(leads_snapshot), _log_wayback),
        ]

        enricher_results = await asyncio.gather(*enricher_tasks)

        # Merge results: for each lead, take the best email found across enrichers
        # Priority: any enricher that found an email for a lead that didn't have one
        for name, enriched_leads, err in enricher_results:
            if err:
                greyhat_errors += 1
                continue
            for i, lead in enumerate(enriched_leads):
                orig = self.all_leads[i]
                if (not orig.email or orig.email in ("N/A", "N/A (invalid)")) and \
                   lead.email and lead.email not in ("N/A", "N/A (invalid)"):
                    orig.email = lead.email
                    orig.email_status = lead.email_status
                # Also merge non-email enrichments (linkedin, role, etc.)
                if (not orig.linkedin or orig.linkedin in ("N/A", "")) and \
                   lead.linkedin and lead.linkedin not in ("N/A", ""):
                    orig.linkedin = lead.linkedin

        # ── Phase 7: Catch-All & JS Scraper (runs after others to skip already-found) ──
        try:
            print("  Phase 7: Catch-All Detection & JS Scraping...")
            catchall = CatchAllDetector(browser_timeout=settings.browser_timeout_ms)
            self.all_leads = await catchall.enrich_batch(self.all_leads)
            cs = catchall.stats
            print(f"  Catch-All/JS: {cs['leads_enriched_catchall']} catch-all enriched, "
                  f"{cs['leads_enriched_js']} JS-scraped "
                  f"({cs['catchall_domains']} catch-all domains detected)")
        except Exception as e:
            greyhat_errors += 1
            logger.error(f"Catch-all detection failed: {e}", extra={"phase": "greyhat", "stage": "catchall"})
            print(f"  Catch-all detection failed (continuing): {e}")

        # ── Summary ──
        self._error_count += greyhat_errors
        missing_after = sum(
            1 for lead in self.all_leads
            if not lead.email or lead.email in ("N/A", "N/A (invalid)")
        )
        recovered = missing_before - missing_after
        print(
            f"\n  Greyhat enrichment complete: "
            f"{recovered} emails recovered "
            f"({missing_before} -> {missing_after} missing)"
        )
        if greyhat_errors:
            print(f"  {greyhat_errors} module(s) encountered errors (see logs for details)")

        # Mark any newly-found emails not yet tagged
        for lead in self.all_leads:
            if lead.email_status == "unknown" and lead.email and lead.email not in ("N/A", "N/A (invalid)") and "@" in lead.email:
                lead.email_status = "greyhat"

        self.metrics.stage_end("greyhat", lead_count=recovered, error_count=greyhat_errors)


    def _print_banner(self):
        print()
        print("  +--------------------------------------------+")
        print("  |   CRAWL ENGINE v3                           |")
        print("  |   Investor Lead Machine                     |")
        print("  +--------------------------------------------+")
        print()
        print(f"  Run ID:   {self.run_id}")
        print(f"  Time:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Sites:    {self.args.site or 'ALL'}")
        print(f"  Stealth:  ON")
        print(f"  Proxy:    {'ON' if self.proxy_mgr.enabled else 'OFF'}")
        print(f"  Headless: {'YES' if self.args.headless else 'NO'}")
        print(f"  Metrics:  {'ON' if settings.metrics_enabled else 'OFF'}")
        print()

    def _print_summary(self, elapsed: float):
        print(f"\n{'='*60}")
        print("  CRAWL SUMMARY")
        print(f"{'='*60}")
        print(f"  Run ID:    {self.run_id}")
        print(f"  Duration:  {elapsed:.1f}s")
        print(f"  Total leads: {len(self.all_leads)}")
        print(f"  Errors:    {self._error_count}")
        print(f"  Stages:    {', '.join(self._stages_completed)}")

        if self.all_leads:
            # Email quality breakdown
            status_counts = {}
            for lead in self.all_leads:
                status_counts[lead.email_status] = status_counts.get(lead.email_status, 0) + 1
            usable = status_counts.get("verified", 0) + status_counts.get("catch_all", 0) + status_counts.get("scraped", 0)
            target = settings.target_lead_count
            print(f"\n  EMAIL QUALITY BREAKDOWN:")
            print(f"       Verified:      {status_counts.get('verified', 0)}")
            print(f"       Catch-all:     {status_counts.get('catch_all', 0)}")
            print(f"       Scraped:       {status_counts.get('scraped', 0)}")
            print(f"       Guessed:       {status_counts.get('guessed', 0)}")
            print(f"       Undeliverable: {status_counts.get('undeliverable', 0)}")
            print(f"       Unknown:       {status_counts.get('unknown', 0)}")
            print(f"       ---")
            print(f"       USABLE (verified+catch_all+scraped): {usable}")
            print(f"       TARGET: {target:,} | Progress: {100*usable//target if target else 0}%")

            scorer_stats = self.scorer.stats
            print(f"\n  Avg score: {scorer_stats.get('avg_score', 0)}")
            print(f"  HOT leads: {scorer_stats.get('hot_count', 0)}")
            print(f"  WARM leads: {scorer_stats.get('warm_count', 0)}")

        fp_stats = self.fingerprint_mgr.stats
        print(f"  Fingerprints used: {fp_stats['total_fingerprints_generated']}")
        print(f"  Proxy requests: {self.proxy_mgr.stats['total_requests_proxied']}")

        # Lead store stats
        store_stats = self.lead_store.stats
        print(f"  DB persistence: {store_stats['total_added']} added, "
              f"{store_stats['duplicates_skipped']} deduped (DB={'available' if store_stats['db_available'] else 'unavailable'})")
        print()

        # Top 5 leads preview
        if self.all_leads:
            print("  TOP 5 LEADS:")
            print(f"  {'_'*50}")
            for lead in self.all_leads[:5]:
                areas = ", ".join(lead.focus_areas[:2]) if lead.focus_areas else "N/A"
                print(f"  {lead.tier}  {lead.name} ({lead.fund})")
                print(f"       Email: {lead.email} | Focus: {areas}")
                print(f"       Check: {lead.check_size} | Score: {lead.lead_score}")
                print()

        # Log final structured progress line for monitoring
        self._log_progress("final")

        # Print metrics summary
        summary = self.metrics.run_summary()
        logger.info(
            "Pipeline run complete",
            extra={
                "run_id": self.run_id,
                "duration_s": round(elapsed, 2),
                "lead_count": len(self.all_leads),
                "error_count": self._error_count,
            },
        )


# ──────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="CRAWL — Investor Lead Machine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--site", type=str, default="",
        help="Crawl a specific site only (e.g. openvc, angelmatch)",
    )
    parser.add_argument(
        "--headless", action="store_true",
        help="Run browser in headless mode (no visible window)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Run crawl but don't write output files",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show detailed error tracebacks",
    )
    parser.add_argument(
        "--webhook", type=str, default="",
        help="Discord/Slack webhook URL for notifications",
    )
    parser.add_argument(
        "--webhook-platform", type=str, default="discord",
        choices=["discord", "slack"],
        help="Webhook platform (default: discord)",
    )
    parser.add_argument(
        "--discover", action="store_true",
        help="Run discovery engine first to find VC domains before crawling",
    )
    parser.add_argument(
        "--force-recrawl", action="store_true",
        help="Ignore seen_domains cache and re-crawl all targets",
    )
    parser.add_argument(
        "--deep", action="store_true",
        help="Run deep crawl on fund websites to extract individual team members",
    )
    parser.add_argument(
        "--skip-smtp", action="store_true",
        help="Skip SMTP deliverability checks on emails (faster but less accurate)",
    )
    parser.add_argument(
        "--skip-greyhat", action="store_true",
        help="Skip greyhat enrichment (Google Dorking, GitHub, SEC EDGAR, Wayback Machine)",
    )
    parser.add_argument(
        "--portfolio", action="store_true",
        help="Scrape portfolio pages from fund websites to extract portfolio companies",
    )
    parser.add_argument(
        "--incremental", action="store_true",
        help="Only crawl domains that haven't been visited within --stale-days (default 7)",
    )
    parser.add_argument(
        "--stale-days", type=int, default=settings.stale_days,
        help=f"Number of days before a domain is considered stale (default: {settings.stale_days})",
    )
    parser.add_argument(
        "--concurrency", type=int, default=settings.concurrency,
        help=f"Max concurrent browser instances for deep crawl (default: {settings.concurrency})",
    )
    parser.add_argument(
        "--smtp-concurrency", type=int, default=settings.smtp_concurrency,
        help=f"Max concurrent SMTP connections for email verification (default: {settings.smtp_concurrency})",
    )
    parser.add_argument(
        "--resume", type=str, default="",
        help="Resume from a checkpoint CSV (e.g. data/enriched/checkpoint_guesser.csv)",
    )
    parser.add_argument(
        "--scale", action="store_true",
        help="Scale mode: auto-enables --deep --discover --headless for maximum volume",
    )
    parser.add_argument(
        "--edgar", action="store_true",
        help="Pull Form D fund officers from SEC EDGAR at bulk scale (no API key required)",
    )
    parser.add_argument(
        "--edgar-years", nargs="+", type=int, default=None,
        metavar="YEAR",
        help="Calendar years to pull EDGAR Form D filings (default: 2016–2025)",
    )
    parser.add_argument(
        "--edgar-max", type=int, default=200000,
        help="Max Form D filings to process per EDGAR run (default: 200000)",
    )
    parser.add_argument(
        "--expand-emails", action="store_true",
        help="Expand each contact into one row per email pattern (up to 8x volume)",
    )
    parser.add_argument(
        "--log-format", type=str, default=settings.log_format,
        choices=["json", "text"],
        help=f"Log output format (default: {settings.log_format})",
    )
    parser.add_argument(
        "--log-file", type=str, default=settings.log_file,
        help="Log to file (in addition to stdout)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    # ── Configure structured logging ──
    log_level = "DEBUG" if args.verbose else settings.log_level
    configure_logging(
        level=log_level,
        fmt=args.log_format,
        log_file=args.log_file,
    )

    engine = CrawlEngine(args)

    # Resume from checkpoint: load leads from CSV and skip directly to enrichment
    if args.resume:
        engine.all_leads = _load_checkpoint(args.resume)
        if engine.all_leads:
            logger.info(f"Resumed {len(engine.all_leads)} leads from {args.resume}")
            await engine._enrich_and_output()
            elapsed = 0.0
            engine._print_summary(elapsed)
            return
        else:
            logger.error(f"Failed to load checkpoint from {args.resume}")
            return

    await engine.run()


def _load_checkpoint(path: str):
    """Load leads from a checkpoint CSV back into InvestorLead objects."""
    import csv as _csv
    from adapters.base import InvestorLead
    leads = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = _csv.DictReader(f)
            for row in reader:
                focus_raw = row.get("Focus Areas", "")
                focus_areas = [s.strip() for s in focus_raw.split(";") if s.strip()] if focus_raw and focus_raw != "N/A" else []
                lead = InvestorLead(
                    name=row.get("Name", ""),
                    email=row.get("Email", "N/A"),
                    role=row.get("Role", "N/A"),
                    fund=row.get("Fund", "N/A"),
                    focus_areas=focus_areas,
                    stage=row.get("Stage", "N/A"),
                    check_size=row.get("Check Size", "N/A"),
                    location=row.get("Location", "N/A"),
                    linkedin=row.get("LinkedIn", "N/A"),
                    website=row.get("Website", "N/A"),
                    source=row.get("Source", ""),
                    scraped_at=row.get("Scraped At", ""),
                    lead_score=int(row.get("Lead Score", 0) or 0),
                    tier=row.get("Tier", ""),
                    email_status=row.get("Email Status", "unknown"),
                )
                if lead.name:
                    leads.append(lead)
    except Exception as e:
        logger.error(f"Checkpoint load failed: {e}")
    return leads


if __name__ == "__main__":
    asyncio.run(main())
