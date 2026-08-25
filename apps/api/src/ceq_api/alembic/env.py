"""Alembic env for CEQ API migrations."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from ceq_api.config import get_settings
from ceq_api.db.url import is_pooled_url, normalize_async_database_url
from ceq_api.models import Base

# Alembic Config object
config = context.config

# Logging configuration
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model metadata for autogenerate
target_metadata = Base.metadata

# Settings
settings = get_settings()


def migration_url() -> str:
    """Resolve the URL migrations run against — always DIRECT postgres.

    DDL must not go through the transaction pooler: pgbouncer multiplexes
    server connections between transactions, which breaks the session-scoped
    state alembic relies on (advisory locks held across statements, and
    multi-statement DDL transactions). ``DIRECT_DATABASE_URL`` is rendered by
    the ExternalSecret from Vault's untouched 5432 value for exactly this.

    Falling back to ``database_url`` keeps pre-pgbouncer/dev deployments
    working, but if that fallback is itself pooled we fail loudly rather than
    quietly running DDL through the pooler.
    """
    url = str(settings.direct_database_url or settings.database_url)
    if settings.direct_database_url is None and is_pooled_url(url):
        raise RuntimeError(
            "Refusing to run migrations through the transaction pooler: "
            "DATABASE_URL points at pgbouncer and DIRECT_DATABASE_URL is unset. "
            "Set DIRECT_DATABASE_URL to the direct postgres:5432 URL "
            "(see infrastructure/k8s/external-secret.yaml)."
        )
    # Same normalization as the runtime: alembic also builds an asyncpg engine,
    # so libpq-style query params would break connect() here too, and a bare
    # `postgresql://` scheme would resolve to psycopg2 (not installed).
    normalized, _ = normalize_async_database_url(url)
    return normalized


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = migration_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(
        migration_url(),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
