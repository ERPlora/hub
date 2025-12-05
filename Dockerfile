# ==============================================================================
# ERPlora Hub - Production Dockerfile
# ==============================================================================
# Usado por docker-compose.yaml para deploy via Dokploy.
#
# STORAGE (automatic via HUB_ID):
#   Docker Volume /app/data/{HUB_ID}/:
#     - db/db.sqlite3 - SQLite database (PERSISTENT)
#
#   S3 hubs/{HUB_ID}/:
#     - backups/     - Database backups
#     - plugin_data/ - Plugin data
#     - reports/     - Generated reports
#     - media/       - User uploads (Django media)
#
#   Container (ephemeral):
#     - /tmp/hub_media/ - Temporary processing files
#     - Logs via stdout/stderr (Docker captures)
#
# ENVIRONMENT VARIABLES (injected by Dokploy):
#   HUB_ID            - UUID del Hub
#   HUB_NAME          - Subdomain del Hub
#   AWS_*             - S3 credentials
#   DJANGO_SETTINGS_MODULE=config.settings.web
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
# Use web settings for proper WhiteNoise configuration
ENV DJANGO_SETTINGS_MODULE=config.settings.web
RUN python manage.py collectstatic --noinput --clear

# Create non-root user for security
# /app/data is mounted as Docker volume for persistent SQLite
RUN useradd --create-home --shell /bin/bash hubuser \
    && mkdir -p /app/data \
    && chown -R hubuser:hubuser /app
USER hubuser

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================
# Fixed variables (don't change between Hubs)
# Dynamic variables (HUB_ID, HUB_NAME, AWS_*) come from docker-compose.yaml
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBUG=false

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
