"""Tests for resilience patterns (circuit breakers, retry logic)."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from ceq_api.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
    RetryConfig,
    retry_with_backoff,
    graceful_degradation,
)


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    @pytest.fixture
    def circuit(self):
        """Create a fresh circuit breaker for each test."""
        return CircuitBreaker(
            f"test-{id(self)}",
            CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout=0.1,  # Short timeout for testing
            ),
        )

    @pytest.mark.asyncio
    async def test_circuit_starts_closed(self, circuit):
        """Circuit should start in closed state."""
        assert circuit.state == CircuitState.CLOSED
        assert circuit.is_closed is True

    @pytest.mark.asyncio
    async def test_circuit_stays_closed_on_success(self, circuit):
        """Successful calls should keep circuit closed."""
        async def success():
            return "ok"

        result = await circuit.call(success)
        assert result == "ok"
        assert circuit.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self, circuit):
        """Circuit should open after reaching failure threshold."""
        async def failure():
            raise ConnectionError("Service unavailable")

        # First 3 failures should open the circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await circuit.call(failure)

        assert circuit.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_rejects_when_open(self, circuit):
        """Open circuit should reject calls immediately."""
        async def failure():
            raise ConnectionError("Service unavailable")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await circuit.call(failure)

        # Now calls should be rejected with CircuitBreakerError
        with pytest.raises(CircuitBreakerError) as exc_info:
            await circuit.call(failure)

        assert circuit.name in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self, circuit):
        """Circuit should transition to half-open after timeout."""
        async def failure():
            raise ConnectionError("Service unavailable")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await circuit.call(failure)

        assert circuit.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Next call should trigger half-open
        async def success():
            return "ok"

        result = await circuit.call(success)
        assert result == "ok"
        # After success in half-open, should be closed (with success_threshold=2)
        # Actually need 2 successes
        result = await circuit.call(success)
        assert circuit.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_reopens_on_failure_in_half_open(self, circuit):
        """Failure in half-open should reopen circuit."""
        async def failure():
            raise ConnectionError("Service unavailable")

        # Open the circuit
        for _ in range(3):
            with pytest.raises(ConnectionError):
                await circuit.call(failure)

        # Wait for timeout
        await asyncio.sleep(0.15)

        # Failure in half-open should reopen
        with pytest.raises(ConnectionError):
            await circuit.call(failure)

        assert circuit.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_circuit_excluded_exceptions(self):
        """Excluded exceptions should not count as failures."""
        circuit = CircuitBreaker(
            "test-excluded",
            CircuitBreakerConfig(
                failure_threshold=2,
                excluded_exceptions=(ValueError,),
            ),
        )

        async def raise_value_error():
            raise ValueError("Not a failure")

        # These should not count as failures
        for _ in range(5):
            with pytest.raises(ValueError):
                await circuit.call(raise_value_error)

        # Circuit should still be closed
        assert circuit.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_circuit_stats(self, circuit):
        """Circuit should track statistics."""
        async def success():
            return "ok"

        async def failure():
            raise ConnectionError("fail")

        await circuit.call(success)
        await circuit.call(success)

        try:
            await circuit.call(failure)
        except ConnectionError:
            pass

        stats = circuit.get_stats()
        assert stats["name"] == circuit.name
        assert stats["total_successes"] == 2
        assert stats["total_failures"] == 1
        assert stats["state"] == "closed"

    def test_circuit_registry(self):
        """All circuits should be registered."""
        circuit1 = CircuitBreaker("registry-test-1", CircuitBreakerConfig())
        circuit2 = CircuitBreaker("registry-test-2", CircuitBreakerConfig())

        all_stats = CircuitBreaker.get_all_stats()

        assert "registry-test-1" in all_stats
        assert "registry-test-2" in all_stats


class TestRetryWithBackoff:
    """Tests for retry logic."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_first_try(self):
        """Should return immediately on success."""
        attempts = []

        async def success():
            attempts.append(1)
            return "ok"

        result = await retry_with_backoff(success)
        assert result == "ok"
        assert len(attempts) == 1

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Should retry and succeed eventually."""
        attempts = []

        async def eventually_succeeds():
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("Try again")
            return "ok"

        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,  # Fast for testing
        )

        result = await retry_with_backoff(eventually_succeeds, config)
        assert result == "ok"
        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        """Should raise after max attempts."""
        attempts = []

        async def always_fails():
            attempts.append(1)
            raise ConnectionError("Always fails")

        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
        )

        with pytest.raises(ConnectionError):
            await retry_with_backoff(always_fails, config)

        assert len(attempts) == 3

    @pytest.mark.asyncio
    async def test_retry_respects_retryable_exceptions(self):
        """Should only retry for specified exceptions."""
        attempts = []

        async def fails_with_value_error():
            attempts.append(1)
            raise ValueError("Not retryable")

        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=(ConnectionError,),  # Not ValueError
        )

        with pytest.raises(ValueError):
            await retry_with_backoff(fails_with_value_error, config)

        # Should not have retried
        assert len(attempts) == 1

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self):
        """Delays should increase exponentially."""
        import time

        attempts = []
        times = []

        async def fails_twice():
            times.append(time.monotonic())
            attempts.append(1)
            if len(attempts) < 3:
                raise ConnectionError("Try again")
            return "ok"

        config = RetryConfig(
            max_attempts=3,
            base_delay=0.1,
            exponential_base=2.0,
            jitter=False,  # Disable jitter for predictable timing
        )

        await retry_with_backoff(fails_twice, config)

        # Check delays increased
        delay1 = times[1] - times[0]
        delay2 = times[2] - times[1]

        # Second delay should be roughly 2x first (base_delay vs base_delay * 2)
        assert delay2 > delay1 * 1.5  # Allow some tolerance


class TestGracefulDegradation:
    """Tests for graceful degradation."""

    @pytest.mark.asyncio
    async def test_returns_primary_on_success(self):
        """Should return primary result when successful."""
        async def primary():
            return "primary"

        result = await graceful_degradation(primary, "fallback")
        assert result == "primary"

    @pytest.mark.asyncio
    async def test_returns_fallback_on_failure(self):
        """Should return fallback when primary fails."""
        async def primary():
            raise ConnectionError("Primary failed")

        result = await graceful_degradation(primary, "fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_calls_fallback_function(self):
        """Should call fallback function when primary fails."""
        async def primary():
            raise ConnectionError("Primary failed")

        async def fallback():
            return "fallback_result"

        result = await graceful_degradation(primary, fallback)
        assert result == "fallback_result"

    @pytest.mark.asyncio
    async def test_sync_primary_and_fallback(self):
        """Should work with sync functions."""
        def primary():
            raise ValueError("Primary failed")

        def fallback():
            return "sync_fallback"

        result = await graceful_degradation(primary, fallback)
        assert result == "sync_fallback"


class TestCircuitBreakerDecorator:
    """Tests for circuit breaker as decorator."""

    @pytest.mark.asyncio
    async def test_decorator_usage(self):
        """Circuit breaker can be used as decorator."""
        circuit = CircuitBreaker("decorator-test", CircuitBreakerConfig())

        call_count = 0

        @circuit
        async def my_service():
            nonlocal call_count
            call_count += 1
            return "result"

        result = await my_service()
        assert result == "result"
        assert call_count == 1
        assert circuit.state == CircuitState.CLOSED


class TestCircuitBreakerHealthEndpoint:
    """Tests for circuit breaker health monitoring."""

    def test_get_all_stats_format(self):
        """Stats should have correct format."""
        circuit = CircuitBreaker("health-test", CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout=30.0,
        ))

        stats = circuit.get_stats()

        assert "name" in stats
        assert "state" in stats
        assert "failure_count" in stats
        assert "success_count" in stats
        assert "total_failures" in stats
        assert "total_successes" in stats
        assert "config" in stats
        assert stats["config"]["failure_threshold"] == 5
        assert stats["config"]["success_threshold"] == 3
        assert stats["config"]["timeout"] == 30.0
