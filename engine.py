"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   🕷️  CRAWL ENGINE v2 — Investor Lead Machine                ║
║                                                              ║
║   Config-driven, multi-site crawler with stealth,            ║
║   enrichment, scoring, and automated output.                 ║
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
from urllib.parse import urlparse
from pathlib import Path
from datetime import datetime

import yaml
from playwright.async_api import async_playwright

# ── Structured logging for progress tracking toward 30k target ──
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger("crawl")

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
from enrichment.dedup import LeadDeduplicator  # fix: was used at line 470 but never imported
from enrichment.email_waterfall import EmailWaterfall  # fix: was used at line 564 but never imported


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
    """

    def __init__(self, args):
        self.args = args
        self.config = self._load_config("config/sites.yaml")
        self.adapter_registry = get_registry()
        self.fingerprint_mgr = FingerprintManager()
        self.behavior = HumanBehavior(speed_factor=1.0)
        self.proxy_mgr = ProxyManager("config/proxies.yaml")
        self.email_validator = EmailValidator()
        self.email_guesser = EmailGuesser(concurrency=10)
        self.scorer = LeadScorer("config/scoring.yaml")
        self.csv_writer = CSVWriter("data")
        self.webhook = WebhookNotifier(
            webhook_url=args.webhook or "",
            platform=args.webhook_platform or "discord",
        )
        self.all_leads = []
        self.crawl_state = CrawlStateManager(
            stale_days=getattr(args, 'stale_days', 7)
        )

    def _load_config(self, path: str) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    async def _run_discovery(self):
        """Run multi-engine discovery and save results to data/target_funds.txt."""
        print("\n  🔍  DISCOVERY MODE — finding VC domains via multi-engine search...")
        import yaml
        with open("config/search.yaml") as f:
            search_config = yaml.safe_load(f).get("discovery", {})

        queries = search_config.get("queries", [])
        target_count = search_config.get("target_domains_count", 2000)
        ignore = set(search_config.get("ignore_domains", []))
        engine_config = search_config.get("engines", {})

        # Use multi-engine discovery if engines are configured, otherwise fallback
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
        print(f"  ✅  Discovery complete: {len(domains)} domains → {target_file}")
        return domains

    async def _run_aggregator(self):
        """Run the Source Aggregator to collect leads from deterministic sources."""
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

        print(f"  📡  Aggregator added {new_count} new leads to pipeline")
        return leads

    async def _run_deep_crawl(self):
        """Run deep crawl on fund websites to extract individual team members."""
        print(f"\n{'='*60}")
        print("  🔬  DEEP CRAWL — extracting team members from fund websites")
        print(f"{'='*60}\n")

        # ── Incremental: load crawl state and filter stale domains ──
        incremental = getattr(self.args, 'incremental', False)
        if incremental:
            await self.crawl_state.load_from_db()
            summary = self.crawl_state.summary()
            print(f"  📅  Incremental mode: {summary['stale_domains']}/{summary['total_domains']} domains stale "
                  f"(>{self.crawl_state.stale_days}d threshold)")

        crawler = DeepCrawler(
            target_file="data/target_funds.txt",
            output_file="data/vc_contacts.csv",
            max_concurrent=getattr(self.args, 'concurrency', 10),  # CLI-tunable concurrency
            headless=getattr(self.args, 'headless', True),
            skip_enrichment=True,  # engine handles enrichment for ALL leads together
            stale_days=getattr(self.args, 'stale_days', 7),
        )

        # Pass force_recrawl if set
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
                print(f"  ⏭️  Skipping {len(fresh_urls)} fresh domains, crawling {len(stale_urls)} stale")
                # Write filtered list to temp file for the crawler
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
                # Inherit fund metadata from seed/aggregator data
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

        print(f"\n  🔬  Deep crawl added {new_count} team member leads to pipeline")
        print(f"  🧬  Enriched {enriched_count}/{new_count} contacts with fund metadata")
        print(f"  📊  Total leads now: {len(self.all_leads)}")

        # ── Record crawl state for incremental tracking ──
        if incremental:
            # Group new contacts by domain to record per-domain stats
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
            print(f"  📈  Updated crawl state for {len(batch)} domains")

    async def _run_portfolio_scrape(self):
        """Scrape portfolio pages from fund websites and persist to database."""
        print(f"\n{'='*60}")
        print("  📂  PORTFOLIO SCRAPE — extracting portfolio companies")
        print(f"{'='*60}\n")

        # Load fund URLs from target_funds.txt
        target_file = Path("data/target_funds.txt")
        if not target_file.exists():
            print("  ⚠️  No target_funds.txt found — run aggregator or discovery first")
            return

        fund_urls = [
            line.strip() for line in target_file.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

        if not fund_urls:
            print("  ⚠️  No fund URLs in target_funds.txt")
            return

        scraper = PortfolioScraper(
            max_concurrent=10,
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
                    print(f"  💾  Persisted {inserted} new portfolio companies to database")
            except Exception as e:
                print(f"  ❌  Failed to persist portfolio data: {e}")

        print(f"  📊  Total portfolio companies: {len(companies)}")

    async def run(self):
        """Execute the full crawl pipeline."""
        start_time = time.time()

        # --scale mode: automatically enables deep crawl + discovery for max volume
        if getattr(self.args, 'scale', False):
            self.args.deep = True
            self.args.discover = True
            self.args.headless = True
            logger.info("SCALE MODE: auto-enabling --deep --discover --headless")

        self._print_banner()

        # Always run the Source Aggregator for deterministic lead volume
        if not self.args.site:  # skip aggregator when targeting a single site
            await self._run_aggregator()

        if self.args.discover:
            await self._run_discovery()

        sites = self.config.get("sites", {})
        defaults = self.config.get("defaults", {})

        # Filter to specific site if requested
        if self.args.site:
            if self.args.site not in sites:
                print(f"\n  ❌  Site '{self.args.site}' not found in config.")
                print(f"  Available: {', '.join(sites.keys())}")
                return
            sites = {self.args.site: sites[self.args.site]}

        # Build list of crawl tasks, then run concurrently for throughput
        async with async_playwright() as p:
            crawl_tasks = []
            for site_name, site_config in sites.items():
                if not site_config.get("enabled", True):
                    print(f"\n  ⏭️  Skipping {site_name} (disabled)")
                    continue

                adapter_name = site_config.get("adapter", "")
                adapter_class = self.adapter_registry.get(adapter_name)

                if not adapter_class:
                    print(f"\n  ⚠️  No adapter found for '{adapter_name}', skipping {site_name}")
                    continue

                crawl_tasks.append(
                    self._crawl_site_safe(p, site_name, site_config, adapter_class, defaults)
                )

            # Run all enabled sites concurrently (each gets its own browser)
            if crawl_tasks:
                results = await asyncio.gather(*crawl_tasks)
                for leads in results:
                    self.all_leads.extend(leads)

        # ── Deep crawl: extract team members from fund websites ──
        if getattr(self.args, 'deep', False):
            await self._run_deep_crawl()

        # ── Portfolio scrape: extract portfolio companies ──
        if getattr(self.args, 'portfolio', False):
            await self._run_portfolio_scrape()

        # ── Post-crawl pipeline ──
        if self.all_leads:
            await self._enrich_and_output()
        else:
            print("\n  ⚠️  No leads collected. Check your site configs and selectors.")

        # ── Stats ──
        elapsed = time.time() - start_time
        self._print_summary(elapsed)

    async def _crawl_site_safe(self, playwright, site_name, site_config, adapter_class, defaults):
        """Wrapper that catches per-site errors so one failure doesn't kill the batch."""
        try:
            return await self._crawl_site(playwright, site_name, site_config, adapter_class, defaults)
        except Exception as e:
            logger.error(f"Error crawling {site_name}: {e}")
            if self.args.verbose:
                import traceback
                traceback.print_exc()
            return []

    async def _crawl_site(self, playwright, site_name, site_config, adapter_class, defaults):
        """Crawl a single site with a fresh browser context."""
        print(f"\n  🌐  Initializing browser for {site_name}...")

        # Generate a fresh fingerprint for this site
        fingerprint = self.fingerprint_mgr.generate()
        context_kwargs = self.fingerprint_mgr.get_context_kwargs(fingerprint)

        # Check for proxy
        proxy = self.proxy_mgr.get_proxy(site_name)

        # Determine headless mode
        headless = self.args.headless or defaults.get("headless", False)

        # Launch browser
        browser = await playwright.chromium.launch(headless=headless)
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
            ss_dir = Path(defaults.get("screenshot_dir", "data/screenshots"))
            ss_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            await page.screenshot(
                path=str(ss_dir / f"{site_name}_{timestamp}.png"),
                full_page=True,
            )
            print("  📸  Screenshot saved")

        await browser.close()
        return leads

    def _checkpoint(self, phase_name: str):
        """Save leads to a checkpoint file after each enrichment phase."""
        self.csv_writer.write(
            self.all_leads,
            f"checkpoint_{phase_name}.csv",
            enriched=True,
        )
        self._log_progress(phase_name)

    def _log_progress(self, phase: str):
        """Log structured progress counters toward 30k target."""
        total = len(self.all_leads)
        with_email = sum(1 for lead in self.all_leads if lead.email and lead.email != "N/A" and "@" in lead.email)
        verified = sum(1 for lead in self.all_leads if lead.email_status == "verified")
        logger.info(
            f"[PROGRESS] phase={phase} total_leads={total} with_email={with_email} "
            f"verified={verified} target=30000 completion={100*with_email//30000}%"
        )

    async def _enrich_and_output(self):
        """Run enrichment and output pipeline on collected leads."""
        print(f"\n{'='*60}")
        print("  🧠  ENRICHMENT PIPELINE")
        print(f"{'='*60}\n")

        # ── Filter fund-level rows FIRST (name == fund name → not a person) ──
        before_filter = len(self.all_leads)
        self.all_leads = [
            lead for lead in self.all_leads
            if lead.name.lower().strip() != lead.fund.lower().strip()
        ]
        filtered_out = before_filter - len(self.all_leads)
        if filtered_out:
            print(f"  🚫  Filtered {filtered_out} fund-level rows (name == fund name)")
        print(f"  👤  {len(self.all_leads)} person-level leads remaining")

        # ── Cross-run deduplication ──
        dedup = LeadDeduplicator()
        self.all_leads = dedup.deduplicate(self.all_leads)
        self._checkpoint("dedup")

        # ── Email validation (with MX verification) ──
        print(f"  📧  Validating {len(self.all_leads)} emails (+ MX check)...")
        emails = [lead.email for lead in self.all_leads]
        results = await self.email_validator.validate_batch(emails)
        for lead, result in zip(self.all_leads, results):
            if result["quality"] == "invalid":
                lead.email = "N/A"
            elif not result.get("has_mx", True):
                lead.email = "N/A"
            elif result["is_disposable"]:
                lead.email = "N/A"

        # ── Mark scraped emails ──
        pre_existing = 0
        for lead in self.all_leads:
            if lead.email and lead.email != "N/A" and "@" in lead.email:
                lead.email_status = "scraped"
                pre_existing += 1
        print(f"  📨  Pre-existing emails (scraped from pages): {pre_existing}")
        self._checkpoint("validation")

        # ── Email guessing (for leads still missing an email) ──
        print("  ✉️  Guessing emails for contacts without one...")
        self.all_leads = await self.email_guesser.guess_batch(self.all_leads)
        gs = self.email_guesser.stats
        print(f"  ✉️  Guesser: {gs['found']} found / {gs['attempted']} domains checked")
        if gs.get("pattern_hits", 0):
            print(f"  🔑  Pattern hits: {gs['pattern_hits']} (from learned patterns)")
        if gs.get("default_hits", 0):
            print(f"  📐  Default pattern (first.last@domain): {gs['default_hits']}")
        if gs.get("mx_rejects", 0):
            print(f"  🚫  Domains without MX records: {gs['mx_rejects']}")
        if gs.get("company_skipped", 0):
            print(f"  🏢  Company/fund names skipped: {gs['company_skipped']}")

        # Mark guessed emails (those that weren't already scraped)
        for lead in self.all_leads:
            if lead.email_status == "unknown" and lead.email and lead.email != "N/A" and "@" in lead.email:
                lead.email_status = "guessed"

        # Total email summary (post-guesser)
        total_emails = sum(
            1 for lead in self.all_leads
            if lead.email and lead.email != "N/A" and "@" in lead.email
        )
        print(f"  📧  TOTAL emails: {total_emails}/{len(self.all_leads)} ({100*total_emails//len(self.all_leads) if self.all_leads else 0}%)")
        self._checkpoint("guesser")

        # ── Greyhat enrichment (Google Dorking, GitHub, SEC EDGAR, Wayback) ──
        if not getattr(self.args, 'skip_greyhat', False):
            await self._run_greyhat_enrichment()
            self._checkpoint("greyhat")
        else:
            print("  ⏭️  Greyhat enrichment skipped (--skip-greyhat)")

        # ── SMTP batch verification (on by default, skip with --skip-smtp) ──
        if not getattr(self.args, 'skip_smtp', False):
            smtp_candidates = [
                lead for lead in self.all_leads
                if lead.email and lead.email != "N/A" and "@" in lead.email
            ]
            if smtp_candidates:
                print(f"  📬  SMTP verification on {len(smtp_candidates)} emails...")
                email_list = [lead.email for lead in smtp_candidates]
                smtp_results = await self.email_validator.verify_smtp_batch(
                    email_list,
                    concurrency=getattr(self.args, 'smtp_concurrency', 20),
                )

                # Update email_status based on SMTP results
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
                        # deliverable is None — indeterminate
                        unknown += 1

                print(f"  📬  SMTP summary: {verified} verified, {undeliverable} undeliverable, "
                      f"{catch_all} catch-all, {unknown} unknown")
            self._checkpoint("smtp")
        else:
            print("  ⏭️  SMTP verification skipped (--skip-smtp)")

        # ── Email waterfall verification (for inconclusive emails) ──
        waterfall = EmailWaterfall()
        if waterfall.providers:
            self.all_leads = await waterfall.verify_batch(self.all_leads)
            self._checkpoint("waterfall")
        else:
            print("  ⏭️  Email waterfall skipped (no API keys configured)")

        # ── Lead scoring ──
        print("  📊  Scoring leads...")
        self.all_leads = self.scorer.score_batch(self.all_leads)

        # ── Delta detection ──
        deltas = self.csv_writer.detect_deltas(self.all_leads)

        # ── Output ──
        if not self.args.dry_run:
            print("\n  💾  Writing output...")
            self.csv_writer.write_master(self.all_leads)

            # Webhook notifications
            hot_count = sum(1 for lead in self.all_leads if lead.lead_score >= 80)
            await self.webhook.notify_hot_leads(self.all_leads)
            await self.webhook.notify_crawl_complete(
                total=len(self.all_leads),
                new=len(deltas),
                hot=hot_count,
            )
        else:
            print("\n  🧪  DRY RUN — no files written")

    async def _run_greyhat_enrichment(self):
        """
        Run all greyhat email enrichment modules in sequence:
          1. Google Dorking  — leaked emails on third-party pages
          2. GitHub Miner    — commit author emails
          3. SEC EDGAR       — regulatory filing emails
          4. Wayback Machine — archived fund team pages
        Each module only touches leads that still have no email.
        """
        print(f"\n{'='*60}")
        print("  🕵️  GREYHAT ENRICHMENT")
        print(f"{'='*60}\n")

        missing_before = sum(
            1 for lead in self.all_leads
            if not lead.email or lead.email in ("N/A", "N/A (invalid)")
        )
        print(f"  ℹ️  {missing_before} leads still need emails — running greyhat modules...")

        # ── 0. DNS Harvester ───────────────────────────────────────────────
        print("  🗄️  Phase 0: DNS Record Harvesting...")
        dns_harvester = DNSHarvester()
        self.all_leads = await dns_harvester.enrich_batch(self.all_leads)
        dns_stats = dns_harvester.stats
        print(
            f"  🗄️  DNS: {dns_stats['leads_enriched']} enriched, "
            f"{dns_stats['emails_found']} emails found, "
            f"{dns_stats['domains_queried']} domains queried"
        )
        
        # ── 1. Google Dorking ──────────────────────────────────────────────
        print("  🔍  Phase 1: Google Dorking...")
        dorker = GoogleDorker(concurrency=3)
        self.all_leads = await dorker.enrich_batch(self.all_leads)
        gs = dorker.stats
        print(
            f"  🔍  Dorker: {gs['leads_enriched']} enriched, "
            f"{gs['emails_found']} emails, "
            f"{gs['queries_made']} queries"
        )

        # ── 2. Gravatar Oracle ──────────────────────────────────────────────
        print("  👻  Phase 2: Gravatar Email Confirmation...")
        gravatar = GravatarOracle(concurrency=50)
        self.all_leads = await gravatar.enrich_batch(self.all_leads)
        grav_s = gravatar.stats
        print(
            f"  👻  Gravatar: {grav_s['emails_confirmed']} confirmed "
            f"out of {grav_s['candidates_probed']} probes"
        )

        # ── 3. PGP Keyserver Scraping ──────────────────────────────────────
        print("  🔑  Phase 3: PGP Keyserver Search...")
        pgp = PGPKeyserverScraper(concurrency=10)
        self.all_leads = await pgp.enrich_batch(self.all_leads)
        pgp_s = pgp.stats
        print(
            f"  🔑  PGP: {pgp_s['leads_enriched']} enriched, "
            f"{pgp_s['emails_extracted']} emails extracted "
            f"({pgp_s['keyservers_queried']} queries)"
        )

        # ── 4. GitHub Commit Mining ────────────────────────────────────────
        print("  🐙  Phase 4: GitHub Commit Mining...")
        miner = GitHubMiner(concurrency=10)
        self.all_leads = await miner.enrich_batch(self.all_leads)
        ghs = miner.stats
        print(
            f"  🐙  GitHub: {ghs['leads_enriched']} enriched, "
            f"{ghs['emails_found']} emails, "
            f"{ghs['commits_inspected']} commits scanned"
        )

        # ── 5. SEC EDGAR ───────────────────────────────────────────────────
        print("  📋  Phase 5: SEC EDGAR Filings...")
        edgar = SECEdgarScraper()
        self.all_leads = await edgar.enrich_batch(self.all_leads)
        es = edgar.stats
        print(
            f"  📋  EDGAR: {es['leads_enriched']} enriched, "
            f"{es['emails_found']} emails, "
            f"{es['domains_searched']} domains searched"
        )

        # ── 6. Wayback Machine ─────────────────────────────────────────────
        print("  🕰️  Phase 6: Wayback Machine Snapshots...")
        wayback = WaybackEnricher()
        self.all_leads = await wayback.enrich_batch(self.all_leads)
        ws = wayback.stats
        print(
            f"  🕰️  Wayback: {ws['leads_enriched']} enriched, "
            f"{ws['emails_found']} emails, "
            f"{ws['snapshots_fetched']} snapshots fetched"
        )

        # ── 7. Catch-All & JS Scraper ──────────────────────────────────────
        print("  🛑  Phase 7: Catch-All Detection & JS Scraping...")
        # Note: Set browser timeout lower than default for engine speed
        catchall = CatchAllDetector(browser_timeout=15000)
        self.all_leads = await catchall.enrich_batch(self.all_leads)
        cs = catchall.stats
        print(
            f"  🛑  Catch-All/JS: {cs['leads_enriched_catchall']} catch-all enriched, "
            f"{cs['leads_enriched_js']} JS-scraped "
            f"({cs['catchall_domains']} catch-all domains detected)"
        )

        # ── Summary ────────────────────────────────────────────────────────
        missing_after = sum(
            1 for lead in self.all_leads
            if not lead.email or lead.email in ("N/A", "N/A (invalid)")
        )
        recovered = missing_before - missing_after
        print(
            f"\n  ✅  Greyhat enrichment complete: "
            f"{recovered} emails recovered "
            f"({missing_before} → {missing_after} missing)"
        )
        # Mark any newly-found emails not yet tagged
        for lead in self.all_leads:
            if lead.email_status == "unknown" and lead.email and lead.email not in ("N/A", "N/A (invalid)") and "@" in lead.email:
                lead.email_status = "greyhat"


    def _print_banner(self):
        print()
        print("  ╔══════════════════════════════════════════╗")
        print("  ║   🕷️  CRAWL ENGINE v2                    ║")
        print("  ║   Investor Lead Machine                  ║")
        print("  ╚══════════════════════════════════════════╝")
        print()
        print(f"  ⏰  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  🎯  Sites: {self.args.site or 'ALL'}")
        print(f"  👻  Stealth: ON")
        print(f"  🔒  Proxy: {'ON' if self.proxy_mgr.enabled else 'OFF'}")
        print(f"  🖥️  Headless: {'YES' if self.args.headless else 'NO'}")
        print()

    def _print_summary(self, elapsed: float):
        print(f"\n{'='*60}")
        print("  📊  CRAWL SUMMARY")
        print(f"{'='*60}")
        print(f"  ⏱️  Duration: {elapsed:.1f}s")
        print(f"  📝  Total leads: {len(self.all_leads)}")

        if self.all_leads:
            # Email quality breakdown — actionable metrics toward 30k target
            status_counts = {}
            for lead in self.all_leads:
                status_counts[lead.email_status] = status_counts.get(lead.email_status, 0) + 1
            usable = status_counts.get("verified", 0) + status_counts.get("catch_all", 0) + status_counts.get("scraped", 0)
            print(f"\n  📧  EMAIL QUALITY BREAKDOWN:")
            print(f"       Verified:      {status_counts.get('verified', 0)}")
            print(f"       Catch-all:     {status_counts.get('catch_all', 0)}")
            print(f"       Scraped:       {status_counts.get('scraped', 0)}")
            print(f"       Guessed:       {status_counts.get('guessed', 0)}")
            print(f"       Undeliverable: {status_counts.get('undeliverable', 0)}")
            print(f"       Unknown:       {status_counts.get('unknown', 0)}")
            print(f"       ─────────────────────────")
            print(f"       USABLE (verified+catch_all+scraped): {usable}")
            print(f"       TARGET: 30,000 | Progress: {100*usable//30000}%")

            scorer_stats = self.scorer.stats
            print(f"\n  📈  Avg score: {scorer_stats.get('avg_score', 0)}")
            print(f"  🔴  HOT leads: {scorer_stats.get('hot_count', 0)}")
            print(f"  🟡  WARM leads: {scorer_stats.get('warm_count', 0)}")

        fp_stats = self.fingerprint_mgr.stats
        print(f"  🎭  Fingerprints used: {fp_stats['total_fingerprints_generated']}")
        print(f"  🔒  Proxy requests: {self.proxy_mgr.stats['total_requests_proxied']}")
        print()

        # Top 5 leads preview
        if self.all_leads:
            print("  🏆  TOP 5 LEADS:")
            print(f"  {'─'*50}")
            for lead in self.all_leads[:5]:
                areas = ", ".join(lead.focus_areas[:2]) if lead.focus_areas else "N/A"
                print(f"  {lead.tier}  {lead.name} ({lead.fund})")
                print(f"       📧 {lead.email} | 🎯 {areas}")
                print(f"       💰 {lead.check_size} | Score: {lead.lead_score}")
                print()

        # Log final structured progress line for monitoring
        self._log_progress("final")


# ──────────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="🕷️ CRAWL — Investor Lead Machine",
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
        "--stale-days", type=int, default=7,
        help="Number of days before a domain is considered stale (default: 7)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=10,
        help="Max concurrent browser instances for deep crawl (default: 10)",
    )
    parser.add_argument(
        "--smtp-concurrency", type=int, default=20,
        help="Max concurrent SMTP connections for email verification (default: 20)",
    )
    parser.add_argument(
        "--resume", type=str, default="",
        help="Resume from a checkpoint CSV (e.g. data/enriched/checkpoint_guesser.csv)",
    )
    parser.add_argument(
        "--scale", action="store_true",
        help="Scale mode: auto-enables --deep --discover --headless for maximum volume toward 30k",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
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
