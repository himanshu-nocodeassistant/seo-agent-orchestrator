"""
Retry Logic Module for SEO Bot Orchestrator.

Provides exponential backoff retry functionality for failed tool calls
with configurable retry conditions and error classification.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    initial_delay_ms: int = 1000
    max_delay_ms: int = 10000
    backoff_multiplier: float = 2.0
    retryable_errors: list[str] = field(
        default_factory=lambda: [
            "rate_limit",
            "timeout",
            "connection_error",
            "service_unavailable",
            "429",
            "503",
        ]
    )


@dataclass
class RetryMetrics:
    """Metrics tracking for retry operations."""

    total_attempts: int = 0
    retry_count: int = 0
    success: bool = False
    final_error: str | None = None


def _is_retryable_error(error: Exception, retryable_errors: list[str]) -> bool:
    """Check if an error is retryable based on error message patterns."""
    error_str = str(error).lower()
    for pattern in retryable_errors:
        if pattern.lower() in error_str:
            return True
    return False


def with_retry(config: RetryConfig | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that adds retry logic with exponential backoff to async functions.

    Args:
        config: RetryConfig instance. If None, uses default config.

    Returns:
        Decorated function with retry logic.

    Example:
        @with_retry(RetryConfig(max_attempts=3, initial_delay_ms=500))
        async def my_function():
            ...
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            metrics = RetryMetrics()
            last_error: Exception | None = None

            for attempt in range(1, config.max_attempts + 1):
                metrics.total_attempts = attempt

                try:
                    result = await func(*args, **kwargs)
                    metrics.success = True
                    logger.debug(
                        "%s succeeded on attempt %d", func.__name__, attempt
                    )
                    return result

                except Exception as e:
                    last_error = e
                    logger.debug(
                        "%s failed on attempt %d: %s",
                        func.__name__,
                        attempt,
                        str(e),
                    )

                    # Check if we should retry
                    if attempt < config.max_attempts and _is_retryable_error(
                        e, config.retryable_errors
                    ):
                        metrics.retry_count = attempt
                        delay_ms = min(
                            config.initial_delay_ms
                            * (config.backoff_multiplier ** (attempt - 1)),
                            config.max_delay_ms,
                        )
                        logger.info(
                            "%s: retry %d/%d in %dms (error: %s)",
                            func.__name__,
                            attempt,
                            config.max_attempts,
                            delay_ms,
                            str(e)[:100],
                        )
                        await asyncio.sleep(delay_ms / 1000.0)
                    else:
                        # Non-retryable error or max attempts reached
                        metrics.final_error = str(e)
                        logger.warning(
                            "%s: exhausted retries (attempts=%d, retryable=%s): %s",
                            func.__name__,
                            attempt,
                            _is_retryable_error(e, config.retryable_errors),
                            str(e)[:200],
                        )
                        raise

            # Should not reach here, but handle gracefully
            if last_error:
                raise last_error
            raise RuntimeError(f"{func.__name__}: retry logic exhausted without error")

        async def wrapper_sync(*args, **kwargs) -> T:
            """Alias for async compatibility."""
            return await wrapper(*args, **kwargs)

        # Attach metrics accessor
        wrapper.metrics = metrics
        wrapper._retry_config = config

        return wrapper_sync

    return decorator


def with_retry_sync(config: RetryConfig | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that adds retry logic with exponential backoff to sync functions.

    Args:
        config: RetryConfig instance. If None, uses default config.

    Returns:
        Decorated function with retry logic.
    """
    import time

    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            metrics = RetryMetrics()
            last_error: Exception | None = None

            for attempt in range(1, config.max_attempts + 1):
                metrics.total_attempts = attempt

                try:
                    result = func(*args, **kwargs)
                    metrics.success = True
                    logger.debug(
                        "%s succeeded on attempt %d", func.__name__, attempt
                    )
                    return result

                except Exception as e:
                    last_error = e
                    logger.debug(
                        "%s failed on attempt %d: %s",
                        func.__name__,
                        attempt,
                        str(e),
                    )

                    if attempt < config.max_attempts and _is_retryable_error(
                        e, config.retryable_errors
                    ):
                        metrics.retry_count = attempt
                        delay_ms = min(
                            config.initial_delay_ms
                            * (config.backoff_multiplier ** (attempt - 1)),
                            config.max_delay_ms,
                        )
                        logger.info(
                            "%s: retry %d/%d in %dms (error: %s)",
                            func.__name__,
                            attempt,
                            config.max_attempts,
                            delay_ms,
                            str(e)[:100],
                        )
                        time.sleep(delay_ms / 1000.0)
                    else:
                        metrics.final_error = str(e)
                        logger.warning(
                            "%s: exhausted retries: %s",
                            func.__name__,
                            str(e)[:200],
                        )
                        raise

            if last_error:
                raise last_error
            raise RuntimeError(f"{func.__name__}: retry logic exhausted without error")

        wrapper.metrics = metrics
        wrapper._retry_config = config
        return wrapper

    return decorator