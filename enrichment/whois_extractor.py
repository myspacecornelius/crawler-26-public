"""
CRAWL — WHOIS Email Extractor
Queries WHOIS data for a list of domains to extract registrant/admin/tech
contact information (name, email).  Results are cached to disk so domains
are only queried once per run, and WHOIS servers are rate-limited to avoid
being blocked.

Strategy (in order):
  1. python-whois library (subprocess-backed whois command or socket)
  2. Fallback: raw whois socket query to the authoritative WHOIS server
  3. If both fail, skip the domain silently.

Output: list of dicts with keys compatible with InvestorLead.
"""

import asyncio
import json
import logging
import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Cache ─────────────────────────────────────────

_CACHE_FILE = Path("data/whois_cache.json")
_CACHE: Dict[str, dict] = {}
_CACHE_LOADED = False

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
_REDACTED_RE = re.compile(r"redacted|privacy|protected|noreply|abuse|hostmaster|postmaster",
                           re.IGNORECASE)

# Per-TLD WHOIS servers (supplement for when python-whois doesn't resolve)
_WHOIS_SERVERS = {
    "com": "whois.verisign-grs.com",
    "net": "whois.verisign-grs.com",
    "org": "whois.pir.org",
    "io":  "whois.nic.io",
    "co":  "whois.nic.co",
    "vc":  "whois2.afilias.net",
    "ai":  "whois.nic.ai",
    "fund": "whois.nic.fund",
    "capital": "whois.nic.capital",
    "ventures": "whois.nic.ventures",
}


def _load_cache():
    global _CACHE, _CACHE_LOADED
    if _CACHE_LOADED:
        return
    try:
        if _CACHE_FILE.exists():
            _CACHE = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            logger.debug(f"  [WHOIS] Loaded {len(_CACHE)} cached entries from {_CACHE_FILE}")
    except Exception as exc:
        logger.debug(f"  [WHOIS] Cache load error: {exc}")
        _CACHE = {}
    _CACHE_LOADED = True


def _save_cache():
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(_CACHE, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.debug(f"  [WHOIS] Cache save error: {exc}")


# ── WHOIS Query Helpers ───────────────────────────

def _extract_emails(raw: str) -> List[str]:
    """Find all non-redacted email addresses in a WHOIS response."""
    found = _EMAIL_RE.findall(raw)
    clean = []
    for e in found:
        e = e.lower().strip(".")
        if _REDACTED_RE.search(e):
            continue
        if any(skip in e for skip in ("example.com", "icann.org", "iana.org")):
            continue
        if e not in clean:
            clean.append(e)
    return clean


def _extract_registrant_name(raw: str) -> str:
    """Try to pull the registrant org or name from WHOIS text."""
    for line in raw.splitlines():
        stripped = line.strip()
        for prefix in ("Registrant Organization:", "Registrant Name:",
                       "org-name:", "owner:", "Organization:"):
            if stripped.lower().startswith(prefix.lower()):
                value = stripped[len(prefix):].strip()
                if value and len(value) > 2 and "REDACTED" not in value.upper():
                    return value
    return ""


def _query_whois_socket(domain: str, timeout: int = 10) -> str:
    """Query a WHOIS server directly via socket — fallback when subprocess fails."""
    tld = domain.rsplit(".", 1)[-1].lower()
    server = _WHOIS_SERVERS.get(tld, f"whois.nic.{tld}")
    try:
        with socket.create_connection((server, 43), timeout=timeout) as sock:
            sock.sendall(f"{domain}\r\n".encode())
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
            return response.decode("utf-8", errors="replace")
    except Exception as exc:
        logger.debug(f"  [WHOIS] Socket query failed for {domain} via {server}: {exc}")
        return ""


def _query_whois_subprocess(domain: str) -> str:
    """Run the system `whois` command. Returns raw text or empty string."""
    try:
        result = subprocess.run(
            ["whois", domain],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout or ""
    except FileNotFoundError:
        logger.debug("  [WHOIS] `whois` command not found — falling back to socket")
        return ""
    except subprocess.TimeoutExpired:
        logger.debug(f"  [WHOIS] Timeout for {domain}")
        return ""
    except Exception as exc:
        logger.debug(f"  [WHOIS] Subprocess error for {domain}: {exc}")
        return ""


def _try_python_whois(domain: str) -> str:
    """Use python-whois library if available."""
    try:
        import whois  # type: ignore  # pip install python-whois
        data = whois.whois(domain)
        # python-whois returns a dict-like object; convert to text
        raw_parts = []
        for k, v in data.items():
            if v:
                raw_parts.append(f"{k}: {v}")
        return "\n".join(raw_parts)
    except ImportError:
        return ""  # library not installed, caller will use subprocess
    except Exception:
        return ""


def _query_single_domain(domain: str) -> dict:
    """Run all WHOIS query strategies for one domain and return structured result."""
    # Strategy 1: python-whois library
    raw = _try_python_whois(domain)
    # Strategy 2: subprocess whois command
    if not raw:
        raw = _query_whois_subprocess(domain)
    # Strategy 3: direct socket
    if not raw:
        raw = _query_whois_socket(domain)

    emails = _extract_emails(raw)
    registrant = _extract_registrant_name(raw)

    return {
        "domain": domain,
        "registrant_name": registrant,
        "emails": emails,
        "primary_email": emails[0] if emails else "",
        "raw_length": len(raw),
        "queried_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ── Public API ────────────────────────────────────

def extract_whois_contacts(
    domains: List[str],
    rate_limit_seconds: float = 1.0,
    max_domains: Optional[int] = None,
) -> List[dict]:
    """
    Query WHOIS for each domain and return a list of contact dicts.

    Each dict contains:
      domain, registrant_name, emails (list), primary_email, queried_at

    Args:
        domains:             Domains to query (bare, e.g. "sequoiacap.com").
        rate_limit_seconds:  Minimum seconds between WHOIS queries (default 1.0).
        max_domains:         Optional cap on total domains processed.

    Returns:
        List of result dicts (only domains that returned at least one email or
        registrant name are included).
    """
    _load_cache()

    if max_domains:
        domains = domains[:max_domains]

    results = []
    queried = 0
    cache_hits = 0

    for domain in domains:
        domain = domain.strip().lower()
        if not domain:
            continue
        # Strip protocol/www prefix if accidentally included
        domain = re.sub(r"^https?://", "", domain)
        domain = re.sub(r"^www\.", "", domain)
        domain = domain.split("/")[0]  # strip any path

        # Check cache
        if domain in _CACHE:
            cache_hits += 1
            cached = _CACHE[domain]
            if cached.get("primary_email") or cached.get("registrant_name"):
                results.append(cached)
            continue

        # Rate limiting
        if queried > 0:
            time.sleep(rate_limit_seconds)

        logger.debug(f"  [WHOIS] Querying {domain} ...")
        try:
            record = _query_single_domain(domain)
        except Exception as exc:
            logger.debug(f"  [WHOIS] Unexpected error for {domain}: {exc}")
            record = {"domain": domain, "registrant_name": "", "emails": [],
                      "primary_email": "", "raw_length": 0,
                      "queried_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}

        _CACHE[domain] = record
        queried += 1

        if record.get("primary_email") or record.get("registrant_name"):
            results.append(record)

        # Persist cache every 25 queries
        if queried % 25 == 0:
            _save_cache()

    # Final cache persist
    if queried > 0:
        _save_cache()

    logger.info(
        f"  [WHOIS] Done: {len(results)} contacts found | "
        f"{queried} queried, {cache_hits} from cache"
    )
    return results


def whois_to_investor_leads(whois_results: List[dict]) -> List[dict]:
    """
    Convert WHOIS result dicts to InvestorLead-compatible dicts.

    Produces one lead per domain that has a usable email address.
    The 'name' field uses the registrant name if available, else the domain.
    """
    from adapters.base import InvestorLead
    from datetime import datetime

    leads = []
    for record in whois_results:
        email = record.get("primary_email", "")
        if not email:
            continue
        name = record.get("registrant_name") or record["domain"]
        domain = record["domain"]
        leads.append(InvestorLead(
            name=name,
            fund=name,
            email=email,
            website=f"https://{domain}",
            source="whois",
            scraped_at=datetime.now().isoformat(),
        ))
    return leads


# ── Async wrapper ─────────────────────────────────

async def async_extract_whois_contacts(
    domains: List[str],
    rate_limit_seconds: float = 1.0,
    max_domains: Optional[int] = None,
) -> List[dict]:
    """
    Async-compatible wrapper — runs the blocking WHOIS queries in a thread pool
    so the event loop is not blocked.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: extract_whois_contacts(domains, rate_limit_seconds, max_domains),
    )
