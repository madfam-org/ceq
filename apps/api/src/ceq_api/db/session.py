"""Async database session management with SQLAlchemy."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ceq_api.config import get_settings

settings = get_settings()

# Global engine and session factory
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db() -> None:
    """
    Initialize the database connection pool.
    
    Called during application startup.
    """
    global _engine, _session_factory

    _engine = create_async_engine(
        str(settings.database_url),
        echo=settings.debug,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Extract host from URL for logging
    db_url = str(settings.database_url)
    host_part = db_url.split("@")[1].split("/")[0] if "@" in db_url else "localhost"
    print(f"   Database connected: {host_part}")


async def close_db() -> None:
    """
    Close the database connection pool.
    
    Called during application shutdown.
    """
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        print("   Database connection closed")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session.
    
    Used as a FastAPI dependency:
    
        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Get a database session as a context manager.
    
    For use outside of FastAPI request context:
    
        async with get_db_context() as db:
            result = await db.execute(...)
    """
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
