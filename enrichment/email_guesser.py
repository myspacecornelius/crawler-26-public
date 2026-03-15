"""
CRAWL — Email Pattern Guesser (v3)
For named contacts with a known fund domain, generates email addresses
using detected patterns, statistical learning, or defaults.

v3 improvements over v2:
- Pattern learning: records all observed patterns per domain with frequency counts
- Statistics endpoint: exposes pattern distribution and confidence metrics
- Improved person/company detection heuristics
"""

import asyncio
import json
import logging
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from enrichment.email_validator import EmailValidator

logger = logging.getLogger(__name__)

# Persistent pattern store path
_PATTERN_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "email_patterns.json"

# Common email patterns ordered by prevalence at professional firms
_PATTERNS = [
    "{first}.{last}@{domain}",
    "{first}@{domain}",
    "{f}{last}@{domain}",
    "{first}{last}@{domain}",
    "{f}.{last}@{domain}",
    "{last}@{domain}",
    "{first}_{last}@{domain}",
    "{last}.{first}@{domain}",
]

# Default pattern when no learned pattern exists
_DEFAULT_PATTERN = "{first}.{last}@{domain}"

# Words that indicate a company/fund name rather than a person name
_COMPANY_WORDS = {
    "capital", "ventures", "partners", "fund", "group", "holdings",
    "management", "investments", "equity", "advisors", "advisory",
    "associates", "labs", "studio", "studios", "foundation",
    "initiative", "institute", "accelerator", "incubator", "llc",
    "inc", "corp", "ltd", "limited", "gmbh", "sa", "ag",
    "news", "our", "the", "about", "additional", "strategic",
    "continuity", "growth", "seed", "series", "demo", "day",
    "portfolio", "companies", "company", "team", "meet", "join",
    "alumni", "network", "community", "program", "programs",
    "scout", "scouts", "bio", "life", "sciences", "games",
    "start", "path", "next", "catalyst", "innovation",
    "development", "fundamentals", "research", "digital",
    "global", "international", "technology", "technologies",
    "operating", "platform", "select", "emerging",
    "twitter", "linkedin", "facebook", "instagram", "youtube",
    "follow", "contact", "apply", "subscribe", "sign", "read",
    "learn", "view", "visit", "more", "blog", "press", "media",
    "on", "in", "at", "for", "to", "of", "an", "by", "from",
    "cookies", "cookie", "functional", "performance", "targeting",
    "marketing", "privacy", "overview", "principles", "core",
    "leadership", "history", "availability", "resources",
    "navigation", "submission", "submissions", "board",
    "shared", "values", "philosophy", "customers", "colleagues",
    "communities", "activity", "putting", "challenging",
    "convention", "smarter", "together", "humbly", "check",
    "your", "every", "stage", "how", "we", "help",
    "startups", "links", "additional", "information", "connect",
}


def _is_person_name(name: str) -> bool:
    """Check if a name looks like a real person (not a company/fund)."""
    if not name or name == "N/A" or name.lower() == "unknown":
        return False
    cleaned = name.strip()
    for prefix in ["Meet ", "About ", "Dr. ", "Prof. "]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    cleaned = cleaned.rstrip(".")
    words = cleaned.lower().split()
    if len(words) < 2 or len(words) > 5:
        return False
    if any(w.rstrip(".,;:") in _COMPANY_WORDS for w in words):
        return False
    if cleaned == cleaned.upper() and len(words) > 2:
        return False
    if any(c.isdigit() for c in cleaned):
        return False
    return True


def _clean_person_name(name: str) -> str:
    """Clean up a person name for email generation."""
    cleaned = name.strip()
    for prefix in ["Meet ", "About ", "Dr. ", "Prof. "]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return cleaned.rstrip(".").strip()


def _normalize(name_part: str) -> str:
    """Lowercase, strip accents, keep only ascii alpha chars."""
    nfkd = unicodedata.normalize("NFKD", name_part)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z]", "", ascii_only.lower())


def _extract_domain(website: str) -> Optional[str]:
    """Pull the bare domain from a website URL."""
    if not website or website == "N/A":
        return None
    try:
        parsed = urlparse(website if "://" in website else f"https://{website}")
        netloc = parsed.netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        return netloc if netloc else None
    except Exception:
        return None


def generate_candidates(name: str, domain: str) -> List[str]:
    """Generate all email pattern candidates for a given name + domain."""
    parts = name.strip().split()
    if len(parts) < 2:
        return []

    first = _normalize(parts[0])
    last = _normalize(parts[-1])

    if not first or not last:
        return []

    f = first[0]

    candidates = []
    for pattern in _PATTERNS:
        candidate = pattern.format(first=first, last=last, f=f, domain=domain)
        candidates.append(candidate)

    return candidates


def detect_pattern(email: str, name: str) -> Optional[str]:
    """
    Given a known email and the person's name, detect which pattern was used.
    Returns the pattern string (e.g. '{first}@{domain}') or None.
    """
    parts = name.strip().split()
    if len(parts) < 2:
        return None

    first = _normalize(parts[0])
    last = _normalize(parts[-1])
    if not first or not last:
        return None

    local, _, domain = email.partition("@")
    if not local or not domain:
        return None

    local = local.lower()
    f = first[0]

    for pattern in _PATTERNS:
        expected_local = pattern.split("@")[0].format(first=first, last=last, f=f, domain=domain)
        if local == expected_local:
            return pattern

    return None


class PatternStore:
    """
    Persistent pattern store that records ALL observed email patterns per domain
    with frequency counts. This enables statistical pattern selection — the most
    frequently observed pattern for a domain is used for future guesses.
    """

    def __init__(self, store_path: Optional[Path] = None):
        self._store_path = store_path or _PATTERN_STORE_PATH
        # domain -> {pattern: count}
        self._patterns: Dict[str, Dict[str, int]] = {}
        # domain -> best pattern (cached)
        self._best_pattern: Dict[str, str] = {}
        self._load()

    def _load(self):
        """Load persisted pattern data from disk."""
        try:
            if self._store_path.exists():
                with open(self._store_path) as f:
                    data = json.load(f)
                self._patterns = data.get("patterns", {})
                # Rebuild best pattern cache
                for domain, counts in self._patterns.items():
                    if counts:
                        self._best_pattern[domain] = max(counts, key=counts.get)
                logger.debug("Loaded pattern store: %d domains", len(self._patterns))
        except Exception as e:
            logger.debug("Could not load pattern store: %s", e)

    def save(self):
        """Persist pattern data to disk."""
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._store_path, "w") as f:
                json.dump({"patterns": self._patterns}, f, indent=2)
        except Exception as e:
            logger.debug("Could not save pattern store: %s", e)

    def get(self, domain: str) -> Optional[str]:
        """Get the best (most frequent) pattern for a domain."""
        return self._best_pattern.get(domain)

    def learn(self, domain: str, email: str, name: str) -> Optional[str]:
        """
        Detect and record the pattern for an observed email at a domain.
        Updates frequency counts and recalculates the best pattern.
        """
        pattern = detect_pattern(email, name)
        if not pattern:
            return None

        if domain not in self._patterns:
            self._patterns[domain] = {}

        self._patterns[domain][pattern] = self._patterns[domain].get(pattern, 0) + 1

        # Recalculate best pattern
        self._best_pattern[domain] = max(self._patterns[domain], key=self._patterns[domain].get)

        logger.debug("Learned pattern for %s: %s (count=%d)", domain, pattern, self._patterns[domain][pattern])
        return pattern

    def apply(self, name: str, domain: str) -> Optional[str]:
        """Apply the best learned pattern to generate an email."""
        pattern = self._best_pattern.get(domain)
        if not pattern:
            return None
        parts = name.strip().split()
        if len(parts) < 2:
            return None
        first = _normalize(parts[0])
        last = _normalize(parts[-1])
        if not first or not last:
            return None
        f = first[0]
        return pattern.format(first=first, last=last, f=f, domain=domain)

    @property
    def domains_known(self) -> int:
        return len(self._best_pattern)

    def get_statistics(self) -> dict:
        """
        Return comprehensive pattern statistics:
        - Total domains with learned patterns
        - Pattern distribution across all domains
        - Per-domain confidence (top pattern count / total observations)
        - Most common patterns globally
        """
        total_domains = len(self._patterns)
        total_observations = 0
        global_pattern_counts: Dict[str, int] = defaultdict(int)
        domain_stats = []

        for domain, counts in self._patterns.items():
            domain_total = sum(counts.values())
            total_observations += domain_total
            best_pattern = max(counts, key=counts.get) if counts else None
            best_count = counts.get(best_pattern, 0) if best_pattern else 0
            confidence = best_count / domain_total if domain_total > 0 else 0

            for pattern, count in counts.items():
                global_pattern_counts[pattern] += count

            domain_stats.append({
                "domain": domain,
                "best_pattern": best_pattern,
                "confidence": round(confidence, 3),
                "observations": domain_total,
                "patterns": dict(counts),
            })

        # Sort domains by observation count
        domain_stats.sort(key=lambda x: x["observations"], reverse=True)

        # Global pattern ranking
        global_ranking = sorted(global_pattern_counts.items(), key=lambda x: x[1], reverse=True)

        return {
            "total_domains": total_domains,
            "total_observations": total_observations,
            "global_pattern_ranking": [
                {"pattern": p, "count": c, "share": round(c / total_observations, 3) if total_observations > 0 else 0}
                for p, c in global_ranking
            ],
            "top_domains": domain_stats[:50],
        }


class EmailGuesser:
    """
    Generates email addresses for contacts using pattern detection and
    domain-level MX verification.

    v3 improvements:
    - Uses PatternStore with frequency-based learning
    - Persists patterns to disk across runs
    - Exposes statistics for pattern analysis
    """

    def __init__(self, concurrency: int = 10):
        self.validator = EmailValidator()
        self.concurrency = concurrency
        self._sem = asyncio.Semaphore(concurrency)
        self._pattern_store = PatternStore()
        self._mx_cache: dict[str, bool] = {}
        self._stats = {
            "attempted": 0, "found": 0, "skipped": 0,
            "pattern_hits": 0, "default_hits": 0, "mx_rejects": 0,
            "company_skipped": 0, "patterns_discovered": 0,
        }

    async def _discover_domain_pattern(self, name: str, domain: str) -> Optional[str]:
        """SMTP-verify top 3 candidates for one contact to discover domain's email pattern."""
        clean = _clean_person_name(name)
        candidates = generate_candidates(clean, domain)[:3]
        if not candidates:
            return None

        smtp_ok = await self.validator.smtp_self_test()
        if not smtp_ok:
            return None

        for candidate in candidates:
            async with self._sem:
                result = await self.validator.verify_smtp(candidate)
            if result.get("deliverable") is True:
                pattern = detect_pattern(candidate, clean)
                if pattern:
                    self._pattern_store.learn(domain, candidate, clean)
                    self._stats["patterns_discovered"] += 1
                    logger.info(f"  \U0001f50d  Discovered pattern for {domain}: {pattern} (via {candidate})")
                    return candidate
            await asyncio.sleep(0.5)

        return None

    async def _check_domain_mx(self, domain: str) -> bool:
        """Check MX once per domain (cached)."""
        if domain in self._mx_cache:
            return self._mx_cache[domain]
        async with self._sem:
            has_mx = await self.validator.verify_mx(f"probe@{domain}")
            self._mx_cache[domain] = has_mx
        return has_mx

    def _generate_best_email(self, name: str, domain: str) -> Optional[str]:
        """Generate the best email using learned pattern or statistical default."""
        clean = _clean_person_name(name)
        # Try learned pattern first
        email = self._pattern_store.apply(clean, domain)
        if email:
            return email
        # Fall back to default pattern
        parts = clean.strip().split()
        if len(parts) < 2:
            return None
        first = _normalize(parts[0])
        last = _normalize(parts[-1])
        if not first or not last:
            return None
        f = first[0]
        return _DEFAULT_PATTERN.format(first=first, last=last, f=f, domain=domain)

    async def guess(self, name: str, website: str) -> Optional[str]:
        """Generate the best email guess for a single contact."""
        if not _is_person_name(name):
            self._stats["company_skipped"] += 1
            return None

        domain = _extract_domain(website)
        if not domain:
            self._stats["skipped"] += 1
            return None

        has_mx = await self._check_domain_mx(domain)
        if not has_mx:
            self._stats["mx_rejects"] += 1
            return None

        self._stats["attempted"] += 1

        email = self._generate_best_email(name, domain)
        if email:
            self._stats["found"] += 1
            self._stats["default_hits"] += 1
            logger.debug(f"  ✉️  Guessed email: {email}")
        return email

    def generate_all_candidates(self, name: str, website: str) -> List[str]:
        """Generate ALL plausible email candidates, ranked by likelihood."""
        domain = _extract_domain(website)
        if not domain or not _is_person_name(name):
            return []
        return generate_candidates(name, domain)

    async def guess_batch(self, leads: list) -> list:
        """
        Run email guessing across a batch of InvestorLead objects.
        Phase 1: Learn patterns from leads that already have emails.
        Phase 2: Apply learned patterns to leads without emails.
        Phase 3: For remaining, check domain MX + apply default pattern.
        """
        # Phase 1: Learn patterns from existing emails
        for lead in leads:
            if lead.email and lead.email not in ("N/A", "N/A (invalid)") and "@" in lead.email:
                domain = _extract_domain(lead.website)
                if domain and _is_person_name(lead.name):
                    self._pattern_store.learn(domain, lead.email, lead.name)

        no_email = [
            lead for lead in leads
            if not lead.email or lead.email in ("N/A", "N/A (invalid)")
        ]

        logger.info(f"  \u2709\ufe0f  Email guesser: {len(no_email)} leads without email (of {len(leads)} total)")
        logger.info(f"  \U0001f511  Patterns learned for {self._pattern_store.domains_known} domains")

        # Phase 1.5: Discover patterns via SMTP for unknown domains
        domains_to_probe = {}
        for lead in no_email:
            if not _is_person_name(lead.name):
                continue
            domain = _extract_domain(lead.website)
            if domain and not self._pattern_store.get(domain) and domain not in domains_to_probe:
                domains_to_probe[domain] = lead

        if domains_to_probe:
            logger.info(f"  \U0001f50d  Probing {len(domains_to_probe)} domains for email patterns via SMTP...")
            for domain, lead in domains_to_probe.items():
                await self._discover_domain_pattern(lead.name, domain)
            logger.info(f"  \U0001f50d  Pattern discovery complete: {self._stats['patterns_discovered']} patterns found")

        # Phase 2: Apply known patterns
        still_no_email = []
        for lead in no_email:
            if not _is_person_name(lead.name):
                self._stats["company_skipped"] += 1
                still_no_email.append(lead)
                continue
            domain = _extract_domain(lead.website)
            if domain:
                email = self._pattern_store.apply(lead.name, domain)
                if email:
                    lead.email = email
                    self._stats["pattern_hits"] += 1
                    continue
            still_no_email.append(lead)

        # Phase 3: Check domain MX once, then apply default pattern
        async def _process(lead):
            if not _is_person_name(lead.name):
                return
            guessed = await self.guess(lead.name, lead.website)
            if guessed:
                lead.email = guessed
                domain = _extract_domain(lead.website)
                if domain:
                    self._pattern_store.learn(domain, guessed, lead.name)

        await asyncio.gather(*[_process(lead) for lead in still_no_email])

        # Persist learned patterns
        self._pattern_store.save()

        found = sum(1 for lead in no_email if lead.email and lead.email not in ("N/A", "N/A (invalid)"))
        logger.info(
            f"  \u2709\ufe0f  Email guesser complete: {found}/{len(no_email)} emails generated "
            f"({self._stats['pattern_hits']} from learned patterns, "
            f"{self._stats['patterns_discovered']} patterns discovered via SMTP, "
            f"{self._stats['default_hits']} from default pattern, "
            f"{self._stats['mx_rejects']} domains had no MX, "
            f"{self._stats['company_skipped']} company names skipped)"
        )
        return leads

    @property
    def stats(self) -> dict:
        return dict(self._stats)

    @property
    def pattern_statistics(self) -> dict:
        """Expose pattern learning statistics for API/dashboard."""
        return self._pattern_store.get_statistics()
