#!/usr/bin/env bash
# ==============================================================================
# Company HRMS - Production Startup Script (Gunicorn + Uvicorn)
# ==============================================================================

set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "========================================================"
echo "🚀 Initializing Company HRMS Enterprise Production Server"
echo "========================================================"

# 1. Activate Virtual Environment if present
if [ -d "$APP_DIR/venv" ]; then
    echo "📦 Activating virtual environment..."
    source "$APP_DIR/venv/bin/activate"
elif [ -d "$APP_DIR/.venv" ]; then
    echo "📦 Activating virtual environment..."
    source "$APP_DIR/.venv/bin/activate"
fi

# 2. Check for .env file
if [ ! -f "$APP_DIR/.env" ]; then
    echo "⚠️  WARNING: No .env file found! Using environment defaults or copying from .env.example..."
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        echo "✅ Created .env from .env.example. Please review sensitive keys."
    fi
fi

# 3. Create required directories
mkdir -p "$APP_DIR/static/uploads"
mkdir -p "$APP_DIR/logs"

# 4. Launch Gunicorn with configuration
echo "⚡ Starting Gunicorn with Uvicorn worker cluster..."
exec gunicorn main:app -c gunicorn_conf.py
