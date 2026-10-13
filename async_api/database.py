"""
High-Performance Asynchronous Database Engine & Session Manager
SQLAlchemy 2.0 Asyncio with Swappable Dialects (PostgreSQL / MySQL)
"""

import logging
from typing import AsyncGenerator
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from async_api.config import settings

logger = logging.getLogger("async_api.database")


class Base(AsyncAttrs, DeclarativeBase):
    """
    SQLAlchemy 2.0 Declarative Base with AsyncAttrs support.
    Enables async attribute loading without lazy-load IO errors.
    """
    pass


def build_async_engine(db_url: str) -> AsyncEngine:
    """
    Constructs an optimized AsyncEngine with dialect-specific optimizations
    and bulletproof connection pool parameters.
    
    Supported Schemes:
      - postgresql+asyncpg:// (PostgreSQL)
      - mysql+aiomysql://     (MySQL)
      - sqlite+aiosqlite://   (Local testing fallback)
    """
    parsed = urlparse(db_url)
    scheme = parsed.scheme.lower()

    # Base engine configuration matching the strict high-performance spec
    engine_kwargs = {
        "echo": settings.DB_ECHO,
        "pool_pre_ping": settings.DB_POOL_PRE_PING,
    }

    if "sqlite" in scheme:
        # SQLite async engine configuration (for local testing / ephemeral runners)
        if ":memory:" in db_url or "mode=memory" in db_url:
            engine_kwargs["poolclass"] = NullPool
        else:
            engine_kwargs["poolclass"] = AsyncAdaptedQueuePool
            engine_kwargs["pool_size"] = settings.DB_POOL_SIZE
            engine_kwargs["max_overflow"] = settings.DB_MAX_OVERFLOW
            engine_kwargs["pool_timeout"] = settings.DB_POOL_TIMEOUT
        logger.info(f"Initialized Async SQLite Engine with {scheme}")

    elif "postgresql" in scheme:
        # PostgreSQL + asyncpg: production workhorse
        engine_kwargs.update({
            "poolclass": AsyncAdaptedQueuePool,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "connect_args": {
                "server_settings": {
                    "application_name": settings.APP_NAME,
                    "jit": "off",  # Disabling JIT saves 5-15ms on quick transactional queries
                },
                "command_timeout": 15,
            },
        })
        logger.info(f"Initialized Async PostgreSQL (asyncpg) Engine with pool_size={settings.DB_POOL_SIZE}")

    elif "mysql" in scheme:
        # MySQL + aiomysql: enterprise relational alternative
        engine_kwargs.update({
            "poolclass": AsyncAdaptedQueuePool,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
            "connect_args": {
                "charset": "utf8mb4",
                "connect_timeout": 10,
            },
        })
        logger.info(f"Initialized Async MySQL (aiomysql) Engine with pool_size={settings.DB_POOL_SIZE}")

    else:
        # Generic async driver configuration
        engine_kwargs.update({
            "poolclass": AsyncAdaptedQueuePool,
            "pool_size": settings.DB_POOL_SIZE,
            "max_overflow": settings.DB_MAX_OVERFLOW,
            "pool_recycle": settings.DB_POOL_RECYCLE,
            "pool_timeout": settings.DB_POOL_TIMEOUT,
        })
        logger.warning(f"Initialized Generic Async Engine with scheme: {scheme}")

    return create_async_engine(db_url, **engine_kwargs)


# Global Async Engine Singleton
engine: AsyncEngine = build_async_engine(settings.DATABASE_URL)

# High-Performance Async Session Factory
# expire_on_commit=False prevents redundant async SELECTs after commit
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI Dependency Injector yielding an AsyncSession.
    Guarantees strict context lifecycle: commits on clean exit, rolls back on exception,
    and returns connection to the pool immediately.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_db_connections() -> None:
    """Disposes engine pool on application shutdown."""
    logger.info("Disposing async database connection pool...")
    await engine.dispose()
    logger.info("Database connection pool disposed cleanly.")
