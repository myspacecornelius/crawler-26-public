"""
CRAWL — DNS Harvester (v2)
Queries DNS records (TXT, DMARC, SOA, MX, SPF, BIMI) for embedded email addresses
and provider intelligence. Zero-cost, instant enrichment that yields:
- Admin/ops/founder emails from DMARC rua/ruf URIs and SOA rname fields
- Email provider detection from SPF includes and MX records (Google/Microsoft/custom)
- Pattern inference from provider type (Google Workspace = first.last, Microsoft 365 = varies)
"""

import asyncio
import logging
import re
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import dns.asyncresolver
from dns.resolver import NXDOMAIN, NoAnswer, NoNameservers, Timeout

logger = logging.getLogger(__name__)

# Standard email regex, relaxed slightly for DNS records which might have quoting
_EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,15}')

# Emails to ignore (common providers we don't care about)
_IGNORE_PATTERNS = {
    "example.com", "email.com", "domain.com",
    "noreply", "no-reply", "donotreply",
    "postmaster", "hostmaster", "webmaster", "abuse",
    "sentry.io",
    "agari.com",
    "dmarcian.com",
    "mimecast.com",
    "rua@dmarc.",
    "rejection@",
}

# SPF include patterns → email provider
_SPF_PROVIDER_MAP = {
    "_spf.google.com": "google_workspace",
    "google.com": "google_workspace",
    "googlemail.com": "google_workspace",
    "spf.protection.outlook.com": "microsoft_365",
    "outlook.com": "microsoft_365",
    "pphosted.com": "proofpoint",
    "mimecast": "mimecast",
    "sendgrid.net": "sendgrid",
    "amazonses.com": "amazon_ses",
    "mailgun.org": "mailgun",
    "zendesk.com": "zendesk",
    "freshdesk.com": "freshdesk",
}

# MX host patterns → email provider
_MX_PROVIDER_MAP = {
    "google.com": "google_workspace",
    "googlemail.com": "google_workspace",
    "outlook.com": "microsoft_365",
    "protection.outlook.com": "microsoft_365",
    "pphosted.com": "proofpoint",
    "mimecast.com": "mimecast",
    "barracuda": "barracuda",
    "protonmail.ch": "protonmail",
    "zoho.com": "zoho",
    "fastmail": "fastmail",
    "migadu.com": "migadu",
    "improvmx.com": "improvmx",
    "forwardemail.net": "forward_email",
}

# Provider → likely email pattern (for pattern inference)
_PROVIDER_PATTERN_HINTS = {
    "google_workspace": "{first}.{last}@{domain}",  # Most common Google Workspace pattern
    "microsoft_365": "{first}.{last}@{domain}",     # Also common for M365
    "protonmail": "{first}@{domain}",               # Protonmail orgs tend simpler
    "zoho": "{first}.{last}@{domain}",
    "fastmail": "{first}@{domain}",
}


def _is_valid_email(email: str, target_domain: str) -> bool:
    """Check if an email is real and not a generic reporting service."""
    if not email or "@" not in email:
        return False
    email = email.lower()
    if len(email) > 60 or len(email) < 5:
        return False
    for pattern in _IGNORE_PATTERNS:
        if pattern in email:
            return False
    return True


class DNSHarvester:
    """
    Scrapes DNS records (TXT, DMARC, SOA, MX, SPF) for emails and provider intelligence.
    Groups leads by domain and distributes found emails back.
    """

    def __init__(self, concurrency: int = 50):
        self._sem = asyncio.Semaphore(concurrency)
        self._domain_cache: Dict[str, Set[str]] = {}
        self._provider_cache: Dict[str, str] = {}       # domain → provider name
        self._pattern_hint_cache: Dict[str, str] = {}   # domain → suggested pattern
        self._resolver = dns.asyncresolver.Resolver()
        self._resolver.timeout = 3.0
        self._resolver.lifetime = 3.0

        self._stats = {
            "domains_queried": 0,
            "emails_found": 0,
            "leads_enriched": 0,
            "providers_detected": 0,
            "pattern_hints_generated": 0,
            "errors": 0,
        }

    def _extract_emails(self, text: str, target_domain: str) -> Set[str]:
        """Extract valid emails from a DNS record string."""
        found = set()
        for match in _EMAIL_RE.finditer(text):
            email = match.group().lower().rstrip(".")
            if _is_valid_email(email, target_domain):
                found.add(email)
        return found

    def _detect_provider_from_spf(self, txt_records: str) -> Optional[str]:
        """Parse SPF include: directives to identify the email provider."""
        includes = re.findall(r'include:([^\s"]+)', txt_records.lower())
        for inc in includes:
            for pattern, provider in _SPF_PROVIDER_MAP.items():
                if pattern in inc:
                    return provider
        return None

    def _detect_provider_from_mx(self, mx_hosts: List[str]) -> Optional[str]:
        """Identify email provider from MX hostnames."""
        for host in mx_hosts:
            host_lower = host.lower()
            for pattern, provider in _MX_PROVIDER_MAP.items():
                if pattern in host_lower:
                    return provider
        return None

    async def _query_record(self, qname: str, rdtype: str) -> str:
        """Helper to run a single DNS query and return combined text."""
        try:
            answers = await self._resolver.resolve(qname, rdtype)
            parts = []
            for rdata in answers:
                if rdtype == "SOA":
                    rname = rdata.rname.to_text().strip('.')
                    if '.' in rname:
                        rname_parts = rname.split('.', 1)
                        rname_email = f"{rname_parts[0]}@{rname_parts[1]}"
                        parts.append(rname_email)
                elif rdtype == "MX":
                    parts.append(str(rdata.exchange).rstrip('.'))
                else:
                    parts.append(rdata.to_text())
            return " ".join(parts)
        except (NXDOMAIN, NoAnswer, NoNameservers, Timeout):
            return ""
        except Exception as e:
            logger.debug(f"  DNS {rdtype} error for {qname}: {e}")
            self._stats["errors"] += 1
            return ""

    async def _query_mx_hosts(self, domain: str) -> List[str]:
        """Get list of MX hostnames for a domain."""
        try:
            answers = await self._resolver.resolve(domain, "MX")
            return [str(rdata.exchange).rstrip('.') for rdata in answers]
        except (NXDOMAIN, NoAnswer, NoNameservers, Timeout):
            return []
        except Exception:
            return []

    async def search_domain(self, domain: str) -> Set[str]:
        """
        Query DNS for a domain to find emails and detect provider.
        Checks: TXT (SPF), DMARC, SOA, MX, BIMI.
        """
        if domain in self._domain_cache:
            return self._domain_cache[domain]

        self._stats["domains_queried"] += 1
        emails: Set[str] = set()

        async with self._sem:
            # Run all queries concurrently
            txt_task = self._query_record(domain, "TXT")
            dmarc_task = self._query_record(f"_dmarc.{domain}", "TXT")
            soa_task = self._query_record(domain, "SOA")
            mx_task = self._query_mx_hosts(domain)
            bimi_task = self._query_record(f"default._bimi.{domain}", "TXT")

            txt_res, dmarc_res, soa_res, mx_hosts, bimi_res = await asyncio.gather(
                txt_task, dmarc_task, soa_task, mx_task, bimi_task,
                return_exceptions=True,
            )

            # Safely collect text results
            combined_text = ""
            txt_text = ""
            if isinstance(txt_res, str):
                combined_text += f" {txt_res}"
                txt_text = txt_res
            if isinstance(dmarc_res, str):
                combined_text += f" {dmarc_res}"
            if isinstance(soa_res, str):
                combined_text += f" {soa_res}"
            if isinstance(bimi_res, str):
                combined_text += f" {bimi_res}"
            if isinstance(mx_hosts, Exception):
                mx_hosts = []

            if combined_text:
                combined_text = combined_text.replace("mailto:", " ")
                found = self._extract_emails(combined_text, domain)
                emails.update(found)

            # Detect email provider from SPF and MX
            provider = self._detect_provider_from_spf(txt_text)
            if not provider and mx_hosts:
                provider = self._detect_provider_from_mx(mx_hosts)

            if provider:
                self._provider_cache[domain] = provider
                self._stats["providers_detected"] += 1
                logger.debug(f"  DNS: {domain} → provider={provider}")

                # Generate pattern hint from provider
                hint = _PROVIDER_PATTERN_HINTS.get(provider)
                if hint:
                    self._pattern_hint_cache[domain] = hint
                    self._stats["pattern_hints_generated"] += 1

        self._domain_cache[domain] = emails
        self._stats["emails_found"] += len(emails)

        if emails:
            logger.info(f"  DNS HARVEST: found {len(emails)} emails for {domain}")

        return emails

    def get_provider(self, domain: str) -> Optional[str]:
        """Get detected email provider for a domain."""
        return self._provider_cache.get(domain)

    def get_pattern_hint(self, domain: str) -> Optional[str]:
        """Get suggested email pattern based on detected provider."""
        return self._pattern_hint_cache.get(domain)

    async def enrich_batch(self, leads: list) -> list:
        """
        Enrich leads with emails found in DNS records.
        Only processes leads that still don't have emails.
        """
        from deep_crawl import _match_email_to_name

        no_email = [
            lead for lead in leads
            if not lead.email or lead.email in ("N/A", "N/A (invalid)")
        ]

        if not no_email:
            logger.info("  📋  DNS HARVEST: no leads need enrichment")
            return leads

        # Group by domain
        domain_leads: Dict[str, List] = {}
        for lead in no_email:
            if lead.website and lead.website not in ("N/A", ""):
                try:
                    parsed = urlparse(
                        lead.website if "://" in lead.website else f"https://{lead.website}"
                    )
                    domain = parsed.netloc.lower().replace("www.", "")
                except Exception:
                    continue
                if domain:
                    domain_leads.setdefault(domain, []).append(lead)

        logger.info(
            f"  📋  DNS HARVEST: querying {len(domain_leads)} domains "
            f"for {len(no_email)} leads..."
        )

        # Process domains concurrently (DNS is very fast/lightweight)
        domain_list = list(domain_leads.keys())
        tasks = [self.search_domain(domain) for domain in domain_list]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
            # Match back to leads
        for domain, domain_emails in zip(domain_list, results):
            if isinstance(domain_emails, Exception) or not domain_emails:
                continue
                
            domain_group = domain_leads[domain]
            unmatched = list(domain_emails)
            
            # First pass: try specifically matching names
            for lead in domain_group:
                if lead.email and lead.email not in ("N/A", "N/A (invalid)"):
                    continue
                    
                best_email = None
                best_score = 0.0
                for email in unmatched:
                    score = _match_email_to_name(email, lead.name)
                    if score > best_score:
                        best_score = score
                        best_email = email
                        
                if best_email and best_score >= 0.3:
                    lead.email = best_email
                    lead.email_status = "dns_harvest"
                    unmatched.remove(best_email)
                    self._stats["leads_enriched"] += 1
                    logger.info(
                        f"  📋  DNS HARVEST email for {lead.name}: "
                        f"{best_email} (score={best_score:.2f})"
                    )

            # Second pass: DNS emails are often generic (admin@, ops@, dmarc@).
            # If we still have unmatched DNS emails for this domain, and leads
            # without emails, distribute them as fallback contacts.
            # ONLY use emails that strictly match the target domain.
            # Ignore third-party services like easydmarc.us, vali.email, cloudflare.com.
            for lead in domain_group:
                if lead.email and lead.email not in ("N/A", "N/A (invalid)"):
                    continue
                if unmatched:
                    # STRICT MATCH: email must end exactly with @target_domain
                    domain_exact_emails = [e for e in unmatched if e.endswith(f"@{domain}")]
                    
                    if domain_exact_emails:
                        best_email = domain_exact_emails[0]
                        lead.email = best_email
                        lead.email_status = "dns_harvest"
                        unmatched.remove(best_email)
                        self._stats["leads_enriched"] += 1
                        logger.info(
                            f"  📋  DNS HARVEST strict fallback email for {lead.name}: {best_email}"
                        )
                        

        logger.info(
            f"  📋  DNS HARVEST complete: {self._stats['leads_enriched']} leads enriched, "
            f"{self._stats['emails_found']} emails found "
            f"({self._stats['domains_queried']} domains queried)"
        )
        return leads

    @property
    def stats(self) -> dict:
        return dict(self._stats)
