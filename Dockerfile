# ==============================================================================
# ERPlora Hub - Production Dockerfile
# ==============================================================================
# Build on deploy por Coolify (sin registry externo)
# Coolify clona el repo → detecta Dockerfile → build → run
#
# MODES:
#   1. PRODUCTION (default): Data on external volume (persistent)
#   2. DEMO (DEMO_MODE=true): Data in /app/data/ (non-persistent)
#
# VOLUMES (mount for persistence - production mode):
#   Defined by HUB_VOLUME_PATH/{HUB_NAME}-{HUB_ID}/
#   ├── db/       - SQLite database
#   ├── media/    - User uploads (images, logos)
#   ├── plugins/  - Installed plugins
#   ├── logs/     - Application logs
#   ├── backups/  - Automatic backups
#   ├── reports/  - Generated reports
#   └── temp/     - Temporary files
#
# ENVIRONMENT VARIABLES (injected by Coolify from Cloud model):
#   HUB_NAME          - Slug del Hub (ej: tienda-de-maria)
#   HUB_ID            - UUID corto (ej: a1b2c3)
#   HUB_VOLUME_PATH   - Ruta del volumen Hetzner (ej: /mnt/HC_Volume_104073157)
#   DEMO_MODE         - Set to "true" for demo deployments (non-persistent)
#
# Result (production):
#   URL:  https://tienda-de-maria.a.erplora.com
#   Data: /mnt/HC_Volume_104073157/tienda-de-maria-a1b2c3/
#
# Result (demo):
#   URL:  https://demo.int.erplora.com
#   Data: /app/data/ (inside container, non-persistent)
# ==============================================================================

FROM python:3.11-slim

# Labels for container metadata
LABEL org.opencontainers.image.title="ERPlora Hub"
LABEL org.opencontainers.image.description="Cloud Hub for ERPlora POS System"
LABEL org.opencontainers.image.vendor="ERPlora"
LABEL org.opencontainers.image.source="https://github.com/ERPlora/hub"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libusb-1.0-0 \
    cups \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv

# Copy application code first (needed for uv pip install)
COPY . .

# Install dependencies directly (no venv needed in Docker)
# Note: We use regular install, not editable (-e) since this is production
RUN uv pip install --system --no-cache .

# Collect static files during build (don't change between Hubs)
RUN python manage.py collectstatic --noinput --clear 2>/dev/null || true

# Create non-root user for security
# Also create /app/data directory for DEMO_MODE (non-persistent storage)
RUN useradd --create-home --shell /bin/bash hubuser \
    && mkdir -p /app/data \
    && chown -R hubuser:hubuser /app
USER hubuser

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================
# Fixed variables (don't change between Hubs)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HUB_ENV=web \
    DEBUG=false

# Dynamic variables come from Coolify at deploy time:
# HUB_NAME, HUB_ID, HUB_VOLUME_PATH

# =============================================================================
# EXPOSE & HEALTHCHECK
# =============================================================================
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# =============================================================================
# ENTRYPOINT
# =============================================================================
CMD ["sh", "-c", "\
    echo '=== ERPlora Hub Starting ===' && \
    echo 'Running database migrations...' && \
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
        --enable-stdio-inheritance \
    "]
