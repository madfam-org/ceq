"""Tests for ceq API application bootstrap behavior."""

from importlib import reload

from fastapi import FastAPI


def _load_app_with_env(monkeypatch, env: str) -> FastAPI:
    """Reload ceq_api.main with a controlled environment."""
    # Minimum required production settings are intentionally explicit to keep
    # config validation deterministic.
    monkeypatch.setenv("ENVIRONMENT", env)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://ceq:ceq_pass@postgres:5432/ceq_production")
    monkeypatch.setenv("REDIS_URL", "redis://:redis_pass@redis:6379/14")
    monkeypatch.setenv("R2_ENDPOINT", "https://account.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_ACCESS_KEY", "test-access")
    monkeypatch.setenv("R2_SECRET_KEY", "test-secret")
    monkeypatch.setenv("JOB_COMPLETION_CALLBACK_TOKEN", "test-callback-token")
    monkeypatch.setenv("JANUA_API_URL", "https://janua.example.internal")

    # If DEBUG was previously set by the test environment, keep it as-is so this
    # helper only enforces environment-level contract.
    monkeypatch.setenv("DEBUG", "false")

    from ceq_api import config

    # Environment changes happen after import in this test session; clear cached
    # settings and rebuild the app module under the target env.
    config.get_settings.cache_clear()
    from ceq_api import main

    return reload(main).app


def test_production_hides_api_documentation(monkeypatch) -> None:
    """Production environments should not expose docs or OpenAPI endpoints."""
    app = _load_app_with_env(monkeypatch, "production")
    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_non_production_exposes_api_documentation(monkeypatch) -> None:
    """Non-production environments should expose docs/openapi by default."""
    app = _load_app_with_env(monkeypatch, "development")
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"
