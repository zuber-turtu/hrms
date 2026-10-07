"""
Gunicorn configuration for Company HRMS Enterprise Deployment.
Provides multi-worker asynchronous process management with Uvicorn ASGI workers.
"""

import os
import multiprocessing

# 1. Network & Binding
host = os.getenv("HOST", "0.0.0.0")
port = os.getenv("PORT", "8000")
bind = os.getenv("GUNICORN_BIND", f"{host}:{port}")
backlog = int(os.getenv("GUNICORN_BACKLOG", "2048"))

# 2. Worker Processes & Concurrency
# Formula: (2 x CPU cores) + 1 with environmental override
default_workers = (multiprocessing.cpu_count() * 2) + 1
workers = int(os.getenv("WEB_CONCURRENCY", os.getenv("GUNICORN_WORKERS", default_workers)))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = int(os.getenv("GUNICORN_WORKER_CONNECTIONS", "1000"))

# 3. Timeouts & Keep-Alive
# 120s allows long-running operations like bulk payslip PDF generation and Excel exports
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", "5"))

# 4. Memory Management & Worker Recycling (Prevents Memory Leaks)
# Recycles worker after handling 1500-1800 requests to reclaim memory
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "1500"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "300"))

# 5. Logging & Observability
accesslog = os.getenv("GUNICORN_ACCESS_LOG", "-")  # "-" means stdout
errorlog = os.getenv("GUNICORN_ERROR_LOG", "-")    # "-" means stderr
loglevel = os.getenv("LOG_LEVEL", "info").lower()
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" (%(L)ss)'

# 6. Process Naming
proc_name = "Company_hrms_app"

# 7. Server Lifecycle Hooks
def on_starting(server):
    server.log.info(f"🚀 Starting Company HRMS on {bind} with {workers} Uvicorn workers...")

def post_fork(server, worker):
    server.log.info(f"Worker spawned (PID: {worker.pid})")

def worker_abort(worker):
    worker.log.error(f"Worker received SIGABRT (PID: {worker.pid})")
