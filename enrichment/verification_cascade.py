"""
CRAWL — Verification Cascade
Orchestrates multi-provider email verification with fallbacks.

Pipeline: format → disposable → role → MX → SMTP → external API
External providers (Hunter, ZeroBounce, MillionVerifier) are tried in
priority order. If one fails or gives an inconclusive result, the next
provider is tried. API keys are loaded from environment variables.
"""

import asyncio
import logging
import os
from typing import Dict, List, Optional

import aiohttp

from enrichment.email_validator import EmailValidator

logger = logging.getLogger(__name__)


class ExternalVerifier:
    """Base class for external email verification providers."""

    name: str = "base"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.calls_made = 0

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def verify(self, session: aiohttp.ClientSession, email: str) -> Optional[dict]:
        """
        Verify a single email. Returns:
        {"deliverable": bool|None, "provider": str, "confidence": float, "reason": str}
        or None if provider can't answer.
        """
        raise NotImplementedError


class HunterVerifier(ExternalVerifier):
    """Hunter.io Email Verifier."""

    name = "hunter"

    async def verify(self, session: aiohttp.ClientSession, email: str) -> Optional[dict]:
        if not self.api_key:
            return None
        try:
            async with session.get(
                "https://api.hunter.io/v2/email-verifier",
                params={"email": email, "api_key": self.api_key},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 429:
                    logger.debug("[hunter] Rate limited for %s", email)
                    return None
                if resp.status != 200:
                    return None
                data = (await resp.json()).get("data", {})
                self.calls_made += 1
                status = data.get("status", "")
                return {
                    "deliverable": status == "valid",
                    "provider": self.name,
                    "confidence": data.get("score", 0) / 100.0,
                    "reason": data.get("status", "unknown"),
                }
        except Exception as e:
            logger.debug("[hunter] Error verifying %s: %s", email, e)
            return None


class ZeroBounceVerifier(ExternalVerifier):
    """ZeroBounce Email Verifier."""

    name = "zerobounce"

    async def verify(self, session: aiohttp.ClientSession, email: str) -> Optional[dict]:
        if not self.api_key:
            return None
        try:
            async with session.get(
                "https://api.zerobounce.net/v2/validate",
                params={"api_key": self.api_key, "email": email},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 429:
                    logger.debug("[zerobounce] Rate limited for %s", email)
                    return None
                if resp.status != 200:
                    return None
                data = await resp.json()
                self.calls_made += 1
                status = data.get("status", "").lower()
                deliverable = True if status == "valid" else (False if status == "invalid" else None)
                return {
                    "deliverable": deliverable,
                    "provider": self.name,
                    "confidence": 0.95 if deliverable is not None else 0.5,
                    "reason": data.get("sub_status", status),
                }
        except Exception as e:
            logger.debug("[zerobounce] Error verifying %s: %s", email, e)
            return None


class MillionVerifierClient(ExternalVerifier):
    """MillionVerifier Email Verifier."""

    name = "millionverifier"

    async def verify(self, session: aiohttp.ClientSession, email: str) -> Optional[dict]:
        if not self.api_key:
            return None
        try:
            async with session.get(
                "https://api.millionverifier.com/api/v3/",
                params={"api": self.api_key, "email": email},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 429:
                    logger.debug("[millionverifier] Rate limited for %s", email)
                    return None
                if resp.status != 200:
                    return None
                data = await resp.json()
                self.calls_made += 1
                result_code = data.get("result", "").lower()
                deliverable = True if result_code == "ok" else (False if result_code in ("invalid", "disposable") else None)
                return {
                    "deliverable": deliverable,
                    "provider": self.name,
                    "confidence": data.get("quality", 0.5),
                    "reason": result_code,
                }
        except Exception as e:
            logger.debug("[millionverifier] Error verifying %s: %s", email, e)
            return None


class VerificationCascade:
    """
    Orchestrates the full email verification cascade:
    1. EmailValidator (format + disposable + role + MX)
    2. SMTP verification
    3. External API providers (waterfall)

    Falls back through providers in priority order until a definitive
    answer is obtained.
    """

    def __init__(self, validator: Optional[EmailValidator] = None):
        self.validator = validator or EmailValidator()
        self._providers: List[ExternalVerifier] = []
        self._init_providers()
        self._stats = {
            "total_verified": 0,
            "format_failures": 0,
            "disposable_detected": 0,
            "role_based_detected": 0,
            "mx_failures": 0,
            "smtp_verified": 0,
            "external_verified": 0,
            "inconclusive": 0,
        }

    def _init_providers(self):
        """Initialize external verification providers from environment."""
        providers = [
            (HunterVerifier, "HUNTER_API_KEY"),
            (ZeroBounceVerifier, "ZEROBOUNCE_API_KEY"),
            (MillionVerifierClient, "MILLIONVERIFIER_API_KEY"),
        ]
        for cls, env_key in providers:
            key = os.environ.get(env_key)
            if key:
                self._providers.append(cls(api_key=key))
                logger.info("External verifier enabled: %s", cls.name)

    async def verify(self, email: str, use_smtp: bool = True, use_external: bool = True) -> dict:
        """
        Full cascade verification of a single email.

        Returns:
            {
                "email": str,
                "valid_format": bool,
                "is_disposable": bool,
                "is_role_based": bool,
                "has_mx": Optional[bool],
                "quality": str,
                "smtp_deliverable": Optional[bool],
                "external_result": Optional[dict],
                "final_verdict": "valid" | "invalid" | "risky" | "unknown",
                "confidence": float,
            }
        """
        self._stats["total_verified"] += 1

        # Step 1: Basic validation (format + disposable + role + MX)
        basic = self.validator.validate(email)
        result = {
            **basic,
            "smtp_deliverable": None,
            "external_result": None,
            "final_verdict": "unknown",
            "confidence": 0.0,
        }

        if not basic["valid_format"]:
            self._stats["format_failures"] += 1
            result["final_verdict"] = "invalid"
            result["confidence"] = 1.0
            return result

        if basic["is_disposable"]:
            self._stats["disposable_detected"] += 1
            result["final_verdict"] = "invalid"
            result["confidence"] = 0.95
            return result

        if basic["is_role_based"]:
            self._stats["role_based_detected"] += 1
            result["final_verdict"] = "risky"
            result["confidence"] = 0.7
            return result

        if basic.get("has_mx") is False:
            self._stats["mx_failures"] += 1
            result["final_verdict"] = "invalid"
            result["confidence"] = 0.9
            return result

        # Step 2: SMTP verification (optional)
        if use_smtp:
            smtp_result = await self.validator.verify_smtp(email)
            result["smtp_deliverable"] = smtp_result.get("deliverable")
            if smtp_result.get("deliverable") is True:
                self._stats["smtp_verified"] += 1
                if smtp_result.get("catch_all"):
                    result["final_verdict"] = "risky"
                    result["confidence"] = 0.6
                else:
                    result["final_verdict"] = "valid"
                    result["confidence"] = 0.9
                return result
            elif smtp_result.get("deliverable") is False:
                result["final_verdict"] = "invalid"
                result["confidence"] = 0.95
                return result

        # Step 3: External API providers (waterfall)
        if use_external and self._providers:
            async with aiohttp.ClientSession() as session:
                for provider in self._providers:
                    if not provider.available:
                        continue
                    ext_result = await provider.verify(session, email)
                    if ext_result and ext_result.get("deliverable") is not None:
                        result["external_result"] = ext_result
                        self._stats["external_verified"] += 1
                        if ext_result["deliverable"]:
                            result["final_verdict"] = "valid"
                            result["confidence"] = ext_result.get("confidence", 0.8)
                        else:
                            result["final_verdict"] = "invalid"
                            result["confidence"] = ext_result.get("confidence", 0.8)
                        return result

        # No definitive answer from any source
        self._stats["inconclusive"] += 1
        if basic.get("has_mx"):
            result["final_verdict"] = "risky"
            result["confidence"] = 0.4
        else:
            result["final_verdict"] = "unknown"
            result["confidence"] = 0.2
        return result

    async def verify_batch(self, emails: List[str], concurrency: int = 10) -> Dict[str, dict]:
        """Verify a batch of emails with concurrency control."""
        sem = asyncio.Semaphore(concurrency)
        results = {}

        async def _verify_one(email: str):
            async with sem:
                results[email] = await self.verify(email)

        await asyncio.gather(*[_verify_one(e) for e in emails])
        return results

    @property
    def stats(self) -> dict:
        provider_stats = {p.name: p.calls_made for p in self._providers}
        return {**self._stats, "provider_calls": provider_stats}
