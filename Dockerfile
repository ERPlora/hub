# ==============================================================================
# ERPlora Hub - Production Dockerfile
# ==============================================================================
# Used for deployment via AWS App Runner or Docker Compose (local testing).
#
# STORAGE (automatic via HUB_ID):
#   AWS App Runner: ephemeral filesystem, S3 for persistent data
#   Docker Compose: bind mount from host → /app/data/
#
#   S3 hubs/{HUB_ID}/:
#     - backups/     - Database backups
#     - plugin_data/ - Plugin data
#     - reports/     - Generated reports
#     - media/       - User uploads (Django media)
#
#   Container (ephemeral):
#     - /tmp/hub_media/ - Temporary processing files
#     - Logs via stdout/stderr (Docker/CloudWatch captures)
#
# ENVIRONMENT VARIABLES:
#   HUB_ID            - UUID del Hub
#   HUB_NAME          - Subdomain del Hub
#   DATABASE_URL      - PostgreSQL connection string (Aurora or direct)
#   AWS_*             - S3 credentials (optional on AWS — IAM role provides them)
#   DJANGO_SETTINGS_MODULE=config.settings.web
# ==============================================================================

FROM python:3.14-slim

# Labels for container metadata
LABEL org.opencontainers.image.title="ERPlora Hub"
LABEL org.opencontainers.image.description="Cloud Hub for ERPlora POS System"
LABEL org.opencontainers.image.vendor="ERPlora"
LABEL org.opencontainers.image.source="https://github.com/ERPlora/hub"

WORKDIR /app

# Install postgresql-client for pg_dump (database backups)
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client git \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv

# Copy application code first (needed for uv pip install)
COPY . .

# Install dependencies directly (no venv needed in Docker)
# Note: We use regular install, not editable (-e) since this is production
RUN uv pip install --system --no-cache .

# Download vendor assets (CSS/JS) from CDN → local static files
RUN DJANGO_SETTINGS_MODULE=config.settings.web \
    HUB_ID=00000000-0000-0000-0000-000000000000 \
    HUB_NAME=build \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    AWS_STORAGE_BUCKET_NAME=dummy \
    AWS_S3_REGION_NAME=eu-west-1 \
    AWS_LOCATION=dummy \
    python manage.py vendor_fetch

# Collect static files during build (don't change between Hubs)
# Use web settings with dummy values (only needed for settings import, not collectstatic)
# Real values come from environment at runtime
RUN DJANGO_SETTINGS_MODULE=config.settings.web \
    HUB_ID=00000000-0000-0000-0000-000000000000 \
    HUB_NAME=build \
    DATABASE_URL=postgres://build:build@localhost:5432/build \
    AWS_STORAGE_BUCKET_NAME=dummy \
    AWS_S3_REGION_NAME=eu-west-1 \
    AWS_LOCATION=dummy \
    python manage.py collectstatic --noinput --clear

# =============================================================================
# ENVIRONMENT VARIABLES
# =============================================================================
# Fixed variables (don't change between Hubs)
# Dynamic variables (HUB_ID, HUB_NAME, DATABASE_URL, AWS_*) come from
# App Runner env vars or docker-compose.yaml
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings.web \
    DEBUG=false

# =============================================================================
# EXPOSE & HEALTHCHECK
# =============================================================================
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

# =============================================================================
# DEFAULT COMMAND
# =============================================================================
# Runs migrations, restores modules, then starts gunicorn on port 8000 (required by App Runner)
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py createcachetable --database default 2>/dev/null; python manage.py ensure_modules && python manage.py djicons_collect --s3 || echo 'Warning: djicons_collect failed (non-fatal)'; exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 300 --pid /run/gunicorn.pid"]
