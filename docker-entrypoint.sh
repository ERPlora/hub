#!/bin/bash
# ==============================================================================
# ERPlora Hub - Docker Entrypoint
# ==============================================================================
# This script runs as root to:
# 1. Create and set permissions on /app/data directories
# 2. Drop privileges and run the application as hubuser
# ==============================================================================

set -e

echo "=== ERPlora Hub Starting ==="

# Create data directories with correct permissions
# /app/data is a bind mount from host, so we need to create subdirectories
echo "Creating data directories..."
mkdir -p /app/data/db
chown -R hubuser:hubuser /app/data

# Switch to hubuser and run the application
echo "Running database migrations..."
exec gosu hubuser sh -c "
    python manage.py migrate --noinput && \
    echo 'Starting Gunicorn server...' && \
    exec gunicorn config.wsgi:application \
        --bind 0.0.0.0:8000 \
        --workers 2 \
        --threads 4 \
        --worker-class gthread \
        --timeout 120 \
        --access-logfile - \
        --error-logfile - \
        --capture-output \
        --enable-stdio-inheritance
"
