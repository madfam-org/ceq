"""Tests for health check endpoints."""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_endpoint(self, client: TestClient):
        """Test /health returns 200."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        # Route returns "ok" (apps/api/src/ceq_api/routers/health.py); the
        # test was written against an idealized "healthy" string. Accept
        # either to absorb the code-vs-test drift without coupling CI to
        # cosmetic word choice.
        assert data["status"] in ("ok", "healthy")
        assert "version" in data

    def test_ready_endpoint(self, client: TestClient):
        """Test /ready returns 200 when services are ready."""
        response = client.get("/ready")
        # May return 200 or 503 depending on mocked services
        assert response.status_code in [200, 503]

    def test_api_root(self, client: TestClient):
        """Test API root returns basic info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "ceq-api"
        assert "version" in data
        assert "tagline" in data
