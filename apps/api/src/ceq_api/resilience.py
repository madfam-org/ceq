"""Resilience patterns for production reliability.

Implements circuit breakers, retry logic, and graceful degradation
for external service calls (Janua, R2, Redis).
"""

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes in half-open to close
    timeout: float = 30.0  # Seconds before trying half-open
    excluded_exceptions: tuple = ()  # Exceptions that don't count as failures


@dataclass
class CircuitBreakerState:
    """Mutable state for circuit breaker."""

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    total_failures: int = 0
    total_successes: int = 0


class CircuitBreakerError(Exception):
    """Raised when circuit is open."""

    def __init__(self, service_name: str, retry_after: float):
        self.service_name = service_name
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker open for {service_name}. Retry after {retry_after:.1f}s")


class CircuitBreaker:
    """
    Circuit breaker pattern implementation.

    Prevents cascading failures by failing fast when a service is down.
    """

    # Registry of all circuit breakers for monitoring
    _registry: dict[str, "CircuitBreaker"] = {}

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitBreakerState()
        self._lock = asyncio.Lock()
        CircuitBreaker._registry[name] = self

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state.state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state.state == CircuitState.CLOSED

    async def _check_state(self) -> None:
        """Check and potentially transition state."""
        if self._state.state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._state.last_failure_time
            if elapsed >= self.config.timeout:
                logger.info(
                    f"Circuit breaker {self.name}: OPEN -> HALF_OPEN after {elapsed:.1f}s"
                )
                self._state.state = CircuitState.HALF_OPEN
                self._state.success_count = 0

    async def _record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self._state.total_successes += 1

            if self._state.state == CircuitState.HALF_OPEN:
                self._state.success_count += 1
                if self._state.success_count >= self.config.success_threshold:
                    logger.info(
                        f"Circuit breaker {self.name}: HALF_OPEN -> CLOSED after "
                        f"{self._state.success_count} successes"
                    )
                    self._state.state = CircuitState.CLOSED
                    self._state.failure_count = 0

    async def _record_failure(self, exc: Exception) -> None:
        """Record a failed call."""
        # Check if this exception should be excluded
        if isinstance(exc, self.config.excluded_exceptions):
            return

        async with self._lock:
            self._state.failure_count += 1
            self._state.total_failures += 1
            self._state.last_failure_time = time.monotonic()

            if self._state.state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"Circuit breaker {self.name}: HALF_OPEN -> OPEN after failure"
                )
                self._state.state = CircuitState.OPEN

            elif self._state.state == CircuitState.CLOSED:
                if self._state.failure_count >= self.config.failure_threshold:
                    logger.warning(
                        f"Circuit breaker {self.name}: CLOSED -> OPEN after "
                        f"{self._state.failure_count} failures"
                    )
                    self._state.state = CircuitState.OPEN

    async def call(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        """Execute function with circuit breaker protection."""
        await self._check_state()

        if self._state.state == CircuitState.OPEN:
            retry_after = self.config.timeout - (
                time.monotonic() - self._state.last_failure_time
            )
            raise CircuitBreakerError(self.name, max(0, retry_after))

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            await self._record_success()
            return result
        except Exception as e:
            await self._record_failure(e)
            raise

    def __call__(
        self, func: Callable[P, T]
    ) -> Callable[P, T]:
        """Decorator for applying circuit breaker to a function."""

        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await self.call(func, *args, **kwargs)

        return wrapper

    def get_stats(self) -> dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "name": self.name,
            "state": self._state.state.value,
            "failure_count": self._state.failure_count,
            "success_count": self._state.success_count,
            "total_failures": self._state.total_failures,
            "total_successes": self._state.total_successes,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout,
            },
        }

    @classmethod
    def get_all_stats(cls) -> dict[str, dict[str, Any]]:
        """Get stats for all registered circuit breakers."""
        return {name: cb.get_stats() for name, cb in cls._registry.items()}


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_attempts: int = 3
    base_delay: float = 1.0  # Initial delay in seconds
    max_delay: float = 30.0  # Maximum delay cap
    exponential_base: float = 2.0  # Exponential backoff multiplier
    jitter: bool = True  # Add randomness to prevent thundering herd
    retryable_exceptions: tuple = (Exception,)


async def retry_with_backoff(
    func: Callable[P, T],
    config: RetryConfig | None = None,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """
    Execute function with exponential backoff retry.

    Args:
        func: Async function to execute
        config: Retry configuration
        *args, **kwargs: Arguments to pass to func

    Returns:
        Result from successful function call

    Raises:
        Last exception if all retries fail
    """
    config = config or RetryConfig()
    last_exception: Exception | None = None

    for attempt in range(1, config.max_attempts + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except config.retryable_exceptions as e:
            last_exception = e

            if attempt == config.max_attempts:
                logger.warning(
                    f"Retry exhausted after {attempt} attempts: {e}"
                )
                raise

            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.exponential_base ** (attempt - 1)),
                config.max_delay,
            )

            # Add jitter (0-25% of delay)
            if config.jitter:
                import random
                delay *= 1 + random.uniform(0, 0.25)

            logger.warning(
                f"Attempt {attempt} failed: {e}. Retrying in {delay:.2f}s"
            )
            await asyncio.sleep(delay)

    # This should never be reached, but satisfy type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Retry logic error")


def with_retry(config: RetryConfig | None = None):
    """Decorator for adding retry logic to async functions."""
    config = config or RetryConfig()

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await retry_with_backoff(func, config, *args, **kwargs)

        return wrapper

    return decorator


# Pre-configured circuit breakers for external services
janua_circuit = CircuitBreaker(
    "janua",
    CircuitBreakerConfig(
        failure_threshold=3,
        timeout=60.0,  # Longer timeout for auth service
    ),
)

r2_circuit = CircuitBreaker(
    "r2",
    CircuitBreakerConfig(
        failure_threshold=5,
        timeout=30.0,
    ),
)

redis_circuit = CircuitBreaker(
    "redis",
    CircuitBreakerConfig(
        failure_threshold=5,
        timeout=15.0,  # Redis should recover quickly
    ),
)


# Retry configurations for different service types
JANUA_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=0.5,
    max_delay=5.0,
    retryable_exceptions=(ConnectionError, TimeoutError),
)

R2_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=10.0,
    retryable_exceptions=(ConnectionError, TimeoutError),
)

REDIS_RETRY_CONFIG = RetryConfig(
    max_attempts=2,
    base_delay=0.1,
    max_delay=1.0,
    retryable_exceptions=(ConnectionError,),
)


async def graceful_degradation(
    primary: Callable[[], T],
    fallback: Callable[[], T] | T,
    log_fallback: bool = True,
) -> T:
    """
    Execute primary function with fallback on failure.

    Args:
        primary: Primary async function to try
        fallback: Fallback function or value if primary fails
        log_fallback: Whether to log when using fallback

    Returns:
        Result from primary or fallback
    """
    try:
        if asyncio.iscoroutinefunction(primary):
            return await primary()
        return primary()
    except Exception as e:
        if log_fallback:
            logger.warning(f"Using fallback due to: {e}")

        if callable(fallback):
            if asyncio.iscoroutinefunction(fallback):
                return await fallback()
            return fallback()
        return fallback
