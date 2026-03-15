"""
Retry utilities for transient errors in the pipeline.

Provides a decorator and an async context manager for retrying
operations with exponential backoff, jitter, and configurable
exception filtering.

Usage:
    from pipeline.retry import retry_async, RetryExhausted

    @retry_async(max_retries=3, base_delay=1.0)
    async def fetch_page(url):
        ...

    # Or inline:
    async with retry_context(max_retries=3) as attempt:
        result = await risky_call()
"""

import asyncio
import functools
import logging
import random
from typing import Callable, Sequence, Type

logger = logging.getLogger(__name__)

# Exceptions that are generally transient and worth retrying
TRANSIENT_EXCEPTIONS: tuple = (
    ConnectionError,
    TimeoutError,
    OSError,
)

try:
    import aiohttp
    TRANSIENT_EXCEPTIONS = TRANSIENT_EXCEPTIONS + (
        aiohttp.ClientError,
        aiohttp.ServerDisconnectedError,
    )
except ImportError:
    pass


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, last_error: Exception, attempts: int):
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(
            f"All {attempts} retry attempts exhausted. Last error: {last_error}"
        )


def retry_async(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable: Sequence[Type[Exception]] = TRANSIENT_EXCEPTIONS,
    on_retry: Callable | None = None,
):
    """
    Decorator for async functions that retries on transient errors.

    Args:
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay between retries (seconds).
        max_delay: Maximum delay between retries (seconds).
        retryable: Tuple of exception types that trigger a retry.
        on_retry: Optional callback(attempt, error, delay) called before each retry.
    """

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(1, max_retries + 2):  # +1 for initial + retries
                try:
                    return await func(*args, **kwargs)
                except tuple(retryable) as e:
                    last_error = e
                    if attempt > max_retries:
                        break
                    # Exponential backoff with jitter
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    delay *= 0.5 + random.random()  # jitter: 50-150% of delay

                    logger.warning(
                        f"Retry {attempt}/{max_retries} for {func.__name__}: {e}",
                        extra={"retry_attempt": attempt, "phase": func.__name__},
                    )
                    if on_retry:
                        on_retry(attempt, e, delay)

                    await asyncio.sleep(delay)

            raise RetryExhausted(last_error, max_retries)

        return wrapper

    return decorator


def retry_sync(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable: Sequence[Type[Exception]] = TRANSIENT_EXCEPTIONS,
):
    """Synchronous version of retry decorator."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import time
            last_error = None
            for attempt in range(1, max_retries + 2):
                try:
                    return func(*args, **kwargs)
                except tuple(retryable) as e:
                    last_error = e
                    if attempt > max_retries:
                        break
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    delay *= 0.5 + random.random()
                    logger.warning(
                        f"Retry {attempt}/{max_retries} for {func.__name__}: {e}",
                    )
                    time.sleep(delay)
            raise RetryExhausted(last_error, max_retries)

        return wrapper

    return decorator
