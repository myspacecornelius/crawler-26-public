"""
CRAWL — Email Validator
Validates email addresses via cascading checks:
  format → disposable → role-based → MX record → SMTP verification.

Configuration is loaded from config/email_validation.yaml so that disposable
domains and role prefixes can be updated without redeploying code.
"""

import re
import os
import asyncio
import logging
import socket
import subprocess
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "email_validation.yaml"


def _load_email_config() -> dict:
    """Load email validation config from YAML, with sensible defaults."""
    try:
        if _CONFIG_PATH.exists():
            with open(_CONFIG_PATH) as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed to load email validation config: %s", e)
    return {}


def _load_set_from_config(key: str, defaults: set) -> set:
    """Load a set from YAML config, falling back to built-in defaults."""
    cfg = _load_email_config()
    items = cfg.get(key, [])
    if items:
        return set(items)
    return defaults


# ── Defaults (used when config file is missing) ──
_DEFAULT_DISPOSABLE_DOMAINS = {
    "tempmail.com", "throwaway.email", "guerrillamail.com", "mailinator.com",
    "yopmail.com", "trashmail.com", "fakeinbox.com", "sharklasers.com",
    "grr.la", "dispostable.com", "10minutemail.com",
}

_DEFAULT_ROLE_PREFIXES = {
    "info", "contact", "hello", "admin", "support", "team", "office",
    "press", "media", "sales", "marketing", "noreply", "no-reply",
}

# ── Load from config (centralised, updatable without code changes) ──
DISPOSABLE_DOMAINS = _load_set_from_config("disposable_domains", _DEFAULT_DISPOSABLE_DOMAINS)
ROLE_PREFIXES = _load_set_from_config("role_prefixes", _DEFAULT_ROLE_PREFIXES)


class EmailValidator:
    """
    Multi-layer email validation with cascading strategy:
    1. Format validation (regex)
    2. Disposable domain detection
    3. Role-based address detection
    4. MX record verification (async DNS lookup)
    5. SMTP deliverability check (optional)

    MX checks are integrated directly into validate() — unknown or
    unreachable domains degrade quality rather than defaulting to "high".
    DNS/network errors result in "medium" quality and flag for retry.
    """

    def __init__(self):
        self._mx_cache: dict[str, bool] = {}  # domain → has_mx
        self._mx_host_cache: dict[str, str] = {}  # domain → best MX host
        self._smtp_cache: dict[str, dict] = {}  # email → smtp result
        self._catch_all_cache: dict[str, bool] = {}  # domain → is_catch_all
        self._dns_error_domains: set[str] = set()  # domains with DNS errors (for retry)
        self._pattern = re.compile(
            r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        )
        # ── SMTP configuration from environment ──
        self._smtp_timeout = int(os.environ.get("SMTP_TIMEOUT", "10"))
        self._smtp_helo_domain = os.environ.get(
            "SMTP_HELO_DOMAIN",
            socket.getfqdn() if socket.getfqdn() != "localhost" else "mail.leadfactory.io",
        )
        self._smtp_proxy_host = os.environ.get("SMTP_PROXY_HOST", "")
        self._smtp_proxy_port = int(os.environ.get("SMTP_PROXY_PORT", "25"))
        self._smtp_available: Optional[bool] = None  # None = not tested yet

        # Load validation settings from config
        cfg = _load_email_config()
        val_cfg = cfg.get("validation", {})
        self._mx_timeout = val_cfg.get("mx_check_timeout", 10)
        self._max_retries = val_cfg.get("max_retries", 2)
        self._retry_on_dns_error = val_cfg.get("retry_on_dns_error", True)

    def validate(self, email: str) -> dict:
        """
        Validate an email address using cascading checks.

        Returns:
            {
                "email": str,
                "valid_format": bool,
                "is_disposable": bool,
                "is_role_based": bool,
                "has_mx": bool | None,
                "dns_error": bool,
                "needs_retry": bool,
                "quality": "high" | "medium" | "low" | "invalid"
            }
        """
        result = {
            "email": email,
            "valid_format": False,
            "is_disposable": False,
            "is_role_based": False,
            "has_mx": None,
            "dns_error": False,
            "needs_retry": False,
            "quality": "invalid",
        }

        if not email or email == "N/A":
            return result

        email = email.strip().lower()
        result["email"] = email

        # Step 1: Format check
        if not self._pattern.match(email):
            return result
        result["valid_format"] = True

        local, domain = email.rsplit("@", 1)

        # Step 2: Disposable domain check
        if domain in DISPOSABLE_DOMAINS:
            result["is_disposable"] = True
            result["quality"] = "low"
            return result

        # Step 3: Role-based prefix check
        if local in ROLE_PREFIXES:
            result["is_role_based"] = True
            result["quality"] = "medium"
            return result

        # Step 4: MX record check (synchronous, using cache)
        mx_result = self._check_mx_sync(domain)
        result["has_mx"] = mx_result["has_mx"]
        result["dns_error"] = mx_result["dns_error"]

        if mx_result["dns_error"]:
            # DNS/network error → medium quality, flag for retry
            result["quality"] = "medium"
            result["needs_retry"] = self._retry_on_dns_error
            self._dns_error_domains.add(domain)
            return result

        if mx_result["has_mx"] is False:
            # No MX records → domain can't receive email → low quality
            result["quality"] = "low"
            return result

        # All checks passed
        result["quality"] = "high"
        return result

    def _check_mx_sync(self, domain: str) -> dict:
        """
        Synchronous MX check with caching.
        Returns {"has_mx": bool|None, "dns_error": bool}
        """
        # Check cache first
        if domain in self._mx_cache:
            return {"has_mx": self._mx_cache[domain], "dns_error": False}

        try:
            import dns.resolver
            answers = dns.resolver.resolve(domain, "MX", lifetime=self._mx_timeout)
            has_mx = len(answers) > 0
            self._mx_cache[domain] = has_mx
            return {"has_mx": has_mx, "dns_error": False}
        except ImportError:
            # dnspython not installed — can't check MX, assume valid
            self._mx_cache[domain] = True
            return {"has_mx": True, "dns_error": False}
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            # Domain doesn't exist or has no MX records
            self._mx_cache[domain] = False
            return {"has_mx": False, "dns_error": False}
        except Exception:
            # DNS timeout, network error — treat as "medium" quality
            return {"has_mx": None, "dns_error": True}

    async def verify_mx(self, email: str) -> bool:
        """
        Check if the email's domain has valid MX records.
        Uses async DNS resolution with caching.
        """
        if not email or "@" not in email:
            return False

        domain = email.rsplit("@", 1)[1].lower()

        # Check cache
        if domain in self._mx_cache:
            return self._mx_cache[domain]

        try:
            import dns.resolver

            loop = asyncio.get_running_loop()
            answers = await loop.run_in_executor(
                None, lambda: dns.resolver.resolve(domain, "MX")
            )
            has_mx = len(answers) > 0
        except Exception:
            has_mx = True

        self._mx_cache[domain] = has_mx
        return has_mx

    def _resolve_mx_host_sync(self, domain: str) -> Optional[str]:
        """Resolve MX host synchronously with dnspython, falling back to nslookup."""
        # --- attempt 1: dnspython ---
        try:
            import dns.resolver
            mx_records = dns.resolver.resolve(domain, "MX")
            mx_host = str(sorted(mx_records, key=lambda r: r.preference)[0].exchange).rstrip(".")
            logger.debug("MX %s → %s (dnspython)", domain, mx_host)
            return mx_host
        except ImportError:
            logger.debug("MX %s → dnspython not available, trying nslookup", domain)
        except Exception as e:
            logger.debug("MX %s → dnspython error: %s, trying nslookup", domain, e)

        # --- attempt 2: nslookup subprocess fallback ---
        try:
            out = subprocess.run(
                ["nslookup", "-type=mx", domain],
                capture_output=True, text=True, timeout=self._smtp_timeout,
            )
            best_pref = 999999
            best_host = None
            for line in out.stdout.splitlines():
                line = line.strip()
                if "mail exchanger" in line.lower():
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        tokens = parts[1].strip().split()
                        if len(tokens) >= 2:
                            try:
                                pref = int(tokens[0])
                            except ValueError:
                                pref = 50
                            host = tokens[1].rstrip(".")
                            if pref < best_pref:
                                best_pref = pref
                                best_host = host
            if best_host:
                logger.debug("MX %s → %s (nslookup)", domain, best_host)
                return best_host
            logger.debug("MX %s → no MX in nslookup output", domain)
        except Exception as e:
            logger.debug("MX %s → nslookup fallback error: %s", domain, e)

        # --- attempt 3: assume domain itself accepts mail ---
        try:
            socket.getaddrinfo(domain, 25, socket.AF_INET)
            logger.debug("MX %s → using domain itself (A-record fallback)", domain)
            return domain
        except Exception:
            pass

        logger.debug("MX %s → resolution failed entirely", domain)
        return None

    async def _resolve_mx_host(self, domain: str) -> Optional[str]:
        """Resolve and cache the best MX host for a domain."""
        if domain in self._mx_host_cache:
            cached = self._mx_host_cache[domain]
            return cached if cached else None
        loop = asyncio.get_running_loop()
        mx_host = await loop.run_in_executor(None, self._resolve_mx_host_sync, domain)
        self._mx_host_cache[domain] = mx_host or ""
        return mx_host

    async def smtp_self_test(self) -> bool:
        """Test if outbound SMTP (port 25) is available from this network."""
        if self._smtp_available is not None:
            return self._smtp_available

        if self._smtp_proxy_host:
            test_host = self._smtp_proxy_host
            test_port = self._smtp_proxy_port
            logger.info("SMTP self-test: testing proxy %s:%d", test_host, test_port)
        else:
            test_host = "gmail-smtp-in.l.google.com"
            test_port = 25
            logger.info("SMTP self-test: testing direct connection to %s:%d", test_host, test_port)

        loop = asyncio.get_running_loop()

        def _probe():
            import smtplib
            for port in ([test_port] if test_port != 25 else [25, 587]):
                try:
                    smtp = smtplib.SMTP(timeout=self._smtp_timeout)
                    smtp.connect(test_host, port)
                    code, _ = smtp.ehlo(self._smtp_helo_domain)
                    smtp.quit()
                    if code == 250:
                        logger.info("SMTP self-test: port %d EHLO OK on %s", port, test_host)
                        return True
                    logger.debug("SMTP self-test: port %d EHLO code %d on %s", port, code, test_host)
                except OSError as e:
                    logger.debug("SMTP self-test: port %d failed on %s — %s", port, test_host, e)
                except Exception as e:
                    logger.debug("SMTP self-test: port %d SMTP error on %s — %s", port, test_host, e)
            return False

        self._smtp_available = await loop.run_in_executor(None, _probe)

        if not self._smtp_available:
            logger.warning(
                "\n⚠️  Outbound SMTP (port 25/587) appears blocked on this network.\n"
                "    SMTP verification will be skipped. Emails tagged as 'guessed' only.\n"
                "    To enable: use a network that allows port 25, or set SMTP_PROXY_HOST env var."
            )
        return self._smtp_available

    def _smtp_connect(self, host: str, port: int):
        """Create an SMTP connection, trying the given port first, then 587 fallback."""
        import smtplib
        ports = [port]
        if port == 25:
            ports.append(587)
        last_err = None
        for p in ports:
            try:
                smtp = smtplib.SMTP(timeout=self._smtp_timeout)
                smtp.connect(host, p)
                logger.debug("SMTP connect %s:%d → OK", host, p)
                return smtp
            except Exception as e:
                logger.debug("SMTP connect %s:%d → FAILED (%s)", host, p, e)
                last_err = e
        raise last_err  # type: ignore[misc]

    async def verify_smtp(self, email: str) -> dict:
        """
        SMTP-level deliverability check using RCPT TO.
        Returns {"deliverable": bool, "smtp_code": int, "catch_all": bool}.
        """
        result = {"deliverable": None, "smtp_code": 0, "catch_all": False}

        if not email or "@" not in email:
            result["deliverable"] = False
            return result

        domain = email.rsplit("@", 1)[1].lower()

        cache_key = f"smtp:{email}"
        if cache_key in self._smtp_cache:
            return self._smtp_cache[cache_key]

        if self._smtp_available is False:
            logger.debug("SMTP %s → skipped (SMTP blocked)", email)
            self._smtp_cache[cache_key] = result
            return result

        try:
            import smtplib

            loop = asyncio.get_running_loop()

            if self._smtp_proxy_host:
                connect_host = self._smtp_proxy_host
                connect_port = self._smtp_proxy_port
                logger.debug("SMTP %s → using proxy %s:%d", email, connect_host, connect_port)
            else:
                mx_host = await self._resolve_mx_host(domain)
                if not mx_host:
                    logger.debug("SMTP %s → no MX record → deliverable=None", email)
                    self._smtp_cache[cache_key] = result
                    return result
                connect_host = mx_host
                connect_port = 25

            helo_domain = self._smtp_helo_domain

            def _smtp_check():
                try:
                    smtp = self._smtp_connect(connect_host, connect_port)

                    code_ehlo, msg_ehlo = smtp.ehlo(helo_domain)
                    if code_ehlo != 250:
                        logger.debug("SMTP %s → EHLO rejected (%d), trying HELO", email, code_ehlo)
                        code_ehlo, msg_ehlo = smtp.helo(helo_domain)
                    logger.debug("SMTP %s → EHLO/HELO %s → %d", email, helo_domain, code_ehlo)
                    if code_ehlo not in (250,):
                        logger.debug("SMTP %s → greeting rejected (%d) → giving up", email, code_ehlo)
                        try:
                            smtp.quit()
                        except Exception:
                            pass
                        return 0

                    sender = f"verify@{helo_domain}"
                    code_mail, msg_mail = smtp.mail(sender)
                    logger.debug("SMTP %s → MAIL FROM <%s> → %d", email, sender, code_mail)
                    if code_mail != 250:
                        smtp.rset()
                        code_mail, msg_mail = smtp.mail("")
                        logger.debug("SMTP %s → MAIL FROM <> (retry) → %d", email, code_mail)
                    if code_mail != 250:
                        logger.debug("SMTP %s → MAIL FROM rejected (%d) → giving up", email, code_mail)
                        try:
                            smtp.quit()
                        except Exception:
                            pass
                        return 0

                    code, msg = smtp.rcpt(email)
                    logger.debug("SMTP %s → RCPT TO → %d %s", email, code, msg)
                    try:
                        smtp.quit()
                    except Exception:
                        pass
                    return code
                except smtplib.SMTPServerDisconnected as e:
                    logger.debug("SMTP %s → server disconnected: %s", email, e)
                    return 0
                except (TimeoutError, socket.timeout, OSError) as e:
                    logger.debug("SMTP %s → timeout/connection error: %s", email, e)
                    return -1
                except Exception as e:
                    logger.debug("SMTP %s → unexpected error: %s", email, e)
                    return 0

            code = await loop.run_in_executor(None, _smtp_check)
            result["smtp_code"] = code

            if code == 250:
                result["deliverable"] = True
                if domain in self._catch_all_cache:
                    result["catch_all"] = self._catch_all_cache[domain]
                else:
                    def _catch_all_check():
                        import random
                        import string
                        fake = "".join(random.choices(string.ascii_lowercase, k=14)) + f"@{domain}"
                        try:
                            smtp = self._smtp_connect(connect_host, connect_port)
                            smtp.helo(helo_domain)
                            smtp.mail(f"verify@{helo_domain}")
                            code, _ = smtp.rcpt(fake)
                            smtp.quit()
                            return code == 250
                        except Exception as e:
                            logger.debug("SMTP catch-all check %s → error: %s", domain, e)
                            return False

                    is_catch_all = await loop.run_in_executor(None, _catch_all_check)
                    self._catch_all_cache[domain] = is_catch_all
                    result["catch_all"] = is_catch_all
                logger.debug("SMTP %s → deliverable=True catch_all=%s", email, result["catch_all"])
            elif code in (550, 551, 552, 553):
                result["deliverable"] = False
                logger.debug("SMTP %s → deliverable=False (code %d)", email, code)
            elif code == -1:
                result["deliverable"] = None
                logger.debug("SMTP %s → deliverable=None (timeout)", email)
            else:
                result["deliverable"] = None
                logger.debug("SMTP %s → deliverable=None (code %d)", email, code)

        except ImportError as e:
            logger.warning("SMTP %s → missing dependency: %s", email, e)
            result["deliverable"] = None
        except Exception as e:
            logger.debug("SMTP %s → outer exception: %s", email, e)
            result["deliverable"] = None

        self._smtp_cache[cache_key] = result
        return result

    async def verify_smtp_batch(self, emails: list[str], concurrency: int = 20) -> dict[str, dict]:
        """
        Batch SMTP verification with concurrency control and per-MX rate limiting.
        """
        smtp_ok = await self.smtp_self_test()
        if not smtp_ok:
            print("  ⚠️  SMTP blocked — skipping verification, all emails tagged 'unknown'")
            return {
                e: {"deliverable": None, "smtp_code": 0, "catch_all": False}
                for e in emails
            }

        sem = asyncio.Semaphore(concurrency)
        results: dict[str, dict] = {}
        checked = 0
        total = len(emails)

        by_domain: dict[str, list[str]] = defaultdict(list)
        for email in emails:
            if not email or "@" not in email:
                results[email] = {"deliverable": None, "smtp_code": 0, "catch_all": False}
                continue
            domain = email.rsplit("@", 1)[1].lower()
            by_domain[domain].append(email)

        mx_last_check: dict[str, float] = {}
        lock = asyncio.Lock()

        async def _check_one(email: str, domain: str):
            nonlocal checked
            async with sem:
                mx_host = await self._resolve_mx_host(domain)
                mx_key = mx_host or domain
                async with lock:
                    now = time.monotonic()
                    last = mx_last_check.get(mx_key, 0)
                    wait = 0.2 - (now - last)
                    if wait > 0:
                        await asyncio.sleep(wait)
                    mx_last_check[mx_key] = time.monotonic()

                result = await self.verify_smtp(email)
                results[email] = result
                checked += 1
                if checked % 100 == 0:
                    print(f"  📬  SMTP progress: {checked}/{total} emails checked...")

        tasks = []
        for domain, domain_emails in by_domain.items():
            for email in domain_emails:
                tasks.append(_check_one(email, domain))

        await asyncio.gather(*tasks)

        if total > 0:
            print(f"  📬  SMTP batch complete: {checked}/{total} emails checked")

        return results

    async def validate_batch(self, emails: list[str]) -> list[dict]:
        """Validate a batch of emails concurrently."""
        results = []
        for email in emails:
            result = self.validate(email)
            if result["valid_format"]:
                result["has_mx"] = await self.verify_mx(email)
            else:
                result["has_mx"] = False
            results.append(result)
        return results

    async def validate_batch_deep(self, emails: list[str], smtp_check: bool = False) -> list[dict]:
        """
        Enhanced validation with optional SMTP deliverability check.
        """
        results = await self.validate_batch(emails)

        if smtp_check:
            sem = asyncio.Semaphore(5)

            async def _check(result):
                if result["valid_format"] and result.get("has_mx"):
                    async with sem:
                        smtp_result = await self.verify_smtp(result["email"])
                        result["smtp_deliverable"] = smtp_result["deliverable"]
                        result["smtp_catch_all"] = smtp_result["catch_all"]
                        result["smtp_code"] = smtp_result["smtp_code"]

            await asyncio.gather(*[_check(r) for r in results])

        return results

    @property
    def dns_error_domains(self) -> set[str]:
        """Domains that encountered DNS errors (candidates for retry)."""
        return set(self._dns_error_domains)

    @property
    def cache_stats(self) -> dict:
        return {
            "domains_cached": len(self._mx_cache),
            "domains_with_mx": sum(1 for v in self._mx_cache.values() if v),
            "smtp_checks_cached": len(self._smtp_cache),
            "dns_error_domains": len(self._dns_error_domains),
        }
