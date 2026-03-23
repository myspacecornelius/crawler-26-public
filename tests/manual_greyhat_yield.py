#!/usr/bin/env python3
"""
Greyhat Enrichment Yield Test
Tests each module against a real set of VC domains and measures email discovery.
Run from project root with: venv/bin/python test_greyhat_yield.py
"""
import asyncio
import sys
import time

# ── Test targets: mix of well-known and mid-tier VC firms ─────────────
TEST_DOMAINS = [
    "sequoiacap.com",
    "a16z.com",
    "accel.com",
    "bvp.com",          # Bessemer
    "firstround.com",
    "usv.com",          # Union Square Ventures
    "ycombinator.com",
]

# ── Stub lead objects ─────────────────────────────────────────────────
class FakeLead:
    def __init__(self, name, domain):
        self.name = name
        self.fund = domain
        self.website = f"https://{domain}"
        self.email = "N/A"
        self.email_status = "unknown"
        self.location = "N/A"
        self.focus_areas = []
        self.stage = "N/A"
        self.check_size = "N/A"
        self.lead_score = 0
        self.tier = "🟡"

# One generic lead per domain (simulates leads without emails)
def make_leads():
    return [
        FakeLead("John Smith", "sequoiacap.com"),
        FakeLead("Roelof Botha", "sequoiacap.com"),
        FakeLead("Marc Andreessen", "a16z.com"),
        FakeLead("Ben Horowitz", "a16z.com"),
        FakeLead("Sonali De Rycker", "accel.com"),
        FakeLead("David Cowan", "bvp.com"),
        FakeLead("Josh Kopelman", "firstround.com"),
        FakeLead("Fred Wilson", "usv.com"),
        FakeLead("Paul Graham", "ycombinator.com"),
    ]


async def test_module(name, enricher, leads):
    t0 = time.time()
    result = await enricher.enrich_batch(leads)
    elapsed = time.time() - t0
    found = [l for l in result if l.email not in ("N/A", "N/A (invalid)", "") and "@" in l.email]
    return found, elapsed


async def main():
    print("=" * 60)
    print("  GREYHAT ENRICHMENT YIELD TEST")
    print("=" * 60)
    print(f"  Domains:  {', '.join(TEST_DOMAINS)}")
    print(f"  Leads:    9 (mix of named partners per fund)\n")

    results = {}

    # ── Module 0: DNS Harvester ─────────────────────────────────────────
    # Zero cost, instant, run absolutely first
    print("── DNS Harvester ─────────────────────────────────────────────")
    from enrichment.dns_harvester import DNSHarvester
    leads = make_leads()
    found, t = await test_module("DNS Harvester", DNSHarvester(concurrency=10), leads)
    results["DNS Harvester"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")

    # ── Module 1: Google Dorker ────────────────────────────────────────
    print("── Google Dorker ─────────────────────────────────────────────")
    from enrichment.google_dorker import GoogleDorker
    leads = make_leads()
    dns_found = {l.name: l for l in results["DNS Harvester"][0]}
    for l in leads:
        if l.name in dns_found:
            l.email = dns_found[l.name].email
            l.email_status = "dns_harvest"
    found, t = await test_module("Google", GoogleDorker(concurrency=2), leads)
    results["Google Dorker"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")

    # ── Module 2: Gravatar Oracle ──────────────────────────────────────
    print("── Gravatar Oracle ───────────────────────────────────────────")
    from enrichment.gravatar_oracle import GravatarOracle
    leads = make_leads()
    google_found = {l.name: l for l in results["Google Dorker"][0]}
    for l in leads:
        if l.name in google_found:
            l.email = google_found[l.name].email
            l.email_status = "google"
    found, t = await test_module("Gravatar", GravatarOracle(concurrency=50), leads)
    results["Gravatar"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")

    # ── Module 3: PGP Keyserver ────────────────────────────────────────
    print("── PGP Keyserver ─────────────────────────────────────────────")
    from enrichment.pgp_keyserver import PGPKeyserverScraper
    leads = make_leads()
    grav_found = {l.name: l for l in results["Gravatar"][0]}
    for l in leads:
        if l.name in grav_found:
            l.email = grav_found[l.name].email
            l.email_status = "gravatar"
    found, t = await test_module("PGP", PGPKeyserverScraper(concurrency=10), leads)
    results["PGP Keyserver"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")

    # ── Module 4: SEC EDGAR ────────────────────────────────────────────
    # Fastest / most polite, run first
    print("── SEC EDGAR ─────────────────────────────────────────────────")
    from enrichment.sec_edgar import SECEdgarScraper
    leads = make_leads()
    # Carry over PGP hits
    pgp_found = {l.name: l for l in results["PGP Keyserver"][0]}
    for l in leads:
        if l.name in pgp_found:
            l.email = pgp_found[l.name].email
            l.email_status = "pgp"
    found, t = await test_module("SEC EDGAR", SECEdgarScraper(), leads)
    results["SEC EDGAR"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")

    # ── Module 5: GitHub Miner ─────────────────────────────────────────
    print("── GitHub Miner ──────────────────────────────────────────────")
    from enrichment.github_miner import GitHubMiner
    leads = make_leads()
    edgar_found = {l.name: l for l in results["SEC EDGAR"][0]}
    for l in leads:
        if l.name in edgar_found:
            l.email = edgar_found[l.name].email
            l.email_status = "sec_edgar"
    found, t = await test_module("GitHub", GitHubMiner(concurrency=5), leads)
    results["GitHub"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")

    # ── Module 6: Wayback Machine ──────────────────────────────────────
    print("── Wayback Machine ───────────────────────────────────────────")
    from enrichment.wayback_enricher import WaybackEnricher
    leads = make_leads()
    # Carry over GitHub hits
    gh_found = {l.name: l for l in results["GitHub"][0]}
    for l in leads:
        if l.name in gh_found:
            l.email = gh_found[l.name].email
            l.email_status = "github"
    found, t = await test_module("Wayback", WaybackEnricher(), leads)
    results["Wayback"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")
    
    # Save wayback state for next module
    wayback_found = {l.name: l for l in results["Wayback"][0]}

    # ── Module 7: Google Dorker ────────────────────────────────────────
    # Note: may get rate-limited without SERPAPI_KEY — run last
    print("── Google Dorker (2nd pass) ──────────────────────────────────")
    from enrichment.google_dorker import GoogleDorker as GD2
    leads = make_leads()
    for l in leads:
        if l.name in wayback_found:
            l.email = wayback_found[l.name].email
            l.email_status = "wayback"
    found, t = await test_module("Google2", GD2(concurrency=2), leads)
    results["Google 2nd"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")

    # ── Module 8: Catch-All + JS Scraper ───────────────────────────────
    print("── Catch-All + JS Scraper ────────────────────────────────────")
    from enrichment.catchall_detector import CatchAllDetector
    # We want to specifically test domains we know are sticky
    leads = make_leads()
    # Carry over previous
    google_found = {l.name: l for l in results["Google Dorker"][0]}
    for l in leads:
        if l.name in google_found:
            l.email = google_found[l.name].email
            l.email_status = "google"
            
    found, t = await test_module("CatchAll/JS", CatchAllDetector(), leads)
    results["CatchAll/JS"] = (found, t)
    for l in found:
        print(f"  ✅  {l.name:30s}  {l.email}")
    print(f"  → {len(found)}/9 emails in {t:.1f}s\n")

    # ── Summary ────────────────────────────────────────────────────────
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    total_unique = set()
    for module, (found, t) in results.items():
        for l in found:
            total_unique.add(l.email)
        print(f"  {module:20s}  {len(found):2d}/9   ({t:.1f}s)")
    print(f"\n  Combined unique emails: {len(total_unique)}/9")
    print(f"  Baseline (no greyhat):  0/9")
    print(f"  Lift:                  +{len(total_unique)}")


if __name__ == "__main__":
    asyncio.run(main())
