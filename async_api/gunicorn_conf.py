"""
Production Gunicorn Configuration for High-Concurrency Async Execution
Process Manager Wrapping Uvicorn ASGI Workers
Formula: (2 * CPU Cores) + 1
"""

import multiprocessing
import os

# 1. Bind Address & Port
host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8000")
bind = f"{host}:{port}"

# 2. Dynamic Worker Allocation (Formula: 2 * Cores + 1)
cpu_cores = multiprocessing.cpu_count()
calculated_workers = (2 * cpu_cores) + 1
workers = int(os.getenv("WEB_CONCURRENCY", os.getenv("GUNICORN_WORKERS", calculated_workers)))

# 3. Asynchronous Worker Class & High-Concurrency Handles
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "1000"))
backlog = int(os.getenv("GUNICORN_BACKLOG", "2048"))

# 4. Timeouts & Keep-Alive Settings
timeout = int(os.getenv("GUNICORN_TIMEOUT", "60"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# 5. Worker Memory Recycling (Defense against memory fragmentation)
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "5000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "500"))

# 6. Observability & Logging
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")
loglevel = os.getenv("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# 7. Process Naming
proc_name = "async_fastapi_highperf"


def on_starting(server):
    server.log.info("=" * 60)
    server.log.info(f"⚡ HIGH-PERFORMANCE ASYNC FASTAPI CLUSTER STARTING")
    server.log.info(f"   CPU Cores Detected: {cpu_cores}")
    server.log.info(f"   Dynamic Workers:    {workers} [(2 * {cpu_cores}) + 1]")
    server.log.info(f"   Worker Class:       {worker_class}")
    server.log.info(f"   Target Concurrency: {workers * worker_connections} simultaneous connections")
    server.log.info(f"   Network Bind:       {bind}")
    server.log.info("=" * 60)


def post_fork(server, worker):
    server.log.info(f"Worker spawned [PID: {worker.pid}]")


def worker_abort(worker):
    server.log.error(f"Worker aborted [PID: {worker.pid}]")
