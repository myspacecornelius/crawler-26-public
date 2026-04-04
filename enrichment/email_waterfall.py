"""
CRAWL — Email Waterfall Verification

Multi-provider email verification pipeline for contacts where SMTP verification
is inconclusive (catch-all domains, timeouts, greylisting). Falls through
providers in priority order until a definitive answer is obtained.

Provider waterfall:
  1. Hunter.io (free tier: 25 verifications/month)
  2. ZeroBounce (free tier: 100 verifications/month)
  3. MillionVerifier (free tier: 200 verifications/month)

Usage:
    from enrichment.email_waterfall import EmailWaterfall
    waterfall = EmailWaterfall()
    results = await waterfall.verify_batch(leads)

Config keys via env vars:
    HUNTER_API_KEY, ZEROBOUNCE_API_KEY, MILLIONVERIFIER_API_KEY
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# ── Provider Base ────────────────────────────────

class VerificationProvider:
    """Base class for email verification providers."""

    name: str = "base"
    requires_key: bool = True

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.calls_made = 0

    async def verify(
        self, session: aiohttp.ClientSession, email: str
    ) -> Optional[Dict[str, any]]:
        """
        Verify a single email. Returns:
        {
            "deliverable": True/False/None,
            "provider": "name",
            "confidence": 0.0-1.0,
            "reason": "human-readable reason",
        }
        Returns None if the provider can't give a definitive answer.
        """
        raise NotImplementedError


# ── Hunter.io ────────────────────────────────────

class HunterVerifier(VerificationProvider):
    """Hunter.io Email Verifier (free: 25/month)."""

    name = "hunter"

    async def verify(self, session: aiohttp.ClientSession, email: str) -> Optional[dict]:
        if not self.api_key:
            return None
        params = {"email": email, "api_key": self.api_key}
        try:
            async with session.get(
                "https://api.hunter.io/v2/email-verifier",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 429:
                    logger.debug(f"  [{self.name}] Rate limited")
                    return None
                if resp.status != 200:
                    return None
                data = await resp.json()
                result = data.get("data", {})
                status = result.get("result", "unknown")
                self.calls_made += 1

                if status == "deliverable":
                    return {
                        "deliverable": True,
                        "provider": self.name,
                        "confidence": result.get("score", 90) / 100,
                        "reason": "Hunter: deliverable",
                    }
                elif status == "undeliverable":
                    return {
                        "deliverable": False,
                        "provider": self.name,
                        "confidence": 0.95,
                        "reason": f"Hunter: {result.get('status', 'undeliverable')}",
                    }
                elif status == "risky":
                    return {
                        "deliverable": None,  # Inconclusive
                        "provider": self.name,
                        "confidence": 0.5,
                        "reason": f"Hunter: risky ({result.get('status', 'unknown')})",
                    }
                return None
        except Exception as e:
            logger.debug(f"  [{self.name}] Error: {e}")
            return None


# ── ZeroBounce ───────────────────────────────────

class ZeroBounceVerifier(VerificationProvider):
    """ZeroBounce Email Verifier (free: 100/month)."""

    name = "zerobounce"

    async def verify(self, session: aiohttp.ClientSession, email: str) -> Optional[dict]:
        if not self.api_key:
            return None
        params = {"api_key": self.api_key, "email": email}
        try:
            async with session.get(
                "https://api.zerobounce.net/v2/validate",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                status = data.get("status", "").lower()
                self.calls_made += 1

                if status == "valid":
                    return {
                        "deliverable": True,
                        "provider": self.name,
                        "confidence": 0.95,
                        "reason": f"ZeroBounce: valid ({data.get('sub_status', '')})",
                    }
                elif status == "invalid":
                    return {
                        "deliverable": False,
                        "provider": self.name,
                        "confidence": 0.95,
                        "reason": f"ZeroBounce: invalid ({data.get('sub_status', '')})",
                    }
                elif status == "catch-all":
                    return {
                        "deliverable": None,
                        "provider": self.name,
                        "confidence": 0.4,
                        "reason": "ZeroBounce: catch-all domain",
                    }
                return None
        except Exception as e:
            logger.debug(f"  [{self.name}] Error: {e}")
            return None


# ── MillionVerifier ──────────────────────────────

class MillionVerifier(VerificationProvider):
    """MillionVerifier (free: 200/month)."""

    name = "millionverifier"

    async def verify(self, session: aiohttp.ClientSession, email: str) -> Optional[dict]:
        if not self.api_key:
            return None
        params = {"api": self.api_key, "email": email}
        try:
            async with session.get(
                "https://api.millionverifier.com/api/v3/",
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                result_label = data.get("resultcode", 0)
                self.calls_made += 1

                # resultcode: 1=ok, 2=catch_all, 3=unknown, 4=error, 5=disposable, 6=invalid
                if result_label == 1:
                    return {
                        "deliverable": True,
                        "provider": self.name,
                        "confidence": 0.90,
                        "reason": "MillionVerifier: ok",
                    }
                elif result_label in (4, 5, 6):
                    return {
                        "deliverable": False,
                        "provider": self.name,
                        "confidence": 0.90,
                        "reason": f"MillionVerifier: {data.get('result', 'invalid')}",
                    }
                elif result_label == 2:
                    return {
                        "deliverable": None,
                        "provider": self.name,
                        "confidence": 0.4,
                        "reason": "MillionVerifier: catch-all",
                    }
                return None
        except Exception as e:
            logger.debug(f"  [{self.name}] Error: {e}")
            return None


# ── Waterfall Orchestrator ───────────────────────

PROVIDER_CLASSES = [HunterVerifier, ZeroBounceVerifier, MillionVerifier]


class EmailWaterfall:
    """
    Multi-provider email verification waterfall.
    Falls through providers until a definitive deliverable/undeliverable answer.

    Domain-level caching: when a domain is confirmed as catch-all by one provider,
    subsequent emails at that domain skip the waterfall entirely (saves API credits).
    When a domain is confirmed as having valid individual mailboxes, provider results
    are trusted for the whole domain's pattern.
    """

    def __init__(self):
        self.providers: List[VerificationProvider] = []
        self._domain_cache: Dict[str, Dict] = {}  # domain → {"catch_all": bool, "provider": str}
        for cls in PROVIDER_CLASSES:
            env_key = f"{cls.name.upper()}_API_KEY"
            api_key = os.environ.get(env_key)
            if api_key:
                self.providers.append(cls(api_key=api_key))
                logger.info(f"  ✅  {cls.name} waterfall provider active")

        if not self.providers:
            logger.info("  ⚠️  No email waterfall providers configured (set API keys via env vars)")

    async def verify_single(
        self, session: aiohttp.ClientSession, email: str
    ) -> Dict[str, any]:
        """
        Verify a single email through the provider waterfall.
        Returns the best result from the first provider with a definitive answer.

        Uses domain-level caching: if a domain is already known to be catch-all,
        skip the waterfall entirely and return inconclusive (saves API credits).
        """
        domain = email.rsplit("@", 1)[1].lower() if "@" in email else ""
        if not hasattr(self, '_domain_cache'):
            self._domain_cache = {}
        cached_domain = self._domain_cache.get(domain)
        if cached_domain and cached_domain.get("catch_all"):
            return {
                "deliverable": None,
                "provider": "waterfall_cache",
                "confidence": 0.4,
                "reason": f"Domain {domain} is catch-all (cached from {cached_domain.get('provider', 'unknown')})",
            }

        for provider in self.providers:
            result = await provider.verify(session, email)
            if result and result.get("deliverable") is not None:
                # Cache domain-level insight
                if domain and domain not in self._domain_cache:
                    self._domain_cache[domain] = {
                        "provider": result.get("provider", ""),
                        "catch_all": False,
                    }
                return result
            # If provider returned catch-all, cache it
            if result and result.get("reason") and "catch-all" in result.get("reason", "").lower():
                if domain:
                    self._domain_cache[domain] = {
                        "provider": result.get("provider", ""),
                        "catch_all": True,
                    }
                    logger.debug("Domain %s cached as catch-all via %s", domain, result.get("provider"))
            # If inconclusive, continue to next provider
            await asyncio.sleep(0.2)  # Polite delay between providers

        # No definitive answer from any provider
        return {
            "deliverable": None,
            "provider": "waterfall",
            "confidence": 0.0,
            "reason": "No provider could verify",
        }

    async def verify_batch(
        self,
        leads: list,
        max_concurrent: int = 5,
    ) -> list:
        """
        Verify emails for leads that have catch-all or unknown email status.
        Updates lead.email_status in place and returns the updated leads list.
        """
        if not self.providers:
            return leads

        # Only verify leads with inconclusive status
        candidates = [
            lead for lead in leads
            if getattr(lead, "email_status", "") in ("catch_all", "unknown", "guessed")
            and getattr(lead, "email", "") not in ("N/A", "", None)
            and "@" in getattr(lead, "email", "")
        ]

        if not candidates:
            print("  ⚠️  No candidates for waterfall verification")
            return leads

        print(f"  🔄  Waterfall verification on {len(candidates)} emails "
              f"({', '.join(p.name for p in self.providers)})")

        sem = asyncio.Semaphore(max_concurrent)
        verified = 0
        rejected = 0

        async with aiohttp.ClientSession() as session:
            async def _verify_lead(lead):
                nonlocal verified, rejected
                async with sem:
                    result = await self.verify_single(session, lead.email)

                    if result["deliverable"] is True:
                        lead.email_status = "verified"
                        verified += 1
                    elif result["deliverable"] is False:
                        lead.email_status = "undeliverable"
                        rejected += 1
                    # else: stays as-is (inconclusive)

            tasks = [_verify_lead(lead) for lead in candidates]
            await asyncio.gather(*tasks)

        # Print stats
        print(f"  📧  Waterfall results: {verified} verified, {rejected} rejected, "
              f"{len(candidates) - verified - rejected} inconclusive")
        for p in self.providers:
            if p.calls_made:
                print(f"      {p.name}: {p.calls_made} calls")

        return leads
