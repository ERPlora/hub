# ==============================================================================
# ERPlora Hub - Production Dockerfile
# ==============================================================================
# Usado por docker-compose.yaml para deploy via Dokploy.
#
# STORAGE (automatic via HUB_ID):
#   Docker Volume (bind mount isolates by HUB_ID):
#     Host: ${VOLUME_PATH}/hubs/${HUB_ID}/ -> Container: /app/data/
#     - /app/data/db/db.sqlite3 - SQLite database (PERSISTENT)
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

# No apt-get needed: all Python deps have precompiled wheels for linux/amd64
# Healthcheck uses Python instead of curl (see HEALTHCHECK below)

# Install uv (fast Python package manager)
RUN pip install --no-cache-dir uv

# Copy application code first (needed for uv pip install)
COPY . .

# Install dependencies directly (no venv needed in Docker)
# Note: We use regular install, not editable (-e) since this is production
RUN uv pip install --system --no-cache .

# Collect static files during build (don't change between Hubs)
# Use web settings with dummy values (only needed for settings import, not collectstatic)
# Real values come from docker-compose.yaml at runtime
ENV DJANGO_SETTINGS_MODULE=config.settings.web \
    HUB_ID=00000000-0000-0000-0000-000000000000 \
    HUB_NAME=build \
    AWS_ACCESS_KEY_ID=dummy \
    AWS_SECRET_ACCESS_KEY=dummy \
    AWS_STORAGE_BUCKET_NAME=dummy \
    AWS_S3_ENDPOINT_URL=https://dummy.com \
    AWS_S3_REGION_NAME=eu-central \
    AWS_LOCATION=dummy
RUN python manage.py collectstatic --noinput --clear

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
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')" || exit 1

# =============================================================================
# DEFAULT COMMAND
# =============================================================================
# Command is defined in docker-compose.yml for flexibility
# This is a fallback for running the container directly
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
