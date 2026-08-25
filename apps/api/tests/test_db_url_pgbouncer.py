"""Regression tests for the asyncpg + pgbouncer runtime URL contract.

Backstop for the 2026-08-24 outage: after the pooler flip (#71/#72) the API
returned ``/ready -> {"database":"error"}`` and 500 on every DB-backed route,
while CI stayed green because nothing exercised a pgbouncer-shaped URL.

The failure was at *connect* time, not query time: SQLAlchemy's asyncpg dialect
forwards unrecognized URL query parameters into ``asyncpg.connect()`` as keyword
arguments, so a URL carrying ``?pgbouncer=true`` raises
``TypeError: connect() got an unexpected keyword argument 'pgbouncer'`` on every
pool checkout.

These tests are pure-unit (no live postgres) so they run in CI on every push.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from ceq_api.db.url import (
    POOLER_UNSAFE_QUERY_PARAMS,
    is_pooled_url,
    normalize_async_database_url,
)

POOLED = "postgresql+asyncpg://ceq:pw@pgbouncer.data.svc.cluster.local:6432/ceq_production"
DIRECT = "postgresql+asyncpg://ceq:pw@postgres.data.svc.cluster.local:5432/ceq_production"


class TestNormalizeAsyncDatabaseUrl:
    """URL normalization must make any rendered URL safe for asyncpg."""

    @pytest.mark.parametrize("param", sorted(POOLER_UNSAFE_QUERY_PARAMS))
    def test_strips_each_pooler_unsafe_param(self, param: str) -> None:
        """Every listed param must be removed, whatever its value."""
        url, dropped = normalize_async_database_url(f"{POOLED}?{param}=whatever")
        assert url == POOLED
        assert dropped == [param]

    def test_strips_the_exact_shape_that_broke_production(self) -> None:
        url, dropped = normalize_async_database_url(f"{POOLED}?pgbouncer=true")
        assert "pgbouncer=true" not in url
        assert url == POOLED
        assert dropped == ["pgbouncer"]

    def test_strips_multiple_params_and_keeps_unknown_ones(self) -> None:
        """Unrecognized params are preserved — we only drop what we know breaks."""
        url, dropped = normalize_async_database_url(
            f"{POOLED}?pgbouncer=true&sslmode=require&application_name=ceq"
        )
        assert url == POOLED
        assert sorted(dropped) == ["application_name", "pgbouncer", "sslmode"]

    def test_preserves_real_asyncpg_params(self) -> None:
        """statement_cache_size is a genuine kwarg and must survive."""
        url, dropped = normalize_async_database_url(
            f"{POOLED}?prepared_statement_cache_size=0"
        )
        assert "prepared_statement_cache_size=0" in url
        assert dropped == []

    def test_clean_url_is_unchanged(self) -> None:
        assert normalize_async_database_url(POOLED) == (POOLED, [])
        assert normalize_async_database_url(DIRECT) == (DIRECT, [])

    def test_is_idempotent(self) -> None:
        once, _ = normalize_async_database_url(f"{POOLED}?pgbouncer=true")
        twice, dropped = normalize_async_database_url(once)
        assert once == twice
        assert dropped == []

    @pytest.mark.parametrize(
        "scheme", ["postgres", "postgresql", "postgres+asyncpg"]
    )
    def test_coerces_bare_scheme_to_asyncpg(self, scheme: str) -> None:
        """A bare postgres:// scheme resolves to psycopg2, which is not installed."""
        url, _ = normalize_async_database_url(
            f"{scheme}://ceq:pw@pgbouncer.data.svc.cluster.local:6432/ceq_production"
        )
        assert url.startswith("postgresql+asyncpg://")

    def test_leaves_sqlite_untouched(self) -> None:
        """The test suite runs on aiosqlite; normalization must not disturb it."""
        sqlite_url = "sqlite+aiosqlite:///:memory:"
        assert normalize_async_database_url(sqlite_url) == (sqlite_url, [])

    def test_does_not_mangle_password_containing_at_sign(self) -> None:
        url, _ = normalize_async_database_url(
            "postgresql+asyncpg://ceq:p%40ss@pgbouncer.data.svc.cluster.local:6432/ceq"
        )
        assert "ceq:p%40ss@" in url

    def test_empty_url_is_safe(self) -> None:
        assert normalize_async_database_url("") == ("", [])


class TestIsPooledUrl:
    def test_detects_pooler_by_host_and_port(self) -> None:
        assert is_pooled_url(POOLED) is True

    def test_direct_url_is_not_pooled(self) -> None:
        assert is_pooled_url(DIRECT) is False

    def test_password_containing_pgbouncer_does_not_false_positive(self) -> None:
        """Host detection must look past userinfo."""
        assert is_pooled_url(
            "postgresql+asyncpg://ceq:pgbouncer@postgres.data.svc.cluster.local:5432/ceq"
        ) is False


class TestEngineBootstrapWithPgbouncerShapedUrl:
    """The engine must actually build and reach connect() with these URLs.

    ``create_async_engine`` binds URL query params into the dialect's connect
    arguments eagerly, so this asserts the real integration point without
    needing a live server.
    """

    def test_raw_pgbouncer_param_would_reach_asyncpg_connect(self) -> None:
        """Guard the premise: unnormalized, the param really does become a kwarg.

        If SQLAlchemy ever stops forwarding unknown params this test fails and
        tells us the normalization rationale needs revisiting.
        """
        engine = create_async_engine(f"{POOLED}?pgbouncer=true")
        _, kwargs = engine.dialect.create_connect_args(engine.url)
        assert "pgbouncer" in kwargs

    def test_normalized_url_yields_no_unexpected_connect_kwargs(self) -> None:
        url, _ = normalize_async_database_url(f"{POOLED}?pgbouncer=true&sslmode=require")
        engine = create_async_engine(url, connect_args={"statement_cache_size": 0})
        _, kwargs = engine.dialect.create_connect_args(engine.url)

        for bad in ("pgbouncer", "sslmode"):
            assert bad not in kwargs, f"{bad} would be passed to asyncpg.connect()"

        assert kwargs["host"] == "pgbouncer.data.svc.cluster.local"
        assert int(kwargs["port"]) == 6432

    def test_normalized_url_contributes_no_connect_kwargs_of_its_own(self) -> None:
        """After normalization the URL supplies only host/port/user/db/password.

        Anything else in this dict came from the URL query string and would be
        forwarded verbatim to ``asyncpg.connect()``.
        """
        url, _ = normalize_async_database_url(
            f"{POOLED}?pgbouncer=true&sslmode=require&options=-c%20search_path%3Dceq"
        )
        engine = create_async_engine(url)
        _, kwargs = engine.dialect.create_connect_args(engine.url)

        assert set(kwargs) <= {"host", "port", "user", "password", "database"}
        # `options` becomes a startup parameter pgbouncer rejects outright
        # (ProtocolViolationError: unsupported startup parameter in options).
        assert "options" not in kwargs


class TestInitDbEngineArguments:
    """``init_db`` must build the engine pgbouncer-safely."""

    @pytest.mark.asyncio
    async def test_init_db_normalizes_url_and_disables_statement_cache(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Assert on the arguments init_db actually passes to the engine factory.

        ``connect_args`` are merged inside SQLAlchemy's pool-creator closure and
        are not introspectable from the built engine, so we capture them at the
        call boundary instead of asserting on library internals.
        """
        from ceq_api.db import session as session_module

        captured: dict[str, object] = {}

        def fake_create_async_engine(url: str, **kwargs: object):
            captured["url"] = url
            captured.update(kwargs)
            return object()

        monkeypatch.setattr(
            session_module, "create_async_engine", fake_create_async_engine
        )
        monkeypatch.setattr(
            session_module, "async_sessionmaker", lambda **_kw: object()
        )
        monkeypatch.setattr(
            session_module.settings, "database_url", f"{POOLED}?pgbouncer=true"
        )

        await session_module.init_db()

        assert captured["url"] == POOLED, "pooler-unsafe param reached the engine"
        assert captured["connect_args"] == {"statement_cache_size": 0}
        # server_settings would be rejected by the pooler at startup.
        assert "server_settings" not in captured
