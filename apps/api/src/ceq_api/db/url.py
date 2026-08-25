"""DATABASE_URL normalization for the asyncpg + pgbouncer runtime.

Why this module exists
----------------------
The runtime ``DATABASE_URL`` is rendered by an ExternalSecret Go template
(``infrastructure/k8s/external-secret.yaml``) that rewrites the Vault value's
``host:port`` to point at the transaction-mode pooler. That rewrite is a plain
string ``replace``: it carries the rest of the URL through **verbatim**,
including any query string Vault happens to hold.

asyncpg does not accept libpq-style URL query parameters. SQLAlchemy's asyncpg
dialect forwards every unrecognized query parameter straight into
``asyncpg.connect()`` as a keyword argument, so a URL carrying ``?pgbouncer=true``
or ``?sslmode=require`` fails at *connect* time with::

    TypeError: connect() got an unexpected keyword argument 'pgbouncer'

That is a total outage shape, not a slow degradation: every pooled checkout
raises, so ``/ready`` reports ``database: error`` and every DB-backed route
500s, while Redis stays green.

Separately, transaction pooling forbids per-session startup parameters. Any
``server_settings`` beyond pgbouncer's ``ignore_startup_parameters`` allowlist
is rejected by the pooler with ``ProtocolViolationError: unsupported startup
parameter``.

So the runtime URL must be normalized before it reaches ``create_async_engine``.
Migrations deliberately do NOT use this path — see ``DIRECT_DATABASE_URL`` and
``alembic/env.py``: DDL keeps a direct 5432 session, where these params are
harmless and where advisory locks and multi-statement DDL transactions are safe.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = [
    "POOLER_UNSAFE_QUERY_PARAMS",
    "is_pooled_url",
    "normalize_async_database_url",
]

# Query parameters that must never survive into ``asyncpg.connect(**kwargs)``.
#
# ``pgbouncer`` is a marker some tools (Prisma, Supabase connection strings)
# append to signal "this endpoint is a pooler". asyncpg has no such kwarg.
# ``sslmode``/``ssl`` and the libpq timeout/appname spellings are likewise
# libpq-isms that asyncpg either does not accept or spells differently.
#
# ``statement_cache_size`` / ``prepared_statement_cache_size`` ARE real asyncpg
# and SQLAlchemy-dialect kwargs, so they are deliberately NOT dropped here —
# they are instead enforced to the pool-safe value in ``session.py``.
POOLER_UNSAFE_QUERY_PARAMS: frozenset[str] = frozenset(
    {
        "pgbouncer",
        "sslmode",
        "ssl",
        "sslcert",
        "sslkey",
        "sslrootcert",
        "connect_timeout",
        "application_name",
        "target_session_attrs",
        "options",
    }
)


def _normalize_scheme(scheme: str) -> str:
    """Force the async driver on an otherwise-bare postgres scheme.

    Vault may hold ``postgresql://`` (the portable spelling used by psql,
    alembic-offline, and pooler auth probes). ``create_async_engine`` on a bare
    ``postgresql://`` resolves to psycopg2, which is not installed in the API
    image and is not an async driver, so the engine fails to build at all.
    """
    if scheme in ("postgres", "postgresql"):
        return "postgresql+asyncpg"
    if scheme == "postgres+asyncpg":
        return "postgresql+asyncpg"
    return scheme


def is_pooled_url(url: str) -> bool:
    """Best-effort: does this URL point at the transaction-mode pooler?

    Used only for logging/diagnostics — normalization is unconditional so that
    a direct URL and a pooled URL are handled identically and there is no
    "works direct, breaks pooled" divergence to rediscover later.
    """
    try:
        netloc = urlsplit(url).netloc
    except ValueError:
        return False
    host_port = netloc.rsplit("@", 1)[-1]
    return "pgbouncer" in host_port or host_port.endswith(":6432")


def normalize_async_database_url(url: str) -> tuple[str, list[str]]:
    """Return a ``(url, dropped_params)`` pair safe for ``create_async_engine``.

    - Coerces ``postgres(ql)://`` to ``postgresql+asyncpg://``.
    - Strips libpq/pooler-marker query params that asyncpg would otherwise
      receive as unexpected ``connect()`` keyword arguments.

    Non-postgres URLs (notably the ``sqlite+aiosqlite://`` used by the test
    suite) are returned untouched apart from being parsed, so this is safe to
    apply unconditionally at engine construction.
    """
    if not url:
        return url, []

    parts = urlsplit(url)
    scheme = _normalize_scheme(parts.scheme)

    # Only postgres URLs carry the libpq params we care about. Leave sqlite and
    # anything else strictly alone.
    if not scheme.startswith("postgresql"):
        return url, []

    kept: list[tuple[str, str]] = []
    dropped: list[str] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in POOLER_UNSAFE_QUERY_PARAMS:
            dropped.append(key)
        else:
            kept.append((key, value))

    query = urlencode(kept)
    normalized = urlunsplit((scheme, parts.netloc, parts.path, query, parts.fragment))
    return normalized, dropped
