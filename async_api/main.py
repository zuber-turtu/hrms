"""
High-Performance Asynchronous FastAPI Application
Optimized for 1,000+ Concurrent Active Users (<100ms Latency Target)
"""

import datetime
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from async_api.cache import cache_manager
from async_api.config import settings
from async_api.database import Base, close_db_connections, engine, get_db
from async_api.models import AttendancePunch, AuditTrail, User
from async_api.schemas import (
    AttendancePunchCreate,
    AttendancePunchResponse,
    AttendanceSummaryResponse,
    HealthResponse,
    ReadinessResponse,
    UserCreate,
    UserResponse,
)

# Logger Configuration
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
)
logger = logging.getLogger("async_api.main")


# ================= Application Lifespan =================
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manages non-blocking startup and shutdown lifecycle hooks.
    Pre-warms connection pools to avoid latency spikes on first client requests.
    """
    logger.info(f"🚀 Initializing {settings.APP_NAME} v{settings.APP_VERSION} [Env: {settings.ENV}]")

    # 1. Warm-up / schema sync (supports auto-table creation for rapid deployment & testing)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database schema verified.")

    # 2. Warm-up Redis async connection pool
    await cache_manager.init_pool()

    yield

    # 3. Clean Graceful Shutdown
    logger.info("Shutting down resources...")
    await cache_manager.close()
    await close_db_connections()
    logger.info("Shutdown complete.")


# Initialize FastAPI Instance
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.ENV != "production" else None,
    redoc_url=None,
)

# High-Performance CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.ENV != "production" else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ================= Middleware: Microsecond Latency Profiler =================
@app.middleware("http")
async def add_process_time_header(request: Request, call_next) -> Response:
    """Non-blocking performance tracking header."""
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time_ms = (time.perf_counter() - start_time) * 1000.0
    response.headers["X-Process-Time-Ms"] = f"{process_time_ms:.2f}"
    return response


# ================= Error Boundaries =================
@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_exception_boundary(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error(f"Database error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Database transaction failure. High load or timeout encountered."},
    )


@app.exception_handler(TimeoutError)
async def timeout_exception_boundary(request: Request, exc: TimeoutError) -> JSONResponse:
    logger.error(f"Timeout on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        content={"detail": "Operation timed out under peak concurrency."},
    )


# ================= 1. Load Balancer Health & Readiness Probes =================
@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    tags=["Observability"],
    summary="Ultra-lightweight Liveness Probe (<0.5ms)",
)
async def health_liveness() -> HealthResponse:
    """
    Zero-IO Liveness check endpoint specifically targeted for ALB/NLB health checks.
    Never hits database or disk; responds immediately to keep load balancers healthy.
    """
    return HealthResponse(status="alive")


@app.get(
    "/health/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    tags=["Observability"],
    summary="Deep Readiness Probe with Latency Benchmarking",
)
async def health_readiness(db: AsyncSession = Depends(get_db)) -> ReadinessResponse:
    """
    Validates end-to-end async connectivity to database and Redis.
    Measures exact round-trip ping latencies.
    """
    components = {}

    # 1. Measure DB ping
    db_start = time.perf_counter()
    try:
        await db.execute(text("SELECT 1"))
        db_latency = (time.perf_counter() - db_start) * 1000.0
        components["database"] = f"OK ({db_latency:.2f}ms)"
    except Exception as e:
        logger.error(f"Readiness check DB error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database readiness check failed",
        )

    # 2. Measure Redis ping
    redis_start = time.perf_counter()
    redis_latency = None
    if settings.CACHE_ENABLED:
        is_redis_ok = await cache_manager.ping()
        redis_latency = (time.perf_counter() - redis_start) * 1000.0
        components["redis"] = f"OK ({redis_latency:.2f}ms)" if is_redis_ok else "DEGRADED (bypassed)"
    else:
        components["redis"] = "DISABLED"

    return ReadinessResponse(
        status="ready",
        database_latency_ms=round(db_latency, 2),
        redis_latency_ms=round(redis_latency, 2) if redis_latency is not None else None,
        components=components,
    )


# ================= 2. Users Endpoint (Composite Index Leveraging) =================
@app.post(
    "/api/v1/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Users"],
)
async def create_user(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> UserResponse:
    """Creates a user using async non-blocking execution."""
    stmt = select(User).where(User.email == payload.email)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Fast SHA-256 password hash for benchmark (use argon2/bcrypt in auth modules)
    pwd_hash = hashlib.sha256(payload.password.encode()).hexdigest()

    new_user = User(
        tenant_id=payload.tenant_id,
        email=payload.email,
        hashed_password=pwd_hash,
        name=payload.name,
        role=payload.role,
        is_active=True,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)
    return UserResponse.model_validate(new_user)


@app.get(
    "/api/v1/users",
    response_model=List[UserResponse],
    status_code=status.HTTP_200_OK,
    tags=["Users"],
)
async def list_users(
    tenant_id: str = "default",
    role: str = "employee",
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> List[UserResponse]:
    """
    Queries users strictly leveraging composite index:
    Index("ix_users_tenant_role_active", "tenant_id", "role", "is_active")
    Bypasses slow sequential table scans under 1,000 active concurrent users.
    """
    stmt = (
        select(User)
        .where(
            User.tenant_id == tenant_id,
            User.role == role,
            User.is_active == True,
        )
        .limit(limit)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]


# ================= 3. Attendance Punch & Cache-Aside Implementation =================
@app.post(
    "/api/v1/punches",
    response_model=AttendancePunchResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Attendance"],
)
async def record_punch(
    payload: AttendancePunchCreate,
    db: AsyncSession = Depends(get_db),
) -> AttendancePunchResponse:
    """
    Append-only high-concurrency punch handler.
    Invalidates the User's cached punch summary in Redis upon successful commit.
    """
    now = datetime.datetime.utcnow()
    punch = AttendancePunch(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        punch_date=now.date(),
        punch_type=payload.punch_type,
        timestamp_utc=now,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_name=payload.location_name,
        is_verified=True,
        metadata_json=json.dumps(payload.metadata or {}),
    )
    db.add(punch)

    # Log audit event non-blockingly within the same transactional unit
    audit = AuditTrail(
        tenant_id=payload.tenant_id,
        actor_id=payload.user_id,
        action=f"ATTENDANCE_{payload.punch_type}",
        entity="AttendancePunch",
        entity_id=0,  # Updated on flush
        timestamp_utc=now,
    )
    db.add(audit)
    await db.flush()
    audit.entity_id = punch.id

    # Invalidate Cache-Aside key so next read fetches fresh state
    cache_key = f"punches:user:{payload.user_id}"
    await cache_manager.delete(cache_key)

    await db.refresh(punch)
    return AttendancePunchResponse.model_validate(punch)


@app.get(
    "/api/v1/punches/{user_id}",
    response_model=AttendanceSummaryResponse,
    status_code=status.HTTP_200_OK,
    tags=["Attendance"],
)
async def get_user_punches(
    user_id: int,
    db: AsyncSession = Depends(get_db),
) -> AttendanceSummaryResponse:
    """
    High-Concurrency Cache-Aside Pattern Implementation:
    1. Check Redis async cache first. (Target: <2ms latency)
    2. On Cache Hit -> Return cached payload directly.
    3. On Cache Miss -> Query database via composite index `(user_id, punch_date)`
       ordered latest-first, serialize, write to Redis with 5-minute TTL (300s).
    """
    cache_key = f"punches:user:{user_id}"

    # 1. Cache Check
    cached_data = await cache_manager.get(cache_key)
    if cached_data is not None:
        return AttendanceSummaryResponse(
            user_id=user_id,
            total_records=len(cached_data),
            punches=[AttendancePunchResponse.model_validate(p) for p in cached_data],
            cached=True,
            cache_ttl_remaining=settings.CACHE_TTL_SECONDS,
        )

    # 2. Database Fetch on Cache Miss (strictly indexed)
    stmt = (
        select(AttendancePunch)
        .where(AttendancePunch.user_id == user_id)
        .order_by(AttendancePunch.punch_date.desc(), AttendancePunch.timestamp_utc.desc())
        .limit(30)
    )
    result = await db.execute(stmt)
    records = result.scalars().all()

    # Serialize items
    punch_responses = [AttendancePunchResponse.model_validate(r) for r in records]
    punch_dicts = [p.model_dump(mode="json") for p in punch_responses]

    # 3. Write back to Redis with 5-minute TTL (300s)
    await cache_manager.set(cache_key, punch_dicts, ttl=settings.CACHE_TTL_SECONDS)

    return AttendanceSummaryResponse(
        user_id=user_id,
        total_records=len(punch_responses),
        punches=punch_responses,
        cached=False,
    )
