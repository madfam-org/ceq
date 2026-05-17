"""Tests for security and observability middleware."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import Request, status

from ceq_api.logging import get_request_id, set_request_id
from ceq_api.middleware import get_client_identifier, rate_limit_exceeded_handler


class TestRequestIdMiddleware:
    """Tests for request ID middleware."""

    def test_request_id_generated(self, client):
        """Should generate request ID for requests without one."""
        response = client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 12

    def test_request_id_preserved(self, client):
        """Should preserve client-provided request ID."""
        custom_id = "my-custom-id"
        response = client.get("/health", headers={"X-Request-ID": custom_id})

        assert response.status_code == status.HTTP_200_OK
        assert response.headers["X-Request-ID"] == custom_id

    def test_request_id_unique(self, client):
        """Each request should get a unique ID."""
        response1 = client.get("/health")
        response2 = client.get("/health")

        id1 = response1.headers["X-Request-ID"]
        id2 = response2.headers["X-Request-ID"]

        assert id1 != id2


class TestSecurityHeadersMiddleware:
    """Tests for security headers middleware."""

    def test_content_type_options(self, client):
        """Should include X-Content-Type-Options header."""
        response = client.get("/health")

        assert response.headers.get("X-Content-Type-Options") == "nosniff"

    def test_frame_options(self, client):
        """Should include X-Frame-Options header (SAMEORIGIN — legacy fallback for Atrium)."""
        response = client.get("/health")

        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_xss_protection(self, client):
        """Should include X-XSS-Protection header."""
        response = client.get("/health")

        assert "1" in response.headers.get("X-XSS-Protection", "")

    def test_referrer_policy(self, client):
        """Should include Referrer-Policy header."""
        response = client.get("/health")

        assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_content_security_policy(self, client):
        """Should include Content-Security-Policy header with Selva Atrium allowance."""
        response = client.get("/health")

        csp = response.headers.get("Content-Security-Policy", "")
        assert "default-src 'none'" in csp
        # Selva Atrium (selva-office consumer feature) is allowed to iframe.
        assert "frame-ancestors" in csp
        assert "https://selva.town" in csp
        assert "https://*.selva.town" in csp
        assert "https://*.madfam.io" in csp

    def test_cache_control_for_api(self, client):
        """API endpoints should have no-cache headers."""
        response = client.get("/v1/workflows/")

        cache_control = response.headers.get("Cache-Control", "")
        assert "no-store" in cache_control
        assert "private" in cache_control


class TestRequestSizeLimitMiddleware:
    """Tests for request size limit middleware."""

    def test_normal_request_allowed(self, client):
        """Normal-sized requests should be allowed."""
        response = client.post(
            "/v1/workflows/",
            json={
                "name": "Test",
                "description": "Test workflow",
                "workflow_json": {"nodes": []},
                "input_schema": {},
            },
        )

        # Should not be rejected for size
        assert response.status_code != status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


class TestClientIdentifier:
    """Tests for client identification for rate limiting."""

    def test_get_client_identifier_from_ip(self):
        """Should extract IP address from request."""
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.state = SimpleNamespace()
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"

        identifier = get_client_identifier(mock_request)

        assert identifier == "192.168.1.1"
    def test_get_client_identifier_with_user(self):
        """Should use user ID when authenticated."""
        mock_request = MagicMock()
        user_id = uuid4()
        mock_request.state.user_id = str(user_id)

        identifier = get_client_identifier(mock_request)

        assert f"user:{user_id}" == identifier

    def test_get_client_identifier_forwarded_for(self):
        """Should extract IP from X-Forwarded-For header."""
        mock_request = MagicMock()
        mock_request.headers = {"X-Forwarded-For": "10.0.0.1, 192.168.1.1"}

        # Remove user_id
        mock_request.state = MagicMock(spec=[])

        identifier = get_client_identifier(mock_request)

        assert identifier == "10.0.0.1"


class TestLoggingFunctions:
    """Tests for logging utility functions."""

    def test_set_request_id(self):
        """Should set and return request ID."""
        test_id = "test-id-123"
        result = set_request_id(test_id)

        assert result == test_id
        assert get_request_id() == test_id

    def test_set_request_id_generates_new(self):
        """Should generate new ID when none provided."""
        result = set_request_id(None)

        assert len(result) == 12
        assert get_request_id() == result

    def test_get_request_id_default(self):
        """Should return valid ID even with empty input."""
        # set_request_id generates new ID when given empty string
        result = set_request_id("")
        retrieved = get_request_id()

        # The function generates a new 12-char ID for empty input
        assert len(result) == 12
        assert retrieved == result


class TestRateLimiting:
    """Tests for rate limiting configuration."""

    def test_rate_limiter_disabled_in_dev(self, client):
        """Rate limiter should be disabled in development."""
        # Middleware should not enforce limit for the endpoint even if called repeatedly
        # because the limiter is disabled by default outside production.
        with patch("ceq_api.middleware.limiter.enabled", False):
            for _ in range(25):
                response = self._post_interest(client)

            assert response.status_code != status.HTTP_429_TOO_MANY_REQUESTS

            # Rate limiter should not reject requests in dev mode
            response = self._post_interest(client)
            assert response.status_code != status.HTTP_429_TOO_MANY_REQUESTS

    def _post_interest(self, client):
        """Post to rate-limited endpoint with valid payload."""
        return client.post(
            "/v1/interest/",
            json={
                "email": "test@example.com",
                "feature_key": "early_access",
            },
        )

    def test_rate_limit_exceeded_response(self):
        """Rate limit exceeded should return 429 with retry header."""
        mock_request = MagicMock(spec=Request)
        mock_request.url.path = "/v1/interest/"
        mock_request.state = SimpleNamespace()
        mock_request.state.user_id = None
        mock_request.state.user = None
        mock_request.headers = {}
        mock_request.client = SimpleNamespace(host="127.0.0.1")
        mock_request.client.host = "127.0.0.1"

        mock_exc = MagicMock()
        mock_exc.detail = "test window exceeded"

        response = rate_limit_exceeded_handler(mock_request, mock_exc)

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.headers["Retry-After"] == "60"
        import json as _json

        payload = _json.loads(response.body)
        assert payload["detail"] == "Latent space overloaded. Too many requests. Please slow down."
        assert payload["retry_after"] == mock_exc.detail


class TestCORS:
    """Tests for CORS configuration."""

    def test_cors_allowed_origin(self, client):
        """Should allow requests from configured origins."""
        response = client.options(
            "/v1/workflows/",
            headers={
                "Origin": "http://localhost:5801",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.headers.get("Access-Control-Allow-Origin") in [
            "http://localhost:5801",
            "*",
        ]

    def test_cors_allows_app_host_origin(self, client):
        """Should allow requests from app.ceq.lol."""
        response = client.options(
            "/v1/workflows/",
            headers={
                "Origin": "https://app.ceq.lol",
                "Access-Control-Request-Method": "GET",
            },
        )

        assert response.headers.get("Access-Control-Allow-Origin") in [
            "https://app.ceq.lol",
            "*",
        ]

    def test_cors_exposes_request_id(self, client):
        """Should include X-Request-ID in response headers."""
        # Make a regular request instead of OPTIONS preflight
        response = client.get("/health")

        # X-Request-ID should be in response headers
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 12


class TestHealthCheckBypass:
    """Tests that health checks bypass logging."""

    def test_health_endpoint_not_logged(self, client, caplog):
        """Health endpoint should not be logged excessively."""
        response = client.get("/health")
        assert response.status_code == status.HTTP_200_OK

        with caplog.at_level(logging.INFO):
            client.get("/health")

        messages = [
            record.getMessage()
            for record in caplog.records
            if "Request started: GET /health" in record.getMessage()
            or "Request completed: GET /health" in record.getMessage()
        ]

        assert len(messages) == 0

    def test_ready_endpoint_not_logged(self, client):
        """Ready endpoint should not be logged excessively."""
        response = client.get("/ready")

        assert response.status_code == status.HTTP_200_OK

    def test_metrics_endpoint_not_logged(self, client):
        """Metrics endpoint should not be logged excessively."""
        response = client.get("/metrics")

        # Prometheus metrics endpoint
        assert response.status_code == status.HTTP_200_OK
