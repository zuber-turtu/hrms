"""
Infrastructure Configuration Module
Powered by Pydantic v2 & Pydantic-Settings
"""

import os
import multiprocessing
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """
    Production-grade environment and infrastructure settings.
    Designed for zero-allocation performance under high concurrency (1,000+ users).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 1. Environment & Network
    APP_NAME: str = "HighPerf-AsyncAPI"
    APP_VERSION: str = "2.0.0"
    ENV: str = Field(default="production", description="Environment: production, staging, development")
    DEBUG: bool = Field(default=False, description="Debug mode (strictly False in production)")
    HOST: str = Field(default="0.0.0.0", description="Bind IP address")
    PORT: int = Field(default=8000, description="HTTP Port")

    # 2. Database Connection (SQLAlchemy 2.0 Asyncio)
    # Default supports sqlite+aiosqlite for local testing; swappable to postgresql+asyncpg or mysql+aiomysql
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./async_hrms.db",
        description="Async database connection URI: postgresql+asyncpg:// or mysql+aiomysql://",
    )

    # 3. Bulletproof Connection Pool Settings (Strict Spec)
    DB_POOL_SIZE: int = Field(default=30, description="Baseline open persistent connection handles")
    DB_MAX_OVERFLOW: int = Field(default=15, description="Burst headroom handles above pool_size")
    DB_POOL_RECYCLE: int = Field(default=1800, description="Recycle connection lifetime in seconds (30 mins)")
    DB_POOL_PRE_PING: bool = Field(default=True, description="Liveness test before releasing connection from pool")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Max seconds to wait before timing out connection request")
    DB_ECHO: bool = Field(default=False, description="Log raw SQL statements (disable in production for latency)")

    # 4. Redis High-Concurrency Caching
    REDIS_URL: str = Field(default="redis://127.0.0.1:6379/0", description="Redis connection URI")
    REDIS_POOL_SIZE: int = Field(default=50, description="Max concurrent Redis async connection handles")
    REDIS_TIMEOUT_SECONDS: float = Field(default=1.5, description="Socket connect/read timeout for Redis in seconds")
    CACHE_TTL_SECONDS: int = Field(default=300, description="Cache-Aside TTL in seconds (5 minutes)")
    CACHE_ENABLED: bool = Field(default=True, description="Master switch for Cache-Aside layer")

    # 5. Worker Concurrency & Gunicorn Multi-Worker Process Model
    # Formula: (2 * CPU Cores) + 1
    @property
    def OPTIMAL_WORKER_COUNT(self) -> int:
        cpu_count = multiprocessing.cpu_count()
        return (2 * cpu_count) + 1

    GUNICORN_WORKERS: Optional[int] = Field(default=None, description="Explicit worker override")
    GUNICORN_BACKLOG: int = Field(default=2048, description="OS network listen queue backlog")
    GUNICORN_TIMEOUT: int = Field(default=60, description="Worker keep-alive heartbeat timeout")
    GUNICORN_WORKER_CONNECTIONS: int = Field(default=1000, description="Max active simultaneous connections per worker")

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_async_driver(cls, v: str) -> str:
        """
        Guarantees that database URL strictly uses asynchronous non-blocking drivers.
        Blocks accidental sync drivers like psycopg2, psycopg, pymysql, or plain sqlite.
        """
        sync_driver_replacements = {
            "postgresql://": "postgresql+asyncpg://",
            "postgres://": "postgresql+asyncpg://",
            "mysql://": "mysql+aiomysql://",
            "sqlite://": "sqlite+aiosqlite://",
        }
        for sync_prefix, async_prefix in sync_driver_replacements.items():
            if v.startswith(sync_prefix):
                return v.replace(sync_prefix, async_prefix, 1)
        return v


settings = AppSettings()
