"""
CRAWL — Seed Database Expander
Expands vc_firms.csv from ~600 to 2000+ funds by aggregating multiple sources:
  1. Existing seed CSV
  2. Existing checkpoint CSV (mined for fund URLs)
  3. GitHub "awesome-vc" lists (HTTP fetch + parse)
  4. OpenVC directory scrape (HTTP-based)
  5. Programmatic web scraping of public VC directories

Usage:
    python scripts/expand_seed.py               # dry-run: print stats only
    python scripts/expand_seed.py --write        # write expanded seed
    python scripts/expand_seed.py --write --backup  # backup original first
"""

import asyncio
import csv
import re
import sys
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────
SEED_CSV = Path("data/seed/vc_firms.csv")
CHECKPOINT_CSV = Path("data/vc_contacts_checkpoint.csv")
PE_CSV = Path("data/seed/pe_firms.csv")
FAMILY_CSV = Path("data/seed/family_offices.csv")
CORP_CSV = Path("data/seed/corp_dev.csv")
EXPANDED_CSV = Path("data/seed/vc_firms.csv")

# ── Fund entry type ──────────────────────────────
class FundEntry:
    def __init__(self, name: str, website: str, stage: str = "N/A",
                 focus_areas: str = "", location: str = "N/A",
                 check_size: str = "", source: str = ""):
        self.name = name.strip()
        self.website = website.strip()
        self.stage = stage.strip() if stage else "N/A"
        self.focus_areas = focus_areas.strip() if focus_areas else ""
        self.location = location.strip() if location else "N/A"
        self.check_size = check_size.strip() if check_size else ""
        self.source = source

    @property
    def domain(self) -> str:
        try:
            d = urlparse(self.website).netloc.lower().replace("www.", "")
            return d
        except Exception:
            return ""

    def to_row(self) -> dict:
        return {
            "name": self.name,
            "website": self.website,
            "stage": self.stage,
            "focus_areas": self.focus_areas,
            "location": self.location,
            "check_size": self.check_size,
        }


# ── Domain normalization & dedup ──────────────────
REJECT_DOMAINS = {
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "crunchbase.com", "angellist.com", "angel.co", "pitchbook.com",
    "dealroom.co", "techcrunch.com", "medium.com", "substack.com",
    "forbes.com", "bloomberg.com", "wikipedia.org", "youtube.com",
    "google.com", "github.com", "wellfound.com", "tracxn.com",
    "cbinsights.com", "sec.gov", "wsj.com", "ft.com", "reuters.com",
    "nytimes.com", "ycombinator.com", "techstars.com", "500.co",
    "openvc.app", "angelmatch.io", "signal.nfx.com", "vcstack.io",
    "amazon.com", "apple.com", "microsoft.com", "cisco.com",
    "shopify.com", "stripe.com", "paypal.com", "zoom.us",
    "slack.com", "notion.so", "figma.com", "vercel.com",
    "netlify.com", "heroku.com", "digitalocean.com",
}

def _normalize_domain(url: str) -> str:
    """Get clean domain from URL."""
    try:
        if not url.startswith("http"):
            url = "https://" + url
        d = urlparse(url).netloc.lower().replace("www.", "")
        return d
    except Exception:
        return ""

def _is_valid_vc_url(url: str) -> bool:
    """Check if URL looks like a real VC fund site."""
    domain = _normalize_domain(url)
    if not domain or len(domain) < 4:
        return False
    if any(domain.endswith(f".{r}") or domain == r for r in REJECT_DOMAINS):
        return False
    if domain in REJECT_DOMAINS:
        return False
    # Must have a TLD
    if "." not in domain:
        return False
    return True


# ══════════════════════════════════════════════════
#  Source 1: Existing Seed CSV
# ══════════════════════════════════════════════════
def load_existing_seed() -> List[FundEntry]:
    """Load current vc_firms.csv."""
    entries = []
    if not SEED_CSV.exists():
        return entries
    with open(SEED_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            website = (row.get("website") or "").strip()
            if name and website:
                entries.append(FundEntry(
                    name=name, website=website,
                    stage=row.get("stage", ""),
                    focus_areas=row.get("focus_areas", ""),
                    location=row.get("location", ""),
                    check_size=row.get("check_size", ""),
                    source="existing_seed"
                ))
    logger.info(f"  📂 Existing seed: {len(entries)} funds")
    return entries


# ══════════════════════════════════════════════════
#  Source 2: Mine Checkpoint CSV for fund URLs
# ══════════════════════════════════════════════════
def mine_checkpoint() -> List[FundEntry]:
    """Extract unique fund URLs from the checkpoint CSV."""
    entries = []
    if not CHECKPOINT_CSV.exists():
        return entries
    
    seen_domains = set()
    with open(CHECKPOINT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fund_name = (row.get("fund_name") or "").strip()
            fund_url = (row.get("fund_url") or "").strip()
            if not fund_url or not fund_url.startswith("http"):
                continue
            domain = _normalize_domain(fund_url)
            if domain and domain not in seen_domains and _is_valid_vc_url(fund_url):
                seen_domains.add(domain)
                entries.append(FundEntry(
                    name=fund_name if fund_name else domain.split(".")[0].title(),
                    website=fund_url,
                    source="checkpoint_mining"
                ))
    logger.info(f"  🔍 Checkpoint mining: {len(entries)} unique fund domains")
    return entries


# ══════════════════════════════════════════════════
#  Source 3: GitHub "awesome-vc" Lists
# ══════════════════════════════════════════════════
GITHUB_SOURCES = [
    # Original sources
    {"name": "awesome-vc (mckaywrigley)", "url": "https://raw.githubusercontent.com/mckaywrigley/awesome-vc/main/README.md"},
    {"name": "awesome-venture-capital", "url": "https://raw.githubusercontent.com/byjonah/awesome-venture-capital/main/README.md"},
    {"name": "vc-firms (jbkunst)", "url": "https://raw.githubusercontent.com/jbkunst/vc-firms/main/README.md"},
    {"name": "awesome-vc-list (govc)", "url": "https://raw.githubusercontent.com/govc/awesome-vc/main/README.md"},
    {"name": "startup-investors", "url": "https://raw.githubusercontent.com/codingforentrepreneurs/startup-investors/main/README.md"},
    {"name": "global-vc-list (dbreunig)", "url": "https://raw.githubusercontent.com/dbreunig/venture-capital/master/README.md"},
    {"name": "european-vc-list", "url": "https://raw.githubusercontent.com/nicbou/european-vc/main/README.md"},
    {"name": "awesome-crypto-vc", "url": "https://raw.githubusercontent.com/nicklockwood/awesome-crypto-vc/main/README.md"},
    {"name": "awesome-climate-vc", "url": "https://raw.githubusercontent.com/elainesfolder/awesome-climate-vc/main/README.md"},
    {"name": "vc-list-usa", "url": "https://raw.githubusercontent.com/founder-resources/vc-database/main/README.md"},
    {"name": "seed-vc-list", "url": "https://raw.githubusercontent.com/seed-vc/awesome-seed-vc/main/README.md"},
    {"name": "women-led-vc", "url": "https://raw.githubusercontent.com/gogirl-vc/women-led-vc/main/README.md"},
    # Additional curated lists
    {"name": "vc-list-india", "url": "https://raw.githubusercontent.com/nicklockwood/awesome-vc-india/main/README.md"},
    {"name": "awesome-fintech-vc", "url": "https://raw.githubusercontent.com/nicklockwood/awesome-fintech-vc/main/README.md"},
    {"name": "southeast-asia-vc", "url": "https://raw.githubusercontent.com/nicklockwood/awesome-sea-vc/main/README.md"},
]


async def _fetch_github_source(session: aiohttp.ClientSession, source: dict) -> List[FundEntry]:
    """Fetch and parse a single GitHub markdown source."""
    try:
        async with session.get(source["url"], timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
    except Exception:
        return []
    
    entries = []
    seen = set()
    
    # Parse markdown links: [Name](https://example.com)
    for match in re.finditer(r'\[([^\]]+)\]\((https?://[^\)]+)\)', text):
        name, url = match.group(1).strip(), match.group(2).strip()
        if len(name) < 3 or name.lower() in ("link", "website", "here", "source"):
            continue
        if "badge" in url or "shields.io" in url or "github.com" in url:
            continue
        domain = _normalize_domain(url)
        if domain and domain not in seen and _is_valid_vc_url(url):
            seen.add(domain)
            entries.append(FundEntry(
                name=name, website=url,
                source=f"github:{source['name']}"
            ))
    
    return entries


async def fetch_github_lists() -> List[FundEntry]:
    """Fetch all GitHub VC lists."""
    all_entries = []
    async with aiohttp.ClientSession(
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    ) as session:
        tasks = [_fetch_github_source(session, src) for src in GITHUB_SOURCES]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, list):
                all_entries.extend(result)
    logger.info(f"  🐙 GitHub lists: {len(all_entries)} fund entries")
    return all_entries


# ══════════════════════════════════════════════════
#  Source 4: OpenVC Scrape (JSON API)
# ══════════════════════════════════════════════════
async def scrape_openvc() -> List[FundEntry]:
    """Scrape OpenVC investor directory via their public JSON endpoint."""
    entries = []
    try:
        async with aiohttp.ClientSession(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        ) as session:
            # OpenVC has a public API endpoint for investor data
            url = "https://www.openvc.app/api/investors"
            params = {"limit": 2000, "offset": 0}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    investors = data if isinstance(data, list) else data.get("investors", data.get("data", []))
                    for inv in investors:
                        name = inv.get("name", "").strip()
                        website = inv.get("website", inv.get("url", "")).strip()
                        if name and website and _is_valid_vc_url(website):
                            entries.append(FundEntry(
                                name=name, website=website,
                                stage=inv.get("stages", ""),
                                focus_areas=inv.get("industries", ""),
                                location=inv.get("location", ""),
                                check_size=inv.get("check_size", ""),
                                source="openvc_api"
                            ))
                else:
                    logger.warning(f"  ⚠️  OpenVC API returned {resp.status}")
    except Exception as e:
        logger.warning(f"  ⚠️  OpenVC scrape failed: {e}")
    logger.info(f"  🌐 OpenVC API: {len(entries)} funds")
    return entries


# ══════════════════════════════════════════════════
#  Source 5: Well-known VC directories (static lists)
# ══════════════════════════════════════════════════
# Curated mega-list of well-known VC firms that should definitely be in the seed
CURATED_VCS = [
    ("Sequoia Capital", "https://www.sequoiacap.com"),
    ("Andreessen Horowitz", "https://a16z.com"),
    ("Accel", "https://www.accel.com"),
    ("Benchmark", "https://www.benchmark.com"),
    ("Greylock Partners", "https://greylock.com"),
    ("Lightspeed Venture Partners", "https://lsvp.com"),
    ("Bessemer Venture Partners", "https://www.bvp.com"),
    ("General Catalyst", "https://www.generalcatalyst.com"),
    ("Index Ventures", "https://www.indexventures.com"),
    ("Founders Fund", "https://foundersfund.com"),
    ("Insight Partners", "https://www.insightpartners.com"),
    ("Tiger Global Management", "https://www.tigerglobal.com"),
    ("Coatue Management", "https://www.coatue.com"),
    ("IVP", "https://www.ivp.com"),
    ("GGV Capital", "https://www.ggvc.com"),
    ("NEA", "https://www.nea.com"),
    ("Kleiner Perkins", "https://www.kleinerperkins.com"),
    ("Battery Ventures", "https://www.battery.com"),
    ("Sapphire Ventures", "https://sapphireventures.com"),
    ("Redpoint Ventures", "https://www.redpoint.com"),
    ("Spark Capital", "https://www.sparkcapital.com"),
    ("Felicis Ventures", "https://www.felicis.com"),
    ("Craft Ventures", "https://www.craftventures.com"),
    ("First Round Capital", "https://firstround.com"),
    ("Lux Capital", "https://luxcapital.com"),
    ("a]ventures", "https://www.a16z.com"),
    ("USV", "https://www.usv.com"),
    ("Bain Capital Ventures", "https://www.baincapitalventures.com"),
    ("GV (Google Ventures)", "https://www.gv.com"),
    ("Khosla Ventures", "https://www.khoslaventures.com"),
    ("Menlo Ventures", "https://www.menlovc.com"),
    ("Foundation Capital", "https://foundationcap.com"),
    ("Scale Venture Partners", "https://www.scalevp.com"),
    ("Norwest Venture Partners", "https://www.nvp.com"),
    ("Ribbit Capital", "https://www.ribbitcap.com"),
    ("QED Investors", "https://www.qedinvestors.com"),
    ("Altimeter Capital", "https://www.altimetercap.com"),
    ("Thrive Capital", "https://www.thrivecap.com"),
    ("8VC", "https://8vc.com"),
    ("Initialized Capital", "https://initialized.com"),
    ("Pear VC", "https://www.pear.vc"),
    ("Abstract Ventures", "https://www.abstractvc.com"),
    ("Amplify Partners", "https://www.amplifypartners.com"),
    ("Atomic", "https://www.atomic.vc"),
    ("Balderton Capital", "https://www.balderton.com"),
    ("Creandum", "https://creandum.com"),
    ("EQT Ventures", "https://eqtventures.com"),
    ("Eurazeo", "https://www.eurazeo.com"),
    ("Felix Capital", "https://www.felixcap.com"),
    ("Headline", "https://headline.com"),
    ("HV Capital", "https://www.hvcapital.com"),
    ("Kaszek Ventures", "https://www.kaszek.com"),
    ("Lakestar", "https://www.lakestar.com"),
    ("LocalGlobe", "https://www.localglobe.vc"),
    ("Molten Ventures", "https://www.moltenventures.com"),
    ("Moonfire Ventures", "https://www.moonfire.com"),
    ("Northzone", "https://northzone.com"),
    ("Partech", "https://partechpartners.com"),
    ("Point Nine Capital", "https://www.pointnine.com"),
    ("Project A Ventures", "https://www.project-a.com"),
    ("Seedcamp", "https://seedcamp.com"),
    ("Cherry Ventures", "https://www.cherry.vc"),
    ("Speedinvest", "https://www.speedinvest.com"),
    ("Stride VC", "https://www.stride.vc"),
    ("Atomico", "https://www.atomico.com"),
    ("Dawn Capital", "https://dawncapital.com"),
    ("Draper Esprit", "https://www.draperesprit.com"),
    ("General Atlantic", "https://www.generalatlantic.com"),
    ("Highland Capital Partners", "https://www.hcp.com"),
    ("JMI Equity", "https://jmiequity.com"),
    ("K1 Investment Management", "https://k1im.com"),
    ("Lead Edge Capital", "https://www.leadedgecapital.com"),
    ("M12 (Microsoft Ventures)", "https://m12.vc"),
    ("Maverick Ventures", "https://www.maverickventures.com"),
    ("Obvious Ventures", "https://obvious.com"),
    ("Plug and Play Ventures", "https://www.plugandplaytechcenter.com"),
    ("Primary Venture Partners", "https://www.primaryvc.com"),
    ("Radical Ventures", "https://www.radical.vc"),
    ("RRE Ventures", "https://rre.com"),
    ("Shasta Ventures", "https://shastaventures.com"),
    ("SignalFire", "https://www.signalfire.com"),
    ("Social Capital", "https://www.socialcapital.com"),
    ("SoftBank Vision Fund", "https://visionfund.com"),
    ("Storm Ventures", "https://www.stormventures.com"),
    ("Sutter Hill Ventures", "https://shv.com"),
    ("SVB Capital", "https://www.svb.com"),
    ("TCV", "https://www.tcv.com"),
    ("Upfront Ventures", "https://upfront.com"),
    ("Venrock", "https://www.venrock.com"),
    ("VersionOne Ventures", "https://versionone.vc"),
    ("Wing Venture Capital", "https://www.wing.vc"),
    ("Work-Bench", "https://www.work-bench.com"),
    ("Y Combinator", "https://www.ycombinator.com"),
    ("Acrew Capital", "https://www.acrewcapital.com"),
    ("Alumni Ventures", "https://www.av.vc"),
    ("Antler", "https://www.antler.co"),
    ("Ascend Venture Capital", "https://www.ascend.vc"),
    ("Basement Fund", "https://basement.vc"),
    ("Betaworks Ventures", "https://www.betaworks.com"),
    ("Boldstart Ventures", "https://boldstart.vc"),
    ("BoxGroup", "https://www.boxgroup.com"),
    ("Breyer Capital", "https://breyercapital.com"),
    ("Brooklyn Bridge Ventures", "https://www.brooklynbridge.vc"),
    ("Cendana Capital", "https://www.cendanacapital.com"),
    ("Charles River Ventures (CRV)", "https://www.crv.com"),
    ("Collaboration Capital", "https://www.collaborationcap.com"),
    ("Conversion Capital", "https://www.conversioncapital.com"),
    ("Costanoa Ventures", "https://www.costanoavc.com"),
    ("Cross Culture Ventures", "https://www.crossculture.vc"),
    ("Data Point Capital", "https://www.datapointcapital.com"),
    ("Decibel Partners", "https://www.decibel.vc"),
    ("Drive Capital", "https://www.drivecapital.com"),
    ("Emergence Capital", "https://www.emcap.com"),
    ("Eniac Ventures", "https://eniacventures.com"),
    ("Fika Ventures", "https://www.fika.vc"),
    ("Forerunner Ventures", "https://forerunnerventures.com"),
    ("Freestyle Capital", "https://freestyle.vc"),
    ("FJ Labs", "https://fjlabs.com"),
    ("Glasswing Ventures", "https://glasswing.vc"),
    ("Greycroft", "https://www.greycroft.com"),
    ("Harlem Capital", "https://www.harlemcapital.com"),
    ("Haystack", "https://haystack.vc"),
    ("Homebrew", "https://homebrew.co"),
    ("Hustle Fund", "https://www.hustlefund.vc"),
    ("Javelin Venture Partners", "https://www.javelinvp.com"),
    ("K9 Ventures", "https://k9ventures.com"),
    ("Kindred Ventures", "https://www.kindredventures.com"),
    ("Lachy Groom", "https://www.lachygroom.com"),
    ("Launch", "https://www.launch.co"),
    ("Lowercase Capital", "https://lowercasecapital.com"),
    ("Madrona Venture Group", "https://www.madrona.com"),
    ("Matrix Partners", "https://www.matrixpartners.com"),
    ("Maveron", "https://www.maveron.com"),
    ("Mucker Capital", "https://www.mucker.com"),
    ("NextView Ventures", "https://nextviewventures.com"),
    ("Notable Capital", "https://www.notablecap.com"),
    ("Origin Ventures", "https://www.originventures.com"),
    ("Precursor Ventures", "https://precursorvc.com"),
    ("Rho Capital Partners", "https://www.rhovc.com"),
    ("Ridge Ventures", "https://www.ridge.vc"),
    ("Romulus Capital", "https://www.romuluscap.com"),
    ("Safety Net", "https://www.safetynet.vc"),
    ("SciFi VC", "https://www.scifi.vc"),
    ("Seven Seven Six", "https://www.sevensevensix.com"),
    ("SineWave Ventures", "https://www.sinewaveventures.com"),
    ("Slow Ventures", "https://slow.co"),
    ("SV Angel", "https://www.svangel.com"),
    ("Tenacity Venture Capital", "https://tenacity.vc"),
    ("Torch Capital", "https://www.torch.vc"),
    ("Tribe Capital", "https://tribecap.co"),
    ("True Ventures", "https://trueventures.com"),
    ("Two Sigma Ventures", "https://www.twosigmaventures.com"),
    ("Uncork Capital", "https://uncorkcapital.com"),
    ("Union Square Ventures", "https://www.usv.com"),
    ("Valar Ventures", "https://www.valarventures.com"),
    ("Vintage Investment Partners", "https://www.vintagelp.com"),
    ("Village Global", "https://www.villageglobal.vc"),
    ("Volition Capital", "https://www.volitioncapital.com"),
    ("XYZ Venture Capital", "https://www.xyz.vc"),
    ("Zynga Ventures", "https://company.zynga.com"),
    # European VCs
    ("Acton Capital", "https://www.actoncapital.com"),
    ("btov Partners", "https://www.btov.com"),
    ("Capnamic Ventures", "https://capnamic.com"),
    ("Cavalry Ventures", "https://cavalry.vc"),
    ("Chalfen Ventures", "https://www.chalfen.com"),
    ("Cherry Ventures", "https://www.cherry.vc"),
    ("Connect Ventures", "https://www.connectventures.co.uk"),
    ("Earlybird Venture Capital", "https://earlybird.com"),
    ("Fly Ventures", "https://fly.vc"),
    ("Hoxton Ventures", "https://www.hoxtonventures.com"),
    ("Keen Venture Partners", "https://www.keenventurepartners.com"),
    ("La Famiglia", "https://www.lafamiglia.vc"),
    ("Nauta Capital", "https://nautacapital.com"),
    ("Picus Capital", "https://www.picuscap.com"),
    ("Samaipata", "https://samaipata.vc"),
    ("Singular", "https://singular.vc"),
    ("Target Global", "https://www.targetglobal.vc"),
    ("Understory Capital", "https://www.understorycapital.com"),
    ("Ventures Together", "https://venturestogether.vc"),
    # Asia VCs
    ("Beenext", "https://www.beenext.com"),
    ("East Ventures", "https://east.vc"),
    ("Golden Gate Ventures", "https://goldengate.vc"),
    ("Jungle Ventures", "https://www.jungleventures.com"),
    ("Lightspeed India", "https://lsip.in"),
    ("Matrix Partners India", "https://www.matrixpartners.in"),
    ("Monk's Hill Ventures", "https://www.monkshill.com"),
    ("Saison Capital", "https://www.saisoncapital.com"),
    ("Sequoia Capital India", "https://www.sequoiacap.com/india"),
    ("Wavemaker Partners", "https://wavemaker.vc"),
    # Sector-specific
    ("Lowercarbon Capital", "https://lowercarboncapital.com"),
    ("Congruent Ventures", "https://www.congruentvc.com"),
    ("DCVC", "https://www.dcvc.com"),
    ("G2 Venture Partners", "https://www.g2vp.com"),
    ("Prelude Ventures", "https://www.preludeventures.com"),
    ("Breakthrough Energy Ventures", "https://www.breakthroughenergy.org"),
    ("The Engine", "https://www.engine.xyz"),
    ("Canaan Partners", "https://www.canaan.com"),
    ("OrbiMed", "https://www.orbimed.com"),
    ("Polaris Partners", "https://www.polarispartners.com"),
    ("RA Capital Management", "https://www.racap.com"),
    ("Section 32", "https://www.section32.com"),
    ("Arch Venture Partners", "https://www.archventure.com"),
    ("Deerfield Management", "https://www.deerfield.com"),
    ("Flagship Pioneering", "https://www.flagshippioneering.com"),
    ("Third Rock Ventures", "https://thirdrockventures.com"),
    ("Versant Ventures", "https://www.versantventures.com"),
    # Fintech-specific
    ("Anthemis", "https://www.anthemis.com"),
    ("Clocktower Technology Ventures", "https://www.clocktowertech.com"),
    ("FinCapital", "https://www.fincapital.com"),
    ("Fin VC", "https://www.finvc.com"),
    ("Flourish Ventures", "https://flourishventures.com"),
    ("Greyhound Capital", "https://www.greyhoundcapital.com"),
    ("Nyca Partners", "https://www.nycapartners.com"),
    ("Portag3 Ventures", "https://www.portag3.com"),
    ("Valor Equity Partners", "https://www.valorep.com"),
    ("Valar Ventures", "https://www.valarventures.com"),
    # Growth-stage
    ("Adams Street Partners", "https://www.adamsstreetpartners.com"),
    ("Advent International", "https://www.adventinternational.com"),
    ("Apax Partners", "https://www.apax.com"),
    ("Ares Management", "https://www.aresmgmt.com"),
    ("B Capital Group", "https://www.bcapgroup.com"),
    ("Dragoneer Investment Group", "https://www.dragoneer.com"),
    ("Elephant", "https://www.elephantvc.com"),
    ("Eurazeo Growth", "https://www.eurazeo.com"),
    ("Francisco Partners", "https://www.franciscopartners.com"),
    ("Georgian Partners", "https://www.georgian.io"),
    ("Goldman Sachs Growth", "https://www.gs.com"),
    ("ICONIQ Capital", "https://www.iconiqcapital.com"),
    ("Permira", "https://www.permira.com"),
    ("Providence Equity Partners", "https://www.provequity.com"),
    ("Summit Partners", "https://www.summitpartners.com"),
    ("TA Associates", "https://www.ta.com"),
    ("Technology Crossover Ventures", "https://www.tcv.com"),
    ("TPG Capital", "https://www.tpg.com"),
    ("Vista Equity Partners", "https://www.vistaequitypartners.com"),
    ("Warburg Pincus", "https://www.warburgpincus.com"),
    ("Wellington Management", "https://www.wellington.com"),
    # More seed/pre-seed
    ("2048 Ventures", "https://www.2048.vc"),
    ("Afore Capital", "https://www.afore.vc"),
    ("Array Ventures", "https://www.arrayventures.com"),
    ("Asymmetric Capital Partners", "https://www.asymmetric.co"),
    ("Banana Capital", "https://www.banana.vc"),
    ("Base10 Partners", "https://base10.vc"),
    ("Bloomberg Beta", "https://www.bloombergbeta.com"),
    ("Bow Capital", "https://www.bowcap.com"),
    ("Brand Foundry Ventures", "https://www.brandfoundry.vc"),
    ("Bull City Venture Partners", "https://www.bcvp.com"),
    ("Cambrian Ventures", "https://www.cambrian.vc"),
    ("Canvas Ventures", "https://www.canvas.vc"),
    ("Cervin Ventures", "https://cervin.com"),
    ("Chapter One", "https://chapterone.com"),
    ("Coefficient Capital", "https://www.coefficientcap.com"),
    ("Commerce Ventures", "https://commerceventures.com"),
    ("Compound", "https://www.compoundvc.com"),
    ("Contrary", "https://contrary.com"),
    ("Correlation Ventures", "https://www.correlationvc.com"),
    ("Cowboy Ventures", "https://www.cowboy.vc"),
    ("Day One Ventures", "https://www.dayoneventures.com"),
    ("Defy Partners", "https://www.defy.vc"),
    ("Designer Fund", "https://designerfund.com"),
    ("Draft Ventures", "https://www.draftventures.com"),
    ("Dreamit Ventures", "https://www.dreamit.com"),
    ("Dynamo Ventures", "https://www.dynamo.vc"),
    ("E14 Fund", "https://e14.fund"),
    ("Eclipse Ventures", "https://eclipse.vc"),
    ("Enjoy The Work", "https://www.enjoythework.com"),
    ("Era Ventures", "https://www.era.vc"),
    ("F-Prime Capital", "https://fprimecapital.com"),
    ("Floodgate", "https://floodgate.com"),
    ("Foundry Group", "https://www.foundrygroup.com"),
    ("FUEL Venture Capital", "https://www.fuelventurecapital.com"),
    ("Gradient Ventures", "https://www.gradient.com"),
    ("Greenoaks Capital", "https://greenoakscap.com"),
    ("H Ventures", "https://www.h.ventures"),
    ("Heroic Ventures", "https://www.heroicvc.com"),
    ("Hyperplane Venture Capital", "https://hyperplane.vc"),
    ("IDEO CoLab Ventures", "https://www.ideocolab.com"),
    ("Impatient Ventures", "https://www.impatientventures.com"),
    ("Infusion Fund", "https://www.infusionfund.com"),
    ("Innovation Endeavors", "https://www.innovationendeavors.com"),
    ("Inspired Capital", "https://www.inspiredcapital.com"),
    ("Invest Nebraska", "https://investnebraska.com"),
    ("January Ventures", "https://www.januaryventures.com"),
    ("Khosla Impact", "https://www.khoslaimpact.com"),
    ("Kindred Capital", "https://www.kindredcapital.vc"),
    ("Launchpad LA", "https://www.launchpad.la"),
    ("Left Lane Capital", "https://www.leftlanecap.com"),
    ("Lightbank", "https://www.lightbank.com"),
    ("M13", "https://m13.co"),
    ("March Capital", "https://marchcp.com"),
    ("Material Impact", "https://www.materialimpact.com"),
    ("Meridian Street Capital", "https://www.meridianstreetcapital.com"),
    ("Moxxie Ventures", "https://www.moxxie.vc"),
    ("Nfx", "https://www.nfx.com"),
    ("Norwest Venture Partners", "https://www.nvp.com"),
    ("Notation Capital", "https://notation.vc"),
    ("Operator Partners", "https://www.operatorpartners.com"),
    ("Owl Ventures", "https://www.owlvc.com"),
    ("Paradigm", "https://www.paradigm.co"),
    ("Pelion Venture Partners", "https://www.pelionvp.com"),
    ("Playground Global", "https://playground.global"),
    ("Point72 Ventures", "https://www.point72.com"),
    ("Rally Ventures", "https://www.rallyventures.com"),
    ("Rethink Impact", "https://www.rethinkimpact.com"),
    ("Revolution", "https://revolution.com"),
    ("S28 Capital", "https://www.s28capital.com"),
    ("Samsara Capital", "https://samsaracap.com"),
    ("Sands Capital Ventures", "https://www.sandscapital.com"),
    ("Scale Asia Ventures", "https://www.scaleasia.vc"),
    ("Signal Peak Ventures", "https://signalpeakventures.com"),
    ("Silverton Partners", "https://silvertonpartners.com"),
    ("SoGal Ventures", "https://www.sogalventures.com"),
    ("Soma Capital", "https://www.somacap.com"),
    ("Sound Ventures", "https://www.sound.vc"),
    ("Spero Ventures", "https://www.speroventures.com"),
    ("SQN Venture Partners", "https://sqnvp.com"),
    ("Stellation Capital", "https://www.stellationcapital.com"),
    ("Techstars Ventures", "https://www.techstarsventures.com"),
    ("Tectonic Capital", "https://www.tectoniccap.com"),
    ("Telstra Ventures", "https://telstraventures.com"),
    ("The Venture Reality Fund", "https://www.thevrfund.com"),
    ("Third Kind Venture Capital", "https://thirdkindvc.com"),
    ("Tishman Speyer Ventures", "https://tishmanspeyer.com"),
    ("Trail Mix Ventures", "https://www.trailmixventures.com"),
    ("TTV Capital", "https://ttvcapital.com"),
    ("Underscore VC", "https://underscore.vc"),
    ("Unusual Ventures", "https://www.unusual.vc"),
    ("Urban Innovation Fund", "https://www.urbaninnovation.fund"),
    ("Valhalla Venture Capital", "https://www.valhalla.vc"),
    ("Valor Ventures", "https://www.valor.vc"),
    ("Vast Ventures", "https://www.vast.vc"),
    ("Venture Highway", "https://venturehighway.in"),
    ("VMG Partners", "https://www.vmgpartners.com"),
    ("Voyager Capital", "https://voyagercapital.com"),
    ("Wharton Alumni Angels", "https://www.whartonalumniangels.com"),
    ("Work-Bench", "https://www.work-bench.com"),
    ("Workday Ventures", "https://www.workday.com"),
    ("XFund", "https://www.xfund.com"),
    ("Zetta Venture Partners", "https://www.zettavp.com"),
    ("Zinc Ventures", "https://www.zinc.vc"),
]


def load_curated_list() -> List[FundEntry]:
    """Load the hardcoded curated VC list."""
    entries = []
    for name, url in CURATED_VCS:
        if _is_valid_vc_url(url):
            entries.append(FundEntry(name=name, website=url, source="curated_list"))
    logger.info(f"  📋 Curated list: {len(entries)} funds")
    return entries


# ══════════════════════════════════════════════════
#  Source 6: Additional Other Seed CSVs
# ══════════════════════════════════════════════════
def load_other_seeds() -> List[FundEntry]:
    """Load PE firms, family offices, corp dev CSVs."""
    entries = []
    for csv_path, source in [(PE_CSV, "pe_firms"), (FAMILY_CSV, "family_offices"), (CORP_CSV, "corp_dev")]:
        if not csv_path.exists():
            continue
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = (row.get("name") or "").strip()
                website = (row.get("website") or "").strip()
                if name and website and _is_valid_vc_url(website):
                    entries.append(FundEntry(
                        name=name, website=website,
                        stage=row.get("stage", ""),
                        focus_areas=row.get("focus_areas", ""),
                        location=row.get("location", ""),
                        check_size=row.get("check_size", ""),
                        source=source,
                    ))
    logger.info(f"  📁 Other seeds (PE/FO/Corp): {len(entries)} funds")
    return entries


# ══════════════════════════════════════════════════
#  Merge & Write
# ══════════════════════════════════════════════════
def merge_funds(all_sources: List[List[FundEntry]]) -> List[FundEntry]:
    """Merge all sources with domain-level dedup. Prefer entries with more metadata."""
    domain_map: Dict[str, FundEntry] = {}
    
    for source_entries in all_sources:
        for entry in source_entries:
            domain = entry.domain
            if not domain:
                continue
            
            existing = domain_map.get(domain)
            if existing:
                # Prefer entries with more metadata
                if (entry.stage and entry.stage != "N/A" and 
                    (not existing.stage or existing.stage == "N/A")):
                    existing.stage = entry.stage
                if entry.focus_areas and not existing.focus_areas:
                    existing.focus_areas = entry.focus_areas
                if (entry.location and entry.location != "N/A" and 
                    (not existing.location or existing.location == "N/A")):
                    existing.location = entry.location
                if entry.check_size and not existing.check_size:
                    existing.check_size = entry.check_size
            else:
                domain_map[domain] = entry
    
    merged = sorted(domain_map.values(), key=lambda e: e.name.lower())
    return merged


def write_expanded_csv(entries: List[FundEntry], output_path: Path, backup: bool = False):
    """Write expanded seed CSV."""
    if backup and output_path.exists():
        backup_path = output_path.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        shutil.copy2(output_path, backup_path)
        logger.info(f"  💾 Backed up original to {backup_path}")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["name", "website", "stage", "focus_areas", "location", "check_size"]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            writer.writerow(entry.to_row())
    
    logger.info(f"  ✅ Wrote {len(entries)} funds to {output_path}")


# ══════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════
async def run_expansion(write: bool = False, backup: bool = False):
    """Run the full seed expansion pipeline."""
    print(f"\n{'='*60}")
    print("  🌱  SEED DATABASE EXPANDER")
    print(f"{'='*60}\n")

    # Collect from all sources
    existing = load_existing_seed()
    checkpoint = mine_checkpoint()
    curated = load_curated_list()
    other_seeds = load_other_seeds()
    github = await fetch_github_lists()
    openvc = await scrape_openvc()

    # Merge with dedup
    all_sources = [existing, checkpoint, curated, other_seeds, github, openvc]
    merged = merge_funds(all_sources)

    print(f"\n{'─'*60}")
    print(f"  📊 SUMMARY")
    print(f"{'─'*60}")
    print(f"  Existing seed:     {len(existing):>6}")
    print(f"  Checkpoint mining: {len(checkpoint):>6}")
    print(f"  Curated list:      {len(curated):>6}")
    print(f"  Other seeds:       {len(other_seeds):>6}")
    print(f"  GitHub lists:      {len(github):>6}")
    print(f"  OpenVC API:        {len(openvc):>6}")
    print(f"{'─'*60}")
    print(f"  TOTAL (deduped):   {len(merged):>6}")
    print(f"{'─'*60}")

    if write:
        write_expanded_csv(merged, EXPANDED_CSV, backup=backup)
    else:
        print(f"\n  ℹ️  Dry run — use --write to save expanded seed")
        print(f"      Use --write --backup to backup original first")

    return merged


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Expand VC seed database")
    parser.add_argument("--write", action="store_true", help="Write expanded CSV")
    parser.add_argument("--backup", action="store_true", help="Backup original before writing")
    args = parser.parse_args()
    
    result = asyncio.run(run_expansion(write=args.write, backup=args.backup))
    return result


if __name__ == "__main__":
    main()
