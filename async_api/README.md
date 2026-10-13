# High-Performance Asynchronous FastAPI Architecture

Engineered for **1,000+ active concurrent users** under heavy load (50–100 requests per second peak traffic) with **<100ms response targets** on vertical cloud instances.

---

## 🏛️ Architectural Blueprint

```
async_api/
├── __init__.py
├── config.py           # Pydantic-settings managing env, DB strings, pool limits & Redis params
├── database.py         # SQLAlchemy 2.0 Asyncio engine (asyncpg/aiomysql) + resilient get_db session injector
├── cache.py            # redis.asyncio ConnectionPool & resilient Cache-Aside pattern (300s TTL)
├── models.py           # Async domain models with strict composite column indexes (zero table-scans)
├── schemas.py          # Pydantic v2 schemas with strict typing, serializers & validation
├── main.py             # FastAPI app with lifespan hooks, <0.5ms /health probe, readiness probe & CRUD
└── gunicorn_conf.py    # Gunicorn process manager wrapping UvicornWorkers: (2 * CPU Cores) + 1
```

---

## 🚀 Key Architectural Highlights

### 1. Swappable Async Database Layer (SQLAlchemy 2.0)
- **Database-Agnostic**: Dynamically adapts dialect, drivers, and connection arguments strictly based on `DATABASE_URL`:
  - `postgresql+asyncpg://...` (PostgreSQL with JIT disabled for fast transactional queries)
  - `mysql+aiomysql://...` (MySQL with utf8mb4 and timeout handling)
  - `sqlite+aiosqlite://...` (Local testing & ephemeral runner fallback)
- **Automatic Validation**: Pydantic validator automatically detects and replaces legacy synchronous drivers (`psycopg2`, `pymysql`) with their non-blocking asynchronous equivalents.

### 2. Bulletproof Connection Pooling
- **Pool Size**: `pool_size = 30` persistent handles.
- **Max Overflow**: `max_overflow = 15` burst handles (up to 45 total handles per worker).
- **Pool Recycle**: `pool_recycle = 1800` (recycles connections older than 30 minutes to prevent stale TCP drops).
- **Pre-Ping**: `pool_pre_ping = True` (executes lightweight validation before releasing handles to prevent dropped connection exceptions).
- **Pool Timeout**: `pool_timeout = 30` seconds.

### 3. High-Concurrency Cache-Aside Pattern (`redis.asyncio`)
- **Connection Pool**: Dedicated async pool (`max_connections = 50`) with non-blocking socket timeouts.
- **Cache-Aside Flow**:
  1. Checks Redis (`<2ms` read target).
  2. Cache hit $\rightarrow$ returns immediately without touching the database.
  3. Cache miss $\rightarrow$ queries database via indexed path, serializes, writes back to Redis with a **5-minute TTL (`ex=300`)**.
  4. Write operations $\rightarrow$ invalidate relevant cache keys.
- **Resilient Degradation**: If Redis experiences network partition or downtime, the application logs a warning and transparently falls back to the async database without failing client requests.

### 4. Strict Composite Indexing (Zero Table-Scans)
Bypasses slow sequential table scans under concurrent traffic:
- `ix_users_tenant_role_active` on `(tenant_id, role, is_active)`
- `ix_punch_user_date` on `(user_id, punch_date)`
- `ix_punch_tenant_date_verified` on `(tenant_id, punch_date, is_verified)`
- `ix_punch_timestamp_user` on `(timestamp_utc, user_id)`

### 5. Multi-Worker Server Execution (Gunicorn + Uvicorn)
- **Process Manager**: Gunicorn wrapping `uvicorn.workers.UvicornWorker`.
- **Dynamic Worker Count**: `(2 * CPU Cores) + 1` dynamically calculated at startup.
- **Worker Connections**: 1,000 active concurrent connections per worker.
- **Backlog**: `2048` socket listen queue depth.

---

## 🏃 Running in Production

### Development / Hot-Reload
```bash
python -m uvicorn async_api.main:app --reload --port 8000
```

### Production Cluster Execution (Gunicorn)
```bash
gunicorn -c async_api/gunicorn_conf.py async_api.main:app
```
